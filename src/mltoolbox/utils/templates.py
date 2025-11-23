from pathlib import Path

try:
    # Python 3.9+
    from importlib.resources import files
except ImportError:
    # Python 3.8 and below, use backport
    try:
        from importlib_resources import files
    except ImportError:
        # Fallback to pkg_resources if importlib_resources is not available
        import pkg_resources

        files = None

from jinja2 import Environment, PackageLoader, select_autoescape


def parse_requirement(req: str) -> str:
    """Parse requirement name without version"""
    req = req.strip()
    for op in [">=", "==", ">"]:
        if op in req:
            name = req.split(op, 1)[0]
            return name.strip()
    return req


def merge_requirements(project_dir: Path) -> None:
    """Merge existing requirements.txt with template requirements, preserving existing versions"""
    requirements_file = project_dir / "requirements.txt"
    existing_reqs = {}
    base_reqs = set()

    # Read base requirements
    if files is not None:
        # Use modern importlib.resources
        base_reqs_path = files("mltoolbox") / "base" / "requirements.txt"
        if base_reqs_path.is_file():
            for req in base_reqs_path.read_text().splitlines():
                if req.strip() and not req.startswith("#"):
                    base_reqs.add(parse_requirement(req))
    else:
        # Fallback to pkg_resources
        base_reqs_path = pkg_resources.resource_filename(
            "mltoolbox", "base/requirements.txt"
        )
        if Path(base_reqs_path).exists():
            for req in Path(base_reqs_path).read_text().splitlines():
                if req.strip() and not req.startswith("#"):
                    base_reqs.add(parse_requirement(req))

    # Read existing requirements if exists
    if requirements_file.exists():
        content = requirements_file.read_text()
        for line in content.splitlines():
            if line.strip() and not line.startswith("#"):
                name = parse_requirement(line)
                existing_reqs[name] = line

    # Add new requirements that don't exist
    new_reqs = base_reqs - set(existing_reqs.keys())

    # Write merged requirements
    with open(requirements_file, "w") as f:
        # Write existing requirements first
        if existing_reqs:
            f.write("# Existing project requirements\n")
            f.write("\n".join(sorted(existing_reqs.values())))
            f.write("\n\n")

        # Write new requirements from base
        if new_reqs:
            f.write("# Added by mltoolbox\n")
            f.write("\n".join(sorted(new_reqs)))
            f.write("\n")


def merge_env_files(project_dir: Path, template_env: dict) -> dict:
    """Merge existing .env file with template values, preserving existing values."""
    env_file = project_dir / ".env"
    current_env = {}

    # Read existing .env if it exists
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    try:
                        key, value = line.split("=", 1)
                        current_env[key.strip()] = value.strip()
                    except ValueError:
                        continue

    # Merge with template, keeping existing values
    merged_env = {**template_env, **current_env}
    return merged_env


def render_template(template_name: str, **kwargs) -> str:
    """Render a template with given context"""
    env = Environment(
        loader=PackageLoader("mltoolbox", "templates"), autoescape=select_autoescape()
    )
    template = env.get_template(template_name)
    return template.render(**kwargs)


def generate_project_files(
    project_dir: Path,
    project_name: str,
    ray: bool,
    env_vars: dict,
    python_version: str = "3.12",
    variant: str = "cuda",
) -> None:
    """Generate project files from templates"""
    # Create directory structure
    (project_dir / "scripts").mkdir(exist_ok=True)
    (project_dir / "assets").mkdir(exist_ok=True)

    if files is not None:
        # Use modern importlib.resources
        base_entrypoint_content = (
            files("mltoolbox") / "base" / "scripts" / "entrypoint.sh"
        ).read_bytes()
        project_entrypoint = project_dir / "scripts/entrypoint.sh"
        project_entrypoint.write_bytes(base_entrypoint_content)
        project_entrypoint.chmod(0o755)  # Make executable

        # Copy Ray init script if needed
        if ray:
            base_ray_init_content = (
                files("mltoolbox") / "base" / "scripts" / "ray-init.sh"
            ).read_bytes()
            project_ray_init = project_dir / "scripts/ray-init.sh"
            project_ray_init.write_bytes(base_ray_init_content)
            project_ray_init.chmod(0o755)  # Make executable
    else:
        # Fallback to pkg_resources
        base_entrypoint = Path(
            pkg_resources.resource_filename("mltoolbox", "base/scripts/entrypoint.sh")
        )
        project_entrypoint = project_dir / "scripts/entrypoint.sh"
        project_entrypoint.write_bytes(base_entrypoint.read_bytes())
        project_entrypoint.chmod(0o755)  # Make executable

        # Copy Ray init script if needed
        if ray:
            base_ray_init = Path(
                pkg_resources.resource_filename("mltoolbox", "base/scripts/ray-init.sh")
            )
            project_ray_init = project_dir / "scripts/ray-init.sh"
            project_ray_init.write_bytes(base_ray_init.read_bytes())
            project_ray_init.chmod(0o755)  # Make executable

    # Extract major.minor version for paths (e.g., "3.11.13" -> "3.11")
    python_version_short = ".".join(python_version.split(".")[:2])

    context = {
        "project_name": project_name.lower(),
        "ray": ray,
        "container_name": project_name.lower(),
        "python_version": python_version,  # Full version for PYTHON_VERSION env var
        "python_version_short": python_version_short,  # Short version for paths
        "variant": variant,
        **env_vars,
    }

    # Generate docker-compose.yml
    docker_compose = render_template("docker-compose.yml.j2", **context)
    (project_dir / "docker-compose.yml").write_text(docker_compose)

    # Generate Dockerfiles
    dockerfile = render_template("Dockerfile.j2", **context)
    (project_dir / "Dockerfile").write_text(dockerfile)

    # Generate Zed editor LSP configuration
    zed_dir = project_dir / ".zed"
    zed_dir.mkdir(exist_ok=True)
    zed_settings = render_template("zed-settings.json.j2", **context)
    (zed_dir / "settings.json").write_text(zed_settings)

    # Create template environment variables directly
    template_env = {
        "PROJECT_NAME": project_name.upper(),
        "CONTAINER_NAME": project_name.lower(),
        "PYTHON_VERSION": python_version,
        "VARIANT": variant,
        **env_vars,
    }

    # Merge with existing .env if it exists
    merged_env = merge_env_files(project_dir, template_env)

    # Write merged .env
    env_file = project_dir / ".env"
    with open(env_file, "w") as f:
        for key, value in merged_env.items():
            # Quote values that contain spaces
            if " " in str(value):
                value = f'"{value}"'
            f.write(f"{key}={value}\n")
