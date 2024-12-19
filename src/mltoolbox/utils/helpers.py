import os
import subprocess
from dataclasses import dataclass
from typing import Optional

import click


@dataclass
class RemoteConfig:
    host: str
    username: str
    ssh_key: Optional[str] = None
    working_dir: Optional[str] = None


def remote_cmd(
    config: RemoteConfig, command: list[str], interactive: bool = False
) -> subprocess.CompletedProcess:
    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no"]
    if interactive:
        ssh_cmd.append("-t")
    # Add SSH key if specified
    if config.ssh_key:
        ssh_cmd.extend(["-i", config.ssh_key])
    # Build the remote command with working directory if specified
    remote_command = []
    if config.working_dir:
        remote_command.extend([f"cd {config.working_dir} &&"])
    remote_command.extend(command)
    ssh_cmd.extend([f"{config.username}@{config.host}", " ".join(remote_command)])

    try:
        # Get remote working directory before running main command
        pwd_cmd = ["ssh"]
        if config.ssh_key:
            pwd_cmd.extend(["-i", config.ssh_key])
        pwd_cmd.extend([f"{config.username}@{config.host}", "pwd"])

        try:
            remote_cwd = subprocess.run(
                pwd_cmd, check=True, capture_output=True, text=True
            ).stdout.strip()
        except subprocess.CalledProcessError:
            remote_cwd = "unknown"

        # Run the actual command
        if not interactive:
            return subprocess.run(ssh_cmd, check=True, capture_output=True, text=True)
        else:
            return os.execvp("ssh", ssh_cmd)
    except subprocess.CalledProcessError as e:
        import traceback
        from pathlib import Path

        # Get additional context
        local_cwd = Path.cwd()
        project_name = local_cwd.name

        # Format the error message with more context
        error_sections = [
            "🔴 Remote Command Failed",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "Context:",
            f"  Project: {project_name}",
            f"  Local Directory: {local_cwd}",
            f"  Remote Directory: {remote_cwd}",
            "",
            "Connection:",
            f"  Host: {config.host}",
            f"  User: {config.username}",
            f"  SSH Key: {config.ssh_key or 'default'}",
            "",
            "Command:",
            f"  Local: {' '.join(ssh_cmd)}",
            f"  Remote: {' '.join(command)}",
            "",
            "Error Details:",
            f"  Exit Code: {e.returncode}",
            f"  stderr: {e.stderr.strip() if e.stderr else 'None'}",
            f"  stdout: {e.stdout.strip() if e.stdout else 'None'}",
            "",
            "Traceback:",
            "".join(traceback.format_stack()),
        ]

        raise click.ClickException("\n".join(error_sections)) from e
