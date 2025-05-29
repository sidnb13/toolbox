"""
Enhanced Docker operations with sophisticated logging.
"""

from typing import Any

from .helpers import RemoteConfig, remote_cmd
from .logger import get_logger
from .subprocess_helper import run_silent, run_with_live_output, run_with_panel_output


class EnhancedDockerRunner:
    """Docker operations with enhanced logging and output handling."""

    def __init__(self, remote_config: RemoteConfig | None = None, dryrun: bool = False):
        self.logger = get_logger()
        self.remote_config = remote_config
        self.dryrun = dryrun

    def build_image(
        self,
        dockerfile_path: str,
        tag: str,
        context_path: str = ".",
        build_args: dict[str, str] | None = None,
        no_cache: bool = False,
        live_output: bool = True,
    ) -> bool:
        """
        Build Docker image with enhanced logging.

        Args:
            dockerfile_path: Path to Dockerfile
            tag: Image tag
            context_path: Build context path
            build_args: Build arguments
            no_cache: Whether to use --no-cache
            live_output: Whether to show live output or panel output

        Returns:
            bool: True if build succeeded
        """
        import time as _time

        self.logger.section(f"Building Docker Image: {tag}")
        if self.dryrun:
            import random
            import time as _time

            steps = [
                "Step 1/7 : FROM python:3.10",
                "Step 2/7 : COPY . /app",
                "Step 3/7 : RUN pip install -r requirements.txt",
                "Step 4/7 : RUN pytest",
                "Step 5/7 : EXPOSE 8080",
                "Step 6/7 : CMD ['python', 'main.py']",
                "Step 7/7 : LABEL version=1.0",
                f"Successfully built {''.join(random.choices('abcdef1234567890', k=12))}",
            ]
            with self.logger.live_output(f"Docker Build: {tag} [DRY RUN]") as output:
                for step in steps:
                    output.write(step + "\n")
                    _time.sleep(0.2)
            self.logger.success(f"[DRY RUN] Successfully built image: {tag}")
            return True
        cmd = ["docker", "build", "-f", dockerfile_path, "-t", tag]
        if no_cache:
            cmd.append("--no-cache")
        if build_args:
            for key, value in build_args.items():
                cmd.extend(["--build-arg", f"{key}={value}"])
        cmd.append(context_path)
        try:
            start_time = _time.time()
            if self.remote_config:
                cmd_str = " ".join(cmd)
                if live_output:
                    with self.logger.live_output(f"Docker Build: {tag}") as output:
                        result = remote_cmd(
                            self.remote_config,
                            [cmd_str],
                            use_working_dir=True,
                        )
                        output.write(result.stdout)
                        if result.stderr:
                            output.write(f"\nSTDERR:\n{result.stderr}")
                else:
                    result = remote_cmd(self.remote_config, [cmd_str])
                    duration = _time.time() - start_time
                    with self.logger.panel_output(
                        f"Docker Build: {tag}",
                        subtitle=f"Exit code: {result.returncode}",
                        status="success" if result.returncode == 0 else "failed",
                        exit_code=result.returncode,
                        duration=duration,
                    ) as panel:
                        panel.write(result.stdout)
                        if result.stderr:
                            panel.write(f"\nSTDERR:\n{result.stderr}")
                success = result.returncode == 0
            else:
                if live_output:
                    result = run_with_live_output(cmd, f"Docker Build: {tag}")
                else:
                    result = run_with_panel_output(cmd, f"Docker Build: {tag}")
                success = result.returncode == 0
            duration = _time.time() - start_time
            if success:
                self.logger.success(
                    f"Successfully built image: {tag} in {duration:.2f}s"
                )
            else:
                self.logger.failure(f"Failed to build image: {tag} in {duration:.2f}s")
            return success
        except Exception as e:
            self.logger.error(f"Docker build failed: {e}")
            return False

    def run_container(
        self,
        image: str,
        name: str | None = None,
        ports: dict[str, str] | None = None,
        volumes: dict[str, str] | None = None,
        env_vars: dict[str, str] | None = None,
        detach: bool = True,
        remove: bool = False,
        network: str | None = None,
    ) -> bool:
        """
        Run Docker container with enhanced logging.

        Args:
            image: Docker image to run
            name: Container name
            ports: Port mappings {host_port: container_port}
            volumes: Volume mappings {host_path: container_path}
            env_vars: Environment variables
            detach: Run in detached mode
            remove: Remove container when it exits
            network: Network to connect to

        Returns:
            bool: True if container started successfully
        """
        self.logger.step(f"Starting container from image: {image}")
        if self.dryrun:
            with self.logger.panel_output(
                f"Run Container: {image}",
                subtitle="[DRY RUN]",
                status="success",
            ) as panel:
                panel.write(
                    f"Would run: docker run ... {image}\nSimulating container start...\nContainer ID: abcdef123456 (simulated)"
                )
            self.logger.success("[DRY RUN] Container started successfully")
            return True
        cmd = ["docker", "run"]

        if detach:
            cmd.append("-d")

        if remove:
            cmd.append("--rm")

        if name:
            cmd.extend(["--name", name])

        if network:
            cmd.extend(["--network", network])

        if ports:
            for host_port, container_port in ports.items():
                cmd.extend(["-p", f"{host_port}:{container_port}"])

        if volumes:
            for host_path, container_path in volumes.items():
                cmd.extend(["-v", f"{host_path}:{container_path}"])

        if env_vars:
            for key, value in env_vars.items():
                cmd.extend(["-e", f"{key}={value}"])

        cmd.append(image)

        try:
            if self.remote_config:
                cmd_str = " ".join(cmd)
                result = remote_cmd(self.remote_config, [cmd_str])
                success = result.returncode == 0

                if success:
                    self.logger.success("Container started successfully")
                    if result.stdout.strip():
                        self.logger.info(f"Container ID: {result.stdout.strip()}")
                else:
                    self.logger.failure("Failed to start container")
                    if result.stderr:
                        self.logger.error(f"Error: {result.stderr}")
            else:
                result = run_silent(cmd, check=False)
                success = result.returncode == 0

                if success:
                    self.logger.success("Container started successfully")
                    if result.stdout.strip():
                        self.logger.info(f"Container ID: {result.stdout.strip()}")
                else:
                    self.logger.failure("Failed to start container")
                    if result.stderr:
                        self.logger.error(f"Error: {result.stderr}")

            return success

        except Exception as e:
            self.logger.error(f"Failed to run container: {e}")
            return False

    def compose_up(
        self,
        compose_file: str = "docker-compose.yml",
        project_name: str | None = None,
        detach: bool = True,
        build: bool = False,
        env_vars: dict[str, str] | None = None,
    ) -> bool:
        """
        Run docker-compose up with enhanced logging.

        Args:
            compose_file: Path to compose file
            project_name: Project name
            detach: Run in detached mode
            build: Build images before starting
            env_vars: Environment variables

        Returns:
            bool: True if compose up succeeded
        """
        import time as _time

        self.logger.section("Starting Docker Compose Services")
        if self.dryrun:
            import time as _time

            services = ["web", "db", "worker"]
            with self.logger.live_output("Docker Compose Up [DRY RUN]") as output:
                for svc in services:
                    output.write(f"Creating service {svc}...\n")
                    _time.sleep(0.2)
                output.write("All services simulated as started.\n")
            self.logger.success(
                "[DRY RUN] Docker Compose services started successfully"
            )
            return True
        cmd = ["docker", "compose", "-f", compose_file]
        if project_name:
            cmd.extend(["-p", project_name])
        cmd.append("up")
        if detach:
            cmd.append("-d")
        if build:
            cmd.append("--build")
        try:
            start_time = _time.time()
            env = None
            if env_vars:
                import os

                env = os.environ.copy()
                env.update(env_vars)
            if self.remote_config:
                env_prefix = ""
                if env_vars:
                    env_prefix = (
                        " ".join([f"{k}={v}" for k, v in env_vars.items()]) + " "
                    )
                cmd_str = env_prefix + " ".join(cmd)
                with self.logger.live_output("Docker Compose Up") as output:
                    result = remote_cmd(self.remote_config, [cmd_str])
                    output.write(result.stdout)
                    if result.stderr:
                        output.write(f"\nSTDERR:\n{result.stderr}")
                success = result.returncode == 0
            else:
                result = run_with_live_output(cmd, "Docker Compose Up", env=env)
                success = result.returncode == 0
            duration = _time.time() - start_time
            if success:
                self.logger.success(
                    f"Docker Compose services started successfully in {duration:.2f}s"
                )
            else:
                self.logger.failure(
                    f"Failed to start Docker Compose services in {duration:.2f}s"
                )
            return success
        except Exception as e:
            self.logger.error(f"Docker Compose failed: {e}")
            return False

    def get_container_status(self, name_or_id: str) -> dict[str, Any] | None:
        """Get container status information."""
        try:
            cmd = ["docker", "inspect", name_or_id, "--format", "{{json .}}"]

            if self.remote_config:
                result = remote_cmd(self.remote_config, [" ".join(cmd)])
                output = result.stdout
            else:
                result = run_silent(cmd)
                output = result.stdout

            if result.returncode == 0:
                import json

                return json.loads(output)
            else:
                return None

        except Exception as e:
            self.logger.debug(f"Failed to get container status: {e}")
            return None

    def show_container_logs(self, name_or_id: str, lines: int = 50):
        """Show container logs with enhanced formatting."""
        try:
            cmd = ["docker", "logs", "--tail", str(lines), name_or_id]

            if self.remote_config:
                result = remote_cmd(self.remote_config, [" ".join(cmd)])
                with self.logger.panel_output(
                    f"Container Logs: {name_or_id}", subtitle=f"Last {lines} lines"
                ) as panel:
                    panel.write(result.stdout)
                    if result.stderr:
                        panel.write(f"\nSTDERR:\n{result.stderr}")
            else:
                result = run_with_panel_output(cmd, f"Container Logs: {name_or_id}")

        except Exception as e:
            self.logger.error(f"Failed to show container logs: {e}")


def get_docker_runner(
    remote_config: RemoteConfig | None = None,
) -> EnhancedDockerRunner:
    """Get an enhanced Docker runner instance."""
    return EnhancedDockerRunner(remote_config)
