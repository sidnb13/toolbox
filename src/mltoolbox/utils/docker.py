import grp
import os
import pwd
import subprocess
import sys
from pathlib import Path
from typing import Optional

import click

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
    project_name: str, container_name: str, remote_config: Optional[RemoteConfig] = None
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

    cmd_wrap(
        [
            "docker",
            "compose",
            "up",
            "--attach",
            service_name,
            "--no-recreate",
            service_name,
        ],
        interactive=True,
    )
