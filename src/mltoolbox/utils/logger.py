"""
Sophisticated logging system for mltoolbox with colorlog and rich console output.
"""

import logging
import re
import sys
import threading
from contextlib import contextmanager
from datetime import datetime

import colorlog
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
)

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

    def hint(self, message: str):
        """Display a helpful hint or tip."""
        now = datetime.now().strftime("%H:%M:%S")
        self.console.print(f"{now}  [yellow]💡[/yellow]  [dim]{message}[/dim]")

    def summary(self, title: str, items: list[str]):
        """Display a completion summary with items."""
        now = datetime.now().strftime("%H:%M:%S")
        self.console.print()  # Blank line for spacing
        self.console.print(f"{now}  [bold green]✓[/bold green]  [bold]{title}[/bold]")
        for idx, item in enumerate(items):
            prefix = "      └─ " if idx == len(items) - 1 else "      ├─ "
            self.console.print(f"{prefix}[dim]{item}[/dim]")
        self.console.print()  # Blank line after summary

    def empty_state(self, message: str, suggestion: str | None = None):
        """Display an empty state message."""
        now = datetime.now().strftime("%H:%M:%S")
        self.console.print(f"{now}  [grey37]○[/grey37]  [dim]{message}[/dim]")
        if suggestion:
            self.console.print(f"      └─ [dim italic]{suggestion}[/dim italic]")

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
        """Log success message with subtle indicator."""
        now = datetime.now().strftime("%H:%M:%S")
        if self.dryrun:
            message = f"[DRY RUN] {message}"
        self.console.print(f"{now}  [green]✓[/green]  [dim]{message}[/dim]")

    def failure(self, message: str):
        """Log failure message with subtle indicator."""
        now = datetime.now().strftime("%H:%M:%S")
        if self.dryrun:
            message = f"[DRY RUN] {message}"
        self.console.print(f"{now}  [red]✗[/red]  [dim]{message}[/dim]")

    def step(self, message: str):
        """Log a step in the process with subtle indicator."""
        now = datetime.now().strftime("%H:%M:%S")
        if self.dryrun:
            message = f"[DRY RUN] {message}"
        self.console.print(f"{now}  [blue]→[/blue]  [dim]{message}[/dim]")

    def section(self, title: str):
        """Print a compact section header."""
        now = datetime.now().strftime("%H:%M:%S")
        prefix = "[DRY RUN] " if self.dryrun else ""
        self.console.print(
            f"{now}  [bold blue]●[/bold blue]  [bold]{prefix}{title}[/bold]"
        )

    @contextmanager
    def spinner(self, message: str):
        """Context manager for spinner during long operations."""
        # Try to acquire the live lock, but don't block
        if self._live_lock.acquire(blocking=False):
            try:
                # Use compact spinner
                now = datetime.now().strftime("%H:%M:%S")
                if self.dryrun:
                    message = f"[DRY RUN] {message}"
                with Progress(
                    SpinnerColumn(style="blue"),
                    TextColumn(f"{now}  [blue]⟳[/blue]  [dim]{message}[/dim]"),
                    console=self.console,
                    transient=True,
                ) as progress:
                    task = progress.add_task("", total=None)
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
    def command_output(
        self,
        command: str,
        status: str = None,
        exit_code: int = None,
        duration: float = None,
    ):
        """Context manager for compact command output with tree-style formatting."""
        import time as _time

        _time.time()
        content_lines = []
        cmd_status = status
        cmd_exit_code = exit_code
        cmd_duration = duration
        dryrun = self.dryrun

        class CommandCapture:
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

        capture = CommandCapture()
        try:
            yield capture
        finally:
            _time.time()
            # Determine status indicator
            if cmd_status == "success":
                indicator = "[green]●[/green]"
            elif cmd_status == "failed":
                indicator = "[red]●[/red]"
            else:
                indicator = "[grey37]●[/grey37]"

            # Compose timestamp and indicator
            now = datetime.now().strftime("%H:%M:%S")
            timestamp_indicator = f"{now}  {indicator}"

            # Truncate command if too long
            display_cmd = command
            max_cmd_length = 60
            if len(display_cmd) > max_cmd_length:
                display_cmd = display_cmd[: max_cmd_length - 3] + "..."

            # Build metadata line
            metadata_parts = []
            if dryrun:
                metadata_parts.append("[DRY RUN]")
            if cmd_exit_code is not None:
                metadata_parts.append(f"Exit code: {cmd_exit_code}")
            if cmd_duration is not None:
                metadata_parts.append(f"Duration: {cmd_duration:.2f}s")
            metadata = "  ".join(metadata_parts)

            # Print main line with command
            self.console.print(f"{timestamp_indicator}  [dim]{display_cmd}[/dim]")

            # Determine if we have both metadata and output
            has_output = bool(content_lines)
            has_metadata = bool(metadata)

            # Print metadata and output with tree-style indentation
            if has_metadata or has_output:
                filtered_lines = []
                if content_lines:
                    prev_line = None
                    for line in content_lines:
                        if line != prev_line and line.strip():
                            filtered_lines.append(line)
                            prev_line = line

                # Determine tree characters based on what follows
                if has_metadata and has_output:
                    # Metadata is not last, use ├─
                    metadata_prefix = "      ├─ "
                    # Output lines use │  except the last one
                    output_prefix = "      │  "
                    last_output_prefix = "      └─ "
                elif has_metadata:
                    # Only metadata, use └─
                    metadata_prefix = "      └─ "
                    output_prefix = None
                    last_output_prefix = None
                else:
                    # Only output
                    metadata_prefix = None
                    output_prefix = "      │  "
                    last_output_prefix = "      └─ "

                # Print metadata
                if has_metadata and metadata_prefix:
                    self.console.print(f"{metadata_prefix}[dim]{metadata}[/dim]")

                # Print output content with tree indentation
                if filtered_lines:
                    # Limit output to first few lines for compactness
                    max_output_lines = 5
                    output_lines = filtered_lines[:max_output_lines]
                    total_lines = len(output_lines)

                    for idx, line in enumerate(output_lines):
                        # Truncate very long lines
                        if len(line) > 80:
                            line = line[:77] + "..."

                        # Use appropriate prefix based on position
                        if idx == total_lines - 1:
                            # Last line uses └─
                            prefix = (
                                last_output_prefix
                                if last_output_prefix
                                else "      └─ "
                            )
                        else:
                            # Middle lines use │
                            prefix = output_prefix if output_prefix else "      │  "

                        self.console.print(f"{prefix}[dim]{line}[/dim]")

                    if len(filtered_lines) > max_output_lines:
                        remaining = len(filtered_lines) - max_output_lines
                        self.console.print(
                            f"      └─ [dim]... ({remaining} more lines)[/dim]"
                        )

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

        if self._live_lock.acquire(blocking=False):
            try:
                content_buffer = []
                last_update_time = 0
                _time.time()
                # Use compact format for live updates
                initial_display = f"{datetime.now().strftime('%H:%M:%S')}  [blue]⟳[/blue]  [dim]{title}[/dim]"
                with Live(
                    initial_display,
                    console=self.console,
                    refresh_per_second=5,
                    transient=True,
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
                                        # Be less aggressive with filtering - show meaningful lines
                                        if line and len(line.strip()) > 0:
                                            # Only filter obvious noise, keep most content
                                            if not self._is_noise_line(line):
                                                content_buffer.append(line)
                                    if len(content_buffer) > 30:
                                        content_buffer = content_buffer[-30:]
                                    if current_time - last_update_time > 0.2:
                                        now = datetime.now().strftime("%H:%M:%S")
                                        # Show last few lines in compact format
                                        recent_lines = (
                                            content_buffer[-3:]
                                            if len(content_buffer) > 3
                                            else content_buffer
                                        )
                                        if recent_lines:
                                            display_lines = "\n".join(
                                                [
                                                    f"      │  [dim]{line[:80]}[/dim]"
                                                    if len(line) <= 80
                                                    else f"      │  [dim]{line[:77]}...[/dim]"
                                                    for line in recent_lines
                                                ]
                                            )
                                            live.update(
                                                f"{now}  [blue]⟳[/blue]  [dim]{title}[/dim]\n{display_lines}"
                                            )
                                        else:
                                            live.update(
                                                f"{now}  [blue]⟳[/blue]  [dim]{title}[/dim]  [dim]Processing...[/dim]"
                                            )
                                        last_update_time = current_time

                        def flush(self):
                            pass

                    yield LiveCapture()
                    # Live display will auto-close when context exits
                # After Live context exits, show compact final output
                if content_buffer:
                    # Extract command from title (e.g., "Remote Docker Command on 150.230.39.56" -> "docker command")
                    # Try to extract a meaningful command name
                    cmd_name = title.lower()
                    if "docker" in cmd_name:
                        cmd_name = "docker command"
                    elif "command" in cmd_name:
                        cmd_name = "remote command"
                    else:
                        cmd_name = title

                    # Filter and clean content
                    filtered_lines = []
                    prev_line = None
                    for line in content_buffer:
                        if line != prev_line and line.strip():
                            filtered_lines.append(line)
                            prev_line = line

                    # Use compact tree-style output
                    now = datetime.now().strftime("%H:%M:%S")
                    indicator = "[green]●[/green]"
                    self.console.print(f"{now}  {indicator}  [dim]{cmd_name}[/dim]")

                    if filtered_lines:
                        max_output_lines = 5
                        output_lines = filtered_lines[:max_output_lines]
                        total_lines = len(output_lines)

                        for idx, line in enumerate(output_lines):
                            # Truncate very long lines
                            if len(line) > 80:
                                line = line[:77] + "..."

                            # Use tree characters
                            if idx == total_lines - 1:
                                prefix = "      └─ "
                            else:
                                prefix = "      │  "

                            self.console.print(f"{prefix}[dim]{line}[/dim]")

                        if len(filtered_lines) > max_output_lines:
                            remaining = len(filtered_lines) - max_output_lines
                            self.console.print(
                                f"      └─ [dim]... ({remaining} more lines)[/dim]"
                            )
            finally:
                self._live_lock.release()
        else:
            # Fallback: use compact command_output format if live display unavailable
            content_lines = []

            class FallbackCapture:
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

            try:
                yield FallbackCapture()
            finally:
                # Show compact output
                cmd_name = title.lower()
                if "docker" in cmd_name:
                    cmd_name = "docker command"
                elif "command" in cmd_name:
                    cmd_name = "remote command"

                now = datetime.now().strftime("%H:%M:%S")
                indicator = "[green]●[/green]"
                self.console.print(f"{now}  {indicator}  [dim]{cmd_name}[/dim]")

                if content_lines:
                    filtered_lines = []
                    prev_line = None
                    for line in content_lines:
                        if line != prev_line and line.strip():
                            filtered_lines.append(line)
                            prev_line = line

                    if filtered_lines:
                        max_output_lines = 5
                        output_lines = filtered_lines[:max_output_lines]
                        total_lines = len(output_lines)

                        for idx, line in enumerate(output_lines):
                            if len(line) > 80:
                                line = line[:77] + "..."

                            if idx == total_lines - 1:
                                prefix = "      └─ "
                            else:
                                prefix = "      │  "

                            self.console.print(f"{prefix}[dim]{line}[/dim]")

                        if len(filtered_lines) > max_output_lines:
                            remaining = len(filtered_lines) - max_output_lines
                            self.console.print(
                                f"      └─ [dim]... ({remaining} more lines)[/dim]"
                            )

    def _is_noise_line(self, line: str) -> bool:
        """Determine if a line is noise that should be filtered out."""
        line_lower = line.lower().strip()

        # Skip empty lines
        if not line_lower:
            return True

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
            return True

        # Skip lines that are just timing or progress indicators
        if re.match(r"^\s*\d+\.\d+s\s*$", line):
            return True
        if re.match(r"^\s*\[\d+/\d+\]\s*$", line):
            return True
        if re.match(r"^\s*#\d+\s*$", line):
            return True

        # Skip lines with ONLY special characters or whitespace (but allow lines with content + special chars)
        if re.match(r"^[\s\[\]\(\)\-\+\=\>\<\|\.]*$", line) and len(line.strip()) < 5:
            return True

        # Most lines should be shown - only filter obvious noise
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
