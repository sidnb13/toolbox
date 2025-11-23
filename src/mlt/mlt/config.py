"""Parse docker-compose.yml for path mappings."""

import os
import re
from pathlib import Path

import yaml


def load_env_file(project_dir: str = ".") -> dict[str, str]:
    """Load environment variables from .env file."""
    env_file = Path(project_dir).resolve() / ".env"
    env_vars = {}

    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, value = line.split("=", 1)
                        # Remove quotes if present
                        value = value.strip().strip('"').strip("'")
                        env_vars[key.strip()] = value

    return env_vars


def substitute_env_vars(text: str, env_vars: dict[str, str]) -> str:
    """Substitute ${VAR} or $VAR patterns with environment variables."""

    # Handle ${VAR} format
    def replace_var(match):
        var_name = match.group(1)
        return env_vars.get(var_name, match.group(0))

    text = re.sub(r"\$\{([^}]+)\}", replace_var, text)
    return text


def parse_docker_compose(project_dir: str = ".") -> dict[str, tuple[str, str]] | None:
    """
    Parse docker-compose.yml to extract volume mount path mappings.

    Args:
        project_dir: Project directory containing docker-compose.yml

    Returns:
        Dict mapping service name to (host_path, container_path) tuple
        Returns None if docker-compose.yml not found or invalid
    """
    project_path = Path(project_dir).resolve()
    compose_file = project_path / "docker-compose.yml"

    if not compose_file.exists():
        return None

    # Load environment variables
    env_vars = load_env_file(project_dir)

    try:
        with open(compose_file) as f:
            compose_content = f.read()
            # Substitute environment variables
            compose_content = substitute_env_vars(compose_content, env_vars)
            compose_data = yaml.safe_load(compose_content)

        if not compose_data or "services" not in compose_data:
            return None

        path_mappings = {}

        for service_name, service_config in compose_data.get("services", {}).items():
            if "volumes" not in service_config:
                continue

            # Look for project directory mount
            for volume in service_config["volumes"]:
                if isinstance(volume, str):
                    # Format: "./path:/container/path" or "~/path:/container/path"
                    parts = volume.split(":")
                    if len(parts) >= 2:
                        host_path = parts[0]
                        container_path = parts[1]

                        # Expand relative paths
                        if host_path.startswith("."):
                            host_path = str(project_path / host_path)
                        elif host_path.startswith("~"):
                            host_path = os.path.expanduser(host_path)

                        # Resolve to absolute path
                        host_path = str(Path(host_path).resolve())

                        # Store the mapping
                        path_mappings[service_name] = (host_path, container_path)

                        # If this is the main project mount, we're done
                        if str(project_path) in host_path:
                            break

        return path_mappings if path_mappings else None

    except Exception:
        return None


def get_path_mapping(project_dir: str = ".") -> tuple[str, str] | None:
    """
    Get the primary path mapping for the project.

    Returns:
        (host_path, container_path) tuple or None
    """
    mappings = parse_docker_compose(project_dir)
    if not mappings:
        return None

    # Return the first mapping (usually there's only one service)
    for service_name, (host_path, container_path) in mappings.items():
        return (host_path, container_path)

    return None


def get_all_path_mappings(
    project_dir: str = ".",
) -> tuple[tuple[str, str] | None, tuple[str, str] | None]:
    """
    Get both project and library path mappings from docker-compose.yml.

    Args:
        project_dir: Project directory containing docker-compose.yml

    Returns:
        Tuple of (project_mapping, library_mapping) where each is (host_path, container_path) or None
        project_mapping: The main project volume mount (e.g., .:/workspace/project)
        library_mapping: The site-packages mount (e.g., ~/.cache/python-packages/X:/usr/local/lib/pythonX.Y/dist-packages)
    """
    project_path = Path(project_dir).resolve()
    compose_file = project_path / "docker-compose.yml"

    if not compose_file.exists():
        return (None, None)

    # Load environment variables
    env_vars = load_env_file(project_dir)

    try:
        with open(compose_file) as f:
            compose_content = f.read()
            # Substitute environment variables
            compose_content = substitute_env_vars(compose_content, env_vars)
            compose_data = yaml.safe_load(compose_content)

        if not compose_data or "services" not in compose_data:
            return (None, None)

        project_mapping = None
        library_mapping = None

        for service_name, service_config in compose_data.get("services", {}).items():
            if "volumes" not in service_config:
                continue

            for volume in service_config["volumes"]:
                if isinstance(volume, str):
                    # Format: "./path:/container/path" or "~/path:/container/path"
                    parts = volume.split(":")
                    if len(parts) >= 2:
                        host_path = parts[0]
                        container_path = parts[1]

                        # Expand relative paths
                        if host_path.startswith("."):
                            host_path = str(project_path / host_path)
                        elif host_path.startswith("~"):
                            host_path = os.path.expanduser(host_path)

                        # Resolve to absolute path
                        host_path = str(Path(host_path).resolve())

                        # Identify project mount (contains project_path)
                        if str(project_path) in host_path:
                            project_mapping = (host_path, container_path)

                        # Identify library mount (contains dist-packages or site-packages)
                        if (
                            "dist-packages" in container_path
                            or "site-packages" in container_path
                        ):
                            library_mapping = (host_path, container_path)

        return (project_mapping, library_mapping)

    except Exception:
        return (None, None)
