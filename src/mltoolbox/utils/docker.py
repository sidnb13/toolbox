from __future__ import annotations  # noqa: INP001

import os
import subprocess
from pathlib import Path
from typing import Optional

import click

from mltoolbox.utils.db import DB
from mltoolbox.utils.remote import update_env_file

from .helpers import RemoteConfig, remote_cmd


def check_docker_group(remote: RemoteConfig) -> None:
    """Check if Docker is properly configured and user is in docker group."""
    try:
        # Check if user is in docker group
        result = remote_cmd(remote, ["groups"], interactive=False)
        needs_group_setup = "docker" not in result.stdout

        # Check if we can use docker without sudo
        try:
            remote_cmd(remote, ["docker ps -q"], interactive=False)
            docker_working = True
        except Exception:
            docker_working = False

        if needs_group_setup or not docker_working:
            click.echo("🔧 Setting up Docker permissions...")

            # Add docker group if needed
            remote_cmd(remote, ["sudo groupadd -f docker"], interactive=True)

            # Add current user to docker group
            remote_cmd(remote, ["sudo usermod -aG docker $USER"], interactive=True)

            # Fix docker socket permissions
            remote_cmd(
                remote, ["sudo chmod 666 /var/run/docker.sock"], interactive=True
            )

            click.echo("✅ Docker permissions set up successfully")

            # Verify docker now works without sudo
            try:
                remote_cmd(
                    remote, ["docker ps -q"], interactive=False, reload_session=True
                )
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
            interactive=False,
        )

        if "needs_config" in result.stdout:
            click.echo("🔧 Configuring Docker cgroup driver...")
            remote_cmd(
                remote,
                [
                    "sudo mkdir -p /etc/docker && "
                    'echo \'{"exec-opts": ["native.cgroupdriver=cgroupfs"]}\' | sudo tee /etc/docker/daemon.json && '
                    "sudo systemctl restart docker"
                ],
                interactive=True,
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

    update_env_file(
        remote_config, project_name, env_updates, container_name=container_name
    )

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

    # Define critical environment variables
    critical_env = {
        "PROJECT_NAME": project_name,
        "CONTAINER_NAME": container_name,
    }

    # Start in detached mode with explicit env vars
    if remote_config:
        # For remote, prepend env vars to the command
        env_string = " ".join([f"{k}={v}" for k, v in critical_env.items()])
        base_cmd = f"{env_string} docker compose up -d"
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
