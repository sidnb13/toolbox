from pathlib import Path

import click


@click.group()
def variant():
    """Manage variant-specific requirements and lockfiles."""
    pass


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
    """List all available variants and their requirements files."""
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
