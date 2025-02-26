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


def check_docker_group(remote: RemoteConfig | None = None) -> None:
    """Check if Docker and NVIDIA are properly set up on host."""
    if remote:
        try:
            # Try a simple docker command first
            remote_cmd(remote, ["docker ps"], use_working_dir=False)
            click.echo("✅ Docker already set up")
            return
        except Exception:
            # If that fails, do the full setup
            click.echo("🔧 Setting up Docker and NVIDIA...")
            try:
                # Setup docker group
                remote_cmd(
                    remote,
                    [
                        "if ! groups | grep -q docker; then "
                        "sudo groupadd -f docker && "
                        "sudo usermod -aG docker $USER; "
                        "fi"
                    ],
                    interactive=True,
                )

                # Configure NVIDIA runtime (only once)
                remote_cmd(
                    remote,
                    [
                        # Check if NVIDIA is already configured
                        "if ! grep -q 'no-cgroups = false' /etc/nvidia-container-runtime/config.toml; then "
                        "sudo sh -c 'echo \"no-cgroups = false\" >> /etc/nvidia-container-runtime/config.toml' && "
                        # Set cgroupfs as cgroup driver
                        "if [ ! -f /etc/docker/daemon.json ]; then "
                        'echo \'{"exec-opts": ["native.cgroupdriver=cgroupfs"]}\' | sudo tee /etc/docker/daemon.json; '
                        "elif ! grep -q 'cgroupfs' /etc/docker/daemon.json; then "
                        "sudo sed -i 's/systemd/cgroupfs/g' /etc/docker/daemon.json; "
                        "fi && "
                        # Reload everything
                        "sudo systemctl daemon-reload && "
                        "sudo systemctl restart nvidia-persistenced && "
                        "sudo systemctl restart docker && "
                        "sudo rmmod nvidia_uvm nvidia_drm nvidia_modeset nvidia || true && "
                        "sudo modprobe nvidia && "
                        "sudo modprobe nvidia_uvm; "
                        "fi"
                    ],
                    interactive=True,
                )
                click.echo("✅ Docker and NVIDIA setup complete")
            except Exception as e:
                raise click.ClickException(f"Failed to setup docker group: {e}")
    else:
        # Local docker group check remains the same
        username = pwd.getpwuid(os.getuid()).pw_name
        try:
            if "docker" not in [
                g.gr_name for g in grp.getgrall() if username in g.gr_mem
            ]:
                subprocess.run(
                    ["sudo", "usermod", "-aG", "docker", username],
                    check=True,
                    capture_output=True,
                )
                click.echo("Added user to docker group. Please logout and login again.")
                sys.exit(0)
        except subprocess.CalledProcessError as e:
            raise click.ClickException(f"Failed to add user to docker group: {e}")


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
) -> None:
    def cmd_wrap(cmd):
        return (
            remote_cmd(remote_config, cmd, interactive=True)
            if remote_config
            else subprocess.run(
                cmd,
                stdout=None,  # Show output in real-time
                stderr=None,  # Show output in real-time
                text=True,
                check=False,
            )
        )

    service_name = project_name.lower()

    # # Start Ray head node using ray compose file
    # ray_cmd = [
    #     "docker",
    #     "compose",
    #     "-f",
    #     "docker-compose-ray.yml",
    #     "up",
    #     "-d",
    #     "--no-recreate",
    #     "ray-head",
    # ]
    # cmd_wrap(ray_cmd, interactive=True)

    # Start in detached mode
    base_cmd = ["sudo", "docker", "compose", "up", "-d"]
    if build:
        base_cmd.append("--build")
    base_cmd.append(service_name)
    
    cmd_wrap(base_cmd)
