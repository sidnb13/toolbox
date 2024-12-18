import os
import re
import subprocess
from pathlib import Path

import click

from ..utils.db import DB
from ..utils.docker import cleanup_containers, verify_env_vars
from ..utils.remote import (
    cleanup_tunnels,
    setup_conda_env,
    setup_ssh_tunnel,
    sync_project,
)


@click.group()
def remote():
    """Manage remote development environment"""
    pass


@remote.command()
@click.argument("host_or_alias")
@click.option("--alias", help="Remote alias")
@click.option("--username", default="ubuntu", help="Remote username")
@click.option(
    "--mode",
    type=click.Choice(["ssh", "container", "conda"]),
    default="ssh",
    help="Connection mode",
)
@click.option("--env-name", help="Conda environment name (for conda mode)")
@click.option("--force-rebuild", is_flag=True, help="Force rebuild of container")
@click.option("--silent", is_flag=True, help="don't show detailed output")
def connect(host_or_alias, alias, username, mode, env_name, force_rebuild, silent):
    """Connect to remote development environment"""
    # Validate host IP address format
    ip_pattern = r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
    if not re.match(ip_pattern, host_or_alias):
        raise click.BadParameter("Host must be a valid IP address")

    def log(msg):
        if not silent:
            click.echo(msg)

    verify_env_vars()

    db = DB()
    project_name = Path.cwd().name

    remote = db.get_remote(host_or_alias)
    if remote:
        username = remote.username
        host = remote.host
        db.update_last_used(host_or_alias)
    else:
        host = host_or_alias
        remote = db.add_remote(username, host, alias, mode == "conda", env_name)

    project_name = Path.cwd().name

    log("📦 Syncing project files...")
    sync_project(username, host, project_name)

    if mode == "container":
        # Clean up any existing containers
        cleanup_containers(project_name)

        # Clean up any existing tunnels
        cleanup_tunnels()

        # Setup SSH tunnel for remote access
        log("🔧 Setting up SSH tunnel...")
        setup_ssh_tunnel(username, host)

        # Sync project files
        log("📦 Syncing project files...")
        sync_project(username, host, project_name)

        # Start the container on the remote host
        log("🚀 Starting remote container...")
        ssh_cmd = (
            f"cd ~/projects/{project_name} && docker compose --profile linux up -d"
        )
        subprocess.run(["ssh", f"{username}@{host}", ssh_cmd], check=True)

        log("✅ Remote environment ready!")

        # Connect to the container
        container_name = f"{project_name}-linux".lower()
        exec_cmd = (
            f"docker exec -it -w /workspace/{project_name} {container_name} /bin/bash"
        )
        os.execvp("ssh", ["ssh", "-t", f"{username}@{host}", exec_cmd])

    elif mode == "conda":
        # Clean up any existing tunnels
        cleanup_tunnels()

        # Setup conda environment
        log("🔧 Setting up conda environment...")
        setup_conda_env(username, host, env_name)

        # Connect to conda environment
        conda_cmd = f"cd ~/projects/{project_name} && conda activate {env_name} && bash"
        os.execvp("ssh", ["ssh", "-t", f"{username}@{host}", conda_cmd])

    else:
        raise click.ClickException(f"Invalid mode: {mode}")


@remote.command()
def list():
    """List remotes"""
    db = DB()
    remotes = db.get_remotes()

    if not remotes:
        click.echo("No remotes found")
        return

    click.echo("\nConfigured remotes:")
    for remote in remotes:
        click.echo(f"\n{remote.alias}:")
        click.echo(f"  Host: {remote.host}")
        click.echo(f"  Project: {remote.project_dir}")
        click.echo(f"  Last used: {remote.last_used}")
        click.echo(f"  Type: {'conda' if remote.is_conda else 'container'}")
        if remote.is_conda and remote.conda_env:
            click.echo(f"  Conda env: {remote.conda_env}")


@remote.command()
@click.argument("host")
@click.option("--username", default="ubuntu", help="Remote username")
def sync(host, username):
    """Sync project files with remote host"""
    project_name = Path.cwd().name
    sync_project(username, host, project_name)


@remote.command()
def cleanup():
    """Clean up SSH tunnels and ports"""
    from ..utils.remote import cleanup_tunnels

    cleanup_tunnels()
    click.echo("🧹 Cleaned up SSH tunnels and ports")
