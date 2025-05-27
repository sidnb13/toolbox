"""
Subprocess utilities with integrated logging and output handling.
"""

import subprocess

from .logger import get_logger


class SubprocessRunner:
    """Enhanced subprocess runner with logging integration."""

    def __init__(self):
        self.logger = get_logger()

    def run_with_live_output(
        self,
        cmd: str | list[str],
        title: str,
        cwd: str | None = None,
        env: dict | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess:
        """
        Run command with live output in a bordered panel.

        Args:
            cmd: Command to run
            title: Title for the output panel
            cwd: Working directory
            env: Environment variables
            shell: Whether to use shell

        Returns:
            CompletedProcess result
        """
        if isinstance(cmd, str) and not shell:
            cmd = cmd.split()

        with self.logger.live_output(title) as output:
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1,
                    cwd=cwd,
                    env=env,
                    shell=shell,
                )

                # Read output line by line
                for line in iter(process.stdout.readline, ""):
                    output.write(line)

                process.wait()

                if process.returncode == 0:
                    self.logger.success(f"{title} completed successfully")
                else:
                    self.logger.failure(
                        f"{title} failed with exit code {process.returncode}"
                    )

                return subprocess.CompletedProcess(cmd, process.returncode, None, None)

            except Exception as e:
                self.logger.error(f"Failed to run {title}: {e}")
                raise

    def run_with_panel_output(
        self,
        cmd: str | list[str],
        title: str,
        cwd: str | None = None,
        env: dict | None = None,
        shell: bool = False,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess:
        """
        Run command and display output in a panel after completion.

        Args:
            cmd: Command to run
            title: Title for the output panel
            cwd: Working directory
            env: Environment variables
            shell: Whether to use shell
            capture_output: Whether to capture and display output

        Returns:
            CompletedProcess result
        """
        if isinstance(cmd, str) and not shell:
            cmd = cmd.split()

        try:
            with self.logger.spinner(f"Running {title}..."):
                result = subprocess.run(
                    cmd,
                    capture_output=capture_output,
                    text=True,
                    cwd=cwd,
                    env=env,
                    shell=shell,
                    check=False,
                )

            if capture_output and (result.stdout or result.stderr):
                output_content = ""
                if result.stdout:
                    output_content += result.stdout
                if result.stderr:
                    if output_content:
                        output_content += "\n" + "─" * 40 + " STDERR " + "─" * 40 + "\n"
                    output_content += result.stderr

                with self.logger.panel_output(
                    title, subtitle=f"Exit code: {result.returncode}"
                ) as panel:
                    panel.write(output_content)

            if result.returncode == 0:
                self.logger.success(f"{title} completed successfully")
            else:
                self.logger.failure(
                    f"{title} failed with exit code {result.returncode}"
                )

            return result

        except Exception as e:
            self.logger.error(f"Failed to run {title}: {e}")
            raise

    def run_silent(
        self,
        cmd: str | list[str],
        cwd: str | None = None,
        env: dict | None = None,
        shell: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """
        Run command silently, only logging errors.

        Args:
            cmd: Command to run
            cwd: Working directory
            env: Environment variables
            shell: Whether to use shell
            check: Whether to raise on non-zero exit

        Returns:
            CompletedProcess result
        """
        if isinstance(cmd, str) and not shell:
            cmd = cmd.split()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=cwd,
                env=env,
                shell=shell,
                check=False,
            )

            if check and result.returncode != 0:
                cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
                self.logger.error(f"Command failed: {cmd_str}")
                if result.stderr:
                    self.logger.error(f"Error output: {result.stderr}")
                raise subprocess.CalledProcessError(
                    result.returncode, cmd, result.stdout, result.stderr
                )

            return result

        except subprocess.CalledProcessError:
            raise
        except Exception as e:
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
            self.logger.error(f"Failed to run command '{cmd_str}': {e}")
            raise


# Global subprocess runner instance
subprocess_runner = SubprocessRunner()


def run_with_live_output(*args, **kwargs) -> subprocess.CompletedProcess:
    """Convenience function for live output subprocess."""
    return subprocess_runner.run_with_live_output(*args, **kwargs)


def run_with_panel_output(*args, **kwargs) -> subprocess.CompletedProcess:
    """Convenience function for panel output subprocess."""
    return subprocess_runner.run_with_panel_output(*args, **kwargs)


def run_silent(*args, **kwargs) -> subprocess.CompletedProcess:
    """Convenience function for silent subprocess."""
    return subprocess_runner.run_silent(*args, **kwargs)
