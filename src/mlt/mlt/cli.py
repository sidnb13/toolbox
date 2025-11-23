"""Main CLI entry point for mlt."""

import sys
from pathlib import Path

import click

from mlt.container import get_container_name
from mlt.lsp_proxy import run_lsp_proxy
from mlt.sync_watchdog import run_sync_watchdog


@click.group()
@click.version_option()
def main():
    """ML Toolbox Remote Helper - LSP proxy and container utilities."""
    pass


@main.command(
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
        allow_interspersed_args=False,
    )
)
@click.option(
    "--container", default=None, help="Container name (auto-detected if not provided)"
)
@click.option(
    "--project-dir", default=".", help="Project directory (default: current directory)"
)
@click.pass_context
def lsp_proxy(ctx, container, project_dir):
    """
    Run LSP server in container with path translation.

    Example:
        mlt lsp-proxy ruff server
        mlt lsp-proxy basedpyright-langserver --stdio
    """
    # Get LSP command from extra args
    lsp_command = ctx.args

    if not lsp_command:
        click.echo("[mlt] ERROR: No LSP command provided", err=True)
        click.echo("[mlt] Usage: mlt lsp-proxy <lsp-command> [args...]", err=True)
        sys.exit(1)

    # Auto-detect container if not provided
    if not container:
        container = get_container_name(project_dir)
        if not container:
            click.echo("[mlt] ERROR: Could not detect container name", err=True)
            click.echo("[mlt] Try: mlt lsp-proxy --container <name> ...", err=True)
            sys.exit(1)

    # Run the LSP proxy
    exit_code = run_lsp_proxy(container, lsp_command, project_dir)
    sys.exit(exit_code)


def find_zed_lsp_binary(lsp_command: list[str]) -> list[str] | None:
    """Find Zed's bundled LSP tool and return the full command.

    Args:
        lsp_command: Original LSP command (e.g., ["ruff", "server"])

    Returns:
        Full command with Zed's bundled binary path, or None if not found
    """
    import platform

    # Zed languages directory
    if platform.system() == "Darwin":
        zed_languages = Path.home() / "Library/Application Support/Zed/languages"
    elif platform.system() == "Linux":
        zed_languages = Path.home() / ".local/share/zed/languages"
    else:
        return None

    if not zed_languages.exists():
        return None

    lsp_tool = lsp_command[0]
    lsp_args = lsp_command[1:]

    if lsp_tool == "ruff":
        # Find ruff binary (versioned directory structure: ruff-*/ruff-*/ruff)
        ruff_pattern = zed_languages / "ruff"
        if ruff_pattern.exists():
            ruff_bins = list(ruff_pattern.glob("ruff-*/ruff-*/ruff"))
            if ruff_bins:
                return [str(ruff_bins[0])] + lsp_args

    elif lsp_tool == "basedpyright-langserver":
        # basedpyright is Node.js - need to run with node
        pyright_js = (
            zed_languages
            / "basedpyright/node_modules/basedpyright/dist/pyright-langserver.js"
        )
        if pyright_js.exists():
            return ["node", str(pyright_js)] + lsp_args

    return None


@main.command(
    name="lsp-auto",
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
        allow_interspersed_args=False,
    ),
)
@click.option(
    "--project-dir", default=".", help="Project directory (default: current directory)"
)
@click.pass_context
def lsp_auto(ctx, project_dir):
    """
    Smart LSP wrapper - auto-detects local vs remote context.

    Local (no docker-compose.yml): Uses Zed's bundled LSP tools
    Remote (has docker-compose.yml): Use mlt lsp-proxy

    Example:
        mlt lsp-auto ruff server
        mlt lsp-auto basedpyright-langserver --stdio
    """
    import subprocess

    # Get LSP command from extra args
    lsp_command = ctx.args

    if not lsp_command:
        click.echo("[mlt] ERROR: No LSP command provided", err=True)
        click.echo("[mlt] Usage: mlt lsp-auto <lsp-command> [args...]", err=True)
        sys.exit(1)

    # Detect remote context by looking for docker-compose.yml
    def detect_remote_context(start_dir):
        """Walk up directory tree looking for docker-compose.yml"""
        current = Path(start_dir).resolve()
        while current != current.parent:
            if (current / "docker-compose.yml").exists():
                return True
            current = current.parent
        return False

    def run_local_passthrough(lsp_cmd):
        """Run LSP command locally using Zed's bundled tools."""
        # Try to find Zed's bundled LSP tool
        zed_command = find_zed_lsp_binary(lsp_cmd)
        if zed_command:
            try:
                result = subprocess.run(zed_command, check=False)
                sys.exit(result.returncode)
            except FileNotFoundError:
                # Zed binary found but execution failed, fall through to error
                pass

        # Zed tool not found or failed, try system PATH as fallback
        try:
            result = subprocess.run(lsp_cmd, check=False)
            sys.exit(result.returncode)
        except FileNotFoundError:
            click.echo(f"[mlt] ERROR: LSP command not found: {lsp_cmd[0]}", err=True)
            click.echo("[mlt] Tried: Zed bundled tools and system PATH", err=True)
            sys.exit(1)

    if detect_remote_context(project_dir):
        # Remote context detected - check if Docker is available
        try:
            subprocess.run(
                ["docker", "ps"],
                capture_output=True,
                check=True,
                timeout=2,
            )
            docker_available = True
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            docker_available = False

        if not docker_available:
            # Docker not available, use local passthrough
            click.echo("[mlt] Docker not available, using local passthrough", err=True)
            run_local_passthrough(lsp_command)

        # Docker is available, get container
        container = get_container_name(project_dir)
        if not container:
            click.echo(
                "[mlt] WARN: Remote context detected but no container found", err=True
            )
            click.echo("[mlt] Falling back to local passthrough", err=True)
            run_local_passthrough(lsp_command)

        exit_code = run_lsp_proxy(container, lsp_command, project_dir)
        sys.exit(exit_code)
    else:
        # Local context - use Zed's bundled tools
        run_local_passthrough(lsp_command)


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


@main.command(name="sync-lsp")
@click.option(
    "--daemon",
    "-d",
    is_flag=True,
    help="Run in background mode (watchdog daemon)",
)
@click.option(
    "--site-packages",
    default=None,
    help="Path to site-packages (auto-detected if not provided)",
)
@click.option(
    "--lsp-packages",
    default="/opt/lsp-packages",
    help="Path to LSP view directory (default: /opt/lsp-packages)",
)
def sync_lsp(daemon, site_packages, lsp_packages):
    """
    Sync Python packages to LSP view using hardlinks.

    By default, runs a watchdog daemon that monitors site-packages
    and automatically syncs changes to the LSP view directory.

    Example:
        mlt sync-lsp --daemon          # Run watchdog in background
        mlt sync-lsp                   # One-time sync
    """
    import subprocess

    # Auto-detect site-packages if not provided
    if not site_packages:
        try:
            result = subprocess.run(
                [
                    "python3",
                    "-c",
                    "import sys; print([p for p in sys.path if 'dist-packages' in p][0])",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            site_packages = result.stdout.strip()
        except (subprocess.CalledProcessError, IndexError):
            click.echo(
                "[mlt] ERROR: Could not auto-detect site-packages path", err=True
            )
            click.echo("[mlt] Try: mlt sync-lsp --site-packages <path>", err=True)
            sys.exit(1)

    site_packages_path = Path(site_packages)
    lsp_packages_path = Path(lsp_packages)

    if daemon:
        # Run watchdog daemon
        exit_code = run_sync_watchdog(
            site_packages_path, lsp_packages_path, daemon=True
        )
    else:
        # One-time sync
        click.echo("[mlt] 🔗 Syncing packages (one-time)...")
        click.echo(f"[mlt]   From: {site_packages_path}")
        click.echo(f"[mlt]   To: {lsp_packages_path}")

        try:
            subprocess.run(
                ["cp", "-alu", f"{site_packages_path}/.", f"{lsp_packages_path}/"],
                check=True,
            )
            click.echo("[mlt] ✅ Sync complete")
            exit_code = 0
        except subprocess.CalledProcessError as e:
            click.echo(f"[mlt] ERROR: Sync failed: {e}", err=True)
            exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
