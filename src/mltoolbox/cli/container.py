import os
from pathlib import Path

import click

from ..utils.docker import (
    check_docker_group,
    check_image_updates,
    cleanup_containers,
    start_container,
    verify_env_vars,
)


@click.group()
def container():
    """Manage development containers"""
    pass


@container.command()
@click.option("--force-rebuild", is_flag=True, help="Force rebuild of container")
def start(force_rebuild):
    """Start development container"""
    project_name = os.getenv("PROJECT_NAME", Path.cwd().name)

    # Check docker group membership
    check_docker_group()

    # Verify environment variables
    verify_env_vars()

    if force_rebuild:
        cleanup_containers(project_name)
    else:
        # Check for updates
        if check_image_updates(project_name):
            cleanup_containers(project_name)

    # Start container
    start_container(project_name)


@container.command()
def stop():
    """Stop development container"""
    project_name = os.getenv("PROJECT_NAME", Path.cwd().name)
    cleanup_containers(project_name)
