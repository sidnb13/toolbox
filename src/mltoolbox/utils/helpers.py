import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

import click
import paramiko

from mltoolbox.utils.logger import get_logger
from mltoolbox.utils.session import session_manager


@dataclass
class RemoteConfig:
    host: str
    username: str
    ssh_key: str | None = None
    working_dir: str | None = None


def get_ssh_config(
    alias: str,
    config_path: Path = "~/.config/mltoolbox/ssh/config",
) -> dict:
    """Parse SSH config and return settings for the given alias."""
    ssh_config = paramiko.config.SSHConfig()

    # Use custom config path if provided, otherwise fallback to default
    config_paths = [
        Path(config_path).expanduser(),
        Path.home() / ".ssh" / "config",
    ]

    # Try reading from config files in order
    config_found = False
    for path in config_paths:
        if path.exists():
            with open(path) as f:
                ssh_config.parse(f)
            config_found = True

    if not config_found:
        raise click.ClickException("No SSH config file found")

    # Get the specific config for this host alias
    host_config = ssh_config.lookup(alias)
    return host_config


def remote_cmd(
    config: RemoteConfig,
    command: list[str],
    use_working_dir=True,
    reload_session=False,
) -> subprocess.CompletedProcess:
    """Execute command on remote host using paramiko SSH."""
    logger = get_logger()
    # Parse SSH config if the host looks like an alias
    ssh_config = get_ssh_config(config.host)
    actual_hostname = ssh_config.get("hostname", config.host)
    actual_username = ssh_config.get("user", config.username)
    identity_file = ssh_config.get("identityfile", [None])[0]

    # Only show command details in debug mode
    if logger.logger.level <= 10:  # DEBUG level
        logger.debug(f"Executing remote command: {command}")
        logger.debug(f"Target host: {config.host}")

    connect_kwargs = {
        "timeout": 10,
        "look_for_keys": True,
        "allow_agent": True,
        "banner_timeout": 60,
    }

    if identity_file:
        connect_kwargs["key_filename"] = identity_file

    try:
        with logger.spinner(f"Executing command on {config.host}"):
            if reload_session:
                ssh = session_manager.reload_session(actual_hostname, actual_username)
            else:
                ssh = session_manager.get_session(
                    actual_hostname,
                    actual_username,
                    **connect_kwargs,
                )

            _, stdout, _ = ssh.exec_command("pwd")
            remote_cwd = stdout.read().decode().strip()

            # Prepare command string
            cmd_str = " ".join(command) if isinstance(command, list) else command
            if config.working_dir and use_working_dir:
                full_cmd = f"mkdir -p {config.working_dir} && cd {config.working_dir} && {cmd_str}"
            else:
                full_cmd = cmd_str

            # Execute command with PTY
            transport = ssh.get_transport()
            channel = transport.open_session()
            channel.get_pty()
            channel.exec_command(full_cmd)

            output = []
            error = []

            # Determine if this looks like a Docker command that needs contained output
            docker_keywords = [
                "docker build",
                "docker compose build",
                "docker-compose build",
                "docker compose up",
                "docker-compose up",
                "docker pull",
                "docker push",
                "docker run",
                "docker system prune",
            ]
            is_docker_command = any(
                keyword in cmd_str.lower() for keyword in docker_keywords
            )

            # Also check for long-running or verbose commands that benefit from contained output
            verbose_keywords = [
                "rsync",
                "wget",
                "curl",
                "pip install",
                "apt install",
                "yum install",
            ]
            is_verbose_command = any(
                keyword in cmd_str.lower() for keyword in verbose_keywords
            )

            if is_docker_command or is_verbose_command:
                # For Docker and other verbose commands, use contained output
                command_type = "Docker Command" if is_docker_command else "Command"
                with logger.live_output(
                    f"Remote {command_type} on {config.host}"
                ) as live_output:
                    while True:
                        data_received = False

                        # Read stdout in larger chunks
                        if channel.recv_ready():
                            data = channel.recv(4096).decode("utf-8", errors="ignore")
                            if data:
                                live_output.write(data)
                                output.append(data)
                                data_received = True

                        # Read stderr in larger chunks
                        if channel.recv_stderr_ready():
                            data = channel.recv_stderr(4096).decode(
                                "utf-8", errors="ignore"
                            )
                            if data:
                                live_output.write(data)
                                error.append(data)
                                data_received = True

                        # Check if the channel is closed
                        if channel.exit_status_ready():
                            # Read any remaining data
                            while channel.recv_ready():
                                data = channel.recv(4096).decode(
                                    "utf-8", errors="ignore"
                                )
                                if data:
                                    live_output.write(data)
                                    output.append(data)
                            while channel.recv_stderr_ready():
                                data = channel.recv_stderr(4096).decode(
                                    "utf-8", errors="ignore"
                                )
                                if data:
                                    live_output.write(data)
                                    error.append(data)
                            break

                        # Only sleep if no data was received to avoid delays
                        if not data_received:
                            time.sleep(0.05)
            else:
                # For simple commands, use direct output
                while True:
                    # Read stdout
                    if channel.recv_ready():
                        data = channel.recv(1024).decode("utf-8", errors="ignore")
                        sys.stdout.write(data)
                        sys.stdout.flush()
                        output.append(data)

                    # Read stderr
                    if channel.recv_stderr_ready():
                        data = channel.recv_stderr(1024).decode(
                            "utf-8", errors="ignore"
                        )
                        sys.stderr.write(data)
                        sys.stderr.flush()
                        error.append(data)

                    # Check if the channel is closed
                    if channel.exit_status_ready():
                        break

                    # Small sleep to prevent busy waiting
                    time.sleep(0.01)

            exit_code = channel.recv_exit_status()
            output_str = "".join(output)
            error_str = "".join(error)

        if exit_code != 0:
            # Create clean error modal without emojis
            error_content = []
            error_content.append("CONTEXT")
            error_content.append(f"Remote Directory: {remote_cwd}")
            error_content.append(f"Working Directory: {config.working_dir or 'None'}")
            error_content.append("")
            error_content.append("CONNECTION")
            error_content.append(f"Host: {actual_hostname}")
            error_content.append(f"User: {actual_username}")
            error_content.append("")
            error_content.append("COMMAND")
            error_content.append(f"{full_cmd}")
            error_content.append("")
            error_content.append("ERROR DETAILS")
            error_content.append(f"Exit Code: {exit_code}")
            if error_str:
                error_content.append(f"stderr: {error_str}")
            if output_str:
                error_content.append(f"stdout: {output_str}")

            # Only include stack trace in debug mode
            if logger.logger.level <= 10:  # DEBUG level
                stack_trace = "".join(traceback.format_stack())
                error_content.append("")
                error_content.append("STACK TRACE")
                error_content.append(stack_trace)

            with logger.panel_output(
                "Remote Command Failed", subtitle=f"Exit code: {exit_code}"
            ) as panel:
                panel.write("\n".join(error_content))

            raise click.ClickException("Remote command execution failed")

        # Return CompletedProcess for compatibility
        return subprocess.CompletedProcess(
            args=full_cmd,
            returncode=exit_code,
            stdout=output_str,
            stderr=error_str,
        )

    except paramiko.SSHException as e:
        with logger.panel_output(
            "SSH Connection Failed", subtitle="Connection Error"
        ) as panel:
            panel.write(f"Failed to establish SSH connection: {str(e)}")
        raise click.ClickException("SSH connection failed")
    except Exception as e:
        with logger.panel_output(
            "Command Execution Failed", subtitle="Unexpected Error"
        ) as panel:
            panel.write(f"An unexpected error occurred: {str(e)}")
        raise click.ClickException("Command execution failed")
