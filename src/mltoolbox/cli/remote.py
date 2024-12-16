import os
import subprocess
from pathlib import Path

import click

from mltoolbox.utils.db import DB

from ..utils.remote import setup_conda_env, setup_ssh_tunnel, sync_project


@click.group()
def remote():
    """Manage remote development environment"""
    pass


@remote.command()
@click.argument("host_or_alias")
@click.option("--alias", help="Remote alias")
@click.option(
    "--conda/--no-conda",
    default=False,
    help="Use conda environment instead of container",
)
@click.option("--env-name", help="Conda environment name")
def connect(host_or_alias, alias, conda, env_name):
    """Connect to remote development environment"""
    db = DB()

    remote = db.get_remote(host_or_alias)
    if remote:
        host = remote.host
        conda = remote.is_conda
        env_name = remote.conda_env
        db.update_last_used(host_or_alias)
    else:
        host = host_or_alias
        remote = db.add_remote(host, alias, conda, env_name)

    project_name = os.getenv("PROJECT_NAME", Path.cwd().name)

    # Install the mltoolbox cli
    click.echo("🔧 Installing mltoolbox on remote...")
    subprocess.run(["pip", "install", "git+https://github.com/sidnb13/toolbox"])

    if conda:
        setup_conda_env(host, env_name)
    else:
        setup_ssh_tunnel(host)
        sync_project(host, project_name)


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
def sync(host):
    """Sync project files with remote host"""
    project_name = os.getenv("PROJECT_NAME", Path.cwd().name)
    sync_project(host, project_name)
