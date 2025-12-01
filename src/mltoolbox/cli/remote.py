import os
import re
import subprocess
from datetime import datetime
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
from mltoolbox.utils.logger import get_logger
from mltoolbox.utils.remote import (
    build_rclone_cmd,
    copy_local_pubkey_to_remote,
    fetch_remote,
    run_rclone_sync,
    setup_claude_code,
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
@click.option("--yes", "-y", is_flag=True, help="Skip all confirmation prompts")
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
@click.option(
    "--port", "-P", default=None, type=int, help="SSH port to use (default 22)"
)
@click.option(
    "--container-ssh-port",
    default=2222,
    type=int,
    help="Port for container SSH server (default: 2222)",
)
@click.option(
    "--jupyter",
    is_flag=True,
    help="Start Jupyter server in container (port 8888, Colab-compatible)",
)
@click.option(
    "--jupyter-port",
    default=8888,
    type=int,
    help="Port for Jupyter server (default: 8888)",
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
    yes,
    python_version,
    branch_name,
    network_mode,
    variant,
    dependency_tags,
    identity_file,
    port,
    container_ssh_port,
    jupyter,
    jupyter_port,
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
        # Not an IP - check if it's an existing alias
        existing_remote = db.get_remote_fuzzy(host_or_alias)
        if (
            existing_remote
            and hasattr(existing_remote, "host")
            and hasattr(existing_remote, "username")
        ):
            # Use existing remote configuration
            click.echo(
                f"Found existing alias '{host_or_alias}', using stored configuration"
            )
            host = existing_remote.host
            username = existing_remote.username
            alias = host_or_alias
            # Use stored identity_file if not overridden
            if not identity_file and existing_remote.identity_file:
                identity_file = existing_remote.identity_file
        else:
            # New alias, need IP address
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
    if not host:
        raise click.ClickException("Host must be specified and not None.")

    # Expand identity file path if provided
    if identity_file:
        identity_file = str(Path(identity_file).expanduser().resolve())

    remote = db.upsert_remote(
        username=username,
        host=str(host),
        project_name=project_name,
        container_name=container_name,
        alias=alias,
        dryrun=dryrun,
        identity_file=identity_file,
    )

    if not dryrun and not wait_for_host(remote.host, timeout, username, port):
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
        identity_file=str(remote.identity_file) if remote.identity_file else None,
        port=port,
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
    skip_block = False
    container_alias = f"{remote.alias}-container"

    if ssh_config_path.exists():
        with ssh_config_path.open("r") as f:
            for line in f:
                if line.startswith("Host "):
                    current_host = line.split()[1].strip()
                    # Skip this block if it matches our alias or container alias
                    skip_block = current_host in (remote.alias, container_alias)
                if not skip_block:
                    existing_config.append(line)

    # Write updated config
    with ssh_config_path.open("w") as f:
        # Write existing entries (excluding the one we're updating)
        f.writelines(existing_config)

        # Add a newline if the file doesn't end with one
        if existing_config and not existing_config[-1].endswith("\n"):
            f.write("\n")

        # Write the new/updated entry for host
        f.write(f"Host {remote.alias}\n")
        f.write(f"    HostName {remote.host}\n")
        f.write(f"    User {remote.username}\n")
        f.write("    ForwardAgent yes\n")
        if remote.identity_file:
            f.write(f"    IdentityFile {remote.identity_file}\n")
        f.write("\n")

        # Write container SSH config entry (always enabled)
        f.write(f"# Container SSH access for {remote.alias}\n")
        f.write(f"Host {container_alias}\n")
        f.write(f"    HostName {remote.host}\n")
        f.write("    User root\n")
        f.write(f"    Port {container_ssh_port}\n")
        f.write("    ForwardAgent yes\n")
        if remote.identity_file:
            f.write(f"    IdentityFile {remote.identity_file}\n")
        f.write("\n")

    from mltoolbox.utils.logger import get_logger

    logger = get_logger()

    logger.console.print()  # Spacing
    logger.hint(f"Access host: [cyan]ssh {remote.alias}[/cyan]")
    logger.hint(
        f"Access container: [cyan]ssh {container_alias}[/cyan] (port {container_ssh_port})"
    )

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

    # Check system requirements
    logger.console.print()  # Spacing before system checks
    if not dryrun:
        check_docker_group(remote_config, force=yes)
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
    logger.console.print()  # Spacing before sync
    if not skip_sync:
        sync_project(
            remote_config,
            project_name,
            remote_path=project_name,
            exclude=exclude,
            dryrun=dryrun,
            force=yes,
        )
        logger.console.print()  # Spacing after sync
    else:
        logger.info("Skipping project sync, continuing with SSH key sync...")

    # Setup Claude Code config AFTER project sync to ensure global config takes precedence
    if not dryrun:
        setup_claude_code(remote_config)
    else:
        logger.info("[DRYRUN] Would setup Claude Code config (skipped)")

    # Set up environment first
    env_updates = {
        **env_vars,
        "NVIDIA_DRIVER_CAPABILITIES": "all",
        "NVIDIA_VISIBLE_DEVICES": "all",
        "PROJECT_NAME": project_name,
        "DEPENDENCY_TAGS": dependency_tags,
    }

    # Container SSH port (always enabled, port is configurable)
    env_updates["CONTAINER_SSH_PORT"] = str(container_ssh_port)

    # Add Jupyter configuration
    if jupyter:
        env_updates["ENABLE_JUPYTER"] = "true"
        env_updates["JUPYTER_PORT"] = str(jupyter_port)
        logger.info(f"Jupyter server enabled on port {jupyter_port}")

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
        # Copy local public key to remote for container SSH access
        copy_local_pubkey_to_remote(remote_config)
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
    if python_version_raw is None:
        python_version_raw = "3.8.0"  # fallback default
    ensure_ray_head_node(
        remote_config, str(python_version_raw)
    )  # Use full/raw version for Ray

    # Store port mappings including new services
    port_mappings_dict = {
        "ray_dashboard": host_ray_dashboard_port,
        "container_ssh": container_ssh_port,
    }
    if jupyter:
        port_mappings_dict["jupyter"] = jupyter_port

    db.upsert_remote(
        username=username,
        host=remote.host,
        project_name=project_name,
        container_name=container_name,
        port_mappings=port_mappings_dict,
    )

    logger.console.print()  # Spacing before container start
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

    # Add port if specified
    if port:
        ssh_args.extend(["-p", str(port)])

    # Print URL information to console
    # Display service URLs in compact tree format
    now = datetime.now().strftime("%H:%M:%S")
    logger.console.print(f"{now}  [bold blue]●[/bold blue]  [bold]Service URLs[/bold]")

    # Add Ray dashboard port forwarding
    ssh_args.extend(["-L", f"{host_ray_dashboard_port}:localhost:8265"])
    logger.console.print(
        f"      ├─ [dim]Ray Dashboard:[/dim] [cyan]http://localhost:{host_ray_dashboard_port}[/cyan]"
    )

    # Add Jupyter port forwarding if enabled
    if jupyter:
        ssh_args.extend(["-L", f"{jupyter_port}:localhost:{jupyter_port}"])
        logger.console.print(
            f"      ├─ [dim]Jupyter:[/dim] [cyan]http://localhost:{jupyter_port}[/cyan]"
        )
        logger.console.print(
            "      │  [dim]Colab:[/dim] Connect → Connect to local runtime → enter URL"
        )

    # Container SSH info (always enabled - no port forwarding needed, direct access)
    logger.console.print(
        f"      ├─ [dim]Container SSH:[/dim] [cyan]ssh {container_alias}[/cyan] (port {container_ssh_port})"
    )

    # Add additional user-specified port forwarding
    port_mappings_list = []
    for port_mapping in forward_ports:
        if port_mapping:
            local_port, remote_port = port_mapping.split(":")
            ssh_args.extend(["-L", f"{local_port}:localhost:{remote_port}"])
            port_mappings_list.append((local_port, remote_port))

    for idx, (local_port, remote_port) in enumerate(port_mappings_list):
        prefix = "      └─ " if idx == len(port_mappings_list) - 1 else "      ├─ "
        logger.console.print(
            f"{prefix}[dim]Port:[/dim] [cyan]{local_port}[/cyan] → {remote_port}"
        )

    # Add spacing before connection
    logger.console.print()
    logger.hint(f"Connecting to {container_name} on {remote.host}...")
    logger.console.print()

    # Add remaining SSH arguments
    ssh_args.extend(["-t", f"{remote.username}@{remote.host}", cmd])

    # Execute SSH command
    os.execvp("ssh", ssh_args)  # noqa: S606


@remote.command()
def list_remotes():  # noqa: A001
    """List remotes and their associated projects."""

    logger = get_logger()

    with db.get_session() as session:
        remotes = session.query(Remote).options(joinedload(Remote.projects)).all()

        if not remotes:
            logger.empty_state(
                "No remotes configured",
                "Use 'mltoolbox remote connect <host>' to add one",
            )
            return

        # Display remotes in compact tree format
        now = datetime.now().strftime("%H:%M:%S")
        logger.console.print(
            f"{now}  [bold blue]●[/bold blue]  [bold]Configured remotes[/bold]"
        )

        for idx, remote in enumerate(remotes):
            is_last_remote = idx == len(remotes) - 1
            prefix_main = "      └─ " if is_last_remote else "      ├─ "
            prefix_sub = "         " if is_last_remote else "      │  "

            logger.console.print(f"{prefix_main}[bold]{remote.alias}[/bold]")
            logger.console.print(f"{prefix_sub}[dim]Host:[/dim] {remote.host}")
            logger.console.print(
                f"{prefix_sub}[dim]Last used:[/dim] {remote.last_used}"
            )

            # Show all projects associated with this remote
            if remote.projects:
                logger.console.print(f"{prefix_sub}[dim]Projects:[/dim]")
                for proj_idx, project in enumerate(remote.projects):
                    is_last_proj = proj_idx == len(remote.projects) - 1
                    proj_prefix = (
                        "         └─ "
                        if (is_last_remote and is_last_proj)
                        else "         ├─ "
                    )
                    logger.console.print(f"{proj_prefix}[dim]{project.name}[/dim]")
                    logger.console.print(
                        f"{prefix_sub}    [dim]Container:[/dim] {project.container_name}"
                    )


@remote.command()
@click.argument("host_or_alias")
def remove(host_or_alias: str):
    """Remove a remote."""

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
@click.option(
    "--port", "-P", default=None, type=int, help="SSH port to use (default 22)"
)
def sync(host_or_alias, exclude, port):
    """Sync project files with remote host."""
    project_name = Path.cwd().name
    remote = db.get_remote_fuzzy(host_or_alias)
    if (
        not remote
        or not getattr(remote, "host", None)
        or not getattr(remote, "username", None)
    ):
        raise click.ClickException(
            f"Remote '{host_or_alias}' not found or missing host/username."
        )
    remote_config = RemoteConfig(host=remote.host, username=remote.username, port=port)

    sync_project(remote_config, project_name, exclude=exclude)

    logger = get_logger()
    logger.console.print()  # Spacing
    logger.success(f"Synced project files with remote host {host_or_alias}")
    logger.hint("Use 'mltoolbox remote sync' to sync again later")


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
@click.option(
    "--port", "-P", default=None, type=int, help="SSH port to use (default 22)"
)
def fetch(host_or_alias, remote_path, local_path, exclude, main_repo, port):
    """Fetch files/directories from remote host to local."""
    exclude_patterns = exclude.split(",") if exclude else []
    remote = db.get_remote_fuzzy(host_or_alias)
    if (
        not remote
        or not getattr(remote, "host", None)
        or not getattr(remote, "username", None)
    ):
        raise click.ClickException(
            f"Remote '{host_or_alias}' not found or missing host/username."
        )
    remote_config = RemoteConfig(host=remote.host, username=remote.username, port=port)

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
@click.option(
    "--port", "-P", default=None, type=int, help="SSH port to use (default 22)"
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
    port,
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
            host = host_or_alias
        else:
            remote = db.get_remote_fuzzy(host_or_alias)
            if (
                not remote
                or not getattr(remote, "host", None)
                or not getattr(remote, "username", None)
            ):
                raise click.ClickException(
                    f"Remote '{host_or_alias}' not found or missing host/username."
                )
            host = remote.host
            username = remote.username

        remote_config = RemoteConfig(
            host=host,
            username=username,
            working_dir=f"~/projects/{project_name}",
            port=port,
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
        if remote_config is None:
            raise click.ClickException("Remote config is required for host mode.")
        setup_rclone(remote_config)

        # Run on remote host
        from mltoolbox.utils.logger import get_logger

        logger = get_logger()
        logger.step(f"Syncing from {source_dir} to {dest_dir} on remote host")

        # Create destination directory if needed
        if direction == "down" and not dest_dir.startswith(
            ("gdrive:", "gdbackup:", "s3:", "b2:")
        ):
            if remote_config is None:
                raise click.ClickException("Remote config is required for host mode.")
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
        if remote_config is None:
            raise click.ClickException("Remote config is required for host mode.")
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
        # Docker compose files live in .mlt/ subdirectory
        docker_cmd = f"cd ~/projects/{project_name}/.mlt && docker compose exec {container_name} {' '.join(rclone_cmd)}"
        if remote_config is None:
            raise click.ClickException("Remote config is required for container mode.")
        remote_cmd(
            remote_config,
            [docker_cmd],
        )


@remote.command()
@click.argument("host_or_alias")
@click.option(
    "--port", "-P", default=None, type=int, help="SSH port to use (default 22)"
)
@click.option(
    "--container-name",
    default=None,
    help="Override container name (defaults to project name or CONTAINER_NAME)",
)
@click.option(
    "--branch-name",
    default=None,
    help="Branch name to use (e.g., 'main', 'feature/new-feature')",
)
def attach(host_or_alias, port, container_name, branch_name):
    """Attach to a running remote container shell (no sync, no checks, just shell)."""

    logger = get_logger()
    project_name = Path.cwd().name
    remote = db.get_remote_fuzzy(host_or_alias)
    if (
        not remote
        or not getattr(remote, "host", None)
        or not getattr(remote, "username", None)
    ):
        raise click.ClickException(
            f"Remote '{host_or_alias}' not found or missing host/username."
        )
    remote_config = RemoteConfig(host=remote.host, username=remote.username, port=port)

    # Determine container name
    if not container_name:
        # Try to get from project association
        container_name = None
        if hasattr(remote, "projects") and remote.projects:
            for project in remote.projects:
                if project.name == project_name:
                    container_name = project.container_name
                    break
        if not container_name:
            container_name = project_name.lower()

    # Get current branch if not specified (same logic as connect command)
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

    # Append branch name to container name (same logic as connect command)
    # But only if it's not already included in the container name
    if branch_name:
        branch_suffix = f"-{branch_name}"
        if not container_name.endswith(branch_suffix):
            container_name = f"{container_name}-{branch_name}"

    # Check if container exists and is running
    check_cmd = [
        f"docker ps --filter 'name=^{container_name}$' --format '{{{{.Names}}}}'"
    ]
    result = remote_cmd(remote_config, check_cmd)
    running_containers = [
        line.strip() for line in result.stdout.splitlines() if line.strip()
    ]
    if container_name not in running_containers:
        logger.failure(
            f"Container '{container_name}' is not running on remote host {remote.host}."
        )
        raise click.ClickException(
            f"Container '{container_name}' is not running on remote host {remote.host}."
        )

    # Build SSH command to attach
    cmd = f"cd ~/projects/{project_name} && docker exec -it -w /workspace/{project_name} {container_name} zsh"
    ssh_args = [
        "ssh",
        "-A",
        "-o",
        "ControlMaster=no",
        "-o",
        "ExitOnForwardFailure=no",
        "-o",
        "ServerAliveInterval=60",
        "-o",
        "ServerAliveCountMax=3",
    ]
    if remote.identity_file:
        ssh_args.extend(["-i", remote.identity_file])
    if port:
        ssh_args.extend(["-p", str(port)])
    ssh_args.extend([f"{remote.username}@{remote.host}", "-t", cmd])
    logger.info(f"Attaching to container '{container_name}' on {remote.host}...")
    os.execvp("ssh", ssh_args)
