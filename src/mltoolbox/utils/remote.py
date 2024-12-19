import os
import subprocess
import time
from pathlib import Path

import click

from .helpers import RemoteConfig, remote_cmd


def check_tunnel_active(ports=[8765, 6380, 10001]) -> bool:
    """Check if SSH tunnel is active and working"""
    try:
        for port in ports:
            result = subprocess.run(
                ["lsof", "-i", f":{port}"], capture_output=True, text=True
            )
            if "LISTEN" not in result.stdout:
                return False
        return True
    except subprocess.CalledProcessError:
        return False


def cleanup_tunnels():
    """Clean up any existing SSH tunnels"""
    # Kill any existing SSH tunnels
    if os.path.exists("/tmp/remote_tunnel.pid"):
        try:
            with open("/tmp/remote_tunnel.pid", "r") as f:
                pid = f.read().strip()
            subprocess.run(["kill", "-9", pid], check=False)
            os.remove("/tmp/remote_tunnel.pid")
        except (IOError, subprocess.CalledProcessError):
            pass

    # Kill any processes using our ports
    for port in [8765, 6380, 10001]:
        try:
            pid_cmd = subprocess.run(
                ["lsof", "-ti", f":{port}"], capture_output=True, text=True
            )
            if pid_cmd.stdout:
                pids = pid_cmd.stdout.strip().split("\n")
                for pid in pids:
                    try:
                        subprocess.run(["kill", "-9", pid], check=True)
                    except subprocess.CalledProcessError:
                        pass
        except subprocess.CalledProcessError:
            pass


def setup_ssh_tunnel(remote_config: RemoteConfig) -> None:
    """Setup SSH tunnel for remote development"""
    click.echo("🔍 Checking for existing tunnels...")

    # Kill existing tunnels using a more reliable method
    for port in [8765, 6380, 10001]:
        try:
            # Get PIDs using ports
            pid_cmd = subprocess.run(
                ["lsof", "-ti", f":{port}"], capture_output=True, text=True
            )
            if pid_cmd.stdout:
                pids = pid_cmd.stdout.strip().split("\n")
                for pid in pids:
                    try:
                        subprocess.run(["kill", "-9", pid], check=True)
                        click.echo(f"Killed process {pid} using port {port}")
                    except subprocess.CalledProcessError:
                        pass
        except subprocess.CalledProcessError:
            pass

    click.echo("🔗 Creating new SSH tunnel...")

    # Wait a moment for ports to clear
    time.sleep(1)

    tunnel_proc = subprocess.Popen(
        [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-A",  # Enable SSH agent forwarding
            "-N",
            "-L",
            "8765:localhost:8765",
            "-L",
            "6380:localhost:6380",
            "-L",
            "10001:localhost:10001",
            f"{remote_config.username}@{remote_config.host}",
        ]
    )

    with open("/tmp/remote_tunnel.pid", "w") as f:
        f.write(str(tunnel_proc.pid))

    # Wait longer to ensure tunnel is established
    time.sleep(3)

    # Verify tunnel is actually running
    if tunnel_proc.poll() is not None:
        raise click.ClickException("Failed to establish SSH tunnel")

    click.echo("✅ SSH tunnel established")


def setup_conda_env(username: str, host: str, env_name: str = None) -> None:
    """Setup conda environment on remote host"""
    if not env_name:
        result = subprocess.run(
            ["conda", "info", "--envs"], capture_output=True, text=True
        )
        env_name = next(
            line.split()[0] for line in result.stdout.splitlines() if "*" in line
        )

    project_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    ).stdout.strip()
    project_dir = Path(project_root).name

    # Setup remote conda environment
    setup_commands = [
        # Install miniconda
        "if [ ! -f ~/miniconda3/bin/conda ]; then "
        "curl -O https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh && "
        "sh Miniconda3-latest-Linux-x86_64.sh -b && "
        "rm Miniconda3-latest-Linux-x86_64.sh && "
        "echo 'export PATH=~/miniconda3/bin:$PATH' >> ~/.bashrc && "
        "~/miniconda3/bin/conda init bash && "
        "source ~/.bashrc; "
        "fi",
        # Create conda environment
        f"export PATH=~/miniconda3/bin:$PATH && "
        f"if ! ~/miniconda3/bin/conda env list | grep -q '^{env_name} '; then "
        f"~/miniconda3/bin/conda create -y -n {env_name} python=$(python -V | cut -d' ' -f2); "
        "fi",
    ]

    for cmd in setup_commands:
        subprocess.run(["ssh", f"{username}@{host}", cmd], check=True)

    # Sync project files
    click.echo("📦 Syncing project files...")
    subprocess.run(
        [
            "rsync",
            "-avz",
            "--progress",
            "--exclude",
            "__pycache__",
            "--exclude",
            "*.pyc",
            "--exclude",
            "node_modules",
            "--exclude",
            ".venv",
            "--exclude",
            "*.egg-info",
            f"{project_root}/",
            f"{username}@{host}:~/projects/{project_dir}/",
        ],
        check=True,
    )


def sync_project(remote_config: RemoteConfig, project_name: str) -> None:
    """Sync project files with remote host"""

    project_root = Path.cwd()
    # Create remote directories
    remote_cmd(
        remote_config,
        ["mkdir", "-p", f"~/.config/{project_name}", f"~/projects/{project_name}"],
    )

    # Sync project files
    subprocess.run(
        [
            "rsync",
            "-avz",
            "--progress",
            "--exclude",
            "__pycache__",
            "--exclude",
            "*.pyc",
            "--exclude",
            "node_modules",
            "--exclude",
            ".venv",
            "--exclude",
            "*.egg-info",
            f"{project_root}/",
            f"{remote_config.username}@{remote_config.host}:~/projects/{project_name}/",
        ],
        check=True,
    )
