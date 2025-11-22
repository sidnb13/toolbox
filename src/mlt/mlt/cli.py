"""Main CLI entry point for mlt."""

import sys

import click

from mlt.container import get_container_name
from mlt.lsp_proxy import run_lsp_proxy


@click.group()
@click.version_option()
def main():
    """ML Toolbox Remote Helper - LSP proxy and container utilities."""
    pass


@main.command()
@click.argument("lsp_command", nargs=-1, required=True)
@click.option(
    "--container", default=None, help="Container name (auto-detected if not provided)"
)
@click.option(
    "--project-dir", default=".", help="Project directory (default: current directory)"
)
def lsp_proxy(lsp_command, container, project_dir):
    """
    Run LSP server in container with path translation.

    Example:
        mlt lsp-proxy ruff server
        mlt lsp-proxy basedpyright-langserver --stdio
    """
    # Auto-detect container if not provided
    if not container:
        container = get_container_name(project_dir)
        if not container:
            click.echo("[mlt] ERROR: Could not detect container name", err=True)
            click.echo("[mlt] Try: mlt lsp-proxy --container <name> ...", err=True)
            sys.exit(1)

    # Run the LSP proxy
    exit_code = run_lsp_proxy(container, list(lsp_command), project_dir)
    sys.exit(exit_code)


@main.command()
@click.argument("container", required=False)
@click.option("--project-dir", default=".", help="Project directory")
def attach(container, project_dir):
    """Attach to container shell."""
    import subprocess

    if not container:
        container = get_container_name(project_dir)
        if not container:
            click.echo("[mlt] ERROR: Could not detect container name", err=True)
            sys.exit(1)

    click.echo(f"[mlt] Attaching to container: {container}")

    try:
        subprocess.run(["docker", "exec", "-it", container, "zsh"], check=True)
    except subprocess.CalledProcessError:
        # Try bash if zsh fails
        try:
            subprocess.run(["docker", "exec", "-it", container, "bash"], check=True)
        except subprocess.CalledProcessError as e:
            click.echo(f"[mlt] ERROR: Failed to attach to container: {e}", err=True)
            sys.exit(1)


@main.command()
@click.argument("project_dir", default=".")
def container(project_dir):
    """Show container name for project."""
    container_name = get_container_name(project_dir)
    if container_name:
        click.echo(container_name)
    else:
        click.echo("[mlt] ERROR: No container found", err=True)
        sys.exit(1)


@main.command()
@click.argument("project_dir", default=".")
def status(project_dir):
    """Show project and container status."""
    import os
    import subprocess

    container_name = get_container_name(project_dir)

    click.echo(f"Project directory: {os.path.abspath(project_dir)}")
    click.echo(f"Container name: {container_name or 'Not found'}")

    if container_name:
        # Check if container is running
        try:
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Status}}", container_name],
                capture_output=True,
                text=True,
                check=True,
            )
            status = result.stdout.strip()
            click.echo(f"Container status: {status}")
        except subprocess.CalledProcessError:
            click.echo("Container status: Not found")


if __name__ == "__main__":
    main()
