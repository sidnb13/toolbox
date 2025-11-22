from __future__ import annotations  # noqa: INP001

import os
import subprocess
import time
from importlib.resources import files
from pathlib import Path

import click

from mltoolbox.utils.db import DB
from mltoolbox.utils.remote import update_env_file

from .helpers import RemoteConfig, remote_cmd
from .logger import get_logger


def ensure_ray_head_node(remote_config: RemoteConfig | None, python_version: str):
    """Ensure Ray head node is running on the remote host.

    Args:
        remote_config: Remote configuration for connection
        git_name: GitHub username for container image
        python_version: Python version to use (e.g., "3.12")
        variant: Base image variant to use (e.g., "cuda", "gh200")
    """
    logger = get_logger()

    if not remote_config:
        return

    # Check NVIDIA Container Toolkit before building containers
    check_nvidia_container_toolkit(remote_config, variant="cuda")

    # Check if Ray head is running (try to connect to port 6379)
    result = remote_cmd(
        remote_config,
        ["nc -z localhost 6379 2>/dev/null || echo 'not_running'"],
        use_working_dir=False,
    )

    if "not_running" in result.stdout:
        logger.step("Starting Ray head node on remote host")

        # Get paths for Ray head files
        temp_files_to_cleanup = []

        # Use modern importlib.resources
        ray_head_compose_content = (
            files("mltoolbox") / "base" / "docker-compose-ray-head.yml"
        ).read_bytes()
        ray_head_dockerfile_content = (
            files("mltoolbox") / "base" / "Dockerfile.ray-head"
        ).read_bytes()

        # Create temporary files
        import tempfile

        ray_head_compose = Path(tempfile.mktemp(suffix=".yml"))
        ray_head_dockerfile = Path(tempfile.mktemp(suffix=".dockerfile"))
        temp_files_to_cleanup.extend([ray_head_compose, ray_head_dockerfile])

        ray_head_compose.write_bytes(ray_head_compose_content)
        ray_head_dockerfile.write_bytes(ray_head_dockerfile_content)

        try:
            # Create directory for compose file
            remote_cmd(
                remote_config,
                ["mkdir -p ~/ray"],
                use_working_dir=False,
            )

            # Copy files to remote
            scp_cmd1 = ["scp"]
            if remote_config.port:
                scp_cmd1.extend(["-P", str(remote_config.port)])
            scp_cmd1.extend(
                [
                    str(ray_head_compose),
                    f"{remote_config.username}@{remote_config.host}:~/ray/docker-compose.yml",
                ]
            )
            subprocess.run(scp_cmd1, check=False)

            scp_cmd2 = ["scp"]
            if remote_config.port:
                scp_cmd2.extend(["-P", str(remote_config.port)])
            scp_cmd2.extend(
                [
                    str(ray_head_dockerfile),
                    f"{remote_config.username}@{remote_config.host}:~/ray/Dockerfile.ray-head",
                ]
            )
            subprocess.run(scp_cmd2, check=False)

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
                logger.warning(f"Initial Ray head node start failed: {e}")
                logger.step("Cleaning Docker cache and retrying")

                # Clean Docker cache and retry with --no-cache
                try:
                    remote_cmd(
                        remote_config,
                        ["docker system prune -f"],
                        use_working_dir=False,
                    )
                    logger.success("Docker cache cleaned")
                except Exception as cleanup_error:
                    logger.warning(f"Cache cleanup failed: {cleanup_error}")

                logger.step("Retrying build without cache")
                # Retry with --no-cache if first attempt fails
                remote_cmd(
                    remote_config,
                    [
                        f"cd ~/ray && DOCKER_BUILDKIT=0 PYTHON_VERSION={python_version} docker compose build --no-cache && docker compose up -d"
                    ],
                    use_working_dir=False,
                )

            # Wait for Ray to be ready
            with logger.spinner("Waiting for Ray head node to be ready"):
                for _ in range(10):
                    time.sleep(2)
                    result = remote_cmd(
                        remote_config,
                        ["nc -z localhost 6379 2>/dev/null || echo 'not_running'"],
                        use_working_dir=False,
                    )
                    if "not_running" not in result.stdout:
                        logger.success("Ray head node is ready")
                        break
                else:
                    logger.warning(
                        "Ray head node not responding after timeout, continuing anyway"
                    )
        finally:
            # Clean up temporary files
            for temp_file in temp_files_to_cleanup:
                try:
                    if temp_file.exists():
                        temp_file.unlink()
                except Exception:
                    pass  # Ignore cleanup errors


def check_nvidia_container_toolkit(
    remote: RemoteConfig, skip_gpu_check: bool = False, variant: str = "cuda"
) -> None:
    """Check if NVIDIA Container Toolkit is properly installed and configured using official NVIDIA docs."""
    logger = get_logger()

    # Skip GPU check for non-GPU variants
    if skip_gpu_check or variant not in ["cuda", "gh200"]:
        logger.info(
            f"Skipping NVIDIA Container Toolkit check (variant: {variant}, GPU not required)"
        )
        return

    # 1. Try the official GPU test first
    if test_gpu_access(remote, skip_gpu_check=variant not in ["cuda", "gh200"]):
        logger.success("NVIDIA Container Toolkit and GPU access already working.")
        return

    try:
        # Check if NVIDIA drivers are available
        try:
            nvidia_smi_result = remote_cmd(
                remote, ["nvidia-smi --query-gpu=name --format=csv,noheader,nounits"]
            )
            gpu_count = (
                len(nvidia_smi_result.stdout.strip().split("\n"))
                if nvidia_smi_result.stdout.strip()
                else 0
            )
            logger.info(f"Detected {gpu_count} NVIDIA GPU(s)")
        except Exception:
            logger.warning("No NVIDIA GPUs detected or nvidia-smi not available")
            return

        # Detect OS
        os_result = remote_cmd(
            remote, ["cat /etc/os-release | grep '^ID=' | cut -d'=' -f2 | tr -d '\"'"]
        )
        os_id = os_result.stdout.strip()

        # Install NVIDIA Container Toolkit using official steps
        if os_id in ["ubuntu", "debian"]:
            logger.info(
                "Installing NVIDIA Container Toolkit on Ubuntu/Debian (official method)"
            )
            # Add NVIDIA GPG key and repo (official multi-line command)
            remote_cmd(
                remote,
                [
                    "curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --batch --yes --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg && "
                    "curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | "
                    "sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | "
                    "sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list"
                ],
            )
            # Update and install with version pinning
            remote_cmd(
                remote,
                ["sudo apt-get update"],
            )
            remote_cmd(
                remote,
                [
                    "export NVIDIA_CONTAINER_TOOLKIT_VERSION=1.17.8-1 && "
                    "sudo apt-get install -y "
                    "nvidia-container-toolkit=${NVIDIA_CONTAINER_TOOLKIT_VERSION} "
                    "nvidia-container-toolkit-base=${NVIDIA_CONTAINER_TOOLKIT_VERSION} "
                    "libnvidia-container-tools=${NVIDIA_CONTAINER_TOOLKIT_VERSION} "
                    "libnvidia-container1=${NVIDIA_CONTAINER_TOOLKIT_VERSION}"
                ],
            )
            # Configure Docker to use NVIDIA runtime (official method)
            remote_cmd(remote, ["sudo nvidia-ctk runtime configure --runtime=docker"])
            remote_cmd(remote, ["sudo systemctl restart docker"])
        elif os_id in ["centos", "rhel", "rocky", "almalinux", "fedora"]:
            logger.info(
                "Installing NVIDIA Container Toolkit on RHEL/CentOS/Fedora (official method)"
            )
            remote_cmd(
                remote,
                [
                    "curl -s -L https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo | "
                    "sudo tee /etc/yum.repos.d/nvidia-container-toolkit.repo"
                ],
            )
            remote_cmd(
                remote,
                [
                    "sudo yum install -y nvidia-container-toolkit nvidia-container-toolkit-base libnvidia-container-tools libnvidia-container1"
                ],
            )
        elif os_id in ["opensuse", "sles"]:
            logger.info(
                "Installing NVIDIA Container Toolkit on OpenSUSE/SLE (official method)"
            )
            remote_cmd(
                remote,
                [
                    "sudo zypper ar https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo"
                ],
            )
            remote_cmd(
                remote,
                [
                    "sudo zypper --gpg-auto-import-keys install -y nvidia-container-toolkit nvidia-container-toolkit-base libnvidia-container-tools libnvidia-container1"
                ],
            )
        else:
            logger.warning(
                f"Unsupported OS: {os_id}. Please install NVIDIA Container Toolkit manually."
            )
            return

        # Test the installation
        logger.step("Testing NVIDIA Container Toolkit installation (official method)")
        test_gpu_access(remote, skip_gpu_check=variant not in ["cuda", "gh200"])

    except Exception as e:
        logger.error(f"NVIDIA Container Toolkit check failed: {e}")
        logger.warning("Continuing without NVIDIA Container Toolkit verification")


def test_gpu_access(remote: RemoteConfig, skip_gpu_check: bool = False) -> bool:
    """Test if GPU access is working in containers using the official NVIDIA test command."""
    logger = get_logger()
    if skip_gpu_check:
        logger.info("Skipping GPU access test (GPU not required)")
        return True
    try:
        result = remote_cmd(
            remote,
            [
                "sudo docker run --rm --gpus all ubuntu nvidia-smi --query-gpu=name --format=csv,noheader"
            ],
        )
        gpu_names = [
            line.strip() for line in result.stdout.splitlines() if line.strip()
        ]
        if gpu_names:
            logger.success(
                f"GPU access in Docker container verified! Detected {len(gpu_names)} GPU(s): {', '.join(gpu_names)}"
            )
            return True
        else:
            logger.error("No GPUs detected in container. GPU access failed.")
            return False
    except Exception as e:
        logger.error(f"GPU access check failed: {e}")
        return False


def check_docker_group(remote: RemoteConfig, force: bool = False) -> None:
    """Check if Docker is properly configured and user is in docker group."""
    logger = get_logger()

    try:
        # Check if user is in docker group
        result = remote_cmd(remote, ["groups"])
        needs_group_setup = "docker" not in result.stdout

        # Check if we can use docker without sudo
        try:
            remote_cmd(remote, ["docker ps -q"])
            docker_working = True
        except click.exceptions.ClickException:
            docker_working = False

        if needs_group_setup or not docker_working:
            logger.step("Setting up Docker permissions")

            # Add docker group if needed
            remote_cmd(remote, ["sudo groupadd -f docker"])

            # Add current user to docker group
            remote_cmd(remote, ["sudo usermod -aG docker $USER"])

            # Fix docker socket permissions
            remote_cmd(remote, ["sudo chmod 666 /var/run/docker.sock"])

            logger.success("Docker permissions set up successfully")

            # Verify docker now works without sudo
            try:
                remote_cmd(remote, ["docker ps -q"], reload_session=True)
                logger.success("Docker now works without sudo")
            except subprocess.CalledProcessError:
                logger.warning("Docker still requires sudo - continuing with sudo")

        # Check if docker daemon uses the right cgroup driver
        result = remote_cmd(
            remote,
            [
                "if [ -f /etc/docker/daemon.json ] && "
                'grep -q \'"native.cgroupdriver":"cgroupfs"\' /etc/docker/daemon.json; then '
                "echo 'configured'; else echo 'needs_config'; fi",
            ],
        )

        if "needs_config" in result.stdout:
            # Check for running containers before modifying daemon config
            running_containers = (
                remote_cmd(
                    remote,
                    ["docker ps --format '{{.Names}}' | wc -l"],
                ).stdout.strip()
                or 0
            )

            if int(running_containers) > 0:
                # List running containers
                containers = remote_cmd(
                    remote,
                    ["docker ps --format '{{.Names}}'"],
                ).stdout.strip()

                logger.warning(
                    f"WARNING: {running_containers} containers currently running:"
                )
                logger.info(containers)
                logger.warning(
                    "Changing Docker daemon configuration will restart Docker and KILL all running containers!"
                )

                if not force and not click.confirm(
                    "Do you want to continue and modify Docker configuration?",
                    default=False,
                ):
                    logger.warning(
                        "Docker configuration skipped. Some features may not work correctly."
                    )
                    return

                logger.step("Configuring Docker cgroup driver")
                remote_cmd(
                    remote,
                    [
                        "sudo mkdir -p /etc/docker && "
                        'echo \'{"exec-opts": ["native.cgroupdriver=cgroupfs"]}\' | sudo tee /etc/docker/daemon.json && '
                        "sudo systemctl restart docker",
                    ],
                )
                logger.success("Docker cgroup driver configured")

        # Verify Docker is working
        logger.success("Docker is properly configured")

    except Exception as e:
        logger.error(f"Docker configuration check failed: {e}")
        raise


def find_available_port(remote_config: RemoteConfig | None, start_port: int) -> int:
    """Find an available port starting from the given port."""
    import socket

    def is_port_in_use(port):
        if remote_config:
            # Check on remote host
            cmd = f"nc -z 127.0.0.1 {port} && echo 'In use' || echo 'Available'"
            result = remote_cmd(remote_config, [cmd])
            return "In use" in result.stdout
        # Check locally
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("127.0.0.1", port)) == 0

    port = start_port
    while is_port_in_use(port):
        port += 1

    return port


def get_image_digest(
    image: str,
    remote: bool = False,
    remote_config: RemoteConfig | None = None,
) -> str:
    def docker_cmd(cmd):
        return (
            remote_cmd(remote_config, cmd)
            if remote_config
            else subprocess.run(cmd, capture_output=True, text=True, check=False)
        )

    if remote:
        git_name = os.getenv("GIT_NAME")
        github_token = os.getenv("GITHUB_TOKEN")
        docker_cmd(
            ["docker", "login", "ghcr.io", "-u", git_name, "--password-stdin"],
        ).input = github_token.encode()

        result = docker_cmd(["docker", "manifest", "inspect", image])
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if '"digest":' in line:
                    return line.split(":")[2].strip(' ",')
    else:
        result = docker_cmd(
            ["docker", "image", "inspect", image, "--format={{index .Id}}"],
        )
        if result.returncode == 0:
            return result.stdout.strip().split(":")[1]
    return "none"


def start_container(
    project_name: str,
    container_name: str,
    remote_config: RemoteConfig | None = None,
    build=False,
    host_ray_dashboard_port=None,
    branch_name: str | None = None,
    network_mode: str | None = None,  # Add this parameter
    dryrun: bool = False,
    python_version: str | None = None,
    variant: str = "cuda",  # Add variant parameter
) -> None:
    logger = get_logger()
    if dryrun:
        with logger.panel_output(
            f"Start Container: {container_name}", subtitle="[DRY RUN]", status="success"
        ) as panel:
            panel.write(
                f"Would start container: {container_name} for project {project_name}\nSimulated Docker start, no actions taken."
            )
        logger.success("[DRY RUN] Container start simulated.")
        return

    # Check NVIDIA Container Toolkit before starting containers
    if remote_config:
        check_nvidia_container_toolkit(remote_config, variant=variant)

    def cmd_wrap(cmd):
        if remote_config:
            return remote_cmd(remote_config, cmd)
        return subprocess.run(
            cmd,
            stdout=None,
            stderr=None,
            text=True,
            check=False,
        )

    def cmd_output(cmd):
        if remote_config:
            return remote_cmd(remote_config, cmd)
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

    # Check container status to determine if we need to rebuild
    container_name = container_name.lower()

    container_status_cmd = [
        "docker",
        "ps",
        "-a",
        "--filter",
        f"name={container_name}",
        "--format",
        "{{.Status}}",
    ]
    status_result = cmd_output(container_status_cmd)

    # Auto-enable build if container doesn't exist, is unhealthy, or has exited
    if not build:
        if status_result.returncode != 0 or not status_result.stdout.strip():
            logger.step(
                f"Container {container_name} not found. Will build from scratch."
            )
            build = True
        elif (
            "Exited" in status_result.stdout
            or "unhealthy" in status_result.stdout.lower()
        ):
            logger.step(
                f"Container {container_name} is in unhealthy state. Rebuilding..."
            )
            build = True
        elif "Restarting" in status_result.stdout:
            logger.step(
                f"Container {container_name} is in a restart loop. Rebuilding..."
            )
            build = True

    # Only need to worry about Ray dashboard port
    if not host_ray_dashboard_port:
        host_ray_dashboard_port = find_available_port(remote_config, 8265)

    # Only update the Ray dashboard port in the env file
    env_updates = {
        "RAY_DASHBOARD_PORT": host_ray_dashboard_port,
    }

    env_vars = update_env_file(remote_config, project_name, env_updates)

    if python_version:
        env_vars["PYTHON_VERSION"] = python_version

    # Store only dashboard port in database
    if remote_config:
        db = DB()
        db.upsert_remote(
            username=remote_config.username,
            host=remote_config.host,
            project_name=project_name,
            container_name=container_name,
            port_mappings={
                "ray_dashboard": host_ray_dashboard_port,
            },
        )

    service_name = (
        container_name.replace("-" + branch_name, "") if branch_name else container_name
    )

    # Start in detached mode with explicit env vars
    if remote_config:
        # For remote, prepend env vars to the command
        env_string = " ".join([f"{k}={v}" for k, v in env_vars.items()])
        env_string = f"COMPOSE_BAKE=true {env_string}"  # Always set COMPOSE_BAKE

        base_cmd = f"{env_string} docker compose up -d"
        if build:
            base_cmd += " --build"

        if network_mode:
            base_cmd += f" --network {network_mode}"

        base_cmd += f" {service_name}"
        cmd_wrap([base_cmd])
    else:
        # For local, use environment parameter
        env_vars = env_vars.copy()
        env_vars["COMPOSE_BAKE"] = "true"
        base_cmd = ["docker", "compose", "up", "-d"]
        if build:
            base_cmd.append("--build")
        base_cmd.append(service_name)

        if network_mode:
            base_cmd.extend(["--network", network_mode])

        subprocess.run(
            base_cmd,
            env=env_vars,
            stdout=None,
            stderr=None,
            text=True,
            check=False,
        )
