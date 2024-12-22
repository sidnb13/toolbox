import subprocess
import sys
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
    config: RemoteConfig,
    command: list[str],
    interactive: bool = False,
    use_working_dir=True,
) -> subprocess.CompletedProcess:
    ssh_command = ["ssh"]
    if config.ssh_key:
        ssh_command.extend(["-i", config.ssh_key])

    # Force TTY allocation to get proper interactive output
    ssh_command.extend(["-tt"])

    working_dir = (
        f"cd {config.working_dir} &&" if config.working_dir and use_working_dir else ""
    )
    full_command = ssh_command + [
        f"{config.username}@{config.host}",
        f"{working_dir} {' '.join(command)}",
    ]

    try:
        # get the cwd on remote
        remote_cwd = subprocess.run(
            ssh_command + [f"{config.username}@{config.host}", "pwd"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        if interactive:
            # For interactive sessions, use Popen without pipe redirection
            return subprocess.run(
                full_command,
                stdin=sys.stdin,
                stdout=sys.stdout,
                stderr=sys.stderr,
                text=True,
            )
        else:
            return subprocess.run(
                full_command,
                check=True,
                capture_output=True,
                text=True,
            )
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
            f"  Local: {' '.join(full_command)}",
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
