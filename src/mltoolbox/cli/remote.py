import os
import re
from pathlib import Path

import click
from dotenv import load_dotenv
from sqlalchemy.orm import joinedload

from mltoolbox.utils.db import DB, Remote
from mltoolbox.utils.docker import (
    RemoteConfig,
    verify_env_vars,
)
from mltoolbox.utils.helpers import remote_cmd
from mltoolbox.utils.remote import (
    build_rclone_cmd,
    check_docker_group_stage,
    connect_ssh_session,
    create_project_dirs_stage,
    fetch_remote,
    run_rclone_sync,
    setup_conda_env_stage,
    setup_rclone,
    setup_rclone_stage,
    setup_ssh_config_stage,
    setup_ssh_keys_stage,
    setup_zshrc_stage,
    start_container_stage,
    sync_project,
    sync_project_stage,
    update_env_file_stage,
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
@click.option("--force-setup", is_flag=True, help="Force re-run of all setup stages")
def direct(
    host_or_alias,
    username,
    force_rebuild,
    forward_ports,
    force_setup,
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
        raise click.ClickException("Failed to get env variables")

    remote_config = RemoteConfig(
        host=host,
        username=username,
        working_dir=f"~/projects/{project_name}",
    )

    # Create a minimal set of directories needed for the container
    create_project_dirs_stage(
        remote_config=remote_config, project_name=project_name, force=force_setup
    )

    # Start the container using our cached stage function
    start_container_stage(
        remote_config=remote_config,
        project_name=project_name,
        container_name=container_name,
        force_rebuild=force_rebuild,
        force=force_setup,
    )

    # Connect to container - use full path to docker compose
    # Use direct SSH connection rather than the helper function
    cmd = f"cd ~/projects/{project_name} && docker compose exec -it -w /workspace/{project_name} {container_name} zsh"

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
@click.option("--force-rebuild", is_flag=True, help="Force rebuild remote container")
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
@click.option("--skip-sync", is_flag=True, help="Skip syncing project files")
@click.option(
    "--variant",
    type=click.Choice(["cuda", "gh200"]),
    default="cuda",
    help="Base image variant to use",
)
@click.option("--env-variant", default="default", help="Environment variant")
@click.option(
    "--python-version",
    default=None,
    help="Python version to use (e.g., '3.10', '3.11')",
)
@click.option("--force-setup", is_flag=True, help="Force re-run of all setup stages")
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
    skip_sync,
    variant,
    env_variant,
    python_version,
    force_setup,
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
        working_dir=f"~/projects/{project_name}",
    )

    # Stage 0: Set up SSH config locally (not cached since it's a local operation)
    setup_ssh_config_stage(remote, project_name)

    # Stage 1: Basic Shell Setup
    setup_zshrc_stage(
        remote_config=remote_config, project_name=project_name, force=force_setup
    )
    setup_rclone_stage(
        remote_config=remote_config, project_name=project_name, force=force_setup
    )
    create_project_dirs_stage(
        remote_config=remote_config, project_name=project_name, force=force_setup
    )

    # Mode-specific stages
    if mode == "container":
        # Stage 2: Docker Setup
        check_docker_group_stage(
            remote_config=remote_config,
            project_name=project_name,
            force=force_setup,
            username=remote.username,
        )

        # Stage 3: Project Sync
        sync_project_stage(
            remote_config=remote_config,
            project_name=project_name,
            force=force_setup,
            exclude=exclude,
            skip_sync=skip_sync,
        )

        # Stage 4: Environment Configuration
        update_env_file_stage(
            remote_config=remote_config,
            project_name=project_name,
            force=force_setup,
            variant=variant,
            env_variant=env_variant,
            python_version=python_version,
        )

        # Stage 5: SSH Key Setup
        ssh_key_name = env_vars.get("SSH_KEY_NAME", "id_ed25519")
        setup_ssh_keys_stage(
            remote_config=remote_config,
            project_name=project_name,
            force=force_setup,
            ssh_key_name=ssh_key_name,
        )

        # Stage 6: Container Start
        start_container_stage(
            remote_config=remote_config,
            project_name=project_name,
            force=force_setup,
            container_name=container_name,
            force_rebuild=force_rebuild,
            host_ray_dashboard_port=host_ray_dashboard_port,
            host_ray_client_port=host_ray_client_port,
            variant=variant,
            env_variant=env_variant,
            python_version=python_version,
        )

    elif mode == "conda":
        # Conda setup stage
        setup_conda_env_stage(
            remote_config=remote_config,
            project_name=project_name,
            force=force_setup,
            env_name=env_name,
            python_version=python_version or "3.12",
        )

    # Final stage: Connect via SSH
    connect_ssh_session(
        remote=remote,
        project_name=project_name,
        mode=mode,
        container_name=container_name,
        env_name=env_name,
        forward_ports=forward_ports,
    )


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
def sync(host_or_alias, exclude):
    """Sync project files with remote host."""
    project_name = Path.cwd().name
    remote = db.get_remote_fuzzy(host_or_alias)
    remote_config = RemoteConfig(host=remote.host, username=remote.username)

    sync_project(remote_config, project_name, exclude=exclude)
    click.echo(f"✅ Synced project files with remote host {host_or_alias}")


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
