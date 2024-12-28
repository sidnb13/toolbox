import os
import re
from pathlib import Path
from typing import Optional

import click
from dotenv import load_dotenv
from sqlalchemy.orm import joinedload

from mltoolbox.utils.helpers import remote_cmd

from ..utils.db import DB, Remote
from ..utils.docker import (
    RemoteConfig,
    check_docker_group,
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
@click.argument("host_or_alias")
@click.option("--username", default="ubuntu", help="Remote username")
@click.option(
    "--mode",
    type=click.Choice(["ssh", "container", "conda"]),
    default="ssh",
    help="Connection mode",
)
@click.option("--env-name", help="Conda environment name (for conda mode)")
@click.option("--silent", is_flag=True, help="don't show detailed output")
@click.option("--force-rebuild", is_flag=True, help="force rebuild remote container")
def connect(
    host_or_alias,
    username,
    mode,
    env_name,
    silent,
    force_rebuild,
):
    """Connect to remote development environment"""

    # Validate host IP address format
    ip_pattern = r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
    if not re.match(ip_pattern, host_or_alias):
        host = None
        alias = host_or_alias
    else:
        host = host_or_alias
        alias = None

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

    remote_config = RemoteConfig(
        host=host, username=username, working_dir=f"~/projects/{project_name}"
    )
    project_name = Path.cwd().name

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
                    # Skip this block if it matches our host or alias
                    skip_block = current_host in (remote.alias, remote.host)
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

    if mode == "container":
        check_docker_group(remote_config)
        click.echo("📦 Syncing project files...")
        sync_project(remote_config, project_name)
        click.echo("🚀 Starting remote container...")
        start_container(
            project_name, project_name, remote_config=remote_config, build=force_rebuild
        )
        cmd = f"cd ~/projects/{project_name} && docker compose exec -it -w /workspace/{project_name} {project_name.lower()} zsh"
    elif mode == "ssh":
        cmd = f"cd ~/projects/{project_name} && zsh"
    elif mode == "conda":
        click.echo("🔧 Setting up conda environment...")
        setup_conda_env(username, host, env_name)
        cmd = f"cd ~/projects/{project_name} && conda activate {env_name} && zsh"

    # Execute the SSH command with port forwarding for all modes
    os.execvp(
        "ssh",
        [
            "ssh",
            "-o",
            "ControlMaster=no",
            "-L",
            "8265:localhost:8265",
            "-t",
            f"{username}@{host}",
            cmd,
        ],
    )


@remote.command()
def list():
    """List remotes and their associated projects"""
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
            if remote.conda_env:
                click.echo(f"  Conda env: {remote.conda_env}")

            # Show all projects associated with this remote
            if remote.projects:
                click.echo("  Projects:")
                for project in remote.projects:
                    click.echo(f"    - {project.name}")
                    click.echo(f"      Container: {project.container_name}")
                    click.echo(f"      Directory: {remote.project_dir}/{project.name}")


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
