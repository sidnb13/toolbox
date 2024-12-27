import os
import re
from pathlib import Path
from typing import Optional

import click
from dotenv import load_dotenv

from ..utils.db import DB
from ..utils.docker import (
    RemoteConfig,
    check_docker_group,
    cleanup_containers,
    start_container,
    verify_env_vars,
)
from ..utils.remote import (
    setup_conda_env,
    sync_project,
)

db = DB()


@click.group()
def remote():
    """Manage remote development environment"""
    load_dotenv(".env")
    pass


@remote.command()
@click.argument("host")
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
@click.option("--clean-containers", is_flag=True, help="Cleanup containers")
def connect(
    host,
    alias,
    username,
    mode,
    env_name,
    force_rebuild,
    silent,
    clean_containers,
):
    load_dotenv(".env")
    """Connect to remote development environment"""
    # Validate host IP address format
    ip_pattern = r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
    if not re.match(ip_pattern, host):
        raise click.BadParameter("Host must be a valid IP address")

    def log(msg):
        if not silent:
            click.echo(msg)

    verify_env_vars()

    project_name = Path.cwd().name

    remote = db.get_remote(alias=alias, host=host, username=username)
    if remote:
        username = remote.username
        host = remote.host
        db.update_last_used(host=host, username=username)
    else:
        host = host
        remote = db.add_remote(username, host, alias, mode == "conda", env_name)

    # create custom ssh config if not exists
    ssh_config_path = Path("~/.config/mltoolbox/ssh/config").expanduser()
    if not ssh_config_path.exists():
        ssh_config_path.touch()

        # add include directive to main ssh config
        main_ssh_config_path = Path("~/.ssh/config").expanduser()
        include_line = f"Include {ssh_config_path}\n"

        # Create main SSH config if it doesn't exist
        if not main_ssh_config_path.exists():
            main_ssh_config_path.touch()

        # Read existing content
        with main_ssh_config_path.open("r") as f:
            content = f.read()

        # Add include at the top if it's not already there
        if include_line not in content:
            with main_ssh_config_path.open("w") as f:
                f.write(include_line + content)

    # add host and alias entry to custom ssh config
    with ssh_config_path.open("a") as f:
        f.write(f"Host {remote.alias}\n")
        f.write(f"    HostName {remote.host}\n")
        f.write(f"    User {remote.username}\n")
        f.write("    ForwardAgent yes\n")

    click.echo(f"Access your instance with `ssh {remote.alias}`")

    remote_config = RemoteConfig(
        host=host, username=username, working_dir=f"~/projects/{project_name}"
    )
    project_name = Path.cwd().name

    if mode == "container":
        check_docker_group(remote_config)
        if clean_containers:
            cleanup_containers(project_name, remote=remote_config)
        log("📦 Syncing project files...")
        sync_project(remote_config, project_name)
        log("🚀 Starting remote container...")
        start_container(project_name, remote_config=remote_config)
        cmd = f"cd ~/projects/{project_name} && docker compose exec -it {project_name.lower()} zsh"
    elif mode == "ssh":
        cmd = f"cd ~/projects/{project_name} && bash"
    elif mode == "conda":
        log("🔧 Setting up conda environment...")
        setup_conda_env(username, host, env_name)
        cmd = f"cd ~/projects/{project_name} && conda activate {env_name} && bash"

    # Execute the SSH command with port forwarding for all modes
    os.execvp(
        "ssh", ["ssh", "-L", "8265:localhost:8265", "-t", f"{username}@{host}", cmd]
    )


@remote.command()
def list():
    """List remotes"""
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
@click.argument("host_or_alias")
@click.option("--username", default="ubuntu", help="Remote username")
def remove(host_or_alias: str, username: Optional[str] = None):
    """Remove a remote"""
    db.delete_remote(host_or_alias=host_or_alias)
    click.echo(f"Removed remote {host_or_alias}")


@remote.command()
@click.argument("host_or_alias")
def sync(host_or_alias):
    """Sync project files with remote host"""
    project_name = Path.cwd().name
    # Get remote config
    remote = db.get_remote_fuzzy(host_or_alias)
    remote_config = RemoteConfig(host=remote.host, username=remote.username)
    sync_project(remote_config, project_name)
    click.echo(f"Synced project files with remote host {host_or_alias}")


@remote.command()
def cleanup():
    """Clean up SSH tunnels and ports"""
    from ..utils.remote import cleanup_tunnels

    cleanup_tunnels()
    click.echo("🧹 Cleaned up SSH tunnels and ports")
