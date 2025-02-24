import subprocess
import time
from pathlib import Path

import click

from .helpers import RemoteConfig, remote_cmd


def update_env_file(remote_config: RemoteConfig, project_name: str, updates: dict):
    """Update environment file with new values, preserving existing variables."""
    # Read current env file content
    result = remote_cmd(
        remote_config,
        [f"cat ~/projects/{project_name}/.env"],
    )
    # Get current env content from result
    current_env = (
        result.stdout if isinstance(result, subprocess.CompletedProcess) else result
    )

    # Parse current env file
    env_dict = {}
    for line in current_env.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            try:
                key, value = line.split("=", 1)
                env_dict[key.strip()] = value.strip()
            except ValueError:
                continue  # Skip invalid lines

    # Update with new values
    env_dict.update(updates)

    # Generate new env file content
    new_env_content = "\n".join(f"{k}={v}" for k, v in env_dict.items())

    # Write back to remote .env file
    remote_cmd(
        remote_config,
        [f"cd ~/projects/{project_name} && echo '{new_env_content}' > .env"],
    )


def wait_for_host(host: str, timeout: int | None = None) -> bool:
    """Wait for host to become available by checking both ping and SSH connectivity.

    Args:
        host: Hostname or IP address to check
        timeout: Maximum time to wait in seconds, None for infinite

    Returns:
        bool: True if host becomes available, False if timeout reached
    """
    start_time = time.time()
    click.echo(f"Waiting for host {host} to become available...")

    def time_exceeded() -> bool:
        return timeout and (time.time() - start_time) > timeout

    remote_config = RemoteConfig(host=host, username="ubuntu")

    while not time_exceeded():
        try:
            # Try to run a simple command
            remote_cmd(
                remote_config, ["echo 'testing connection'"], use_working_dir=False
            )
            click.echo("✅ Host is available and accepting SSH connections!")
            return True
        except Exception as e:
            click.echo(f"Connection failed ({str(e)}), retrying...")
            time.sleep(5)

    click.echo(f"❌ Timeout reached after {timeout} seconds")
    return False


def setup_conda_env(
    remote_config: RemoteConfig, env_name: str = None, python_version: str = "3.12"
) -> None:
    """Setup conda environment on remote host.

    Args:
        remote_config: Remote configuration containing username and host
        env_name: Name of the conda environment to create
        python_version: Python version to install (e.g. "3.12", "3.10")
    """
    project_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    project_name = Path(project_root).name

    # Single command to handle everything
    setup_command = f"""
    # Download and install Miniconda if not present
    if [ ! -f $HOME/miniconda3/bin/conda ]; then
        wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
        bash Miniconda3-latest-Linux-x86_64.sh -b
        rm Miniconda3-latest-Linux-x86_64.sh
    fi

    # Create the environment using absolute path
    $HOME/miniconda3/bin/conda create -y -n {env_name} python={python_version}
    """

    try:
        click.echo("Installing/updating conda and creating environment...")
        result = subprocess.run(
            ["ssh", f"{remote_config.username}@{remote_config.host}", setup_command],
            check=True,
            capture_output=True,
            text=True,
        )
        click.echo(result.stdout)
    except subprocess.CalledProcessError as e:
        click.echo("❌ Failed to setup conda environment")
        if e.stdout:
            click.echo(e.stdout)
        if e.stderr:
            click.echo(e.stderr)
        raise

    # Create remote directories
    remote_cmd(
        remote_config,
        [f"mkdir -p ~/.config/{project_name} ~/projects/{project_name}"],
        use_working_dir=False,
    )

    # Sync project files
    click.echo("📦 Syncing project files...")
    sync_project(remote_config, project_name)


def sync_project(
    remote_config: RemoteConfig, project_name: str, exclude: list = ""
) -> None:
    """Sync project files with remote host (one-way, local to remote)"""
    project_root = Path.cwd()

    # Create remote directories
    remote_cmd(
        remote_config,
        [f"mkdir -p ~/.config/{project_name} ~/projects/{project_name}"],
        use_working_dir=False,
    )

    # Default exclusions for temporary/generated files
    default_excludes = [
        "__pycache__",
        "*.pyc",
        "node_modules",
        ".venv",
        "*.egg-info",
        ".DS_Store",
        "wandb/",  # Weights & Biases logs
        "outputs/",  # Common output directory
        ".vscode-server/",  # VSCode server files
        "*.swp",  # Vim swap files
        ".idea/",  # PyCharm files
        "dist/",  # Python distribution files
        "build/",  # Build artifacts
        ".git/modules/",
    ]

    # Combine default excludes with user-provided patterns
    all_excludes = default_excludes + (exclude.split(",") if exclude else [])

    # Build rsync command
    rsync_cmd = [
        "rsync",
        "-avz",  # archive, verbose, compress
        "--progress",  # Show progress during transfer
        "--stats",  # Show detailed transfer statistics
        "--delete",  # Delete extraneous files on destination
        "--no-perms",  # Don't sync permissions
        "--no-owner",  # Don't sync owner
        "--no-group",  # Don't sync group
        "--chmod=Du=rwx,go=rx,Fu=rw,go=r",  # Set sane permissions
        "-e",
        "ssh -o StrictHostKeyChecking=no",  # Less strict SSH checking
    ]

    # Add exclude patterns
    for pattern in all_excludes:
        rsync_cmd.extend(["--exclude", pattern.strip()])

    # Add source and destination
    rsync_cmd.extend(
        [
            f"{project_root}/",
            f"{remote_config.username}@{remote_config.host}:~/projects/{project_name}/",
        ]
    )

    try:
        click.echo("📦 Starting project sync...")
        click.echo(f"From: {project_root}")
        click.echo(f"To: {remote_config.host}:~/projects/{project_name}")

        # Run rsync and stream output in real-time
        process = subprocess.Popen(
            rsync_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
        )

        # Print stdout in real-time
        while True:
            output = process.stdout.readline()
            if output == "" and process.poll() is not None:
                break
            if output:
                click.echo(output.rstrip())

        if process.returncode == 0:
            click.echo("✅ Sync completed successfully!")
        else:
            stderr = process.stderr.read()
            raise subprocess.CalledProcessError(
                process.returncode, rsync_cmd, stderr=stderr
            )

    except subprocess.CalledProcessError as e:
        click.echo("❌ Sync failed!")
        click.echo(f"Exit code: {e.returncode}")
        if e.stderr:
            click.echo("Error output:")
            click.echo(e.stderr)
        raise click.ClickException(
            "Failed to sync project files. See error details above."
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
    rsync_cmd.extend(
        [
            f"{remote_config.username}@{remote_config.host}:{remote_path}",
            str(local_path),
        ]
    )

    click.echo(f"📥 Downloading {remote_path} to {local_path}...")
    subprocess.run(rsync_cmd, check=True)
    click.echo("✅ Download complete!")
