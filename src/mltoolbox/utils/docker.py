from __future__ import annotations  # noqa: INP001

import os
import subprocess
from pathlib import Path
from re import A
from typing import Optional

import click

from mltoolbox.utils.db import DB
from mltoolbox.utils.remote import update_env_file, verify_env_vars

from .helpers import RemoteConfig, remote_cmd


def check_docker_group(remote: RemoteConfig) -> None:
    """Check if Docker is properly configured and user is in docker group."""
    try:
        # Check if user is in docker group
        result = remote_cmd(remote, ["groups"])
        needs_group_setup = "docker" not in result.stdout

        # Check if we can use docker without sudo
        try:
            remote_cmd(remote, ["docker ps -q"])
            docker_working = True
        except Exception:
            docker_working = False

        if needs_group_setup or not docker_working:
            click.echo("🔧 Setting up Docker permissions...")

            # Add docker group if needed
            remote_cmd(remote, ["sudo groupadd -f docker"])

            # Add current user to docker group
            remote_cmd(remote, ["sudo usermod -aG docker $USER"])

            # Fix docker socket permissions
            remote_cmd(remote, ["sudo chmod 666 /var/run/docker.sock"])

            click.echo("✅ Docker permissions set up successfully")

            # Verify docker now works without sudo
            try:
                remote_cmd(remote, ["docker ps -q"], reload_session=True)
                click.echo("✅ Docker now works without sudo")
            except Exception:
                click.echo("⚠️ Docker still requires sudo - continuing with sudo")

        # Check if docker daemon uses the right cgroup driver
        result = remote_cmd(
            remote,
            [
                "if [ -f /etc/docker/daemon.json ] && "
                'grep -q \'"native.cgroupdriver":"cgroupfs"\' /etc/docker/daemon.json; then '
                "echo 'configured'; else echo 'needs_config'; fi"
            ],
        )

        if "needs_config" in result.stdout:
            # Check for running containers before modifying daemon config
            running_containers = (
                remote_cmd(
                    remote, ["docker ps --format '{{.Names}}' | wc -l"]
                ).stdout.strip()
                or 0
            )

            if int(running_containers) > 0:
                # List running containers
                containers = remote_cmd(
                    remote, ["docker ps --format '{{.Names}}'"]
                ).stdout.strip()

                click.echo(
                    f"⚠️ WARNING: {running_containers} containers currently running:"
                )
                click.echo(containers)
                click.echo(
                    "⚠️ Changing Docker daemon configuration will restart Docker and KILL all running containers!"
                )

                if not click.confirm(
                    "Do you want to continue and modify Docker configuration?",
                    default=False,
                ):
                    click.echo(
                        "❌ Docker configuration skipped. Some features may not work correctly."
                    )
                    return

                click.echo("🔧 Configuring Docker cgroup driver...")
                remote_cmd(
                    remote,
                    [
                        "sudo mkdir -p /etc/docker && "
                        'echo \'{"exec-opts": ["native.cgroupdriver=cgroupfs"]}\' | sudo tee /etc/docker/daemon.json && '
                        "sudo systemctl restart docker"
                    ],
                )
                click.echo("✅ Docker cgroup driver configured")

        # Verify Docker is working
        click.echo("✅ Docker is properly configured")

    except Exception as e:
        click.echo(f"❌ Docker configuration check failed: {e}")
        raise


def find_available_port(remote_config: Optional[RemoteConfig], start_port: int) -> int:
    """Find an available port starting from the given port."""
    import socket

    def is_port_in_use(port):
        if remote_config:
            # Check on remote host
            cmd = f"nc -z 127.0.0.1 {port} && echo 'In use' || echo 'Available'"
            result = remote_cmd(remote_config, [cmd], interactive=False)
            return "In use" in result.stdout
        else:
            # Check locally
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                return s.connect_ex(("127.0.0.1", port)) == 0

    port = start_port
    while is_port_in_use(port):
        port += 1

    return port


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
            ["docker", "login", "ghcr.io", "-u", git_name, "--password-stdin"],
        ).input = github_token.encode()

        result = docker_cmd(["docker", "manifest", "inspect", image])
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if '"digest":' in line:
                    return line.split(":")[2].strip(' ",')
    else:
        result = docker_cmd(
            ["docker", "image", "inspect", image, "--format={{index .Id}}"],
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
    branch_name: Optional[str] = None,
    network_mode: Optional[str] = None,  # Add this parameter
) -> None:
    def cmd_wrap(cmd):
        if remote_config:
            return remote_cmd(remote_config, cmd)
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
            return remote_cmd(remote_config, cmd)
        else:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )

    # Check container status to determine if we need to rebuild
    container_name = container_name.lower()

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

    # Only need to worry about Ray dashboard port
    if not host_ray_dashboard_port:
        host_ray_dashboard_port = find_available_port(remote_config, 8265)

    # Only update the Ray dashboard port in the env file
    env_updates = {
        "RAY_DASHBOARD_PORT": host_ray_dashboard_port,
    }

    env_vars = update_env_file(remote_config, project_name, env_updates)

    # Store only dashboard port in database
    if remote_config:
        db = DB()
        db.upsert_remote(
            username=remote_config.username,
            host=remote_config.host,
            project_name=project_name,
            container_name=container_name,
            port_mappings={
                "ray_dashboard": host_ray_dashboard_port,
            },
        )

    service_name = (
        container_name.replace("-" + branch_name, "") if branch_name else container_name
    )

    # Start in detached mode with explicit env vars
    if remote_config:
        # For remote, prepend env vars to the command
        env_string = " ".join([f"{k}={v}" for k, v in env_vars.items()])
        base_cmd = f"{env_string} docker compose up -d"
        if build:
            base_cmd += " --build"

        if network_mode:
            base_cmd += f" --network {network_mode}"

        base_cmd += f" {service_name}"
        cmd_wrap([base_cmd])
    else:
        # For local, use environment parameter
        base_cmd = ["docker", "compose", "up", "-d"]
        if build:
            base_cmd.append("--build")
        base_cmd.append(service_name)

        if network_mode:
            base_cmd.extend(["--network", network_mode])

        subprocess.run(
            base_cmd,
            env=env_vars,
            stdout=None,
            stderr=None,
            text=True,
            check=False,
        )
