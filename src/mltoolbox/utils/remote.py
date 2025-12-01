import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import click

from .helpers import RemoteConfig, remote_cmd
from .logger import get_logger


def parse_gitignore_patterns(root_path: Path) -> set[str]:
    """
    Parse .gitignore file from root directory and return exclusion patterns.

    Note: Only parses the root .gitignore file to avoid issues with nested .gitignore
    files (e.g., .venv/.gitignore with '*' which would exclude everything).

    Args:
        root_path: Root directory containing .gitignore

    Returns:
        Set of exclusion patterns compatible with rsync
    """
    patterns = set()
    gitignore_path = root_path / ".gitignore"

    if not gitignore_path.exists():
        return patterns

    try:
        with open(gitignore_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue

                # Handle negation patterns (starting with !)
                if line.startswith("!"):
                    # Skip negation patterns as rsync doesn't handle them well
                    continue

                # Convert gitignore pattern to rsync pattern
                pattern = convert_gitignore_to_rsync(line, gitignore_path, root_path)
                if pattern:
                    patterns.add(pattern)

    except (OSError, UnicodeDecodeError):
        # Silently skip files that can't be read
        pass

    return patterns


def parse_dockerignore_patterns(root_path: Path) -> set[str]:
    """
    Parse .dockerignore file from root directory and return exclusion patterns.

    Note: Only parses the root .dockerignore file.

    Args:
        root_path: Root directory containing .dockerignore

    Returns:
        Set of exclusion patterns compatible with rsync
    """
    patterns = set()
    dockerignore_path = root_path / ".dockerignore"

    if not dockerignore_path.exists():
        return patterns

    try:
        with open(dockerignore_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue

                # Convert dockerignore pattern to rsync pattern
                pattern = convert_gitignore_to_rsync(line, dockerignore_path, root_path)
                if pattern:
                    patterns.add(pattern)

    except (OSError, UnicodeDecodeError):
        # Silently skip files that can't be read
        pass

    return patterns


def convert_gitignore_to_rsync(
    pattern: str, ignore_file_path: Path, root_path: Path
) -> str:
    """
    Convert a gitignore pattern to an rsync-compatible pattern.

    Args:
        pattern: The gitignore pattern
        ignore_file_path: Path to the ignore file containing this pattern
        root_path: Root directory of the project

    Returns:
        Rsync-compatible pattern or None if conversion fails
    """
    # Remove leading slash if present (gitignore treats it as root-relative)
    if pattern.startswith("/"):
        pattern = pattern[1:]

    # Skip if pattern is empty after processing
    if not pattern:
        return None

    # Handle directory patterns (ending with /)
    if pattern.endswith("/"):
        pattern = pattern[:-1]
        # For directories, we want to exclude the directory and all contents
        return f"{pattern}/"

    # Handle wildcard patterns
    if "*" in pattern or "?" in pattern or "[" in pattern:
        # Convert gitignore wildcards to rsync patterns
        # gitignore uses ** for recursive matching, rsync uses *
        pattern = pattern.replace("**", "*")
        return pattern

    # Handle simple file/directory patterns
    if "/" in pattern:
        # Path with directories - use as-is
        return pattern
    else:
        # Simple filename pattern
        return pattern


def get_all_exclusion_patterns(
    root_path: Path, user_excludes: list = None
) -> list[str]:
    """
    Get all exclusion patterns from gitignore, dockerignore, and user-provided patterns.

    Args:
        root_path: Root directory to parse ignore files from
        user_excludes: Additional user-provided exclusion patterns

    Returns:
        List of all exclusion patterns for rsync
    """
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

    # Parse ignore files
    gitignore_patterns = parse_gitignore_patterns(root_path)
    dockerignore_patterns = parse_dockerignore_patterns(root_path)

    # Combine all patterns
    all_patterns = set(default_excludes)
    all_patterns.update(gitignore_patterns)
    all_patterns.update(dockerignore_patterns)

    # Add user-provided patterns
    if user_excludes:
        all_patterns.update(user_excludes)

    # Convert to list and sort for consistent ordering
    return sorted(list(all_patterns))


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
        scp_cmd = [
            "scp",
            "-o",
            "StrictHostKeyChecking=accept-new",
        ]
        if remote_config.port:
            scp_cmd.extend(["-P", str(remote_config.port)])
        scp_cmd.extend(
            [
                str(local_rclone_config),
                f"{remote_config.username}@{remote_config.host}:~/.config/rclone/rclone.conf",
            ]
        )
        subprocess.run(scp_cmd, check=True)
        logger.success("Rclone config synced successfully")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to sync rclone config: {e}")


def setup_claude_code(remote_config: RemoteConfig) -> None:
    """Setup Claude Code configuration on remote host by syncing entire ~/.claude directory."""
    logger = get_logger()
    local_claude_dir = Path.home() / ".claude"

    if not local_claude_dir.exists():
        logger.warning("No local Claude Code directory found at ~/.claude")
        return

    logger.step("Setting up Claude Code configuration")

    # Create remote Claude Code config directory
    remote_cmd(
        remote_config,
        ["mkdir -p ~/.claude"],
        use_working_dir=False,
    )

    # Use rsync to sync entire .claude directory
    try:
        ssh_cmd = "ssh"
        if remote_config.port:
            ssh_cmd = f"ssh -p {remote_config.port}"

        rsync_cmd = [
            "rsync",
            "-avz",  # archive, verbose, compress
            "--progress",
            "-e",
            ssh_cmd,
            f"{local_claude_dir}/",  # Trailing slash to sync contents
            f"{remote_config.username}@{remote_config.host}:~/.claude/",
        ]

        subprocess.run(rsync_cmd, check=True)
        logger.success("Claude Code directory synced successfully")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to sync Claude Code directory: {e}")


def update_env_file(
    remote_config: RemoteConfig | None,
    project_name: str,
    updates: dict,
    dryrun: bool = False,
):
    """Update environment file with new values, preserving existing variables."""
    logger = get_logger()
    if dryrun:
        with logger.command_output(
            command="update .env file",
            status="success",
        ) as cmd_output:
            cmd_output.write(
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
        with logger.command_output(
            command="update .env file",
            status="failed",
        ) as cmd_output:
            cmd_output.write(f"Failed to update .env file: {str(e)}")
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
        with logger.command_output(
            command="check SSH key",
            status="failed",
        ) as cmd_output:
            cmd_output.write(f"SSH key '{ssh_key_name}' not found on remote host")
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
            with logger.command_output(
                command="setup SSH agent",
                status="failed",
            ) as cmd_output:
                cmd_output.write("Failed to add SSH key to agent")
            return False

        logger.success("SSH key added successfully to host SSH agent")
        return True

    except Exception as e:
        with logger.command_output(
            command="setup SSH agent",
            status="failed",
        ) as cmd_output:
            cmd_output.write(f"Failed to set up SSH agent: {str(e)}")
        return False


def copy_local_pubkey_to_remote(remote_config: RemoteConfig):
    """
    Copy local machine's public key to remote host for container SSH access.
    The container's entrypoint creates authorized_keys from .pub files in ~/.ssh/
    """
    logger = get_logger()
    logger.step("Copying local public key to remote for container SSH access")

    # Find local public key - try common names
    local_ssh_dir = Path.home() / ".ssh"
    pubkey_names = ["id_ed25519.pub", "id_rsa.pub", "id_ecdsa.pub"]

    local_pubkey = None
    for name in pubkey_names:
        candidate = local_ssh_dir / name
        if candidate.exists():
            local_pubkey = candidate
            break

    if not local_pubkey:
        logger.warning(
            "No local public key found in ~/.ssh/ - container SSH may not work"
        )
        return False

    # Read the public key content
    pubkey_content = local_pubkey.read_text().strip()

    # Copy to remote host as local_client.pub (distinct name to avoid overwriting)
    copy_cmd = f'echo "{pubkey_content}" > ~/.ssh/local_client.pub && chmod 644 ~/.ssh/local_client.pub'

    try:
        remote_cmd(remote_config, [copy_cmd], use_working_dir=False)
        logger.success(f"Copied {local_pubkey.name} to remote as local_client.pub")
        return True
    except Exception as e:
        logger.warning(f"Failed to copy local public key: {e}")
        return False


def wait_for_host(
    host: str,
    timeout: int | None = None,
    username: str = "ubuntu",
    port: int | None = None,
) -> bool:
    """Wait for host to become available by checking both ping and SSH connectivity.

    Args:
        host: Hostname or IP address to check
        timeout: Maximum time to wait in seconds, None for infinite
        username: Remote username to use for SSH connection (default: "ubuntu")
        port: SSH port to use (default: None, which means 22)

    Returns:
        bool: True if host becomes available, False if timeout reached
    """
    logger = get_logger()
    start_time = time.time()

    def time_exceeded() -> bool:
        return timeout and (time.time() - start_time) > timeout

    remote_config = RemoteConfig(host=host, username=username, port=port)

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


def should_exclude(path: Path, root: Path, exclude_patterns: list[str]) -> bool:
    """
    Check if a path should be excluded based on exclusion patterns.

    Args:
        path: Path to check
        root: Root directory for relative path calculation
        exclude_patterns: List of exclusion patterns

    Returns:
        True if path should be excluded, False otherwise
    """
    import fnmatch

    # Get relative path from root
    try:
        rel_path = path.relative_to(root)
    except ValueError:
        return False

    rel_path_str = str(rel_path)

    # Check against each exclusion pattern
    for pattern in exclude_patterns:
        # Remove trailing slash for directory patterns
        clean_pattern = pattern.rstrip("/")

        # Check direct match
        if fnmatch.fnmatch(rel_path_str, clean_pattern):
            return True

        # Check if any parent directory matches
        if fnmatch.fnmatch(path.name, clean_pattern):
            return True

        # Check directory patterns (pattern ending with /)
        if pattern.endswith("/"):
            if (
                rel_path_str.startswith(clean_pattern + "/")
                or rel_path_str == clean_pattern
            ):
                return True

    return False


def generate_sync_preview(root_path: Path, exclude_patterns: list[str]) -> dict:
    """
    Generate a first-level tree preview of what will be synced.

    Args:
        root_path: Root directory to preview
        exclude_patterns: List of exclusion patterns

    Returns:
        Dictionary with files and directories that will be synced
    """
    preview = {"files": [], "directories": []}

    try:
        # Get first-level items only
        for item in sorted(root_path.iterdir()):
            # Skip hidden files/directories except specific ones
            if item.name.startswith(".") and item.name not in [
                ".env",
                ".gitignore",
                ".dockerignore",
                ".mlt",  # mltoolbox config directory
            ]:
                continue

            # Check if excluded
            if should_exclude(item, root_path, exclude_patterns):
                continue

            if item.is_file():
                # Get file size
                try:
                    size = item.stat().st_size
                    size_str = format_size(size)
                    preview["files"].append((item.name, size_str))
                except (OSError, PermissionError):
                    preview["files"].append((item.name, "?"))
            elif item.is_dir():
                # Count items in directory (non-recursively)
                try:
                    count = sum(1 for _ in item.iterdir())
                    preview["directories"].append((item.name, count))
                except (OSError, PermissionError):
                    preview["directories"].append((item.name, "?"))

    except (OSError, PermissionError):
        pass

    return preview


def format_size(size_bytes: int) -> str:
    """Format size in bytes to human-readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}TB"


def print_sync_preview(logger, root_path: Path, exclude_patterns: list[str]):
    """Print a preview of what will be synced."""
    preview = generate_sync_preview(root_path, exclude_patterns)

    # Use compact tree-style format
    now = datetime.now().strftime("%H:%M:%S")
    indicator = "[blue]●[/blue]"
    cmd_name = f"sync preview ({root_path.name})"

    logger.console.print(f"{now}  {indicator}  [dim]{cmd_name}[/dim]")

    # Build content lines
    content_lines = []

    # Print directories
    if preview["directories"]:
        for dir_name, count in preview["directories"]:
            count_str = f"{count} items" if isinstance(count, int) else count
            content_lines.append(f"📁 {dir_name}/ ({count_str})")

    # Print files
    if preview["files"]:
        for file_name, size in preview["files"]:
            content_lines.append(f"📄 {file_name} ({size})")

    # Summary
    total_dirs = len(preview["directories"])
    total_files = len(preview["files"])
    content_lines.append(f"📊 Total: {total_dirs} directories, {total_files} files")
    content_lines.append(f"🚫 Excluding {len(exclude_patterns)} patterns")

    # Print with tree indentation
    if content_lines:
        max_output_lines = 10  # Show more lines for preview
        output_lines = content_lines[:max_output_lines]
        total_lines = len(output_lines)

        for idx, line in enumerate(output_lines):
            if idx == total_lines - 1:
                prefix = "      └─ "
            else:
                prefix = "      │  "
            logger.console.print(f"{prefix}[dim]{line}[/dim]")

        if len(content_lines) > max_output_lines:
            remaining = len(content_lines) - max_output_lines
            logger.console.print(f"      └─ [dim]... ({remaining} more items)[/dim]")


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
    force: bool = False,
) -> None:
    """Sync project files with remote host (one-way, local to remote)

    Args:
        remote_config: Remote configuration
        project_name: Project name
        remote_path: Optional custom remote path to use instead of project_name
        exclude: Patterns to exclude
        force: Skip confirmation prompts
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

        if (
            remote_status
            and not force
            and not click.confirm(
                "WARNING: Remote has untracked/modified files:\n"
                f"{remote_status}\n"
                "Do you want to proceed with sync? This might overwrite changes!",
                default=False,
            )
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
                scp_cmd = [
                    "scp",
                    "-o",
                    "StrictHostKeyChecking=accept-new",
                ]
                if remote_config.port:
                    scp_cmd.extend(["-P", str(remote_config.port)])
                scp_cmd.extend(
                    [
                        str(local_ssh_dir / key_file),
                        f"{remote_config.username}@{remote_config.host}:~/.ssh/{key_file}",
                    ]
                )
                subprocess.run(scp_cmd, check=True)
                logger.success(f"Copied SSH key {key_file} to remote host")
            except Exception as e:
                logger.warning(f"Failed to sync {key_file}: {e}")

    # Fix for the .env problem: manually copy .env file first if it exists
    local_env_file = Path.cwd() / ".env"
    if local_env_file.exists():
        logger.step("Syncing .env file separately to ensure it's transferred")
        try:
            scp_cmd = [
                "scp",
                "-o",
                "StrictHostKeyChecking=accept-new",
            ]
            if remote_config.port:
                scp_cmd.extend(["-P", str(remote_config.port)])
            scp_cmd.extend(
                [
                    str(local_env_file),
                    f"{remote_config.username}@{remote_config.host}:~/projects/{remote_path or project_name}/.env",
                ]
            )
            subprocess.run(scp_cmd, check=True)
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

    # Get all exclusion patterns from gitignore, dockerignore, and user-provided patterns
    user_excludes = exclude.split(",") if exclude else []
    all_excludes = get_all_exclusion_patterns(project_root, user_excludes)

    # Show sync preview
    print_sync_preview(logger, project_root, all_excludes)

    # Build rsync command
    ssh_cmd = "ssh"
    if remote_config.port:
        ssh_cmd = f"ssh -p {remote_config.port}"
    rsync_cmd = [
        "rsync",
        "-avz",  # archive, verbose, compress
        "--progress",  # Show progress during transfer (compatible with older rsync)
        "--stats",  # Show detailed transfer statistics
        "--no-owner",  # Don't sync owner
        "--no-group",  # Don't sync group
        "--ignore-errors",  # Delete even if there are I/O errors
        "--chmod=Du=rwx,go=rx,Fu=rw,go=r",  # Set sane permissions
        "-e",
        ssh_cmd,
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
        # Display sync info in compact tree format
        now = datetime.now().strftime("%H:%M:%S")
        logger.console.print(
            f"{now}  [bold blue]●[/bold blue]  [bold]Starting project sync[/bold]"
        )
        logger.console.print(f"      ├─ [dim]From:[/dim] {project_root}")
        logger.console.print(
            f"      └─ [dim]To:[/dim] {remote_config.host}:~/projects/{remote_path}"
        )

        # Run rsync with progress bar
        # Note: rsync sends progress to stdout, errors to stderr
        process = subprocess.Popen(
            rsync_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
        )

        # Parse rsync progress output and display minimal progress updates
        # Regex patterns for rsync --progress output
        # Actual format from stderr:
        # 1. "Transfer starting: N files"
        # 2. "filename.ext" (standalone line)
        # 3. "          10000 100%  179.37MB/s   00:00:00 (xfer#1, to-check=0/1)"
        #    Format: spaces + size + percentage + speed + time + optional transfer info

        transfer_starting_pattern = re.compile(r"Transfer starting:\s+(\d+)\s+files")
        # Progress line after strip: "50000 100%  85.62MB/s   00:00:00 (xfer#1, to-check=1/2)"
        # Format: size + space + percentage + space + speed + space + time
        file_progress_pattern = re.compile(
            r"^(\d+(?:,\d+)*)\s+(\d+)%\s+([\d.]+)([kKMGT]?B/s)\s+(\d+:\d+:\d+)"
        )
        # Match total bytes from stats (stdout)
        total_bytes_pattern = re.compile(r"total size is\s+(\d+(?:,\d+)*)")

        def format_bytes(bytes_val):
            """Format bytes to human-readable format."""
            for unit in ["B", "KB", "MB", "GB", "TB"]:
                if bytes_val < 1024.0:
                    return f"{bytes_val:.1f}{unit}"
                bytes_val /= 1024.0
            return f"{bytes_val:.1f}PB"

        total_bytes = None
        bytes_transferred = 0
        completed_files = {}  # Track completed files to avoid double counting
        current_file = "Scanning files..."
        current_file_size = 0
        last_update_time = time.time()
        stderr_output = []  # Capture stderr for error reporting
        expecting_filename = False  # Track if we're expecting a filename line
        file_count = 0

        # Read stdout for progress (rsync sends progress to stdout!)
        # stderr is only for errors
        import threading

        def read_stdout():
            nonlocal \
                bytes_transferred, \
                total_bytes, \
                current_file, \
                current_file_size, \
                completed_files, \
                last_update_time, \
                expecting_filename, \
                file_count
            for line in process.stdout:
                if not line:
                    continue
                line_stripped = line.strip()
                if not line_stripped:
                    continue

                # Parse "Transfer starting: N files"
                match = transfer_starting_pattern.match(line_stripped)
                if match:
                    expecting_filename = True
                    continue

                # Parse filename (standalone line, no leading spaces, not stats)
                if (
                    expecting_filename
                    and not line_stripped.startswith(" ")
                    and not line_stripped.startswith("sent")
                    and not line_stripped.startswith("total")
                ):
                    # This is a filename
                    full_filename = line_stripped
                    current_file = full_filename.split("/")[-1]
                    if len(current_file) > 50:
                        current_file = current_file[:47] + "..."
                    expecting_filename = False
                    # Initialize tracking for this file
                    if full_filename not in completed_files:
                        completed_files[full_filename] = 0
                    continue

                # Parse progress line (starts with spaces, has numbers and %)
                match = file_progress_pattern.match(line_stripped)
                if match:
                    (
                        size_str,
                        percent,
                        speed_val,
                        speed_unit,
                        time_remaining,
                    ) = match.groups()

                    # Convert size to bytes
                    size_bytes = int(size_str.replace(",", ""))
                    current_file_size = size_bytes
                    percent_int = int(percent)

                    # Get current file being processed
                    full_filename = current_file  # Use the last filename we saw
                    if full_filename not in completed_files:
                        completed_files[full_filename] = 0

                    # Calculate bytes for this file based on percentage
                    file_bytes_transferred = int((percent_int / 100) * size_bytes)

                    # When file reaches 100%, mark it as completed
                    if percent_int == 100:
                        # File completed - add remaining bytes
                        if completed_files[full_filename] < size_bytes:
                            bytes_transferred += (
                                size_bytes - completed_files[full_filename]
                            )
                            completed_files[full_filename] = size_bytes
                            file_count += 1
                    else:
                        # File in progress - update bytes
                        if completed_files[full_filename] < file_bytes_transferred:
                            bytes_transferred += (
                                file_bytes_transferred - completed_files[full_filename]
                            )
                            completed_files[full_filename] = file_bytes_transferred

                    # Print minimal progress update every 1 second
                    current_time = time.time()
                    if current_time - last_update_time >= 1.0:
                        if total_bytes:
                            percent_done = min(
                                100, int((bytes_transferred / total_bytes) * 100)
                            )
                            logger.console.print(
                                f"      └─ [dim]{format_bytes(bytes_transferred)}/{format_bytes(total_bytes)} ({percent_done}%)[/dim]"
                            )
                        else:
                            logger.console.print(
                                f"      └─ [dim]{format_bytes(bytes_transferred)} transferred[/dim]"
                            )
                        last_update_time = current_time
                    continue

                # Parse "total size is X" from stats (also in stdout)
                match = total_bytes_pattern.search(line_stripped)
                if match:
                    total_bytes = int(match.group(1).replace(",", ""))
                    continue

                # Log other stdout lines as debug
                logger.debug(line_stripped)

        def read_stderr():
            # Capture stderr for error reporting only
            nonlocal stderr_output
            for line in process.stderr:
                stderr_output.append(line)
                if line.strip():
                    logger.debug(f"rsync stderr: {line.strip()}")

        # Start threads to read both streams
        # stdout has progress, stderr has errors
        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        # Wait for process to complete
        process.wait()

        # Wait for threads to finish reading
        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)

        if process.returncode == 0:
            logger.success("Sync completed successfully!")
            # Show summary of what was synced
            preview = generate_sync_preview(project_root, all_excludes)
            total_dirs = len(preview["directories"])
            total_files = len(preview["files"])
            if total_dirs > 0 or total_files > 0:
                logger.summary(
                    "Sync Summary",
                    [
                        f"{total_dirs} directories synced",
                        f"{total_files} files synced",
                        f"Excluded {len(all_excludes)} patterns",
                    ],
                )
        else:
            # Use captured stderr output from the thread
            stderr_text = "".join(stderr_output) if stderr_output else ""
            raise subprocess.CalledProcessError(
                process.returncode, rsync_cmd, stderr=stderr_text
            )

    except subprocess.CalledProcessError as e:
        logger = get_logger()
        error_details = []
        if e.stderr:
            error_details.append(e.stderr)
        if e.stdout:
            if error_details:
                error_details.append(f"\nstdout: {e.stdout}")
            else:
                error_details.append(e.stdout)

        with logger.command_output(
            command="rsync sync",
            status="failed",
            exit_code=e.returncode,
        ) as cmd_output:
            if error_details:
                cmd_output.write("\n".join(error_details))

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
    ssh_cmd = "ssh"
    if remote_config.port:
        ssh_cmd = f"ssh -p {remote_config.port}"
    rsync_cmd = [
        "rsync",
        "-avz",
        "--progress",
        "-e",
        ssh_cmd,
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
            with logger.command_output(
                command="rclone sync",
                status="failed",
                exit_code=exit_code,
            ) as cmd_output:
                cmd_output.write(result_msg)

        # Append to history log
        with open(history_path, "a") as history_file:
            history_file.write(result_msg + "\n")

        if exit_code != 0:
            raise click.ClickException(f"rclone sync failed with exit code {exit_code}")

    except Exception as e:
        with logger.command_output(
            command="rclone sync",
            status="failed",
        ) as cmd_output:
            cmd_output.write(f"Error during sync: {str(e)}")
        raise click.ClickException(str(e))
