
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

import click
import paramiko


@dataclass
class RemoteConfig:
    host: str
    username: str
    ssh_key: Optional[str] = None
    working_dir: Optional[str] = None


def remote_cmd(
    config: RemoteConfig,
    command: list[str],
    interactive=False,
    use_working_dir=True,
) -> subprocess.CompletedProcess:
    """Execute command on remote host using paramiko SSH."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(
            hostname=config.host,
            username=config.username,
            timeout=10,
            look_for_keys=True,
            allow_agent=True,  # This is the key part - use the SSH agent
        )
        _, stdout, _ = ssh.exec_command("pwd")
        remote_cwd = stdout.read().decode().strip()

        # Prepare command string
        cmd_str = " && ".join(command) if isinstance(command, list) else command
        if config.working_dir and use_working_dir:
            full_cmd = f"mkdir -p {config.working_dir} && cd {config.working_dir} && {cmd_str}"
        else:
            full_cmd = cmd_str

        if interactive:
            # For interactive commands, use subprocess since paramiko doesn't handle interactive well
            ssh.close()
            return subprocess.run(
                ["ssh", f"{config.username}@{config.host}", full_cmd],
                stdin=sys.stdin,
                stdout=sys.stdout,
                stderr=sys.stderr,
                text=True, check=False,
            )

        # Execute command
        stdin, stdout, stderr = ssh.exec_command(full_cmd)
        exit_code = stdout.channel.recv_exit_status()

        # Get output
        output = stdout.read().decode()
        error = stderr.read().decode()

        if exit_code != 0:
            # Format error message
            error_sections = [
                "🔴 Remote Command Failed",
                "━━━━━━━━━━━━━━━━━━━━━━",
                "Context:",
                f"  Remote Directory: {remote_cwd}",
                f"  Working Directory: {config.working_dir}",
                "",
                "Connection:",
                f"  Host: {config.host}",
                f"  User: {config.username}",
                "",
                "Command:",
                f"  {full_cmd}",
                "",
                "Error Details:",
                f"  Exit Code: {exit_code}",
                f"  stderr: {error or 'None'}",
                f"  stdout: {output or 'None'}",
            ]
            raise click.ClickException("\n".join(error_sections))

        # Return CompletedProcess for compatibility
        return subprocess.CompletedProcess(
            args=full_cmd,
            returncode=exit_code,
            stdout=output,
            stderr=error,
        )

    except paramiko.SSHException as e:
        raise click.ClickException(f"SSH connection failed: {e!s}")
    except Exception as e:
        raise click.ClickException(f"Command failed: {e!s}")
    finally:
        ssh.close()
