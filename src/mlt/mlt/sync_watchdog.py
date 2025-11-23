"""Watchdog daemon to sync packages to LSP view using hardlinks."""

import subprocess
import sys
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class PackageSyncHandler(FileSystemEventHandler):
    """Handler that syncs site-packages to LSP view on changes."""

    def __init__(
        self, site_packages: Path, lsp_packages: Path, debounce_seconds: float = 1.0
    ):
        self.site_packages = site_packages
        self.lsp_packages = lsp_packages
        self.debounce_seconds = debounce_seconds
        self.last_sync_time = 0

    def sync_packages(self):
        """Sync packages using hardlinks (cp -alu)."""
        current_time = time.time()

        # Debounce: only sync if enough time has passed
        if current_time - self.last_sync_time < self.debounce_seconds:
            return

        try:
            # Use cp -alu to hardlink new/updated files only
            subprocess.run(
                [
                    "cp",
                    "-alu",  # archive + hardlink + update
                    f"{self.site_packages}/.",
                    f"{self.lsp_packages}/",
                ],
                check=True,
                capture_output=True,
            )
            self.last_sync_time = current_time
            print("[mlt] ✅ Synced packages to LSP view", file=sys.stderr, flush=True)
        except subprocess.CalledProcessError as e:
            print(f"[mlt] ⚠️  Sync failed: {e}", file=sys.stderr, flush=True)

    def on_created(self, event):
        """Called when a file or directory is created."""
        if not event.is_directory and "__pycache__" not in event.src_path:
            print(
                f"[mlt] 📦 Package change detected: {Path(event.src_path).name}",
                file=sys.stderr,
                flush=True,
            )
            self.sync_packages()

    def on_modified(self, event):
        """Called when a file or directory is modified."""
        if not event.is_directory and "__pycache__" not in event.src_path:
            self.sync_packages()

    def on_deleted(self, event):
        """Called when a file or directory is deleted."""
        if not event.is_directory and "__pycache__" not in event.src_path:
            # For deletions, we might want to remove from LSP view too
            # But hardlinks make this tricky - deleting source doesn't delete hardlink
            # For now, just log it
            print(
                f"[mlt] 🗑️  Package deleted: {Path(event.src_path).name}",
                file=sys.stderr,
                flush=True,
            )


def run_sync_watchdog(site_packages: Path, lsp_packages: Path, daemon: bool = False):
    """
    Run watchdog to monitor site-packages and sync to LSP view.

    Args:
        site_packages: Path to real site-packages directory
        lsp_packages: Path to LSP view directory (mounted)
        daemon: If True, run in background mode
    """
    # Ensure directories exist
    if not site_packages.exists():
        print(f"[mlt] ERROR: site-packages not found: {site_packages}", file=sys.stderr)
        return 1

    if not lsp_packages.exists():
        print(
            f"[mlt] ERROR: LSP packages directory not found: {lsp_packages}",
            file=sys.stderr,
        )
        return 1

    # Initial sync
    print("[mlt] 🔗 Starting LSP sync watchdog...", file=sys.stderr, flush=True)
    print(f"[mlt]   Watching: {site_packages}", file=sys.stderr, flush=True)
    print(f"[mlt]   Syncing to: {lsp_packages}", file=sys.stderr, flush=True)

    handler = PackageSyncHandler(site_packages, lsp_packages)

    # Do initial sync
    handler.sync_packages()

    # Set up observer
    observer = Observer()
    observer.schedule(handler, str(site_packages), recursive=True)
    observer.start()

    print(
        "[mlt] 👀 Watchdog running (press Ctrl+C to stop)", file=sys.stderr, flush=True
    )

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[mlt] 🛑 Stopping watchdog...", file=sys.stderr, flush=True)
        observer.stop()

    observer.join()
    return 0
