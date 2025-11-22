"""Container detection logic."""

import os
import subprocess
from pathlib import Path


def get_container_name(project_dir: str = ".") -> str | None:
    """
    Get container name for the project.

    Tries in order:
    1. CONTAINER_NAME environment variable
    2. Read from .env file in project directory
    3. Auto-detect by querying docker ps with project name filter

    Args:
        project_dir: Project directory path

    Returns:
        Container name if found, None otherwise
    """
    project_path = Path(project_dir).resolve()

    # Try environment variable first
    container_name = os.getenv("CONTAINER_NAME")
    if container_name:
        return container_name

    # Try reading from .env file
    env_file = project_path / ".env"
    if env_file.exists():
        try:
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("CONTAINER_NAME="):
                        value = line.split("=", 1)[1]
                        # Remove quotes if present
                        value = value.strip('"').strip("'")
                        if value:
                            return value
        except Exception:
            pass

    # Auto-detect by project name
    # Try exact match first, then partial match
    project_name = project_path.name.lower()
    try:
        # First try: filter by name (partial match)
        result = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                f"name={project_name}",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        containers = [c.strip() for c in result.stdout.strip().split("\n") if c.strip()]

        if containers:
            # Prefer exact match if exists
            for container in containers:
                if container == project_name:
                    return container
            # Otherwise return first container that starts with project name
            for container in containers:
                if container.startswith(project_name):
                    return container
            # Fallback: return first match
            return containers[0]
    except subprocess.CalledProcessError:
        pass

    return None
