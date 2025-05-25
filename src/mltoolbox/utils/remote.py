import datetime
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import click
import pkg_resources

from .helpers import RemoteConfig, remote_cmd


def ensure_ray_head_node(remote_config: Optional[RemoteConfig], python_version: str):
    """Ensure Ray head node is running on the remote host.

    Args:
        remote_config: Remote configuration for connection
        git_name: GitHub username for container image
        python_version: Python version to use (e.g., "3.12")
        variant: System variant to use (e.g., "cpu", "cuda", "cuda-nightly")
    """
    if not remote_config:
        return

    # Check if Ray head is running (try to connect to port 6379)
    result = remote_cmd(
        remote_config,
        ["nc -z localhost 6379 2>/dev/null || echo 'not_running'"],
        use_working_dir=False,
    )

    if "not_running" in result.stdout:
        click.echo("🚀 Starting Ray head node on remote host...")

        # Get paths for Ray head files
        ray_head_compose = Path(
            pkg_resources.resource_filename(
                "mltoolbox", "base/docker-compose-ray-head.yml"
            )
        )
        ray_head_dockerfile = Path(
            pkg_resources.resource_filename("mltoolbox", "base/Dockerfile.ray-head")
        )

        # Create directory for compose file
        remote_cmd(
            remote_config,
            ["mkdir -p ~/ray"],
            use_working_dir=False,
        )

        # Copy files to remote
        subprocess.run(
            [
                "scp",
                str(ray_head_compose),
                f"{remote_config.username}@{remote_config.host}:~/ray/docker-compose.yml",
            ],
            check=False,  # Changed from check=True to handle potential errors gracefully
        )

        subprocess.run(
            [
                "scp",
                str(ray_head_dockerfile),
                f"{remote_config.username}@{remote_config.host}:~/ray/Dockerfile.ray-head",
            ],
            check=False,  # Changed from check=True to handle potential errors gracefully
        )

        # Start the Ray head node with docker compose, with explicit error handling
        try:
            remote_cmd(
                remote_config,
                [
                    f"cd ~/ray && PYTHON_VERSION={python_version} DOCKER_BUILDKIT=0 docker compose up -d"
                ],  # Added DOCKER_BUILDKIT=0
                use_working_dir=False,
            )
        except Exception as e:
            click.echo(f"⚠️ Initial Ray head node start failed: {e}")
            click.echo("🔄 Retrying without build cache...")
            # Retry with --no-cache if first attempt fails
            remote_cmd(
                remote_config,
                [
                    f"cd ~/ray && DOCKER_BUILDKIT=0 PYTHON_VERSION={python_version} docker compose build --no-cache && docker compose up -d"
                ],
                use_working_dir=False,
            )

        # Wait for Ray to be ready
        click.echo("⏳ Waiting for Ray head node to be ready...")
        for _ in range(10):
            time.sleep(2)
            result = remote_cmd(
                remote_config,
                ["nc -z localhost 6379 2>/dev/null || echo 'not_running'"],
                use_working_dir=False,
            )
            if "not_running" not in result.stdout:
                click.echo("✅ Ray head node is ready")
                break
        else:
            click.echo(
                "⚠️ Ray head node not responding after timeout, continuing anyway"
            )


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
                "-o",
                "StrictHostKeyChecking=accept-new",
                str(local_rclone_config),
                f"{remote_config.username}@{remote_config.host}:~/.config/rclone/rclone.conf",
            ],
            check=True,
        )
        click.echo("✅ Rclone config synced successfully")
    except subprocess.CalledProcessError as e:
        click.echo(f"❌ Failed to sync rclone config: {e}")


def update_env_file(
    remote_config: Optional[RemoteConfig],
    project_name: str,
    updates: dict,
):
    """Update environment file with new values, preserving existing variables."""
    try:
        # Get existing env vars (remote or local)
        if remote_config:
            env_cmd = f"cd ~/projects/{project_name} && cat .env 2>/dev/null || echo ''"
            result = remote_cmd(remote_config, [env_cmd])
            env_content = result.stdout
        else:
            env_file = Path.cwd() / ".env"
            env_content = env_file.read_text() if env_file.exists() else ""

        # Parse existing env vars
        env_dict = {}
        for line in env_content.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env_dict[key.strip()] = value.strip().strip("'\"")

        # Merge updates (updates take priority)
        env_dict.update(updates)

        # Format env vars back into a file
        env_lines = [f"{key}={value}" for key, value in env_dict.items()]
        updated_env = "\n".join(env_lines)

        # Write back
        if remote_config:
            write_cmd = f"cd ~/projects/{project_name} && cat > .env << 'EOF'\n{updated_env}\nEOF"
            remote_cmd(remote_config, [write_cmd])
        else:
            env_file = Path.cwd() / ".env"
            env_file.write_text(updated_env)

        click.echo(f"✅ Updated .env file with {len(updates)} variables")

        return env_dict

    except Exception as e:
        click.echo(f"❌ Failed to update .env file: {e}")
        raise


def setup_remote_ssh_keys(remote_config: RemoteConfig, ssh_key_name: str = None):
    """
    Set up SSH keys on remote host - runs commands in one session to ensure agent vars are accessible.
    """
    # Get key name from argument, env, or use default
    ssh_key_name = ssh_key_name or os.environ.get("SSH_KEY_NAME", "id_ed25519")

    click.echo(f"🔑 Setting up SSH key '{ssh_key_name}' on remote host...")

    # Check if the key exists
    key_check = remote_cmd(
        remote_config,
        [f"test -f ~/.ssh/{ssh_key_name} && echo 'exists' || echo 'missing'"],
        use_working_dir=False,
    ).stdout.strip()

    if key_check == "missing":
        click.echo(f"❌ SSH key '{ssh_key_name}' not found on remote host")
        return False

    # Setup agent and add key - ONLY ON THE HOST, NOT IN CONTAINER
    ssh_agent_cmd = f"""
    # Start SSH agent if not running
    if [ -z "$SSH_AUTH_SOCK" ]; then
        eval $(ssh-agent -s)
        echo "Started new SSH agent"
    fi
    
    # Temporarily fix permissions only for adding to agent
    chmod 600 ~/.ssh/{ssh_key_name}
    
    # Add key to agent
    ssh-add ~/.ssh/{ssh_key_name}
    
    # Save agent environment variables for later use
    echo "export SSH_AUTH_SOCK=$SSH_AUTH_SOCK" > ~/.ssh/agent_env
    echo "export SSH_AGENT_PID=$SSH_AGENT_PID" >> ~/.ssh/agent_env
    """

    try:
        result = remote_cmd(
            remote_config,
            [ssh_agent_cmd],
            use_working_dir=False,
        )

        if "The agent has no identities" in result.stdout:
            click.echo("❌ Failed to add SSH key to agent")
            return False

        click.echo("✅ SSH key added successfully to host SSH agent")
        return True

    except Exception as e:
        click.echo(f"❌ Failed to set up SSH agent: {str(e)}")
        return False


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


def verify_env_vars(remote: Optional[RemoteConfig] = None) -> dict:  # noqa: FA100
    """Verify required environment variables and return all env vars as dict."""
    required_vars = ["GIT_NAME", "GITHUB_TOKEN", "GIT_EMAIL"]
    env_vars = {}

    if remote:
        # First get all env vars
        result = remote_cmd(remote, ["test -f .env && cat .env || echo ''"])

        # Parse env vars from the output
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env_vars[key] = value.strip("'\"")

        # Check if required vars exist
        missing_vars = [var for var in required_vars if var not in env_vars]
        if missing_vars:
            raise click.ClickException(
                f"Required environment variables not set on remote: {', '.join(missing_vars)}",
            )
    else:
        # Local environment check
        if not Path.cwd().joinpath(".env").exists():
            raise click.ClickException("❌ .env file not found")

        # Load env vars from the .env file
        with open(Path.cwd().joinpath(".env")) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key] = value.strip("'\"")

        # Check also in current environment for required vars
        for var in required_vars:
            if var not in env_vars and os.getenv(var):
                env_vars[var] = os.getenv(var)

        # Check if required vars exist
        missing_vars = [var for var in required_vars if var not in env_vars]
        if missing_vars:
            raise click.ClickException(
                f"Required environment variables not set: {', '.join(missing_vars)}",
            )

    return env_vars


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

        # Transfer SSH keys using scp - NO PERMISSION CHANGES
        for key_file in [ssh_key_name, f"{ssh_key_name}.pub"]:
            try:
                # Use scp for direct file copy
                subprocess.run(
                    [
                        "scp",
                        "-o",
                        "StrictHostKeyChecking=accept-new",
                        str(local_ssh_dir / key_file),
                        f"{remote_config.username}@{remote_config.host}:~/.ssh/{key_file}",
                    ],
                    check=True,
                )
                click.echo(f"✅ Copied SSH key {key_file} to remote host")
            except Exception as e:
                click.echo(f"Warning: Failed to sync {key_file}: {e}")

    # Fix for the .env problem: manually copy .env file first if it exists
    local_env_file = Path.cwd() / ".env"
    if local_env_file.exists():
        click.echo("📄 Syncing .env file separately to ensure it's transferred...")
        try:
            subprocess.run(
                [
                    "scp",
                    "-o",
                    "StrictHostKeyChecking=accept-new",
                    str(local_env_file),
                    f"{remote_config.username}@{remote_config.host}:~/projects/{remote_path or project_name}/.env",
                ],
                check=True,
            )
            click.echo("✅ .env file synced successfully")
        except Exception as e:
            click.echo(f"Warning: Failed to sync .env file: {e}")

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
