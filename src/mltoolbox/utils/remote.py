import datetime
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import click

from mltoolbox.utils.docker import start_container as docker_start_container
from mltoolbox.utils.stage_cache import SetupStage

from .helpers import RemoteConfig, remote_cmd


@SetupStage(name="zshrc_setup", description="Setting up zshrc configuration")
def setup_zshrc_stage(remote_config: RemoteConfig, project_name: str):
    """Set up basic zshrc configuration on remote host."""
    setup_zshrc(remote_config)
    return True


@SetupStage(name="rclone_setup", description="Setting up rclone configuration")
def setup_rclone_stage(remote_config: RemoteConfig, project_name: str):
    """Set up rclone configuration on remote host."""
    setup_rclone(remote_config)
    return True


@SetupStage(name="create_project_dirs", description="Creating project directories")
def create_project_dirs_stage(remote_config: RemoteConfig, project_name: str):
    """Create project directories on remote host."""
    click.echo(f"📁 Creating remote project directories for {project_name}")
    remote_cmd(
        remote_config,
        [f"mkdir -p ~/projects/{project_name}"],
        use_working_dir=False,
    )
    return True


@SetupStage(
    name="docker_group_check",
    description="Verifying Docker group membership",
    cache_key_func=lambda kwargs: {"username": kwargs.get("username", "ubuntu")},
)
def check_docker_group_stage(
    remote_config: RemoteConfig, project_name: str, username: str = "ubuntu"
):
    """Check if Docker is properly configured and user is in docker group."""
    from mltoolbox.utils.docker import check_docker_group

    result = check_docker_group(remote_config)
    if result:
        click.echo("✅ Docker group checked")
    return result


@SetupStage(
    name="project_sync",
    description="Syncing project files",
    cache_key_func=lambda kwargs: {
        "exclude": kwargs.get("exclude", ""),
        "skip_sync": kwargs.get("skip_sync", False),
    },
)
def sync_project_stage(
    remote_config: RemoteConfig,
    project_name: str,
    exclude: str = "",
    skip_sync: bool = False,
):
    """Sync project files to remote host."""
    if skip_sync:
        click.echo("Skipping project sync, continuing with SSH key sync...")
        return True

    sync_project(
        remote_config,
        project_name,
        remote_path=project_name,
        exclude=exclude,
    )
    return True


@SetupStage(
    name="env_file_update",
    description="Updating environment configuration",
    cache_key_func=lambda kwargs: {
        "variant": kwargs.get("variant", "cuda"),
        "env_variant": kwargs.get("env_variant", "default"),
        "python_version": kwargs.get("python_version", None),
    },
)
def update_env_file_stage(
    remote_config: RemoteConfig,
    project_name: str,
    variant: str = "cuda",
    env_variant: str = "default",
    python_version: str = None,
):
    """Update environment file on remote host."""
    # Set up environment updates
    env_updates = {
        "VARIANT": variant,
        "ENV_VARIANT": env_variant,
        "NVIDIA_DRIVER_CAPABILITIES": "all",
        "NVIDIA_VISIBLE_DEVICES": "all",
    }

    # Add Python version to environment if specified
    if python_version:
        env_updates["PYTHON_VERSION"] = python_version
        click.echo(f"🐍 Setting Python version to {python_version}")

    click.echo(
        f"🔧 Updating environment with variant '{variant}' and env-variant '{env_variant}'..."
    )
    update_env_file(remote_config, project_name, env_updates)
    return True


@SetupStage(
    name="ssh_keys_setup",
    description="Setting up SSH keys",
    cache_key_func=lambda kwargs: {
        "ssh_key_name": kwargs.get("ssh_key_name", "id_ed25519")
    },
)
def setup_ssh_keys_stage(
    remote_config: RemoteConfig, project_name: str, ssh_key_name: str = "id_ed25519"
):
    """Set up SSH keys on remote host."""
    return setup_remote_ssh_keys(remote_config, ssh_key_name)


@SetupStage(
    name="container_start",
    description="Starting container",
    cache_key_func=lambda kwargs: {
        "container_name": kwargs.get("container_name", ""),
        "force_rebuild": kwargs.get("force_rebuild", False),
        "host_ray_dashboard_port": kwargs.get("host_ray_dashboard_port", None),
        "host_ray_client_port": kwargs.get("host_ray_client_port", None),
        "variant": kwargs.get("variant", "cuda"),
        "env_variant": kwargs.get("env_variant", "default"),
        "python_version": kwargs.get("python_version", None),
    },
)
def start_container_stage(
    remote_config: RemoteConfig,
    project_name: str,
    container_name: str,
    force_rebuild: bool = False,
    host_ray_dashboard_port: str = None,
    host_ray_client_port: str = None,
    variant: str = "cuda",
    env_variant: str = "default",
    python_version: str = None,
):
    """Start the container on remote host."""
    click.echo("🚀 Starting remote container...")
    docker_start_container(
        project_name,
        container_name,
        remote_config=remote_config,
        build=force_rebuild,
        host_ray_dashboard_port=host_ray_dashboard_port,
        host_ray_client_port=host_ray_client_port,
    )
    return True


@SetupStage(
    name="conda_env_setup",
    description="Setting up conda environment",
    cache_key_func=lambda kwargs: {
        "env_name": kwargs.get("env_name", "mltoolbox"),
        "python_version": kwargs.get("python_version", "3.12"),
    },
)
def setup_conda_env_stage(
    remote_config: RemoteConfig,
    project_name: str,
    env_name: str = "mltoolbox",
    python_version: str = "3.12",
):
    """Set up conda environment on remote host."""
    click.echo("🔧 Setting up conda environment...")
    setup_conda_env(remote_config, env_name, python_version)
    return True


def setup_ssh_config_stage(remote, project_name):
    """Set up SSH configuration for the remote host."""
    # create custom ssh config if not exists
    ssh_config_path = Path("~/.config/mltoolbox/ssh/config").expanduser()
    ssh_config_path.parent.mkdir(parents=True, exist_ok=True)

    # add include directive to main ssh config if needed
    main_ssh_config_path = Path("~/.ssh/config").expanduser()
    include_line = f"Include {ssh_config_path}\n"

    if not main_ssh_config_path.exists():
        main_ssh_config_path.touch()

    with main_ssh_config_path.open("r") as f:
        content = f.read()

    if include_line not in content:
        with main_ssh_config_path.open("w") as f:
            f.write(include_line + content)

    # Read existing config and filter out previous entries for this host/alias
    existing_config = []
    current_host = None
    skip_block = False

    if ssh_config_path.exists():
        with ssh_config_path.open("r") as f:
            for line in f:
                if line.startswith("Host "):
                    current_host = line.split()[1].strip()
                    # Skip this block if it matches our alias, regardless of host
                    skip_block = current_host == remote.alias
                if not skip_block:
                    existing_config.append(line)
                elif not line.strip() or line.startswith("Host "):
                    skip_block = False

    # Write updated config
    with ssh_config_path.open("w") as f:
        # Write existing entries (excluding the one we're updating)
        f.writelines(existing_config)

        # Add a newline if the file doesn't end with one
        if existing_config and not existing_config[-1].endswith("\n"):
            f.write("\n")

        # Write the new/updated entry
        f.write(f"Host {remote.alias}\n")
        f.write(f"    HostName {remote.host}\n")
        f.write(f"    User {remote.username}\n")
        f.write("    ForwardAgent yes\n\n")

    click.echo(f"Access your instance with `ssh {remote.alias}`")
    return True


def connect_ssh_session(
    remote, project_name, mode, container_name, env_name, forward_ports
):
    """Connect to remote host via SSH with appropriate command.

    Args:
        remote: Remote database object
        project_name: Project name
        mode: Connection mode (ssh, container, conda)
        container_name: Container name to use
        env_name: Conda environment name
        forward_ports: List of port forwarding specifications

    Returns:
        None (executes SSH command)
    """
    # Determine command based on mode
    if mode == "container":
        cmd = f"cd ~/projects/{project_name} && docker compose exec -it -w /workspace/{project_name} {container_name} zsh"
    elif mode == "ssh":
        cmd = f"cd ~/projects/{project_name} && zsh"
    elif mode == "conda":
        cmd = f"cd ~/projects/{project_name} && export PATH=$HOME/miniconda3/bin:$PATH && source $HOME/miniconda3/etc/profile.d/conda.sh && conda activate {env_name} && zsh"

    # Build SSH command with port forwarding
    ssh_args = [
        "ssh",
        "-A",  # Forward SSH agent
        "-o",
        "ControlMaster=no",
        "-o",
        "ExitOnForwardFailure=no",
        "-o",
        "ServerAliveInterval=60",
        "-o",
        "ServerAliveCountMax=3",
    ]

    # Add port forwarding arguments
    for port_mapping in forward_ports:
        if port_mapping:
            local_port, remote_port = port_mapping.split(":")
            ssh_args.extend(["-L", f"{local_port}:localhost:{remote_port}"])

    # Add remaining SSH arguments
    ssh_args.extend(["-t", f"{remote.username}@{remote.host}", cmd])

    # Execute SSH command
    os.execvp("ssh", ssh_args)  # noqa: S606


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
