"""Parse docker-compose.yml for path mappings."""

import os
from pathlib import Path

import yaml


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

    try:
        with open(compose_file) as f:
            compose_data = yaml.safe_load(f)

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
