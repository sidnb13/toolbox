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

    click.echo(f"🔄 Executing remote command on {config.host}")
    click.echo(f"Command: {command}")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        click.echo(f"Connecting to {config.host}...")
        ssh.connect(
            hostname=config.host,
            username=config.username,
            timeout=10,
            look_for_keys=True,
            allow_agent=True,
            banner_timeout=60,  # Give more time for initial connection
        )
        click.echo("✅ SSH connection established")
        _, stdout, _ = ssh.exec_command("pwd")
        remote_cwd = stdout.read().decode().strip()

        # Prepare command string
        cmd_str = " ".join(command) if isinstance(command, list) else command
        if config.working_dir and use_working_dir:
            full_cmd = (
                f"mkdir -p {config.working_dir} && cd {config.working_dir} && {cmd_str}"
            )
        else:
            full_cmd = cmd_str

        # Execute command with PTY
        transport = ssh.get_transport()
        channel = transport.open_session()
        channel.get_pty()
        channel.exec_command(full_cmd)

        output = []
        error = []

        while True:
            # Read stdout
            if channel.recv_ready():
                data = channel.recv(1024).decode()
                sys.stdout.write(data)
                sys.stdout.flush()
                output.append(data)

            # Read stderr
            if channel.recv_stderr_ready():
                data = channel.recv_stderr(1024).decode()
                sys.stderr.write(data)
                sys.stderr.flush()
                error.append(data)

            # Check if the channel is closed
            if channel.exit_status_ready():
                break

        exit_code = channel.recv_exit_status()
        output_str = "".join(output)
        error_str = "".join(error)

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
                f"  stderr: {error_str or 'None'}",
                f"  stdout: {output_str or 'None'}",
            ]
            raise click.ClickException("\n".join(error_sections))

        # Return CompletedProcess for compatibility
        return subprocess.CompletedProcess(
            args=full_cmd,
            returncode=exit_code,
            stdout=output_str,
            stderr=error_str,
        )

    except paramiko.SSHException as e:
        click.echo(f"❌ SSH connection failed: {str(e)}")
        raise
    except Exception as e:
        raise click.ClickException(f"Command failed: {e!s}")
    finally:
        ssh.close()
