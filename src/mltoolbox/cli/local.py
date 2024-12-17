from pathlib import Path

import click

from ..utils.docker import cleanup_containers, start_container


@click.group()
def local():
    """Manage local development environment"""
    pass


@local.command()
@click.option("--force-rebuild", is_flag=True, help="Force rebuild of container")
def start(force_rebuild):
    """Start local development container"""
    project_name = Path.cwd().name

    if force_rebuild:
        cleanup_containers(project_name)

    start_container(project_name)


@local.command()
def stop():
    """Stop local development container"""
    project_name = Path.cwd().name
    cleanup_containers(project_name)
    click.echo("✅ Development container stopped")
