import subprocess
from pathlib import Path

import click

from .helpers import RemoteConfig, remote_cmd


def setup_conda_env(username: str, host: str, env_name: str = None) -> None:
    """Setup conda environment on remote host."""  # noqa: D401
    if not env_name:
        result = subprocess.run(
            ["conda", "info", "--envs"], capture_output=True, text=True, check=False,
        )
        env_name = next(
            line.split()[0] for line in result.stdout.splitlines() if "*" in line
        )

    project_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False,
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
            # Your existing excludes
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
            "--exclude",
            "wandb",
            "--exclude",
            "outputs",
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
        [f"mkdir -p ~/.config/{project_name} ~/projects/{project_name}"],  # Single command string
        use_working_dir=False,
    )

    # Sync project files
    subprocess.run(
        [
            "rsync",
            "-avz",
            "--progress",
            # Your existing excludes
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
            "--exclude",
            "wandb",
            "--exclude",
            "outputs",
            f"{project_root}/",
            f"{remote_config.username}@{remote_config.host}:~/projects/{project_name}/",
        ],
        check=True,
    )
