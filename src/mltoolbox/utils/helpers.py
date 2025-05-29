import subprocess
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
    dryrun: bool = False,
) -> subprocess.CompletedProcess:
    """Execute command on remote host using paramiko SSH."""
    logger = get_logger()
    if dryrun:
        import time as _time

        with logger.live_output(f"Remote Command on {config.host} [DRY RUN]") as output:
            for i in range(8):
                output.write(f"Simulated remote output line {i + 1}\n")
                _time.sleep(0.1)
        logger.success(f"[DRY RUN] Remote command simulated: {' '.join(command)}")
        return subprocess.CompletedProcess(command, 0, "Simulated remote stdout", "")
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
        start_time = time.time()
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
                command_type = "Docker Command" if is_docker_command else "Command"
                with logger.live_output(
                    f"Remote {command_type} on {config.host}"
                ) as live_output:
                    while True:
                        data_received = False
                        if channel.recv_ready():
                            data = channel.recv(4096).decode("utf-8", errors="ignore")
                            if data:
                                live_output.write(data)
                                output.append(data)
                                data_received = True
                        if channel.recv_stderr_ready():
                            data = channel.recv_stderr(4096).decode(
                                "utf-8", errors="ignore"
                            )
                            if data:
                                live_output.write(data)
                                error.append(data)
                                data_received = True
                        if channel.exit_status_ready():
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
                        if not data_received:
                            time.sleep(0.05)
            else:
                while True:
                    if channel.recv_ready():
                        data = channel.recv(1024).decode("utf-8", errors="ignore")
                        output.append(data)
                    if channel.recv_stderr_ready():
                        data = channel.recv_stderr(1024).decode(
                            "utf-8", errors="ignore"
                        )
                        error.append(data)
                    if channel.exit_status_ready():
                        break
                    time.sleep(0.01)
            exit_code = channel.recv_exit_status()
            output_str = "".join(output)
            error_str = "".join(error)
        duration = time.time() - start_time
        if exit_code != 0:
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
            if logger.logger.level <= 10:  # DEBUG level
                stack_trace = "".join(traceback.format_stack())
                error_content.append("")
                error_content.append("STACK TRACE")
                error_content.append(stack_trace)
            with logger.panel_output(
                "Remote Command Failed",
                subtitle=f"Exit code: {exit_code}",
                status="failed",
                exit_code=exit_code,
                duration=duration,
            ) as panel:
                panel.write("\n".join(error_content))
            raise click.ClickException("Remote command execution failed")
        # Success panel for non-live commands
        if not (is_docker_command or is_verbose_command):
            with logger.panel_output(
                "Remote Command Output",
                subtitle=f"Exit code: {exit_code}",
                status="success",
                exit_code=exit_code,
                duration=duration,
            ) as panel:
                if output_str:
                    panel.write(output_str)
                if error_str:
                    panel.write("\nSTDERR:\n" + error_str)
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
