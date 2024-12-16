import subprocess
from pathlib import Path
import click
import time


def setup_ssh_tunnel(host: str) -> None:
    """Setup SSH tunnel for remote development"""
    click.echo("🔍 Checking for existing tunnels...")
    # Kill existing tunnels
    for port in [8765, 6380, 10001]:
        try:
            subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, check=True)
            subprocess.run(["lsof", "-ti", f":{port}", "|", "xargs", "kill", "-9"])
        except subprocess.CalledProcessError:
            pass

    click.echo("🔗 Creating new SSH tunnel...")
    tunnel_proc = subprocess.Popen(
        [
            "ssh",
            "-N",
            "-L",
            "8765:localhost:8765",
            "-L",
            "6380:localhost:6380",
            "-L",
            "10001:localhost:10001",
            f"ubuntu@{host}",
        ]
    )

    with open("/tmp/remote_tunnel.pid", "w") as f:
        f.write(str(tunnel_proc.pid))

    time.sleep(2)
    click.echo("✅ SSH tunnel established")


def setup_conda_env(host: str, env_name: str = None) -> None:
    """Setup conda environment on remote host"""
    # Reference setup_conda_remote.sh functionality
    """
    startLine: 16
    endLine: 70
    """
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
        subprocess.run(["ssh", f"ubuntu@{host}", cmd], check=True)

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
            f"ubuntu@{host}:~/projects/{project_dir}/",
        ],
        check=True,
    )


def sync_project(host: str, project_name: str) -> None:
    """Sync project files with remote host"""
    # Reference setup_remote.sh functionality
    """
    startLine: 38
    endLine: 80
    """
    project_root = Path.cwd()

    # Create remote directories
    subprocess.run(
        [
            "ssh",
            f"ubuntu@{host}",
            f"mkdir -p ~/.config/{project_name} ~/projects/{project_name}",
        ],
        check=True,
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
            f"ubuntu@{host}:~/projects/{project_name}/",
        ],
        check=True,
    )
