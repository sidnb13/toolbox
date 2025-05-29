"""
Subprocess utilities with integrated logging and output handling.
"""

import subprocess
import time as _time

from .logger import get_logger


class SubprocessRunner:
    """Enhanced subprocess runner with logging integration."""

    def __init__(self, dryrun: bool = False):
        self.logger = get_logger()
        self.dryrun = dryrun

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
        """
        if self.dryrun:
            with self.logger.live_output(f"{title} [DRY RUN]") as output:
                for i in range(10):
                    output.write(f"Simulated output line {i + 1}\n")
                    _time.sleep(0.1)
            self.logger.success(f"[DRY RUN] {title} completed successfully")
            return subprocess.CompletedProcess(cmd, 0, "Simulated stdout", "")
        if isinstance(cmd, str) and not shell:
            cmd = cmd.split()
        start_time = _time.time()
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
                for line in iter(process.stdout.readline, ""):
                    output.write(line)
                process.wait()
                duration = _time.time() - start_time
                if process.returncode == 0:
                    self.logger.success(
                        f"{title} completed successfully in {duration:.2f}s"
                    )
                else:
                    self.logger.failure(
                        f"{title} failed with exit code {process.returncode} in {duration:.2f}s"
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
        """
        if self.dryrun:
            with self.logger.panel_output(
                f"{title}", subtitle="[DRY RUN]", status="success"
            ) as panel:
                panel.write(
                    f"Would run: {cmd}\nSimulated output...\nAll actions skipped."
                )
            self.logger.success(f"[DRY RUN] {title} completed successfully")
            return subprocess.CompletedProcess(cmd, 0, "Simulated stdout", "")
        if isinstance(cmd, str) and not shell:
            cmd = cmd.split()
        start_time = _time.time()
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
            duration = _time.time() - start_time
            status = "success" if result.returncode == 0 else "failed"
            output_content = ""
            if capture_output and (result.stdout or result.stderr):
                if result.stdout:
                    output_content += result.stdout
                if result.stderr:
                    if output_content:
                        output_content += "\n" + "─" * 40 + " STDERR " + "─" * 40 + "\n"
                    output_content += result.stderr
            with self.logger.panel_output(
                title,
                subtitle=f"Exit code: {result.returncode}",
                status=status,
                exit_code=result.returncode,
                duration=duration,
            ) as panel:
                panel.write(output_content)
            if result.returncode == 0:
                self.logger.success(
                    f"{title} completed successfully in {duration:.2f}s"
                )
            else:
                self.logger.failure(
                    f"{title} failed with exit code {result.returncode} in {duration:.2f}s"
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
        if self.dryrun:
            self.logger.info(f"[DRY RUN] Would run silently: {cmd}")
            return subprocess.CompletedProcess(cmd, 0, "Simulated stdout", "")
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
