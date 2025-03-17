import os
import re
from pathlib import Path

import click
from dotenv import load_dotenv
from sqlalchemy.orm import joinedload

from mltoolbox.utils.db import DB, Remote
from mltoolbox.utils.docker import (
    RemoteConfig,
    check_docker_group,
    start_container,
    verify_env_vars,
)
from mltoolbox.utils.helpers import remote_cmd
from mltoolbox.utils.remote import (
    build_rclone_cmd,
    fetch_remote,
    run_rclone_sync,
    setup_conda_env,
    setup_rclone,
    setup_zshrc,
    sync_project,
    update_env_file,
    wait_for_host,
)

db = DB()


@click.group()
def remote():
    """Manage remote development environment."""
    load_dotenv(".env")


@remote.command()
def provision():
    raise click.ClickException("Not implemented yet")


@remote.command()
@click.argument("host_or_alias")
@click.option("--username", default="ubuntu", help="Remote username")
@click.option("--force-rebuild", is_flag=True, help="Force rebuild remote container")
@click.option(
    "--forward-ports",
    "-p",
    multiple=True,
    default=["8000:8000", "8265:8265"],
    help="Port forwarding in local:remote format",
)
@click.option(
    "--worktree",
    default=None,
    help="Use a custom worktree name instead of the directory name",
)
def direct(
    host_or_alias,
    username,
    force_rebuild,
    forward_ports,
    worktree,
):
    """Connect directly to remote container with zero setup."""
    # Validate host IP address format
    ip_pattern = r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
    if not re.match(ip_pattern, host_or_alias):
        remote = db.get_remote_fuzzy(host_or_alias)
        host = remote.host
        username = remote.username
    else:
        host = host_or_alias

    # Get env variables for project and container names
    try:
        env_vars = verify_env_vars()
        project_name = env_vars.get("PROJECT_NAME", Path.cwd().name)
        container_name = env_vars.get("CONTAINER_NAME", project_name.lower())
    except Exception:
        # Fallback if env file doesn't exist
        project_name = Path.cwd().name
        container_name = project_name.lower()

    # Use the provided worktree name or fall back to project_name
    worktree_name = worktree or project_name

    # Log the worktree usage if different from project name
    if worktree and worktree != project_name:
        click.echo(
            f"🌲 Using worktree name '{worktree_name}' instead of '{project_name}'"
        )

    remote_config = RemoteConfig(
        host=host,
        username=username,
        working_dir=f"~/projects/{worktree_name}",
    )

    # Update .env file to include WORKTREE_NAME if needed
    if worktree and worktree != project_name:
        click.echo(f"🔧 Adding worktree information to environment...")
        env_updates = {
            "WORKTREE_NAME": worktree_name,
        }
        update_env_file(remote_config, worktree_name, env_updates, container_name)

    # Just start the container
    start_container(
        worktree_name,
        container_name,
        remote_config=remote_config,
        build=force_rebuild,
    )

    # Connect to container - use full path to docker compose
    # Use worktree_name for directory but container_name for the actual container
    cmd = f"cd ~/projects/{worktree_name} && docker compose exec -it -w /workspace/{worktree_name} {container_name} zsh"

    # Build SSH command with port forwarding
    ssh_args = [
        "ssh",
        "-A",  # Forward SSH agent
        "-o",
        "ControlMaster=no",
        "-o",
        "ExitOnForwardFailure=no",
        "-o",
        "ServerAliveInterval=60",
        "-o",
        "ServerAliveCountMax=3",
    ]

    # Add port forwarding arguments
    for port_mapping in forward_ports:
        if port_mapping:
            local_port, remote_port = port_mapping.split(":")
            ssh_args.extend(["-L", f"{local_port}:localhost:{remote_port}"])

    # Add remaining SSH arguments
    ssh_args.extend(["-t", f"{username}@{host}", cmd])

    # Execute SSH command
    os.execvp("ssh", ssh_args)  # noqa: S606


@remote.command()
@click.argument("host_or_alias")
@click.option("--alias")
@click.option("--username", default="ubuntu", help="Remote username")
@click.option(
    "--mode",
    type=click.Choice(["ssh", "container", "conda"]),
    default="ssh",
    help="Connection mode",
)
@click.option(
    "--env-name", default="mltoolbox", help="Conda environment name (for conda mode)"
)
@click.option("--force-rebuild", is_flag=True, help="force rebuild remote container")
@click.option(
    "--forward-ports",
    "-p",
    multiple=True,
    default=["8000:8000", "8265:8265"],
    help="Port forwarding in local:remote format",
)
@click.option(
    "--host-ray-dashboard-port",
    default=None,
    help="Host port to map to Ray dashboard (container port remains 8265)",
)
@click.option(
    "--host-ray-client-port",
    default=None,
    help="Host port to map to Ray client server (container port remains 10001)",
)
@click.option(
    "--wait/--no-wait",
    default=False,
    help="Wait for host to become available",
)
@click.option(
    "--timeout",
    default=None,
    help="Maximum time to wait for host in seconds",
)
@click.option(
    "--exclude",
    "-e",
    default="",
    help="Comma-separated patterns to exclude (e.g., 'checkpoints,wandb')",
)
@click.option(
    "--variant",
    type=click.Choice(["cuda", "gh200"]),
    default="cuda",
    help="Base image variant to use",
)
@click.option(
    "--python-version",
    default=None,
    help="Python version to use (e.g., '3.10', '3.11')",
)
@click.option(
    "--worktree",
    default=None,
    help="Use a custom worktree name instead of the directory name",
)
def connect(
    host_or_alias,
    alias,
    username,
    mode,
    env_name,
    force_rebuild,
    forward_ports,
    host_ray_dashboard_port,
    host_ray_client_port,
    wait,
    timeout,
    exclude,
    variant,
    python_version,
    worktree,
):
    """Connect to remote development environment."""
    # Validate host IP address format
    ip_pattern = r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
    if not re.match(ip_pattern, host_or_alias):
        host = None
        alias = host_or_alias
    else:
        host = host_or_alias

    env_vars = verify_env_vars()
    project_name = env_vars.get("PROJECT_NAME", Path.cwd().name)
    container_name = env_vars.get("CONTAINER_NAME", project_name.lower())

    # Use the provided worktree name or fall back to project_name
    worktree_name = worktree or project_name

    # Log the worktree usage if different from project name
    if worktree and worktree != project_name:
        click.echo(
            f"🌲 Using worktree name '{worktree_name}' instead of '{project_name}'"
        )

    # Get or create/update remote and project
    remote = db.upsert_remote(
        username=username,
        host=host,
        project_name=project_name,
        container_name=container_name,
        conda_env=env_name if mode == "conda" else None,
        alias=alias,
    )

    if wait:
        click.echo(f"Waiting for host {remote.host} to become available...")
        if not wait_for_host(remote.host, timeout):
            raise click.ClickException(
                f"Timeout waiting for host {remote.host} after {timeout} seconds"
            )

    remote_config = RemoteConfig(
        host=remote.host,
        username=remote.username,
        working_dir=f"~/projects/{worktree_name}",
    )

    # create custom ssh config if not exists
    ssh_config_path = Path("~/.config/mltoolbox/ssh/config").expanduser()
    ssh_config_path.parent.mkdir(parents=True, exist_ok=True)

    # add include directive to main ssh config if needed
    main_ssh_config_path = Path("~/.ssh/config").expanduser()
    include_line = f"Include {ssh_config_path}\n"

    if not main_ssh_config_path.exists():
        main_ssh_config_path.touch()

    with main_ssh_config_path.open("r") as f:
        content = f.read()

    if include_line not in content:
        with main_ssh_config_path.open("w") as f:
            f.write(include_line + content)

    # Read existing config and filter out previous entries for this host/alias
    existing_config = []
    current_host = None
    skip_block = False

    if ssh_config_path.exists():
        with ssh_config_path.open("r") as f:
            for line in f:
                if line.startswith("Host "):
                    current_host = line.split()[1].strip()
                    # Skip this block if it matches our alias, regardless of host
                    skip_block = current_host == remote.alias
                if not skip_block:
                    existing_config.append(line)
                elif not line.strip() or line.startswith("Host "):
                    skip_block = False

    # Write updated config
    with ssh_config_path.open("w") as f:
        # Write existing entries (excluding the one we're updating)
        f.writelines(existing_config)

        # Add a newline if the file doesn't end with one
        if existing_config and not existing_config[-1].endswith("\n"):
            f.write("\n")

        # Write the new/updated entry
        f.write(f"Host {remote.alias}\n")
        f.write(f"    HostName {remote.host}\n")
        f.write(f"    User {remote.username}\n")
        f.write("    ForwardAgent yes\n\n")

    click.echo(f"Access your instance with `ssh {remote.alias}`")

    setup_zshrc(remote_config)
    setup_rclone(remote_config)

    click.echo(f"📁 Creating remote project directories for {worktree_name}")
    remote_cmd(
        remote_config,
        [f"mkdir -p ~/projects/{worktree_name}"],
        use_working_dir=False,
    )
    if mode == "container":
        check_docker_group(remote_config)
        click.echo("✅ Docker group checked")

        # First ensure remote directory exists
        remote_cmd(
            remote_config,
            [f"mkdir -p ~/projects/{worktree_name}"],
            use_working_dir=False,
        )

        # Handle worktree case - sync both parent repo and worktree
        if worktree and worktree != project_name:
            try:
                # Read the .git file to find the parent repository path
                with open(".git", "r") as f:
                    git_content = f.read().strip()
                    if git_content.startswith("gitdir:"):
                        parent_gitdir = git_content.split("gitdir:")[1].strip()

                        # Extract parent repo path
                        if "/worktrees/" in parent_gitdir:
                            main_repo_path = parent_gitdir.split("/worktrees/")[0]
                            main_repo_dir = Path(main_repo_path).parent
                            main_repo_name = main_repo_dir.name

                            click.echo(
                                f"🔍 Detected Git worktree structure. Parent repo: {main_repo_name}"
                            )

                            # Sync parent repo first
                            click.echo(
                                f"🔄 Syncing parent repository {main_repo_name}..."
                            )

                            # Get original working directory
                            original_dir = os.getcwd()

                            try:
                                # Change to parent repo directory
                                os.chdir(str(main_repo_dir))

                                # Now sync the parent repo from its own directory
                                parent_remote_config = RemoteConfig(
                                    host=remote.host,
                                    username=remote.username,
                                    working_dir=f"~/projects/{main_repo_name}",
                                )

                                sync_project(
                                    parent_remote_config,
                                    main_repo_name,
                                    remote_path=main_repo_name,
                                    exclude=exclude,
                                )

                                # Now fix the worktree .git file on remote to point to the correct location
                                remote_cmd(
                                    remote_config,
                                    [
                                        f"cd ~/projects/{worktree_name} && "
                                        f'echo "gitdir: ../{{main_repo_name}}/.git/worktrees/{worktree_name}" > .git'
                                    ],
                                    use_working_dir=False,
                                )
                                click.echo(
                                    f"✅ Fixed worktree Git reference to point to parent repo"
                                )

                            finally:
                                # Change back to original directory
                                os.chdir(original_dir)

            except Exception as e:
                click.echo(f"⚠️ Failed to sync parent repository: {e}")
                click.echo("⚠️ Continuing with normal worktree sync...")

        # Now sync the worktree/project
        sync_project(
            remote_config, project_name, remote_path=worktree_name, exclude=exclude
        )

        # Set up environment first
        env_updates = {
            "VARIANT": variant,
            "NVIDIA_DRIVER_CAPABILITIES": "all",
            "NVIDIA_VISIBLE_DEVICES": "all",
        }

        if worktree and worktree != project_name:
            env_updates["WORKTREE_NAME"] = worktree_name
            click.echo(f"🌲 Adding worktree name to environment")

        # Add Python version to environment if specified
        if python_version:
            env_updates["PYTHON_VERSION"] = python_version
            click.echo(f"🐍 Setting Python version to {python_version}")

        click.echo(f"🔧 Updating environment configuration for {variant}...")
        update_env_file(remote_config, worktree_name, env_updates)

        click.echo("🚀 Starting remote container...")
        start_container(
            worktree_name,
            container_name,
            remote_config=remote_config,
            build=force_rebuild,
            host_ray_dashboard_port=host_ray_dashboard_port,
            host_ray_client_port=host_ray_client_port,
        )
    elif mode == "conda":
        click.echo("🔧 Setting up conda environment...")
        setup_conda_env(remote_config, env_name)

    if mode == "container":
        cmd = f"cd ~/projects/{worktree_name} && docker compose exec -it -w /workspace/{worktree_name} {container_name} zsh"
    elif mode == "ssh":
        cmd = f"cd ~/projects/{worktree_name} && zsh"
    elif mode == "conda":
        cmd = f"cd ~/projects/{worktree_name} && export PATH=$HOME/miniconda3/bin:$PATH && source $HOME/miniconda3/etc/profile.d/conda.sh && conda activate {env_name} && zsh"

    # Execute the SSH command with port forwarding for all modes
    # Build SSH command with port forwarding
    ssh_args = [
        "ssh",
        "-A",  # Forward SSH agent
        "-o",
        "ControlMaster=no",
        "-o",
        "ExitOnForwardFailure=no",
        "-o",
        "ServerAliveInterval=60",
        "-o",
        "ServerAliveCountMax=3",
    ]

    # Add port forwarding arguments
    for port_mapping in forward_ports:
        if port_mapping:
            local_port, remote_port = port_mapping.split(":")
            ssh_args.extend(["-L", f"{local_port}:localhost:{remote_port}"])

    # Add remaining SSH arguments
    ssh_args.extend(["-t", f"{remote.username}@{remote.host}", cmd])

    # Execute SSH command
    os.execvp("ssh", ssh_args)  # noqa: S606


@remote.command()
def list():  # noqa: A001
    """List remotes and their associated projects."""
    with db.get_session() as session:
        remotes = session.query(Remote).options(joinedload(Remote.projects)).all()

        if not remotes:
            click.echo("No remotes found")
            return

        click.echo("\nConfigured remotes:")
        for remote in remotes:
            click.echo(f"\n{remote.alias}:")
            click.echo(f"  Host: {remote.host}")
            click.echo(f"  Last used: {remote.last_used}")

            # Show all projects associated with this remote
            if remote.projects:
                click.echo("  Projects:")
                for project in remote.projects:
                    if project.conda_env:
                        click.echo(f"  Conda env: {project.conda_env}")
                    click.echo(f"    - {project.name}")
                    click.echo(f"      Container: {project.container_name}")


@remote.command()
@click.argument("host_or_alias")
def remove(host_or_alias: str):
    """Remove a remote."""
    db.delete_remote(host_or_alias=host_or_alias)
    click.echo(f"Removed remote {host_or_alias}")


@remote.command()
@click.argument("host_or_alias")
@click.option(
    "--exclude",
    "-e",
    default="",
    help="Comma-separated patterns to exclude (e.g., 'checkpoints,wandb')",
)
@click.option(
    "--fix-worktree",
    is_flag=True,
    help="Fix worktree Git reference on remote",
)
def sync(host_or_alias, exclude, fix_worktree):
    """Sync project files with remote host."""
    project_name = Path.cwd().name
    remote = db.get_remote_fuzzy(host_or_alias)
    remote_config = RemoteConfig(host=remote.host, username=remote.username)

    # Check if we're in a worktree
    is_worktree = False
    main_repo_name = None
    main_repo_dir = None

    try:
        # Check if .git is a file (indicating a worktree) rather than a directory
        if Path(".git").is_file():
            with open(".git", "r") as f:
                git_content = f.read().strip()
                if git_content.startswith("gitdir:"):
                    is_worktree = True
                    parent_gitdir = git_content.split("gitdir:")[1].strip()

                    # Extract parent repo path
                    if "/worktrees/" in parent_gitdir:
                        main_repo_path = parent_gitdir.split("/worktrees/")[0]
                        main_repo_dir = Path(main_repo_path).parent
                        main_repo_name = main_repo_dir.name

                        click.echo(
                            f"🔍 Detected Git worktree. Parent repo: {main_repo_name}"
                        )
    except Exception as e:
        click.echo(f"⚠️ Could not detect Git worktree structure: {e}")

    # If we're in a worktree, sync the parent repo first
    if is_worktree and main_repo_dir:
        click.echo(f"🔄 Syncing parent repository {main_repo_name}...")
        original_dir = os.getcwd()
        worktree_name = project_name

        try:
            # Change to parent repo directory
            os.chdir(str(main_repo_dir))

            # Create parent repo remote config
            parent_remote_config = RemoteConfig(
                host=remote.host,
                username=remote.username,
                working_dir=f"~/projects/{main_repo_name}",
            )

            # Sync parent repo
            sync_project(
                parent_remote_config,
                main_repo_name,
                remote_path=main_repo_name,
                exclude=exclude,
            )
            click.echo(f"✅ Parent repository {main_repo_name} synced")

            # Change back to original directory
            os.chdir(original_dir)

            # Sync worktree
            click.echo(f"🔄 Syncing worktree {worktree_name}...")
            sync_project(
                remote_config,
                worktree_name,
                remote_path=worktree_name,
                exclude=exclude,
            )

            # Fix worktree Git reference if requested
            if fix_worktree:
                click.echo("🔧 Fixing Git worktree reference...")
                remote_cmd(
                    remote_config,
                    [
                        f"cd ~/projects/{worktree_name} && "
                        f'echo "gitdir: ../{main_repo_name}/.git/worktrees/{worktree_name}" > .git'
                    ],
                    use_working_dir=False,
                )
                click.echo("✅ Fixed worktree Git reference")

            click.echo(f"✅ Worktree {worktree_name} synced")
            click.echo(
                f"🎉 Successfully synced parent repo and worktree with {host_or_alias}"
            )
            return

        except Exception as e:
            click.echo(f"⚠️ Error syncing parent repo: {e}")
            click.echo("⚠️ Continuing with normal sync...")
            os.chdir(original_dir)

    # Normal sync for non-worktree case
    sync_project(remote_config, project_name, exclude=exclude)
    click.echo(f"✅ Synced project files with remote host {host_or_alias}")


@remote.command()
@click.argument("host_or_alias")
@click.argument("worktree_name")
@click.argument("main_repo_name")
def fix_worktree(host_or_alias, worktree_name, main_repo_name):
    """Fix Git worktree reference to point to parent repo."""
    remote = db.get_remote_fuzzy(host_or_alias)
    remote_config = RemoteConfig(
        host=remote.host,
        username=remote.username,
        working_dir=f"~/projects/{worktree_name}",
    )

    click.echo(f"🔧 Fixing Git worktree reference for {worktree_name}...")
    remote_cmd(
        remote_config,
        [
            f"cd ~/projects/{worktree_name} && "
            f'echo "gitdir: ../{main_repo_name}/.git/worktrees/{worktree_name}" > .git'
        ],
        use_working_dir=False,
    )
    click.echo("✅ Fixed worktree Git reference")


@remote.command()
@click.argument("host_or_alias")
@click.argument("remote_path")
@click.option(
    "--local-path",
    "-l",
    default=".",
    help="Local path to download to",
)
@click.option(
    "--exclude",
    "-e",
    default="",
    help="Comma-separated patterns to exclude (e.g., 'checkpoints,wandb')",
)
@click.option(
    "--worktree",
    is_flag=True,
    help="Fetch from worktree and update its Git reference",
)
@click.option(
    "--main-repo",
    help="Name of the main repository (for worktree setup)",
)
def fetch(host_or_alias, remote_path, local_path, exclude, worktree, main_repo):
    """Fetch files/directories from remote host to local."""
    exclude_patterns = exclude.split(",") if exclude else []

    remote = db.get_remote_fuzzy(host_or_alias)
    remote_config = RemoteConfig(host=remote.host, username=remote.username)

    # Check if we're in a worktree context automatically
    if worktree:
        if not main_repo:
            # Try to auto-detect main repo name from the current .git file
            try:
                if Path(".git").is_file():
                    with open(".git", "r") as f:
                        git_content = f.read().strip()
                        if git_content.startswith("gitdir:"):
                            parent_gitdir = git_content.split("gitdir:")[1].strip()

                            # Extract parent repo path
                            if "/worktrees/" in parent_gitdir:
                                main_repo_path = parent_gitdir.split("/worktrees/")[0]
                                main_repo_dir = Path(main_repo_path).parent
                                main_repo = main_repo_dir.name

                                click.echo(
                                    f"🔍 Auto-detected main repository: {main_repo}"
                                )
            except Exception as e:
                click.echo(f"⚠️ Could not auto-detect main repository: {e}")
                if not click.confirm(
                    "Continue without main repository reference?", default=False
                ):
                    raise click.ClickException(
                        "Main repository name required for worktree mode. Use --main-repo."
                    )

        # Get the worktree-specific files first
        click.echo(f"📥 Fetching worktree files from {remote_path}...")
        fetch_remote(
            remote_config=remote_config,
            remote_path=remote_path,
            local_path=local_path,
            exclude=exclude_patterns,
        )

        # If main repo is known, fix the .git file
        if main_repo:
            # Extract the worktree name from the remote path
            worktree_name = Path(remote_path).name

            click.echo(f"🔧 Setting up Git worktree reference to {main_repo}...")

            # Create or fix .git file to point to the parent repo
            local_path_obj = Path(local_path)
            git_file_path = local_path_obj / ".git"

            # Only proceed if we found a .git file or we're at the root of a path
            if (
                git_file_path.exists()
                or local_path_obj.resolve() == Path(".").resolve()
            ):
                with open(
                    git_file_path if git_file_path.exists() else ".git", "w"
                ) as f:
                    f.write(f"gitdir: ../{main_repo}/.git/worktrees/{worktree_name}")
                click.echo(
                    f"✅ Git worktree reference updated in {git_file_path if git_file_path.exists() else '.git'}"
                )
            else:
                click.echo("⚠️ Could not find .git file to update")
    else:
        # Normal fetch without worktree handling
        fetch_remote(
            remote_config=remote_config,
            remote_path=remote_path,
            local_path=local_path,
            exclude=exclude_patterns,
        )


@remote.command()
@click.argument("direction", type=click.Choice(["up", "down"]))
@click.argument("host_or_alias", required=False)
@click.option(
    "--local-dir",
    "-l",
    default="assets/checkpoints/",
    help="Local directory path to sync",
)
@click.option(
    "--remote-dir",
    "-r",
    default=None,
    help="Remote rclone path (e.g., 'gdbackup:research/my-checkpoints/')",
)
@click.option(
    "--project-name",
    "-p",
    default=None,
    help="Project name (used as part of remote path if remote-dir not specified)",
)
@click.option(
    "--transfers",
    default=16,
    help="Number of file transfers to run in parallel",
)
@click.option(
    "--checkers",
    default=32,
    help="Number of checkers to run in parallel",
)
@click.option(
    "--chunk-size",
    default="128M",
    help="Drive chunk size for uploads",
)
@click.option(
    "--cutoff",
    default="256M",
    help="Drive upload cutoff size",
)
@click.option(
    "--exclude",
    "-e",
    default="*.tmp,*.temp,*.DS_Store,__pycache__/*",
    help="Comma-separated patterns to exclude",
)
@click.option(
    "--mode",
    type=click.Choice(["local", "host", "container"]),
    default="local",
    help="Where to run rclone: local machine, remote host, or inside container",
)
@click.option(
    "--container-name",
    default=None,
    help="Container name to use (defaults to project name)",
)
@click.option(
    "--username",
    default="ubuntu",
    help="Remote username (only used with host or container mode)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Perform a trial run with no changes made",
)
@click.option(
    "--verbose/--quiet",
    "-v/-q",
    default=True,
    help="Enable/disable verbose output",
)
def datasync(
    direction,
    host_or_alias,
    local_dir,
    remote_dir,
    project_name,
    transfers,
    checkers,
    chunk_size,
    cutoff,
    exclude,
    mode,
    container_name,
    username,
    dry_run,
    verbose,
):
    """Sync data between local, remote host, and cloud storage using rclone.

    Examples:
        # Run rclone locally to sync with cloud storage
        mltoolbox remote datasync up

        # Run rclone on remote host to sync between host and cloud
        mltoolbox remote datasync up myserver --mode host

        # Run rclone inside container to sync container data with cloud
        mltoolbox remote datasync down myserver --mode container

        # Specify custom paths
        mltoolbox remote datasync up myserver -l data/images/ -r gdbackup:research/images/ --mode host
    """
    # If project name not specified, use current directory name
    if not project_name:
        project_name = Path.cwd().name

    # Set container name if not specified
    if not container_name:
        container_name = project_name.lower()

    # Build remote path if not provided
    if not remote_dir:
        remote_dir = f"gdbackup:research/{project_name}-data/"
        click.echo(f"No remote directory specified, using: {remote_dir}")

    # Handle remote operation if needed
    if mode in ["host", "container"] and not host_or_alias:
        raise click.ClickException(f"Host or alias required for '{mode}' mode")

    # Get remote configuration if needed
    remote_config = None
    if mode in ["host", "container"] and host_or_alias:
        if re.match(
            r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$",
            host_or_alias,
        ):
            # Direct IP address
            host = host_or_alias
        else:
            # Alias - look up in database
            remote = db.get_remote_fuzzy(host_or_alias)
            host = remote.host
            username = remote.username

        remote_config = RemoteConfig(
            host=host,
            username=username,
            working_dir=f"~/projects/{project_name}",
        )

    # Ensure local directory exists when in local mode
    if mode == "local":
        local_dir_path = Path(local_dir)
        local_dir_path.mkdir(parents=True, exist_ok=True)

    # Determine source and destination based on direction
    if direction == "up":
        source_dir = local_dir
        dest_dir = remote_dir
    else:  # down
        source_dir = remote_dir
        dest_dir = local_dir

    # Build rclone command based on mode
    if mode == "local":
        # Run locally
        click.echo(f"Syncing from {source_dir} to {dest_dir} on local machine...")
        run_rclone_sync(
            source_dir,
            dest_dir,
            transfers,
            checkers,
            chunk_size,
            cutoff,
            exclude,
            dry_run,
            verbose,
        )

    elif mode == "host":
        # Ensure rclone is set up on remote
        setup_rclone(remote_config)

        # Run on remote host
        click.echo(f"Syncing from {source_dir} to {dest_dir} on remote host...")

        # Create destination directory if needed
        if direction == "down" and not dest_dir.startswith(
            ("gdrive:", "gdbackup:", "s3:", "b2:")
        ):
            remote_cmd(
                remote_config,
                [f"mkdir -p {dest_dir}"],
                interactive=True,
            )

        # Build rclone command for remote execution
        rclone_cmd = build_rclone_cmd(
            source_dir,
            dest_dir,
            transfers,
            checkers,
            chunk_size,
            cutoff,
            exclude,
            dry_run,
            verbose,
        )

        # Execute on remote host
        remote_cmd(
            remote_config,
            [" ".join(rclone_cmd)],
            interactive=True,
        )

    elif mode == "container":
        # Run inside the container on remote host
        click.echo(f"Syncing from {source_dir} to {dest_dir} inside container...")

        # Build rclone command for container execution
        rclone_cmd = build_rclone_cmd(
            source_dir,
            dest_dir,
            transfers,
            checkers,
            chunk_size,
            cutoff,
            exclude,
            dry_run,
            verbose,
        )

        # Execute inside container
        docker_cmd = f"cd ~/projects/{project_name} && docker compose exec {container_name} {' '.join(rclone_cmd)}"
        remote_cmd(
            remote_config,
            [docker_cmd],
            interactive=True,
        )
