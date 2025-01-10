import subprocess
from pathlib import Path

import click

from .helpers import RemoteConfig, remote_cmd


def setup_conda_env(remote_config: RemoteConfig, env_name: str = None) -> None:
    """Setup conda environment on remote host."""
    project_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False,
    ).stdout.strip()
    project_name = Path(project_root).name

    # Setup remote conda environment
    setup_commands = [
        # Install miniconda
        "if [ ! -f ~/miniconda3/bin/conda ]; then "
        "curl -O https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh && "
        "sh Miniconda3-latest-Linux-x86_64.sh -b && "
        "rm Miniconda3-latest-Linux-x86_64.sh && "
        "echo 'export PATH=~/miniconda3/bin:$PATH' >> ~/.bashrc && "
        "~/miniconda3/bin/conda init bash && "
        "~/miniconda3/bin/conda init zsh && "
        "source ~/.bashrc; "
        "fi",
        # Create conda environment
        f"export PATH=~/miniconda3/bin:$PATH && "
        f"if ! conda env list | grep -q '^{env_name} '; then "
        f"conda create -y -n {env_name} python=3.12; "
        "fi",
    ]

    for cmd in setup_commands:
        subprocess.run(["ssh", f"{remote_config.username}@{remote_config.host}", cmd], check=True)

    # Create remote directories
    remote_cmd(
        remote_config,
        [f"mkdir -p ~/.config/{project_name} ~/projects/{project_name}"],
        use_working_dir=False,
    )

    # Sync project files
    click.echo("📦 Syncing project files...")
    sync_project(remote_config, project_name)


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


def fetch_remote(
    remote_config: RemoteConfig,
    remote_path: str,
    local_path: str,
    exclude: list[str] = None,
) -> None:
    """Fetch files/directories from remote host to local.

    Args:
        remote_config: Remote configuration containing username and host
        remote_path: Path on remote host to download from
        local_path: Local path to download to
        exclude: List of patterns to exclude from download (default: None)
    """
    # Ensure local directory exists
    local_dir = Path(local_path)
    local_dir.parent.mkdir(parents=True, exist_ok=True)

    # Build rsync command
    rsync_cmd = [
        "rsync",
        "-avz",
        "--progress",
    ]

    # Add exclude patterns if specified
    if exclude:
        for pattern in exclude:
            rsync_cmd.extend(["--exclude", pattern])

    # Add source and destination
    rsync_cmd.extend([
        f"{remote_config.username}@{remote_config.host}:{remote_path}",
        str(local_path),
    ])

    click.echo(f"📥 Downloading {remote_path} to {local_path}...")
    subprocess.run(rsync_cmd, check=True)
    click.echo("✅ Download complete!")
