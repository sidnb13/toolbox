import subprocess
import sys
from pathlib import Path

import click


@click.group()
def variant():
    """Manage variant-specific dependencies using uv extras."""
    pass


@variant.command()
@click.option(
    "--extra",
    multiple=True,
    help="Extra dependencies to install (e.g., cuda, cpu, ray, dev)",
)
@click.option(
    "--locked/--no-locked",
    default=True,
    help="Use locked dependencies (uv.lock file)",
)
def sync(extra, locked):
    """Sync dependencies with specified extras using uv."""
    project_dir = Path.cwd()

    # Check if pyproject.toml exists
    if not (project_dir / "pyproject.toml").exists():
        click.echo("❌ No pyproject.toml found. Run 'mltoolbox init' first.")
        return

    # Build uv sync command
    cmd = ["uv", "sync"]

    if locked:
        cmd.append("--locked")

    # Add extras
    for e in extra:
        cmd.extend(["--extra", e])

    # If no extras specified, show available ones
    if not extra:
        click.echo("No extras specified. Available extras:")
        list_extras()
        return

    click.echo(f"🔄 Running: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, check=True, cwd=project_dir)
        click.echo("✅ Dependencies synced successfully!")
    except subprocess.CalledProcessError as e:
        click.echo(f"❌ Failed to sync dependencies: {e}")
        sys.exit(1)
    except FileNotFoundError:
        click.echo("❌ uv not found. Please install uv first.")
        sys.exit(1)


@variant.command()
def list_extras():
    """List all available extras from pyproject.toml."""
    project_dir = Path.cwd()
    pyproject_file = project_dir / "pyproject.toml"

    if not pyproject_file.exists():
        click.echo("❌ No pyproject.toml found.")
        return

    try:
        import tomli

        with open(pyproject_file, "rb") as f:
            data = tomli.load(f)

        optional_deps = data.get("project", {}).get("optional-dependencies", {})

        if not optional_deps:
            click.echo("No optional dependencies (extras) found.")
            return

        click.echo("🧩 Available Extras:")
        for extra, deps in optional_deps.items():
            click.echo(f"  - {extra} ({len(deps)} dependencies)")

    except ImportError:
        click.echo("❌ tomli not available. Install with: pip install tomli")
    except Exception as e:
        click.echo(f"❌ Error reading pyproject.toml: {e}")


@variant.command()
@click.argument("variant", type=click.Choice(["cuda", "cpu", "cuda-nightly"]))
def install_torch(variant):
    """Install PyTorch for a specific variant."""
    click.echo(f"🔄 Installing PyTorch for {variant} variant...")

    cmd = ["uv", "sync", "--locked", "--extra", variant, "--extra", "dev"]

    try:
        subprocess.run(cmd, check=True)
        click.echo(f"✅ PyTorch {variant} variant installed successfully!")
    except subprocess.CalledProcessError as e:
        click.echo(f"❌ Failed to install PyTorch {variant}: {e}")
        sys.exit(1)
    except FileNotFoundError:
        click.echo("❌ uv not found. Please install uv first.")
        sys.exit(1)
