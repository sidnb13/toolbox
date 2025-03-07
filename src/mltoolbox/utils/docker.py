from __future__ import annotations  # noqa: INP001

import grp
import os
import pwd
import subprocess
import sys
from pathlib import Path
from typing import Optional

import click

from .helpers import RemoteConfig, remote_cmd


def check_docker_group(remote: RemoteConfig) -> None:
    """Check if Docker is properly configured and user is in docker group."""
    try:
        # First check if we need to add user to docker group
        result = remote_cmd(remote, ["groups"], interactive=True)
        needs_group_reload = "docker" not in result.stdout
        # Check if docker is running by listing containers
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

            # If any changes are needed, warn the user
            if docker_needs_changes or nvidia_needs_changes:
                if running_containers:
                    click.echo(
                        f"⚠️ Found {len(running_containers)} running containers on the remote machine"
                    )
                    click.echo(
                        "⚠️ These changes may restart Docker and disrupt running containers"
                    )

                    # Only prompt if there are running containers
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
                            # Check if docker daemon.json exists
                            "if [ -f /etc/docker/daemon.json ]; then "
                            # If it exists, check if it has JSON content
                            "if grep -q '{' /etc/docker/daemon.json; then "
                            # If it has JSON content but no cgroupfs setting, add it
                            "if ! grep -q 'cgroupfs' /etc/docker/daemon.json; then "
                            "sudo cp /etc/docker/daemon.json /etc/docker/daemon.json.bak && "
                            'sudo sed -i \'s/{/{"exec-opts": ["native.cgroupdriver=cgroupfs"], /\' /etc/docker/daemon.json; '
                            "fi; "
                            # If it doesn't exist or is empty, create it
                            "else "
                            'echo \'{"exec-opts": ["native.cgroupdriver=cgroupfs"]}\' | sudo tee /etc/docker/daemon.json; '
                            "fi; "
                            "else "
                            "sudo mkdir -p /etc/docker && "
                            'echo \'{"exec-opts": ["native.cgroupdriver=cgroupfs"]}\' | sudo tee /etc/docker/daemon.json; '
                            "fi"
                        ],
                        interactive=True,
                    )

                    # Modified docker group setup with shell reload
                    click.echo("🔧 Setting up Docker group...")
                    remote_cmd(remote, ["sudo -n groupadd -f docker"], interactive=True)
                    remote_cmd(
                        remote, ["sudo -n usermod -aG docker $USER"], interactive=True
                    )

                    click.echo("🔄 Restarting Docker daemon...")
                    remote_cmd(
                        remote, ["sudo systemctl restart docker"], interactive=True
                    )

                if nvidia_needs_changes:
                    click.echo("🔧 Configuring NVIDIA GPU device symlinks...")
                    # Setup NVIDIA device symlinks
                    remote_cmd(
                        remote,
                        [
                            "sudo apt-get update && "
                            "sudo apt-get install -y nvidia-container-toolkit && "
                            "sudo nvidia-ctk runtime configure --runtime=docker && "
                            "sudo systemctl restart docker"
                        ],
                        interactive=True,
                    )

                click.echo("✅ Docker and NVIDIA configuration complete")

            if needs_group_reload:
                click.echo("🔧 Setting up Docker group and reloading shell session...")
                remote_cmd(remote, ["sudo -n groupadd -f docker"], interactive=True)
                remote_cmd(
                    remote, ["sudo -n usermod -aG docker $USER"], interactive=True
                )

                # Force a shell reload to apply group changes
                remote_cmd(
                    remote,
                    ["newgrp docker << EOF\nexit\nEOF"],
                    interactive=True,
                )
    except Exception as e:
        click.echo(f"❌ Docker check failed: {e}")
        raise


def verify_env_vars(remote: Optional[RemoteConfig] = None) -> None:
    required_vars = ["GIT_NAME", "GITHUB_TOKEN", "GIT_EMAIL"]

    if remote:
        cmd = [
            f'test -f .env && source .env && [ ! -z "${var}" ]' for var in required_vars
        ]
        try:
            remote_cmd(remote, [" && ".join(cmd)])
        except subprocess.CalledProcessError:
            raise click.ClickException(
                f"Required environment variables not set on remote: {', '.join(required_vars)}",
            )
    else:
        if not Path.cwd().joinpath(".env").exists():
            raise click.ClickException("❌ .env file not found")
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise click.ClickException(
                f"Required environment variables not set: {', '.join(missing_vars)}",
            )


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
    service_name = project_name.lower()
    container_status_cmd = [
        "docker",
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

        from mltoolbox.utils.remote import update_env_file

        update_env_file(remote_config, project_name, env_updates)

    service_name = project_name.lower()

    # Start in detached mode
    base_cmd = ["docker", "compose", "up", "-d"]
    if build:
        base_cmd.append("--build")
    base_cmd.append(service_name)

    cmd_wrap(base_cmd)
