import os
import re
import subprocess
from pathlib import Path

import click
from dotenv import load_dotenv
from sqlalchemy.orm import joinedload

from mltoolbox.utils.db import DB, Remote
from mltoolbox.utils.docker import (
    RemoteConfig,
    check_docker_group,
    check_nvidia_container_toolkit,
    ensure_ray_head_node,
    find_available_port,
    start_container,
)
from mltoolbox.utils.helpers import remote_cmd
from mltoolbox.utils.remote import (
    build_rclone_cmd,
    fetch_remote,
    run_rclone_sync,
    setup_rclone,
    setup_remote_ssh_keys,
    setup_zshrc,
    sync_project,
    update_env_file,
    verify_env_vars,
    wait_for_host,
)

db = DB()


@click.group()
def remote():
    """Manage remote development environment."""
    load_dotenv(".env")


@remote.command()
@click.argument("host_or_alias")
@click.option("--alias")
@click.option("--username", default="ubuntu", help="Remote username")
@click.option("--force-rebuild", is_flag=True, help="force rebuild remote container")
@click.option(
    "--forward-ports",
    "-p",
    multiple=True,
    default=[],
    help="Port forwarding in local:remote format",
)
@click.option(
    "--host-ray-dashboard-port",
    default=None,
    help="Host port to map to Ray dashboard (container port remains 8265)",
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
@click.option("--skip-sync", is_flag=True, help="Skip syncing project files")
@click.option(
    "--python-version",
    default=None,
    help="Python version to use (e.g., '3.10', '3.11')",
)
@click.option(
    "--branch-name",
    default=None,
    help="Branch name to use (e.g., 'main', 'feature/new-feature')",
)
@click.option(
    "--network-mode",
    type=click.Choice(["host", "bridge", "none"]),
    default=None,
    help="Override network mode (default is 'host' from compose file)",
)
@click.option(
    "--variant",
    type=click.Choice(["cuda", "gh200"]),
    default=None,
    help="Base image variant to use (e.g., 'cuda', 'gh200')",
)
@click.option(
    "--dependency-tags",
    default="dev",
    help="Comma-separated dependency tags to install (e.g., 'dev,array')",
)
@click.option(
    "--identity-file",
    default=None,
    help="Identity file to use for SSH connection (e.g., '~/.ssh/id_ed25519')",
)
@click.pass_context
def connect(
    ctx,
    host_or_alias,
    alias,
    username,
    force_rebuild,
    forward_ports,
    host_ray_dashboard_port,
    timeout,
    exclude,
    skip_sync,
    python_version,
    branch_name,
    network_mode,
    variant,
    dependency_tags,
    identity_file,
):
    """Connect to remote development environment."""
    dryrun = ctx.obj.get("dryrun", False)

    # Validate Python version early if specified
    if python_version:
        if not re.match(r"^\d+\.\d+\.\d+$", python_version):
            raise click.ClickException(
                "Please specify the full Python version, e.g., 3.11.12"
            )

    # Validate host IP address format
    ip_pattern = r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
    if not re.match(ip_pattern, host_or_alias):
        host = None
        alias = host_or_alias
    else:
        host = host_or_alias

    env_vars = verify_env_vars(dryrun=dryrun)
    project_name = env_vars.get("PROJECT_NAME", Path.cwd().name)

    # If project name from env doesn't match cwd, use cwd name to avoid conflicts
    cwd_name = Path.cwd().name
    if project_name != cwd_name:
        project_name = cwd_name

    container_name = env_vars.get("CONTAINER_NAME", project_name.lower())

    if not branch_name:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            branch_name = result.stdout.strip()
        except:  # noqa: E722
            branch_name = None

    # Get or create/update remote and project
    remote = db.upsert_remote(
        username=username,
        host=host,
        project_name=project_name,
        container_name=container_name,
        alias=alias,
        dryrun=dryrun,
        identity_file=identity_file,
    )

    if not dryrun and not wait_for_host(remote.host, timeout, username):
        raise click.ClickException(
            f"Timeout waiting for host {remote.host} after {timeout} seconds"
        )
    elif dryrun:
        from mltoolbox.utils.logger import get_logger

        logger = get_logger()
        logger.info(f"[DRYRUN] Would wait for host {remote.host} (skipped)")

    remote_config = RemoteConfig(
        host=remote.host,
        username=remote.username,
        working_dir=f"~/projects/{project_name}",
        identity_file=remote.identity_file or Path.home() / ".ssh/id_ed25519",
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
        f.write("    ForwardAgent yes\n")
        if remote.identity_file:
            f.write(f"    IdentityFile {remote.identity_file}\n")
        f.write("\n")

    from mltoolbox.utils.logger import get_logger

    logger = get_logger()

    logger.info(f"Access your instance with `ssh {remote.alias}`")

    if not dryrun:
        setup_zshrc(remote_config)
        setup_rclone(remote_config)
    else:
        logger.info("[DRYRUN] Would setup zshrc and rclone (skipped)")

    logger.step(f"Creating remote project directories for {project_name}")
    if not dryrun:
        remote_cmd(
            remote_config,
            [f"mkdir -p ~/projects/{project_name}"],
            use_working_dir=False,
        )
    else:
        logger.info("[DRYRUN] Would create remote project directories (skipped)")

    if not dryrun:
        check_docker_group(remote_config)
        logger.success("Docker group checked")
        check_nvidia_container_toolkit(remote_config, variant=variant or "cuda")
        logger.success("NVIDIA Container Toolkit checked")
    else:
        logger.info("[DRYRUN] Would check Docker group (skipped)")
        logger.success("[DRYRUN] Docker group checked (simulated)")
        logger.info("[DRYRUN] Would check NVIDIA Container Toolkit (skipped)")
        logger.success("[DRYRUN] NVIDIA Container Toolkit checked (simulated)")

    # First ensure remote directory exists
    if not dryrun:
        remote_cmd(
            remote_config,
            [f"mkdir -p ~/projects/{project_name}"],
            use_working_dir=False,
        )
    else:
        logger.info("[DRYRUN] Would ensure remote directory exists (skipped)")

    # Simple sync - no worktree detection or special handling
    if not skip_sync:
        sync_project(
            remote_config,
            project_name,
            remote_path=project_name,
            exclude=exclude,
            dryrun=dryrun,
        )
    else:
        logger.info("Skipping project sync, continuing with SSH key sync...")

    # Set up environment first
    env_updates = {
        **env_vars,
        "NVIDIA_DRIVER_CAPABILITIES": "all",
        "NVIDIA_VISIBLE_DEVICES": "all",
        "PROJECT_NAME": project_name,
        "DEPENDENCY_TAGS": dependency_tags,
    }

    # Get current branch if not specified
    if branch_name:
        container_name = f"{container_name}-{branch_name}"
        env_updates["CONTAINER_NAME"] = container_name

    # Add Python version to environment if specified
    if python_version:
        env_updates["PYTHON_VERSION"] = python_version
        logger.info(f"Setting Python version to {python_version}")
        # Strip to major.minor for main container build
        python_version_major_minor = ".".join(python_version.split(".")[:2])
        python_version_raw = python_version  # Keep full version for Ray
    else:
        python_version_major_minor = None
        python_version_raw = None

    # Add variant to environment if specified
    if variant:
        env_updates["VARIANT"] = variant
        logger.info(f"Setting variant to {variant}")

    logger.step("Updating environment")
    env_vars = update_env_file(remote_config, project_name, env_updates, dryrun=dryrun)
    ssh_key_name = env_vars.get("SSH_KEY_NAME", "id_ed25519")
    # Set up SSH keys on remote host
    if not dryrun:
        setup_remote_ssh_keys(remote_config, ssh_key_name)
    else:
        logger.info("[DRYRUN] Would setup remote SSH keys (skipped)")

    # Get existing Ray dashboard port if available
    port_mappings = db.get_port_mappings(remote.id, project_name)

    # Extract Ray dashboard port if it exists
    if port_mappings and "ray_dashboard" in port_mappings:
        ray_dashboard_value = port_mappings["ray_dashboard"]
        if isinstance(ray_dashboard_value, list):
            existing_dashboard_port = ray_dashboard_value[0]
        else:
            existing_dashboard_port = ray_dashboard_value
    else:
        existing_dashboard_port = None

    # Use provided dashboard port or existing or generate a new one
    if not host_ray_dashboard_port:
        host_ray_dashboard_port = existing_dashboard_port or find_available_port(
            None, 8265
        )

    # Ensure Ray head node is running with explicit parameters
    ensure_ray_head_node(
        remote_config, python_version_raw
    )  # Use full/raw version for Ray

    # Store only the Ray dashboard port
    db.upsert_remote(
        username=username,
        host=remote.host,
        project_name=project_name,
        container_name=container_name,
        port_mappings={"ray_dashboard": host_ray_dashboard_port},
    )

    logger.step("Starting remote container")

    start_container(
        project_name,
        container_name,
        remote_config=remote_config,
        build=force_rebuild,
        host_ray_dashboard_port=host_ray_dashboard_port,
        branch_name=branch_name,
        network_mode=network_mode,
        python_version=python_version_major_minor,  # Use major.minor for main container
        variant=variant or "cuda",
    )

    cmd = f"cd ~/projects/{project_name} && docker exec -it -w /workspace/{project_name} {container_name} zsh"

    # Build SSH command with dashboard port forwarding
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

    # Add identity file if specified
    if remote.identity_file:
        ssh_args.extend(["-i", remote.identity_file])

    # Print URL information to console
    logger.section("Service URLs")

    # Add Ray dashboard port forwarding
    ssh_args.extend(["-L", f"{host_ray_dashboard_port}:localhost:8265"])
    logger.info(f"Ray Dashboard: http://localhost:{host_ray_dashboard_port}")

    # Add additional user-specified port forwarding
    for port_mapping in forward_ports:
        if port_mapping:
            local_port, remote_port = port_mapping.split(":")
            ssh_args.extend(["-L", f"{local_port}:localhost:{remote_port}"])
            logger.info(f"Custom port: {local_port} -> {remote_port}")

    # Add remaining SSH arguments
    ssh_args.extend(["-t", f"{remote.username}@{remote.host}", cmd])

    # Execute SSH command
    os.execvp("ssh", ssh_args)  # noqa: S606


@remote.command()
def list_remotes():  # noqa: A001
    """List remotes and their associated projects."""
    from mltoolbox.utils.logger import get_logger

    logger = get_logger()

    with db.get_session() as session:
        remotes = session.query(Remote).options(joinedload(Remote.projects)).all()

        if not remotes:
            logger.info("No remotes found")
            return

        logger.section("Configured remotes")
        for remote in remotes:
            logger.info(f"{remote.alias}:")
            logger.info(f"  Host: {remote.host}")
            logger.info(f"  Last used: {remote.last_used}")

            # Show all projects associated with this remote
            if remote.projects:
                logger.info("  Projects:")
                for project in remote.projects:
                    logger.info(f"    - {project.name}")
                    logger.info(f"      Container: {project.container_name}")


@remote.command()
@click.argument("host_or_alias")
def remove(host_or_alias: str):
    """Remove a remote."""
    from mltoolbox.utils.logger import get_logger

    logger = get_logger()

    db.delete_remote(host_or_alias=host_or_alias)
    logger.success(f"Removed remote {host_or_alias}")


@remote.command()
@click.argument("host_or_alias")
@click.option(
    "--exclude",
    "-e",
    default="",
    help="Comma-separated patterns to exclude (e.g., 'checkpoints,wandb')",
)
def sync(host_or_alias, exclude):
    """Sync project files with remote host."""
    project_name = Path.cwd().name
    remote = db.get_remote_fuzzy(host_or_alias)
    remote_config = RemoteConfig(host=remote.host, username=remote.username)

    sync_project(remote_config, project_name, exclude=exclude)
    from mltoolbox.utils.logger import get_logger

    logger = get_logger()
    logger.success(f"Synced project files with remote host {host_or_alias}")


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
    "--main-repo",
    help="Name of the main repository (for worktree setup)",
)
def fetch(host_or_alias, remote_path, local_path, exclude, main_repo):
    """Fetch files/directories from remote host to local."""
    exclude_patterns = exclude.split(",") if exclude else []

    remote = db.get_remote_fuzzy(host_or_alias)
    remote_config = RemoteConfig(host=remote.host, username=remote.username)

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
        from mltoolbox.utils.logger import get_logger

        logger = get_logger()
        logger.info(f"No remote directory specified, using: {remote_dir}")

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
        from mltoolbox.utils.logger import get_logger

        logger = get_logger()
        logger.step(f"Syncing from {source_dir} to {dest_dir} on local machine")
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
        from mltoolbox.utils.logger import get_logger

        logger = get_logger()
        logger.step(f"Syncing from {source_dir} to {dest_dir} on remote host")

        # Create destination directory if needed
        if direction == "down" and not dest_dir.startswith(
            ("gdrive:", "gdbackup:", "s3:", "b2:")
        ):
            remote_cmd(
                remote_config,
                [f"mkdir -p {dest_dir}"],
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
        )

    elif mode == "container":
        # Run inside the container on remote host
        from mltoolbox.utils.logger import get_logger

        logger = get_logger()
        logger.step(f"Syncing from {source_dir} to {dest_dir} inside container")

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
        )
