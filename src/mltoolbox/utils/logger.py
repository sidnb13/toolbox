"""
Sophisticated logging system for mltoolbox with colorlog and rich console output.
"""

import logging
import re
import sys
import threading
from contextlib import contextmanager

import colorlog
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# ANSI escape sequence pattern - more comprehensive
ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
# Additional control characters to strip
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
# Cursor movement and other terminal control sequences
CURSOR_CONTROL = re.compile(r"\x1B\[[0-9;]*[A-Za-z]")


def clean_terminal_output(text: str) -> str:
    """Clean terminal output by removing ANSI escape sequences and control characters."""
    # Remove ANSI escape sequences
    text = ANSI_ESCAPE.sub("", text)
    # Remove cursor control sequences
    text = CURSOR_CONTROL.sub("", text)
    # Remove other control characters
    text = CONTROL_CHARS.sub("", text)

    # Remove cursor positioning sequences more aggressively
    text = re.sub(r"\x1b\[[0-9]*[ABCD]", "", text)  # Cursor movement
    text = re.sub(r"\x1b\[[0-9]*[JK]", "", text)  # Clear sequences
    text = re.sub(r"\x1b\[2J", "", text)  # Clear screen
    text = re.sub(r"\x1b\[H", "", text)  # Home cursor
    text = re.sub(r"\x1b\[\?25[hl]", "", text)  # Show/hide cursor

    # Docker-specific cleaning - more aggressive patterns
    docker_noise_patterns = [
        r"^\s*\d+\.\d+s\s*$",  # Timing indicators
        r"^\s*\[\d+/\d+\]\s*$",  # Progress indicators
        r"^\s*#\d+\s*$",  # Step numbers
        r"^\s*\.\.\.\s*$",  # Ellipsis
        r"^\s*\r\s*$",  # Carriage returns
        r"^\s*\x1b\[[0-9;]*[mK]\s*$",  # Remaining escape sequences
        r"^\s*\[?\+\]?\s*Building\s+\d+\.\d+s.*$",  # Docker build progress
        r"^\s*=>\s*.*$",  # Docker build steps
        r"^\s*\[1A\[.*$",  # Cursor movement artifacts
        r"^\s*\[0G.*$",  # Cursor positioning artifacts
        r"^\s*\[\?25[hl].*$",  # Cursor visibility artifacts
    ]

    lines = text.split("\n")
    cleaned_lines = []

    for line in lines:
        # Skip lines that match Docker noise patterns
        if any(re.match(pattern, line) for pattern in docker_noise_patterns):
            continue

        # Remove inline cursor control sequences
        line = re.sub(r"\x1b\[[0-9]*[ABCD]", "", line)
        line = re.sub(r"\x1b\[[0-9]*[JK]", "", line)
        line = re.sub(r"\[\d+[AG]", "", line)

        # Clean up the line
        line = line.rstrip()
        if line and len(line.strip()) > 2:  # Only keep meaningful lines
            cleaned_lines.append(line)

    # Join lines and remove excessive whitespace
    text = "\n".join(cleaned_lines)
    # Remove excessive newlines but preserve structure
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    return text


class MLToolboxLogger:
    """Centralized logger for mltoolbox with rich formatting."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.console = Console(stderr=True)
        self.logger = self._setup_logger()
        self._live_lock = threading.Lock()  # Lock to prevent concurrent Live displays
        self._initialized = True
        self.dryrun = False

    def _setup_logger(self) -> logging.Logger:
        """Set up colorlog logger with rich formatting."""
        logger = logging.getLogger("mltoolbox")
        logger.setLevel(logging.INFO)

        # Remove existing handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        # Create colorlog handler
        handler = colorlog.StreamHandler(sys.stderr)
        handler.setFormatter(
            colorlog.ColoredFormatter(
                "%(log_color)s%(levelname)-8s%(reset)s %(blue)s%(name)s%(reset)s %(message)s",
                datefmt=None,
                reset=True,
                log_colors={
                    "DEBUG": "cyan",
                    "INFO": "green",
                    "WARNING": "yellow",
                    "ERROR": "red",
                    "CRITICAL": "red,bg_white",
                },
                secondary_log_colors={},
                style="%",
            )
        )

        logger.addHandler(handler)
        logger.propagate = False

        return logger

    def set_dryrun(self, dryrun: bool = True):
        self.dryrun = dryrun

    def info(self, message: str, **kwargs):
        """Log info message."""
        if self.dryrun:
            message = f"[DRY RUN] {message}"
        self.logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message."""
        if self.dryrun:
            message = f"[DRY RUN] {message}"
        self.logger.warning(message, **kwargs)

    def error(self, message: str, **kwargs):
        """Log error message."""
        if self.dryrun:
            message = f"[DRY RUN] {message}"
        self.logger.error(message, **kwargs)

    def debug(self, message: str, **kwargs):
        """Log debug message."""
        if self.dryrun:
            message = f"[DRY RUN] {message}"
        self.logger.debug(message, **kwargs)

    def success(self, message: str):
        """Log success message (no emoji, just green text)."""
        if self.dryrun:
            message = f"[DRY RUN] {message}"
        self.console.print(f"[green]{message}[/green]")

    def failure(self, message: str):
        """Log failure message (no emoji, just red text)."""
        if self.dryrun:
            message = f"[DRY RUN] {message}"
        self.console.print(f"[red]{message}[/red]")

    def step(self, message: str):
        """Log a step in the process (no emoji, just blue text)."""
        if self.dryrun:
            message = f"[DRY RUN] {message}"
        self.console.print(f"[blue]{message}[/blue]")

    def section(self, title: str):
        """Print a section header with timestamp and horizontal rule."""
        from datetime import datetime

        now = datetime.now().strftime("%H:%M:%S")
        prefix = "[DRY RUN] " if self.dryrun else ""
        self.console.print(f"[bold blue]{now}  {prefix}{title}[/bold blue]")
        self.console.print("[grey37]" + "─" * 60 + "[/grey37]")

    @contextmanager
    def spinner(self, message: str):
        """Context manager for spinner during long operations."""
        # Try to acquire the live lock, but don't block
        if self._live_lock.acquire(blocking=False):
            try:
                # Use spinner if we can get the lock
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=self.console,
                    transient=True,
                ) as progress:
                    task = progress.add_task(description=message, total=None)
                    try:
                        yield progress
                    finally:
                        progress.remove_task(task)
            finally:
                self._live_lock.release()
        else:
            # Fallback to simple step message if live display is already active
            self.step(message)
            yield None

    @contextmanager
    def panel_output(
        self,
        title: str,
        subtitle: str | None = None,
        status: str = None,
        exit_code: int = None,
        duration: float = None,
    ):
        """Context manager for bordered output panel with summary and clean look."""
        import time as _time
        from datetime import datetime

        _time.time()
        content_lines = []
        panel_status = status
        panel_exit_code = exit_code
        panel_duration = duration
        dryrun = self.dryrun

        class PanelCapture:
            def write(self, text):
                if text.strip():
                    clean_text = clean_terminal_output(text)
                    if clean_text.strip():
                        lines = [
                            line.rstrip()
                            for line in clean_text.split("\n")
                            if line.strip()
                        ]
                        content_lines.extend(lines)

            def flush(self):
                pass

        capture = PanelCapture()
        try:
            yield capture
        finally:
            _time.time()
            if content_lines:
                filtered_lines = []
                prev_line = None
                for line in content_lines:
                    if line != prev_line and line.strip():
                        filtered_lines.append(line)
                        prev_line = line
                content = "\n".join(filtered_lines)
                # Compose summary line
                now = datetime.now().strftime("%H:%M:%S")
                summary = f"{now}  "
                if dryrun:
                    summary += "[DRY RUN] "
                if panel_status:
                    summary += f"{panel_status.upper()}  "
                if panel_exit_code is not None:
                    summary += f"Exit code: {panel_exit_code}  "
                if panel_duration is not None:
                    summary += f"Duration: {panel_duration:.2f}s"
                border_style = "grey37"
                if panel_status == "success":
                    border_style = "green"
                elif panel_status == "failed":
                    border_style = "red"
                panel = Panel(
                    f"[bold]{summary}[/bold]\n[white on black]{content}[/white on black]",
                    title=f"[bold]{title}[/bold]",
                    subtitle=subtitle,
                    border_style=border_style,
                    padding=(0, 2),
                    expand=True,
                )
                self.console.print(panel)

    @contextmanager
    def live_output(self, title: str):
        """Context manager for live updating output with pro CLI look."""
        import time as _time
        from datetime import datetime

        dryrun = self.dryrun
        if self._live_lock.acquire(blocking=False):
            try:
                content_buffer = []
                last_update_time = 0
                _time.time()
                with Live(
                    Panel(
                        "Starting...",
                        title=f"[bold]{title}[/bold]",
                        border_style="grey37",
                        padding=(0, 2),
                        expand=True,
                    ),
                    console=self.console,
                    refresh_per_second=5,  # 0.2s
                ) as live:

                    class LiveCapture:
                        def write(self, content):
                            nonlocal last_update_time
                            current_time = _time.time()
                            if content.strip():
                                clean_content = clean_terminal_output(content)
                                if clean_content.strip():
                                    lines = clean_content.split("\n")
                                    for line in lines:
                                        line = line.strip()
                                        if line and self._should_show_line(line):
                                            content_buffer.append(line)
                                    if len(content_buffer) > 30:
                                        content_buffer = content_buffer[-30:]
                                    if current_time - last_update_time > 0.2:
                                        now = datetime.now().strftime("%H:%M:%S")
                                        header = f"[bold]{now}  {'[DRY RUN] ' if dryrun else ''}{title}[/bold]"
                                        display_text = (
                                            "\n".join(content_buffer)
                                            if content_buffer
                                            else "Processing..."
                                        )
                                        live.update(
                                            Panel(
                                                f"{header}\n[white on black]{display_text}[/white on black]",
                                                border_style="grey37",
                                                padding=(0, 2),
                                                expand=True,
                                            )
                                        )
                                        last_update_time = current_time

                        def flush(self):
                            pass

                    yield LiveCapture()
                    # Final update with all content
                    if content_buffer:
                        now = datetime.now().strftime("%H:%M:%S")
                        header = f"[bold]{now}  {'[DRY RUN] ' if dryrun else ''}{title} - Complete[/bold]"
                        final_content = "\n".join(content_buffer)
                        live.update(
                            Panel(
                                f"{header}\n[white on black]{final_content}[/white on black]",
                                border_style="green",
                                padding=(0, 2),
                                expand=True,
                            )
                        )
            finally:
                self._live_lock.release()
        else:
            with self.panel_output(title) as panel:
                yield panel

    def _should_show_line(self, line: str) -> bool:
        """Determine if a line should be shown in live output."""
        line_lower = line.lower()

        # Skip Docker build noise
        docker_noise = [
            "sending build context",
            "step 1/",
            "step 2/",
            "step 3/",
            "step 4/",
            "step 5/",
            "step 6/",
            "step 7/",
            "step 8/",
            "step 9/",
            "step 10/",
            "---> using cache",
            "---> running in",
            "removing intermediate container",
            "successfully built",
            "successfully tagged",
            "[+] building",
            "=> load build definition",
            "=> load .dockerignore",
            "=> load metadata",
            "=> transferring context",
            "=> transferring dockerfile",
            "=> cached",
            "docker:default",
            "=> =>",
        ]

        # Skip lines that are just Docker build progress
        if any(noise in line_lower for noise in docker_noise):
            return False

        # Skip lines that are just timing or progress indicators
        if re.match(r"^\s*\d+\.\d+s\s*$", line):
            return False
        if re.match(r"^\s*\[\d+/\d+\]\s*$", line):
            return False
        if re.match(r"^\s*#\d+\s*$", line):
            return False

        # Skip lines with just special characters or whitespace
        if re.match(r"^[\s\[\]\(\)\-\+\=\>\<\|]*$", line):
            return False

        # Skip very short lines that are likely noise
        if len(line.strip()) < 3:
            return False

        # Show lines that contain actual meaningful content
        meaningful_indicators = [
            "installing",
            "downloading",
            "building",
            "compiling",
            "error",
            "warning",
            "failed",
            "success",
            "creating",
            "copying",
            "updating",
            "using cpython",
            "creating virtual environment",
            "updated https://",
            "failed to download",
        ]

        if any(indicator in line_lower for indicator in meaningful_indicators):
            return True

        # Show lines that look like actual command output or errors
        if any(char in line for char in [":", "=", "/", "@"]):
            return True

        return False

    def table(self, data: list, headers: list, title: str | None = None):
        """Display data in a formatted table."""
        from rich.table import Table

        table = Table(title=title, show_header=True, header_style="bold blue")

        for header in headers:
            table.add_column(header)

        for row in data:
            table.add_row(*[str(cell) for cell in row])

        self.console.print(table)

    def set_debug(self, debug: bool = True):
        """Enable or disable debug logging."""
        level = logging.DEBUG if debug else logging.INFO
        self.logger.setLevel(level)


# Global logger instance
logger = MLToolboxLogger()


def get_logger() -> MLToolboxLogger:
    """Get the global logger instance."""
    return logger
