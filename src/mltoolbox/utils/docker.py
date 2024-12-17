import grp
import importlib.resources as pkg_resources
import os
import platform
import pwd
import subprocess
import sys
from pathlib import Path

import click

from .. import base


def check_docker_group() -> None:
    """Check if user is in docker group and add if not"""
    username = pwd.getpwuid(os.getuid()).pw_name
    try:
        if "docker" not in [g.gr_name for g in grp.getgrall() if username in g.gr_mem]:
            click.echo("👥 Adding user to docker group...")
            subprocess.run(["sudo", "adduser", username, "docker"], check=True)
            os.execvp("sg", ["sg", "docker", "-c", f'"{" ".join(sys.argv)}"'])
    except subprocess.CalledProcessError:
        raise click.ClickException("Failed to add user to docker group")


def cleanup_containers(project_name: str) -> None:
    """Cleanup existing containers and networks"""
    click.echo("🧹 Cleaning up existing containers...")

    # Remove both platform variants
    container_names = [
        f"{project_name}-linux".lower(),
        f"{project_name}-mac".lower(),
        "ray-head",
    ]

    # Kill any existing SSH tunnels
    if os.path.exists("/tmp/remote_tunnel.pid"):
        subprocess.run(["pkill", "-F", "/tmp/remote_tunnel.pid"], check=False)
        os.remove("/tmp/remote_tunnel.pid")

    # Remove containers and network
    for container in container_names:
        subprocess.run(["docker", "rm", "-f", container], check=False)
    subprocess.run(["docker", "network", "rm", "ray_network"], check=False)


def verify_env_vars() -> None:
    """Verify required environment variables are set"""
    env_file = Path.cwd() / ".env"
    if not env_file.exists():
        raise click.ClickException("❌ .env file not found")

    required_vars = ["GIT_NAME", "GITHUB_TOKEN", "GIT_EMAIL"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        raise click.ClickException(
            f"❌ Required environment variables not set: {', '.join(missing_vars)}"
        )


def get_image_digest(image: str, remote: bool = False) -> str:
    """Get image digest (local or remote)"""
    if remote:
        # Login to ghcr.io
        git_name = os.getenv("GIT_NAME")
        github_token = os.getenv("GITHUB_TOKEN")
        subprocess.run(
            ["docker", "login", "ghcr.io", "-u", git_name, "--password-stdin"],
            input=github_token.encode(),
            capture_output=True,
        )

        result = subprocess.run(
            ["docker", "manifest", "inspect", image], capture_output=True, text=True
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if '"digest":' in line:
                    return line.split(":")[2].strip(' ",')
    else:
        result = subprocess.run(
            ["docker", "image", "inspect", image, "--format={{index .Id}}"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip().split(":")[1]

    return "none"


def check_base_image_updates() -> bool:
    """Check if image needs updating"""
    click.echo("🔍 Checking for updates...")
    git_name = os.getenv("GIT_NAME")
    image = f"ghcr.io/{git_name}/ml-base:latest"

    local_digest = get_image_digest(image)
    remote_digest = get_image_digest(image, remote=True)

    return local_digest != remote_digest


def start_container(project_name: str) -> None:
    """Start the development container"""
    click.echo("🚀 Launching container...")

    # Determine platform-specific service name
    is_arm_mac = platform.system() == "Darwin" and platform.machine() == "arm64"
    platform_profile = "mac" if is_arm_mac else "linux"
    service_name = f"{project_name}-{platform_profile}".lower()

    result = subprocess.run(
        [
            "docker",
            "network",
            "ls",
            "--filter",
            "name=ray_network",
            "--format",
            "{{.Name}}",
        ],
        capture_output=True,
        text=True,
    )
    if "ray_network" not in result.stdout:
        subprocess.run(["docker", "network", "create", "ray_network"], check=False)

    # Build the project-specific image
    click.echo("🏗️  Starting project image...")
    result = subprocess.run(
        ["docker", "compose", "--profile", platform_profile, "up", "-d", service_name]
    )
    if result.returncode != 0:
        raise click.ClickException("Failed to start container")

    container_name = f"{project_name}-{platform_profile}".lower()
    if (
        subprocess.run(
            ["docker", "ps", "-q", "-f", f"name={container_name}"]
        ).returncode
        == 0
    ):
        click.echo("✅ Container started successfully!")

        # Show GPU info only on Linux
        if not is_arm_mac:
            subprocess.run(
                ["docker", "exec", container_name, "nvidia-smi", "--list-gpus"]
            )

        # Connect to container
        click.echo("🔌 Connecting to container...")
        os.execvp(
            "docker",
            [
                "docker",
                "exec",
                "-it",
                "-w",
                f"/workspace/{project_name}",
                container_name,
                "/bin/bash",
            ],
        )
    else:
        click.echo("❌ Container failed to start")
        subprocess.run(["docker", "logs", container_name])
        raise click.ClickException("Container startup failed")


def build_base_image(cuda_version: str, python_version: str, push: bool = False):
    """Build the base ML image"""
    # Get base directory from package resources
    with pkg_resources.path(base, "Dockerfile") as base_dockerfile:
        base_dir = base_dockerfile.parent

    if not base_dir.exists():
        raise click.ClickException(f"Base directory not found at {base_dir}")

    # Get GitHub credentials from environment
    git_name = os.getenv("GIT_NAME")
    github_token = os.getenv("GITHUB_TOKEN")
    if not git_name or not github_token:
        raise click.ClickException(
            "GIT_NAME and GITHUB_TOKEN environment variables must be set"
        )

    # Check platform and set version
    is_arm_mac = platform.system() == "Darwin" and platform.machine() == "arm64"
    dockerfile = "Dockerfile.mac" if is_arm_mac else "Dockerfile"
    platform_tag = "mac" if is_arm_mac else "linux"

    # Get package version from pyproject.toml
    import tomli

    with open(Path(__file__).parent.parent.parent.parent / "pyproject.toml", "rb") as f:
        version = tomli.load(f)["project"]["version"]

    # Define image names with versioning
    base_name = f"ghcr.io/{git_name}/ml-base"
    image_tags = [
        f"{base_name}:{platform_tag}-{version}",  # Versioned platform tag
        f"{base_name}:{platform_tag}-latest",  # Latest platform tag
    ]

    # Try to pull latest image first
    click.echo("🔄 Checking for existing image...")
    pull_result = subprocess.run(
        ["docker", "pull", f"{base_name}:{platform_tag}-latest"], capture_output=True
    )

    if pull_result.returncode == 0:
        click.echo("✅ Found existing image, will use as cache")
    else:
        click.echo("⚠️  No existing image found, building from scratch")

    # Login if pushing
    if push:
        click.echo("🔑 Logging in to GitHub Container Registry...")
        login_result = subprocess.run(
            ["docker", "login", "ghcr.io", "-u", git_name, "--password-stdin"],
            input=github_token.encode(),
            capture_output=True,
        )
        if login_result.returncode != 0:
            raise click.ClickException(
                f"Failed to login to ghcr.io: {login_result.stderr.decode()}"
            )

    # Build the image
    click.echo(f"🏗️  Building base image v{version} for {platform_tag}")

    build_args = [
        "docker",
        "build",
        "--pull",  # Always check for updated base images
        "--cache-from",
        f"{base_name}:{platform_tag}-latest",
    ]

    # Add tags
    for tag in image_tags:
        build_args.extend(["-t", tag])

    # Add build args
    build_args.extend(
        [
            "-f",
            str(base_dir / dockerfile),
            "--build-arg",
            f"PYTHON_VERSION={python_version}",
            str(base_dir),
        ]
    )

    if not is_arm_mac:
        build_args.extend(["--build-arg", f"CUDA_VERSION={cuda_version}"])

    result = subprocess.run(build_args)
    if result.returncode != 0:
        raise click.ClickException("Failed to build base image")

    if push:
        click.echo("📤 Pushing base image...")
        for tag in image_tags:
            result = subprocess.run(["docker", "push", tag])
            if result.returncode != 0:
                raise click.ClickException(f"Failed to push {tag}")

        # Logout after push
        subprocess.run(["docker", "logout", "ghcr.io"], check=False)
