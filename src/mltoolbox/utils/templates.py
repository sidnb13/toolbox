from pathlib import Path

import pkg_resources
from jinja2 import Environment, PackageLoader, select_autoescape


def merge_requirements(project_dir: Path) -> None:
    """Merge existing requirements.txt with template requirements"""
    requirements_file = project_dir / "requirements.txt"
    template_reqs = set()
    existing_reqs = set()

    # Read template requirements if exists
    template_path = pkg_resources.resource_filename("mltoolbox", "templates/requirements.txt.j2")
    template_path = Path(template_path)
    if template_path.exists():
        template_reqs = set(template_path.read_text().splitlines())

    # Read existing requirements if exists
    if requirements_file.exists():
        existing_reqs = set(requirements_file.read_text().splitlines())

    # Merge requirements, keeping existing versions if there are conflicts
    merged_reqs = template_reqs.union(existing_reqs)

    # Write merged requirements
    with open(requirements_file, "w") as f:
        f.write("\n".join(sorted(merged_reqs)))


def merge_env_files(project_dir: Path, template_env: dict) -> dict:
    """Merge existing .env file with template values, preserving existing values."""
    env_file = project_dir / ".env"
    current_env = {}

    # Read existing .env if it exists
    if env_file.exists():
        with open(env_file, "r") as f:
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
    project_dir: Path, project_name: str, ray: bool, env_vars: dict
) -> None:
    """Generate project files from templates"""
    # Create directory structure
    (project_dir / "scripts").mkdir(exist_ok=True)
    (project_dir / "src").mkdir(exist_ok=True)
    (project_dir / "tests").mkdir(exist_ok=True)
    (project_dir / "assets").mkdir(exist_ok=True)

    # Template context with all variables
    context = {
        "project_name": project_name,
        "ray": ray,
        **env_vars,  # Include all env vars in template context
    }

    # Generate docker-compose.yml
    docker_compose = render_template("docker-compose.yml.j2", **context)
    (project_dir / "docker-compose.yml").write_text(docker_compose)

    # Generate Dockerfile
    dockerfile = render_template("Dockerfile.j2", **context)
    (project_dir / "Dockerfile").write_text(dockerfile)

    # Generate .env from template first, then merge with existing
    env_template = render_template(".env.j2", **context)

    # Parse the rendered template into a dict
    template_env = {}
    for line in env_template.splitlines():
        if line.strip() and not line.startswith("#"):
            try:
                key, value = line.split("=", 1)
                template_env[key.strip()] = value.strip().strip('"')
            except ValueError:
                continue

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

    # Create empty requirements.txt
    merge_requirements(project_dir)
