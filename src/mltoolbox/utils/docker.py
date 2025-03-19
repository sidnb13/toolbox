from __future__ import annotations  # noqa: INP001

import os
import subprocess
from pathlib import Path
from typing import Optional

import click

from mltoolbox.utils.remote import update_env_file

from .helpers import RemoteConfig, remote_cmd


def check_docker_group(remote: RemoteConfig) -> None:
    """Check if Docker is properly configured and user is in docker group."""
    try:
        # First check if we need to add user to docker group
        result = remote_cmd(remote, ["groups"], interactive=True)
        needs_group_reload = "docker" not in result.stdout

        # Try using docker directly first - this might work if group is already active
        try:
            remote_cmd(remote, ["docker ps -q"], interactive=True)
            needs_sudo = False
        except Exception:  # If direct docker access fails, fall back to sudo
            needs_sudo = True
            remote_cmd(remote, ["sudo docker ps -q"], interactive=True)

        # Check if docker daemon.json has cgroupfs configured
        result = remote_cmd(
            remote,
            [
                "if [ -f /etc/docker/daemon.json ] && "
                '(grep -q \'"native.cgroupdriver":"cgroupfs"\' /etc/docker/daemon.json || '
                "grep -q '\"native.cgroupdriver=cgroupfs\"' /etc/docker/daemon.json); then "
                "echo 'docker_configured'; "
                "else "
                "echo 'docker_needs_config'; "
                "fi"
            ],
            interactive=True,
        )
        docker_needs_changes = "docker_needs_config" in result.stdout

        # Check if NVIDIA is configured
        result = remote_cmd(
            remote,
            [
                "if [ -f /lib/udev/rules.d/71-nvidia-dev-char.rules ] && "
                "command -v nvidia-ctk >/dev/null 2>&1; then "
                "echo 'nvidia_configured'; "
                "else "
                "echo 'nvidia_needs_config'; "
                "fi"
            ],
            interactive=True,
        )
        nvidia_needs_changes = "nvidia_needs_config" in result.stdout

        # Check for running containers
        result = remote_cmd(remote, ["sudo docker ps -q"], interactive=True)
        running_containers = (
            result.stdout.strip().split("\n") if result.stdout.strip() else []
        )

        # If any changes are needed, warn the user
        if docker_needs_changes or nvidia_needs_changes or needs_group_reload:
            if running_containers:
                click.echo(
                    f"⚠️ Found {len(running_containers)} running containers on the remote machine"
                )

            if docker_needs_changes:
                click.echo("⚠️ Docker cgroup driver needs to be updated to cgroupfs")

            if nvidia_needs_changes:
                click.echo("⚠️ NVIDIA device symlinks need to be configured")

            if running_containers:
                click.echo(
                    "⚠️ These changes may restart Docker and disrupt running containers"
                )

            # Only prompt if there are running containers
            if running_containers:
                choice = click.prompt(
                    "Choose an option",
                    type=click.Choice(["continue", "skip", "abort"]),
                    default="skip",
                )

                if choice == "abort":
                    raise click.Abort()
                elif choice == "skip":
                    click.echo("⏭️ Skipping Docker configuration")
                    return
            else:
                # No running containers, proceed without prompting
                click.echo(
                    "No running containers found. Proceeding with Docker configuration..."
                )
                choice = "continue"

            if docker_needs_changes:
                click.echo("🔧 Updating Docker cgroup driver configuration...")
                remote_cmd(
                    remote,
                    [
                        "sudo cp /etc/docker/daemon.json /etc/docker/daemon.json.bak 2>/dev/null || true && "
                        "sudo mkdir -p /etc/docker && "
                        'echo \'{"exec-opts": ["native.cgroupdriver=cgroupfs"]}\' | sudo tee /etc/docker/daemon.json'
                    ],
                    interactive=True,
                )

                # Stop Docker service
                click.echo("🛑 Stopping Docker service...")
                remote_cmd(remote, ["sudo systemctl stop docker"], interactive=True)

                # Wait for service to fully stop
                remote_cmd(remote, ["sleep 2"], interactive=True)

                # Start Docker service
                click.echo("🚀 Starting Docker service...")
                remote_cmd(remote, ["sudo systemctl start docker"], interactive=True)

                # Wait for service to be ready
                remote_cmd(remote, ["sleep 2"], interactive=True)

                # Verify Docker is running
                click.echo("🔍 Verifying Docker service status...")
                result = remote_cmd(
                    remote,
                    ["sudo systemctl --no-pager status docker"],
                    interactive=True,
                )
                if "active (running)" not in result.stdout:
                    raise click.ClickException("Failed to start Docker service")

            if nvidia_needs_changes:
                click.echo("🔧 Configuring NVIDIA GPU device symlinks...")
                remote_cmd(
                    remote,
                    [
                        "sudo apt-get update && "
                        "sudo apt-get install -y nvidia-container-toolkit && "
                        "sudo nvidia-ctk runtime configure --runtime=docker"
                    ],
                    interactive=True,
                )

                # Restart Docker service after NVIDIA changes
                click.echo("🔄 Restarting Docker service for NVIDIA changes...")
                remote_cmd(remote, ["sudo systemctl restart docker"], interactive=True)
                remote_cmd(remote, ["sleep 2"], interactive=True)

            click.echo("✅ Docker and NVIDIA configuration complete")

        if needs_group_reload:
            click.echo("🔧 Setting up Docker group and reloading group membership...")
            remote_cmd(remote, ["sudo groupadd -f docker"], interactive=True)
            remote_cmd(remote, ["sudo usermod -aG docker $USER"], interactive=True)

            # Reload group membership using newgrp
            click.echo("🔄 Reloading group membership...")
            remote_cmd(
                remote,
                ["sg docker -c 'groups && docker ps -q || echo docker-test-failed'"],
                interactive=True,
            )
            click.echo("✅ Docker group membership reloaded")

    except Exception as e:
        click.echo(f"❌ Docker check failed: {e}")
        raise


def verify_env_vars(remote: Optional[RemoteConfig] = None) -> dict:
    """Verify required environment variables and return all env vars as dict."""
    required_vars = ["GIT_NAME", "GITHUB_TOKEN", "GIT_EMAIL"]
    env_vars = {}

    if remote:
        # First get all env vars
        result = remote_cmd(
            remote, ["test -f .env && cat .env || echo ''"], interactive=False
        )

        # Parse env vars from the output
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env_vars[key] = value.strip("'\"")

        # Check if required vars exist
        missing_vars = [var for var in required_vars if var not in env_vars]
        if missing_vars:
            raise click.ClickException(
                f"Required environment variables not set on remote: {', '.join(missing_vars)}",
            )
    else:
        # Local environment check
        if not Path.cwd().joinpath(".env").exists():
            raise click.ClickException("❌ .env file not found")

        # Load env vars from the .env file
        with open(Path.cwd().joinpath(".env"), "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key] = value.strip("'\"")

        # Check also in current environment for required vars
        for var in required_vars:
            if var not in env_vars and os.getenv(var):
                env_vars[var] = os.getenv(var)

        # Check if required vars exist
        missing_vars = [var for var in required_vars if var not in env_vars]
        if missing_vars:
            raise click.ClickException(
                f"Required environment variables not set: {', '.join(missing_vars)}",
            )

    return env_vars


def get_image_digest(
    image: str,
    remote: bool = False,
    remote_config: Optional[RemoteConfig] = None,
) -> str:
    def docker_cmd(cmd):
        return (
            remote_cmd(remote_config, cmd)
            if remote_config
            else subprocess.run(cmd, capture_output=True, text=True, check=False)
        )

    if remote:
        git_name = os.getenv("GIT_NAME")
        github_token = os.getenv("GITHUB_TOKEN")
        docker_cmd(
            ["sudo", "docker", "login", "ghcr.io", "-u", git_name, "--password-stdin"],
        ).input = github_token.encode()

        result = docker_cmd(["sudo", "docker", "manifest", "inspect", image])
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if '"digest":' in line:
                    return line.split(":")[2].strip(' ",')
    else:
        result = docker_cmd(
            ["sudo", "docker", "image", "inspect", image, "--format={{index .Id}}"],
        )
        if result.returncode == 0:
            return result.stdout.strip().split(":")[1]
    return "none"


def start_container(
    project_name: str,
    container_name: str,
    remote_config: Optional[RemoteConfig] = None,
    build=False,
    host_ray_dashboard_port=None,
    host_ray_client_port=None,
) -> None:
    def cmd_wrap(cmd):
        if remote_config:
            return remote_cmd(remote_config, cmd, interactive=True)
        else:
            return subprocess.run(
                cmd,
                stdout=None,
                stderr=None,
                text=True,
                check=False,
            )

    def cmd_output(cmd):
        if remote_config:
            return remote_cmd(remote_config, cmd, interactive=False)
        else:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )

    # Check container status to determine if we need to rebuild
    container_name = container_name.lower()

    # Add sudo when using remote connections
    docker_cmd_prefix = ["sudo", "docker"] if remote_config else ["docker"]

    container_status_cmd = [
        *docker_cmd_prefix,
        "ps",
        "-a",
        "--filter",
        f"name={container_name}",
        "--format",
        "{{.Status}}",
    ]
    status_result = cmd_output(container_status_cmd)

    # Auto-enable build if container doesn't exist, is unhealthy, or has exited
    if not build:
        if status_result.returncode != 0 or not status_result.stdout.strip():
            click.echo(
                f"🔄 Container {container_name} not found. Will build from scratch."
            )
            build = True
        elif (
            "Exited" in status_result.stdout
            or "unhealthy" in status_result.stdout.lower()
        ):
            click.echo(
                f"🔄 Container {container_name} is in unhealthy state. Rebuilding..."
            )
            build = True
        elif "Restarting" in status_result.stdout:
            click.echo(
                f"🔄 Container {container_name} is in a restart loop. Rebuilding..."
            )
            build = True

    # Update the .env file with custom port mappings if specified
    if host_ray_dashboard_port or host_ray_client_port:
        env_updates = {}
        if host_ray_dashboard_port:
            env_updates["HOST_RAY_DASHBOARD_PORT"] = host_ray_dashboard_port
        if host_ray_client_port:
            env_updates["HOST_RAY_CLIENT_PORT"] = host_ray_client_port

        update_env_file(
            remote_config, project_name, env_updates, container_name=container_name
        )

    # Define critical environment variables
    critical_env = {
        "PROJECT_NAME": project_name,
        "CONTAINER_NAME": container_name,
    }

    # Start in detached mode with explicit env vars
    if remote_config:
        # For remote, prepend env vars to the command and use sudo for docker compose
        env_string = " ".join([f"{k}={v}" for k, v in critical_env.items()])
        base_cmd = f"{env_string} sudo docker compose up -d"
        if build:
            base_cmd += " --build"
        base_cmd += f" {container_name}"
        cmd_wrap([base_cmd])
    else:
        # For local, use environment parameter
        base_cmd = ["docker", "compose", "up", "-d"]
        if build:
            base_cmd.append("--build")
        base_cmd.append(container_name)

        env = os.environ.copy()
        env.update(critical_env)

        subprocess.run(
            base_cmd,
            env=env,
            stdout=None,
            stderr=None,
            text=True,
            check=False,
        )
