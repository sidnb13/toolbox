import click
from pathlib import Path
import subprocess
import sys


@click.group()
def variant():
    """Manage variant-specific requirements and lockfiles."""
    pass


@variant.command()
@click.option(
    "--system-variant",
    type=str,
    default="cuda",
    help="System variant (cuda, gh200)",
)
@click.option(
    "--env-variant",
    type=str,
    default="default",
    help="Environment variant (a10, a100, etc.)",
)
@click.option(
    "--python-version",
    type=str,
    help="Python version to target (e.g., 3.10, 3.11)",
)
def create_lockfile(system_variant, env_variant, python_version):
    """Create lockfile for a specific variant combination.

    This uses uv to generate a lockfile and doesn't need GPU access.
    Dependency resolution happens without hardware access.
    """
    project_dir = Path.cwd()

    # Input files
    input_files = []
    base_req = project_dir / "requirements.txt"
    system_req = project_dir / f"requirements-{system_variant}.txt"
    env_req = project_dir / f"requirements-env-{env_variant}.txt"
    ray_req = project_dir / "requirements-ray.txt"

    # Check which files exist
    if base_req.exists():
        input_files.append(str(base_req))
    if system_req.exists():
        input_files.append(str(system_req))
    if env_req.exists():
        input_files.append(str(env_req))
    if ray_req.exists():
        input_files.append(str(ray_req))

    if not input_files:
        click.echo("❌ No requirements files found.")
        return

    # Output file
    output_file = project_dir / f"requirements-{system_variant}-{env_variant}.lock"

    # Generate lockfile using uv
    click.echo(f"📦 Creating lockfile for {system_variant}/{env_variant} variant...")
    click.echo(f"📦 Using requirements: {', '.join(input_files)}")

    command = ["uv", "pip", "compile", "--output-file", str(output_file)]

    # Add Python version constraint if specified
    if python_version:
        click.echo(f"🐍 Targeting Python {python_version}")
        command.extend(["--python-version", python_version])

    command.extend(input_files)

    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)  # noqa: F841
        click.echo(f"✅ Created lockfile: {output_file}")
    except subprocess.CalledProcessError as e:
        click.echo(f"❌ Failed to create lockfile: {e}")
        if e.stderr:
            click.echo(e.stderr)
        sys.exit(1)


@variant.command()
@click.option(
    "--system-variant",
    type=str,
    required=True,
    help="System variant to create (cuda, gh200)",
)
@click.option(
    "--env-variant",
    type=str,
    required=True,
    help="Environment variant to create (a10, a100, etc)",
)
def create_requirements(system_variant, env_variant):
    """Create empty requirements files for specified variants."""
    project_dir = Path.cwd()

    # Create system variant requirements
    system_req = project_dir / f"requirements-{system_variant}.txt"
    if not system_req.exists():
        with open(system_req, "w") as f:
            f.write(f"# {system_variant} variant requirements\n")
        click.echo(f"✅ Created {system_req}")
    else:
        click.echo(f"ℹ️ {system_req} already exists")

    # Create environment variant requirements
    env_req = project_dir / f"requirements-env-{env_variant}.txt"
    if not env_req.exists():
        with open(env_req, "w") as f:
            f.write(f"# {env_variant} environment requirements\n")
        click.echo(f"✅ Created {env_req}")
    else:
        click.echo(f"ℹ️ {env_req} already exists")


@variant.command()
def list():
    """List all available variants and their requirements/lockfiles."""
    project_dir = Path.cwd()

    # Find all system variants
    system_variants = set()
    env_variants = set()

    for req_file in project_dir.glob("requirements-*.txt"):
        filename = req_file.name
        if filename.startswith("requirements-env-"):
            # Extract env variant
            env_variant = filename.replace("requirements-env-", "").replace(".txt", "")
            env_variants.add(env_variant)
        elif filename.startswith("requirements-"):
            # Extract system variant
            system_variant = filename.replace("requirements-", "").replace(".txt", "")
            if system_variant != "ray":
                system_variants.add(system_variant)

    # Show results
    if not system_variants and not env_variants:
        click.echo("No variants found.")
        return

    click.echo("🧩 Available Variants:")

    click.echo("\nSystem Variants:")
    for variant in sorted(system_variants):
        req_file = project_dir / f"requirements-{variant}.txt"
        click.echo(f"  - {variant} ({'exists' if req_file.exists() else 'missing'})")

    click.echo("\nEnvironment Variants:")
    for variant in sorted(env_variants):
        req_file = project_dir / f"requirements-env-{variant}.txt"
        click.echo(f"  - {variant} ({'exists' if req_file.exists() else 'missing'})")

    click.echo("\nLockfiles:")
    for s_variant in sorted(system_variants):
        for e_variant in sorted(env_variants):
            lockfile = project_dir / f"requirements-{s_variant}-{e_variant}.lock"
            if lockfile.exists():
                click.echo(f"  - {s_variant}/{e_variant}: ✅")
            else:
                click.echo(f"  - {s_variant}/{e_variant}: ❌")
