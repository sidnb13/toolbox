import datetime
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import click

from .helpers import RemoteConfig, remote_cmd


def setup_zshrc(remote_config: RemoteConfig):
    """Create a basic .zshrc file if it doesn't exist."""
    remote_cmd(
        remote_config,
        [
            "test -f ~/.zshrc || echo \"# Basic zsh configuration\nbindkey -e\nsetopt PROMPT_SUBST\nPS1='%n@%m:%~%# '\" > ~/.zshrc"
        ],
        use_working_dir=False,
    )


def setup_rclone(remote_config: RemoteConfig) -> None:
    """Setup rclone configuration on remote host."""
    local_rclone_config = Path.home() / ".config/rclone/rclone.conf"

    if not local_rclone_config.exists():
        click.echo("⚠️ No local rclone config found at ~/.config/rclone/rclone.conf")
        return

    click.echo("📦 Setting up rclone configuration...")

    # Create remote rclone config directory
    remote_cmd(
        remote_config,
        ["mkdir -p ~/.config/rclone"],
        use_working_dir=False,
    )

    # Use scp to copy rclone config
    try:
        subprocess.run(
            [
                "scp",
                str(local_rclone_config),
                f"{remote_config.username}@{remote_config.host}:~/.config/rclone/rclone.conf",
            ],
            check=True,
        )
        click.echo("✅ Rclone config synced successfully")
    except subprocess.CalledProcessError as e:
        click.echo(f"❌ Failed to sync rclone config: {e}")


def update_env_file(
    remote_config: RemoteConfig,
    project_name: str,
    updates: dict,
    container_name: str = None,
):
    """Update environment file with new values, preserving existing variables.

    Args:
        remote_config: Remote configuration
        project_name: Project name for the remote directory path
        updates: Dictionary of environment variables to update
        container_name: Optional container name, defaults to project_name if not provided
    """
    # Use container_name if provided, otherwise default to project_name
    container_name = (container_name or project_name).lower()

    # Read current env file content
    try:
        result = remote_cmd(
            remote_config,
            [f"cat ~/projects/{project_name}/.env 2>/dev/null || echo ''"],
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

        # Verify the env file has all required variables
        click.echo("Verifying environment variables...")
        required_vars = [
            "PROJECT_NAME",
            "CONTAINER_NAME",
            "GIT_NAME",
            "GIT_EMAIL",
            "GITHUB_TOKEN",
        ]
        for var in required_vars:
            if var not in env_dict:
                click.echo(f"⚠️ Warning: {var} is missing from .env file")

                # If PROJECT_NAME or CONTAINER_NAME is missing, add them
                if var == "PROJECT_NAME":
                    remote_cmd(
                        remote_config,
                        [
                            f"cd ~/projects/{project_name} && echo 'PROJECT_NAME={project_name}' >> .env"
                        ],
                    )
                    click.echo(f"✅ Added PROJECT_NAME={project_name} to .env file")
                elif var == "CONTAINER_NAME":
                    remote_cmd(
                        remote_config,
                        [
                            f"cd ~/projects/{project_name} && echo 'CONTAINER_NAME={container_name}' >> .env"
                        ],
                    )
                    click.echo(f"✅ Added CONTAINER_NAME={container_name} to .env file")

    except Exception as e:
        click.echo(f"❌ Failed to update .env file: {e}")
        raise


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
    remote_config: RemoteConfig,
    project_name: str,
    remote_path=None,
    exclude: list = "",
    source_path: Optional[Path] = None,
) -> None:
    """Sync project files with remote host (one-way, local to remote)

    Args:
        remote_config: Remote configuration
        project_name: Project name
        remote_path: Optional custom remote path to use instead of project_name
        exclude: Patterns to exclude
        source_path: Optional source path to sync from (defaults to current directory)
    """

    remote_path = remote_path or project_name
    project_root = source_path if source_path else Path.cwd()

    # Check if project directory exists and is a git repo
    check_git = remote_cmd(
        remote_config,
        [
            f"test -d ~/projects/{remote_path}/.git && echo 'exists' || echo 'not_exists'"
        ],
    ).stdout.strip()

    # Only check git status if the repo exists
    do_project_sync = True
    if check_git == "exists":
        remote_status = remote_cmd(
            remote_config,
            [f"cd ~/projects/{remote_path} && git status --porcelain"],
        ).stdout.strip()

        if remote_status and not click.confirm(
            "⚠️ WARNING: Remote has untracked/modified files:\n"
            f"{remote_status}\n"
            "Do you want to proceed with sync? This might overwrite changes!",
            default=False,
        ):
            click.echo("Skipping project sync, continuing with SSH key sync...")
            do_project_sync = False

    # First sync SSH keys if they exist
    local_ssh_dir = Path.home() / ".ssh"
    ssh_key_name = os.getenv("SSH_KEY_NAME", "id_ed25519")

    if (local_ssh_dir / ssh_key_name).exists():
        # Create .ssh directory with correct permissions
        remote_cmd(
            remote_config,
            ["mkdir -p ~/.ssh", "chmod 700 ~/.ssh"],
            use_working_dir=False,
        )

        # Transfer SSH keys using scp instead of rsync
        for key_file, perms in [(ssh_key_name, "700"), (f"{ssh_key_name}.pub", "644")]:
            try:
                # Use scp for direct file copy
                subprocess.run(
                    [
                        "scp",
                        str(local_ssh_dir / key_file),
                        f"{remote_config.username}@{remote_config.host}:~/.ssh/{key_file}",
                    ],
                    check=True,
                )
                remote_cmd(
                    remote_config,
                    [f"chmod {perms} ~/.ssh/{key_file}"],
                    use_working_dir=False,
                )
            except Exception as e:
                click.echo(f"Warning: Failed to sync {key_file}: {e}")

    if not do_project_sync:
        return

    # Create remote directories
    remote_cmd(
        remote_config,
        [f"mkdir -p ~/.config/{remote_path} ~/projects/{remote_path}"],
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
    ]

    # Combine default excludes with user-provided patterns
    all_excludes = default_excludes + (exclude.split(",") if exclude else [])

    # Build rsync command
    rsync_cmd = [
        "rsync",
        "-avz",  # archive, verbose, compress
        "--progress",  # Show progress during transfer
        "--stats",  # Show detailed transfer statistics
        "--no-perms",  # Don't sync permissions
        "--no-owner",  # Don't sync owner
        "--no-group",  # Don't sync group
        "--ignore-errors",  # Delete even if there are I/O errors
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
            f"{remote_config.username}@{remote_config.host}:~/projects/{remote_path}/",
        ]
    )

    try:
        click.echo("📦 Starting project sync...")
        click.echo(f"From: {project_root}")
        click.echo(f"To: {remote_config.host}:~/projects/{remote_path}")

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


def build_rclone_cmd(
    source_dir,
    dest_dir,
    transfers,
    checkers,
    chunk_size,
    cutoff,
    exclude,
    dry_run,
    verbose,
):
    """Build rclone command with all parameters."""
    rclone_args = [
        "rclone",
        "sync",
        source_dir,
        dest_dir,
        f"--transfers={transfers}",
        f"--checkers={checkers}",
        f"--drive-chunk-size={chunk_size}",
        f"--drive-upload-cutoff={cutoff}",
        "--drive-use-trash=false",
        "--stats=10s",
        "--retries=3",
        "--low-level-retries=10",
    ]

    # Add verbose flag if requested
    if verbose:
        rclone_args.extend(["--progress", "--verbose"])

    # Add dry-run flag if requested
    if dry_run:
        rclone_args.append("--dry-run")

    # Add exclude patterns
    for pattern in exclude.split(","):
        if pattern.strip():
            rclone_args.append(f"--exclude={pattern.strip()}")

    return rclone_args


def run_rclone_sync(
    source_dir,
    dest_dir,
    transfers,
    checkers,
    chunk_size,
    cutoff,
    exclude,
    dry_run,
    verbose,
):
    """Execute rclone sync command locally with all parameters."""
    # Build rclone command
    rclone_args = build_rclone_cmd(
        source_dir,
        dest_dir,
        transfers,
        checkers,
        chunk_size,
        cutoff,
        exclude,
        dry_run,
        verbose,
    )

    # Execute rclone command
    click.echo(f"Running: {' '.join(rclone_args)}")

    try:
        # Create log files
        log_path = Path.home() / "rclone.log"
        history_path = Path.home() / "sync_history.log"

        # Execute the command and capture output
        process = subprocess.Popen(
            rclone_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
        )

        # Stream output to both console and log file
        with open(log_path, "w") as log_file:
            for line in iter(process.stdout.readline, ""):
                sys.stdout.write(line)
                log_file.write(line)

        # Wait for process to complete
        exit_code = process.wait()

        # Log result
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result_msg = f"{timestamp}: Sync "
        if exit_code == 0:
            result_msg += "successful"
            click.echo(f"\n✅ {result_msg}")
        else:
            result_msg += f"failed with exit code {exit_code}"
            click.echo(f"\n❌ {result_msg}")

        # Append to history log
        with open(history_path, "a") as history_file:
            history_file.write(result_msg + "\n")

        if exit_code != 0:
            raise click.ClickException(f"rclone sync failed with exit code {exit_code}")

    except Exception as e:
        click.echo(f"Error during sync: {e}")
        raise click.ClickException(str(e))
