import os
import re
import subprocess
from pathlib import Path

import click

from mltoolbox.utils.db import DB

from ..utils.remote import (
    check_tunnel_active,
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

    # Check if tunnel is needed and active
    if not check_tunnel_active():
        log("🔄 Setting up SSH tunnel...")
        cleanup_tunnels()
        setup_ssh_tunnel(username, host)

    log("📦 Syncing project files...")
    sync_project(username, host, project_name)

    if mode == "container":
        # Check if docker group setup is needed
        check_docker = "groups | grep -q docker"
        result = subprocess.run(
            ["ssh", f"{username}@{host}", check_docker],
            capture_output=True,
            check=False,
        )

        if result.returncode != 0:
            log("🔧 Setting up docker permissions...")
            setup_commands = [
                "sudo groupadd -f docker",
                f"sudo usermod -aG docker {username}",
                "sudo systemctl restart docker",
                "newgrp docker",
            ]

            for cmd in setup_commands:
                subprocess.run(["ssh", f"{username}@{host}", cmd], check=False)

        # Check if container is already running
        container_name = f"{project_name}-dev"
        check_container = f"docker ps -q -f name={container_name}"

        result = subprocess.run(
            ["ssh", f"{username}@{host}", check_container],
            capture_output=True,
            text=True,
        )

        if not result.stdout.strip() or force_rebuild:
            log("🚀 Starting container on remote...")
            remote_commands = [
                f"cd ~/projects/{project_name}",
                "set -a",  # Auto-export all variables
                f"export PROJECT_NAME={project_name}",
                "source .env",
                "set +a",
                f"docker compose build \
                    --build-arg GIT_NAME='{os.getenv('GIT_NAME')}' \
                    --build-arg GIT_EMAIL='{os.getenv('GIT_EMAIL')}' \
                    --build-arg PROJECT_NAME='{project_name}'",
                "docker compose up -d",
                f"docker exec -it {container_name} /bin/bash",
            ]
        else:
            remote_commands = [
                f"cd ~/projects/{project_name}",
                "source .env",
                f"docker exec -it {container_name} /bin/bash",
            ]

        cmd = " && ".join(remote_commands)

        os.execvp(
            "ssh",
            [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-A",
                "-t",
                f"{username}@{host}",
                cmd,
            ],
        )

    elif mode == "conda":
        # Check if conda env exists
        check_env = f"conda env list | grep '{env_name}'"
        result = subprocess.run(
            ["ssh", f"{username}@{host}", check_env], capture_output=True
        )

        if result.returncode != 0:
            log("🔧 Setting up conda environment...")
            setup_conda_env(username, host, env_name)

        os.execvp(
            "ssh",
            [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-A",
                "-t",
                f"{username}@{host}",
                f"cd ~/projects/{project_name} && conda activate {env_name} && bash",
            ],
        )

    else:  # ssh mode
        log("🔌 Connecting to remote shell...")
        os.execvp(
            "ssh",
            [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-A",
                "-t",
                f"{username}@{host}",
                f"cd ~/projects/{project_name} && bash",
            ],
        )


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
