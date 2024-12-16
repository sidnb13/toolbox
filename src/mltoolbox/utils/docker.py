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
    container_name = project_name.lower()

    # Kill any existing SSH tunnels
    if os.path.exists("/tmp/remote_tunnel.pid"):
        subprocess.run(["pkill", "-F", "/tmp/remote_tunnel.pid"], check=False)
        os.remove("/tmp/remote_tunnel.pid")

    # Remove containers and network
    subprocess.run(["docker", "rm", "-f", container_name, "ray-head"], check=False)
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


def check_image_updates(project_name: str) -> bool:
    """Check if image needs updating"""
    click.echo("🔍 Checking for updates...")
    git_name = os.getenv("GIT_NAME")
    image = f"ghcr.io/{git_name}/{project_name}:latest"

    local_digest = get_image_digest(image)
    remote_digest = get_image_digest(image, remote=True)

    return local_digest != remote_digest


def start_container(project_name: str) -> None:
    """Start the development container"""
    click.echo("🚀 Launching container...")

    # Create network if it doesn't exist
    subprocess.run(["docker", "network", "create", "ray_network"], check=False)

    # Start container with docker compose
    result = subprocess.run(["docker", "compose", "up", "-d"])
    if result.returncode != 0:
        raise click.ClickException("Failed to start container")

    container_name = project_name.lower()
    if (
        subprocess.run(
            ["docker", "ps", "-q", "-f", f"name={container_name}"]
        ).returncode
        == 0
    ):
        click.echo("✅ Container started successfully!")

        # Show GPU info
        subprocess.run(["docker", "exec", container_name, "nvidia-smi", "--list-gpus"])

        # Connect to container
        click.echo("🔌 Connecting to container...")
        os.execvp("docker", ["docker", "exec", "-it", container_name, "/bin/bash"])
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
    if not git_name:
        raise click.ClickException("GIT_NAME environment variable not set")

    image_name = f"ghcr.io/{git_name}/ml-base:latest"

    # Check if running on ARM Mac
    is_arm_mac = platform.system() == "Darwin" and platform.machine() == "arm64"
    if is_arm_mac:
        click.echo("⚠️  Detected ARM Mac - cannot build CUDA image locally")
        if click.confirm("Would you like to pull the pre-built image instead?"):
            # Try to pull existing image
            result = subprocess.run(["docker", "pull", image_name])
            if result.returncode != 0:
                raise click.ClickException(
                    f"Failed to pull image. Please build this image on a Linux machine with NVIDIA GPU and push to {image_name}"
                )
            click.echo("✅ Successfully pulled base image")
            return
        else:
            click.echo("\nTo build this image:")
            click.echo(f"1. SSH into a Linux machine with NVIDIA GPU")
            click.echo(
                f"2. Run: mltoolbox init-base --cuda-version {cuda_version} --python-version {python_version} --push"
            )
            click.echo(f"3. The image will be pushed to: {image_name}")
            return

    click.echo(f"🏗️  Building base image: {image_name}")

    # Build the image
    result = subprocess.run(
        [
            "docker",
            "build",
            "-t",
            image_name,
            "--build-arg",
            f"CUDA_VERSION={cuda_version}",
            "--build-arg",
            f"PYTHON_VERSION={python_version}",
            str(base_dir),
        ]
    )

    if result.returncode != 0:
        raise click.ClickException("Failed to build base image")

    if push:
        click.echo("📤 Pushing base image...")
        result = subprocess.run(["docker", "push", image_name])
        if result.returncode != 0:
            raise click.ClickException("Failed to push base image")
