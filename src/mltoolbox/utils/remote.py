import datetime
import os
import subprocess
import sys
import time
from pathlib import Path

import click

from .helpers import RemoteConfig, remote_cmd
from .logger import get_logger


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
    logger = get_logger()
    local_rclone_config = Path.home() / ".config/rclone/rclone.conf"

    if not local_rclone_config.exists():
        logger.warning("No local rclone config found at ~/.config/rclone/rclone.conf")
        return

    logger.step("Setting up rclone configuration")

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
        logger.success("Rclone config synced successfully")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to sync rclone config: {e}")


def update_env_file(
    remote_config: RemoteConfig | None,
    project_name: str,
    updates: dict,
    dryrun: bool = False,
):
    """Update environment file with new values, preserving existing variables."""
    logger = get_logger()
    if dryrun:
        with logger.panel_output(
            "Update .env File", subtitle="[DRY RUN]", status="success"
        ) as panel:
            panel.write(
                f"Would update .env with: {updates}\nSimulated update, no changes made."
            )
        logger.success("[DRY RUN] .env file update simulated.")
        return updates

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

        logger = get_logger()
        logger.success(f"Updated .env file with {len(updates)} variables")

        return env_dict

    except Exception as e:
        logger = get_logger()
        with logger.panel_output(
            "Environment File Update Failed", subtitle="Configuration Error"
        ) as panel:
            panel.write(f"Failed to update .env file: {str(e)}")
        raise


def setup_remote_ssh_keys(remote_config: RemoteConfig, ssh_key_name: str = None):
    """
    Set up SSH keys on remote host - runs commands in one session to ensure agent vars are accessible.
    """
    # Get key name from argument, env, or use default
    ssh_key_name = ssh_key_name or os.environ.get("SSH_KEY_NAME", "id_ed25519")

    logger = get_logger()
    logger.step(f"Setting up SSH key '{ssh_key_name}' on remote host")

    # Check if the key exists
    key_check = remote_cmd(
        remote_config,
        [f"test -f ~/.ssh/{ssh_key_name} && echo 'exists' || echo 'missing'"],
        use_working_dir=False,
    ).stdout.strip()

    if key_check == "missing":
        with logger.panel_output(
            "SSH Key Not Found", subtitle="Configuration Error"
        ) as panel:
            panel.write(f"SSH key '{ssh_key_name}' not found on remote host")
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
            with logger.panel_output(
                "SSH Agent Setup Failed", subtitle="Authentication Error"
            ) as panel:
                panel.write("Failed to add SSH key to agent")
            return False

        logger.success("SSH key added successfully to host SSH agent")
        return True

    except Exception as e:
        with logger.panel_output(
            "SSH Agent Setup Failed", subtitle="Authentication Error"
        ) as panel:
            panel.write(f"Failed to set up SSH agent: {str(e)}")
        return False


def wait_for_host(
    host: str, timeout: int | None = None, username: str = "ubuntu"
) -> bool:
    """Wait for host to become available by checking both ping and SSH connectivity.

    Args:
        host: Hostname or IP address to check
        timeout: Maximum time to wait in seconds, None for infinite
        username: Remote username to use for SSH connection (default: "ubuntu")

    Returns:
        bool: True if host becomes available, False if timeout reached
    """
    logger = get_logger()
    start_time = time.time()

    def time_exceeded() -> bool:
        return timeout and (time.time() - start_time) > timeout

    remote_config = RemoteConfig(host=host, username=username)

    with logger.spinner(f"Waiting for host {host} to become available"):
        while not time_exceeded():
            try:
                # Try to run a simple command
                remote_cmd(
                    remote_config, ["echo 'testing connection'"], use_working_dir=False
                )
                logger.success("Host is available and accepting SSH connections!")
                return True
            except Exception as e:
                logger.debug(f"Connection failed ({str(e)}), retrying...")
                time.sleep(5)

    logger.error(f"Timeout reached after {timeout} seconds")
    return False


def verify_env_vars(remote: RemoteConfig | None = None, dryrun: bool = False) -> dict:  # noqa: FA100
    """Verify required environment variables and return all env vars as dict."""
    required_vars = ["GIT_NAME", "GITHUB_TOKEN", "GIT_EMAIL"]
    env_vars = {}
    if dryrun:
        # Return plausible dummy env vars
        return {
            "GIT_NAME": "dummyuser",
            "GITHUB_TOKEN": "ghp_dummy1234567890",
            "GIT_EMAIL": "dummy@example.com",
            "PROJECT_NAME": "dummyproject",
            "CONTAINER_NAME": "dummycontainer",
        }
    if remote:
        # First get all env vars
        result = remote_cmd(remote, ["test -f .env && cat .env || echo ''"])
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env_vars[key] = value.strip("'\"")
        missing_vars = [var for var in required_vars if var not in env_vars]
        if missing_vars:
            raise click.ClickException(
                f"Required environment variables not set on remote: {', '.join(missing_vars)}",
            )
    else:
        # Local environment check
        if not Path.cwd().joinpath(".env").exists():
            raise click.ClickException(".env file not found")
        with open(Path.cwd().joinpath(".env")) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key] = value.strip("'\"")
        for var in required_vars:
            if var not in env_vars and os.getenv(var):
                env_vars[var] = os.getenv(var)
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
    source_path: Path | None = None,
    dryrun: bool = False,
) -> None:
    """Sync project files with remote host (one-way, local to remote)

    Args:
        remote_config: Remote configuration
        project_name: Project name
        remote_path: Optional custom remote path to use instead of project_name
        exclude: Patterns to exclude
        source_path: Optional source path to sync from (defaults to current directory)
    """
    logger = get_logger()
    if dryrun:
        with logger.live_output(
            f"Sync Project to {remote_config.host} [DRY RUN]"
        ) as output:
            for i in range(10):
                output.write(f"Simulated sync file {i + 1}\n")
                import time as _time

                _time.sleep(0.1)
        logger.success("[DRY RUN] Project sync simulated.")
        return

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
            "WARNING: Remote has untracked/modified files:\n"
            f"{remote_status}\n"
            "Do you want to proceed with sync? This might overwrite changes!",
            default=False,
        ):
            logger.info("Skipping project sync, continuing with SSH key sync...")
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
                logger.success(f"Copied SSH key {key_file} to remote host")
            except Exception as e:
                logger.warning(f"Failed to sync {key_file}: {e}")

    # Fix for the .env problem: manually copy .env file first if it exists
    local_env_file = Path.cwd() / ".env"
    if local_env_file.exists():
        logger.step("Syncing .env file separately to ensure it's transferred")
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
            logger.success(".env file synced successfully")
        except Exception as e:
            logger.warning(f"Failed to sync .env file: {e}")

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
        logger.section("Starting project sync")
        logger.info(f"From: {project_root}")
        logger.info(f"To: {remote_config.host}:~/projects/{remote_path}")

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
                logger.debug(output.rstrip())

        if process.returncode == 0:
            logger.success("Sync completed successfully!")
        else:
            stderr = process.stderr.read()
            raise subprocess.CalledProcessError(
                process.returncode, rsync_cmd, stderr=stderr
            )

    except subprocess.CalledProcessError as e:
        logger = get_logger()
        error_content = []
        error_content.append(f"Exit code: {e.returncode}")
        if e.stderr:
            error_content.append("Error output:")
            error_content.append(e.stderr)

        with logger.panel_output(
            "Project Sync Failed", subtitle="Rsync Error"
        ) as panel:
            panel.write("\n".join(error_content))

        raise click.ClickException("Failed to sync project files")


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

    logger = get_logger()
    logger.step(f"Downloading {remote_path} to {local_path}")
    subprocess.run(rsync_cmd, check=True)
    logger.success("Download complete!")


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
    logger = get_logger()
    if logger.logger.level <= 10:  # DEBUG level
        logger.debug(f"Running: {' '.join(rclone_args)}")

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
            logger.success(result_msg)
        else:
            result_msg += f"failed with exit code {exit_code}"
            with logger.panel_output(
                "Rclone Sync Failed", subtitle=f"Exit code: {exit_code}"
            ) as panel:
                panel.write(result_msg)

        # Append to history log
        with open(history_path, "a") as history_file:
            history_file.write(result_msg + "\n")

        if exit_code != 0:
            raise click.ClickException(f"rclone sync failed with exit code {exit_code}")

    except Exception as e:
        with logger.panel_output(
            "Rclone Sync Error", subtitle="Unexpected Error"
        ) as panel:
            panel.write(f"Error during sync: {str(e)}")
        raise click.ClickException(str(e))
