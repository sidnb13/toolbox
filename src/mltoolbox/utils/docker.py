import grp
import os
import pwd
import subprocess
import sys
from pathlib import Path
from typing import Optional

import click
import pkg_resources

from .. import base
from .helpers import RemoteConfig, remote_cmd


def check_docker_group(remote: Optional[RemoteConfig] = None) -> None:
    if remote:
        try:
            remote_cmd(
                remote, ["groups | grep docker || sudo usermod -aG docker $USER"]
            )
        except subprocess.CalledProcessError:
            raise click.ClickException(
                "Failed to add user to docker group on remote host"
            )
    else:
        username = pwd.getpwuid(os.getuid()).pw_name
        try:
            if "docker" not in [
                g.gr_name for g in grp.getgrall() if username in g.gr_mem
            ]:
                subprocess.run(["sudo", "adduser", username, "docker"], check=True)
                os.execvp("sg", ["sg", "docker", "-c", f'"{" ".join(sys.argv)}"'])
        except subprocess.CalledProcessError:
            raise click.ClickException("Failed to add user to docker group")


def cleanup_containers(
    project_name: str, remote: Optional[RemoteConfig] = None
) -> None:
    container_names = [
        f"{project_name}-linux".lower(),
        "ray-head",
    ]

    def docker_cmd(cmd):
        return (
            remote_cmd(remote, cmd)
            if remote
            else subprocess.run(cmd, check=False, capture_output=True, text=True)
        )

    # First check which containers are running
    ps_result = docker_cmd(["docker", "ps"])
    if ps_result.returncode == 0:
        running_containers = ps_result.stdout.strip().split("\n")
    else:
        running_containers = []

    # Only remove containers that aren't running
    containers_removed = False
    for container in container_names:
        if container not in running_containers:
            result = docker_cmd(["docker", "rm", "-f", container])
            if result.returncode == 0:
                containers_removed = True
                click.echo(f"Removed stopped container: {container}")

    # Only remove the network if we removed containers and it exists
    if containers_removed:
        network_result = docker_cmd(["docker", "network", "ls", "--format={{.Name}}"])
        if network_result.returncode == 0 and "ray_network" in network_result.stdout:
            network_rm_result = docker_cmd(["docker", "network", "rm", "ray_network"])
            if network_rm_result.returncode == 0:
                click.echo("Removed ray_network")


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
                f"Required environment variables not set on remote: {', '.join(required_vars)}"
            )
    else:
        if not Path.cwd().joinpath(".env").exists():
            raise click.ClickException("❌ .env file not found")
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise click.ClickException(
                f"Required environment variables not set: {', '.join(missing_vars)}"
            )


def get_image_digest(
    image: str, remote: bool = False, remote_config: Optional[RemoteConfig] = None
) -> str:
    def docker_cmd(cmd):
        return (
            remote_cmd(remote_config, cmd)
            if remote_config
            else subprocess.run(cmd, capture_output=True, text=True)
        )

    if remote:
        git_name = os.getenv("GIT_NAME")
        github_token = os.getenv("GITHUB_TOKEN")
        docker_cmd(
            ["docker", "login", "ghcr.io", "-u", git_name, "--password-stdin"]
        ).input = github_token.encode()

        result = docker_cmd(["docker", "manifest", "inspect", image])
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if '"digest":' in line:
                    return line.split(":")[2].strip(' ",')
    else:
        result = docker_cmd(
            ["docker", "image", "inspect", image, "--format={{index .Id}}"]
        )
        if result.returncode == 0:
            return result.stdout.strip().split(":")[1]
    return "none"


def start_container(
    project_name: str, remote_config: Optional[RemoteConfig] = None
) -> None:
    def cmd_wrap(cmd, interactive=False):
        return (
            remote_cmd(remote_config, cmd, interactive=interactive)
            if remote_config
            else subprocess.run(
                cmd,
                stdout=None,  # Show output in real-time
                stderr=None,  # Show output in real-time
                text=True,
            )
            if not interactive
            else os.execvp(cmd[0], cmd)
        )

    service_name = project_name.lower()

    try:
        inspect_result = cmd_wrap(
            [
                "docker",
                "container",
                "inspect",
                "-f",
                "'{{.State.Running}}'",
                service_name,
            ],
        )
        if not isinstance(inspect_result, subprocess.CompletedProcess):
            inspect_result.returncode = inspect_result.wait()
    except Exception:
        inspect_result = type("CompletedProcess", (), {"returncode": 1, "stdout": ""})()

    if (
        inspect_result.returncode == 0
        and "true" in inspect_result.stdout.strip().lower()
    ):
        cmd_wrap(["docker", "exec", service_name, "nvidia-smi", "--list-gpus"])
        cmd_wrap(
            [
                "docker",
                "exec",
                "-it",
                "-w",
                f"/workspace/{project_name}",
                service_name,
                "/bin/bash",
            ],
            interactive=True,
        )
    else:
        result = cmd_wrap(
            [
                "docker",
                "compose",
                "up",
                "-d",
                service_name,
            ],
            interactive=True
        )

        if result.returncode != 0:
            cmd_wrap(["docker", "logs", service_name])
            raise click.ClickException("Failed to start container")

        cmd_wrap(
            [
                "docker",
                "exec",
                "-it",
                "-w",
                f"/workspace/{project_name}",
                service_name,
                "/bin/bash",
            ],
            interactive=True,
        )


def build_base_image(
    cuda_version: str,
    python_version: str,
    push: bool = False,
    remote: Optional[RemoteConfig] = None,
):
    """Build the base ML image locally or on a remote host"""
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

    # Get package version from pyproject.toml
    import tomli

    with open(Path(__file__).parent.parent.parent.parent / "pyproject.toml", "rb") as f:
        version = tomli.load(f)["project"]["version"]

    # Define image names with versioning
    base_name = f"ghcr.io/{git_name}/ml-base"
    image_tags = [
        f"{base_name}:{version}",  # Versioned platform tag
        f"{base_name}:latest",  # Latest platform tag
    ]

    def docker_cmd(cmd, input_data=None):
        if remote:
            return remote_cmd(remote, cmd)
        else:
            return subprocess.run(
                cmd,
                input=input_data,
                stdout=None,  # Show output in real-time
                stderr=None,  # Show output in real-time
                text=True,
            )

    # Try to pull latest image first
    click.echo("🔄 Checking for existing image...")
    pull_result = docker_cmd(["docker", "pull", f"{base_name}:latest"])
    if pull_result.returncode == 0:
        click.echo("✅ Found existing image, will use as cache")
    else:
        click.echo("⚠️  No existing image found, building from scratch")

    # Login if pushing
    if push:
        click.echo("🔑 Logging in to GitHub Container Registry...")
        login_result = docker_cmd(
            ["docker", "login", "ghcr.io", "-u", git_name, "--password-stdin"],
            github_token.encode() if not remote else None,
        )
        if login_result.returncode != 0:
            raise click.ClickException(
                f"Failed to login to ghcr.io: {login_result.stderr}"
            )

    # Build the image
    click.echo(f"🏗️  Building base image v{version}")

    build_args = [
        "docker",
        "build",
        "--pull",  # Always check for updated base images
        "--cache-from",
        f"{base_name}:latest",
    ]

    # Add tags
    for tag in image_tags:
        build_args.extend(["-t", tag])

    # Add build args
    build_args.extend(
        [
            "-f",
            str(base_dir / "Dockerfile"),
            "--build-arg",
            f"PYTHON_VERSION={python_version}",
            str(base_dir),
        ]
    )

    build_args.extend(["--build-arg", f"CUDA_VERSION={cuda_version}"])

    result = docker_cmd(build_args)
    if result.returncode != 0:
        raise click.ClickException("Failed to build base image")

    if push:
        click.echo("📤 Pushing base image...")
        for tag in image_tags:
            result = docker_cmd(["docker", "push", tag])
            if result.returncode != 0:
                raise click.ClickException(f"Failed to push {tag}")

        # Logout after push
        docker_cmd(["docker", "logout", "ghcr.io"])
