import threading
import time

import click
import paramiko


class SSHSessionManager:
    _instance = None

    def __new__(cls: "SSHSessionManager") -> "SSHSessionManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # Initialize instance attributes
            cls._instance._sessions = {}
            cls._instance._locks = {}
            cls._instance._last_used = {}
            cls._instance._cleanup_thread = None
            cls._instance._cleanup_interval = 300
            cls._instance._session_timeout = 1800
        return cls._instance

    def __init__(self):
        # Skip initialization if already done
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

    def _get_session_key(self, hostname: str, username: str) -> str:
        return f"{username}@{hostname}"

    def get_session(
        self, hostname: str, username: str, **connect_kwargs
    ) -> paramiko.SSHClient:
        session_key = self._get_session_key(hostname, username)

        # Create lock if it doesn't exist
        if session_key not in self._locks:
            self._locks[session_key] = threading.Lock()

        with self._locks[session_key]:
            # Check if session exists and is active
            if session_key in self._sessions:
                transport = self._sessions[session_key].get_transport()
                if transport and transport.is_active():
                    try:
                        transport.send_ignore()
                        self._last_used[session_key] = time.time()
                        return self._sessions[session_key]
                    except (EOFError, paramiko.SSHException):
                        self._remove_session(session_key)
                else:
                    self._remove_session(session_key)

            # Create new session
            ssh = paramiko.SSHClient()
            click.echo(f"🔄 Establishing new SSH session to {hostname}...")
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            try:
                ssh.connect(hostname=hostname, username=username, **connect_kwargs)
                self._sessions[session_key] = ssh
                self._last_used[session_key] = time.time()
                self._start_cleanup_thread()
                return ssh
            except Exception as e:
                if session_key in self._sessions:
                    self._remove_session(session_key)
                raise click.ClickException(f"Failed to establish SSH connection: {e}")

    def _remove_session(self, session_key: str) -> None:
        """Safely remove and close a session."""
        if session_key in self._sessions:
            try:
                if self._sessions[session_key].get_transport():
                    self._sessions[session_key].close()
            except:  # noqa: E722
                pass  # Ignore any errors during closure
            self._sessions.pop(session_key, None)
            self._last_used.pop(session_key, None)

    def _cleanup_old_sessions(self) -> None:
        """Clean up expired sessions."""
        current_time = time.time()
        for session_key in list(self._sessions.keys()):
            if (
                current_time - self._last_used.get(session_key, 0)
                > self._session_timeout
            ):
                with self._locks[session_key]:
                    self._remove_session(session_key)

    def _start_cleanup_thread(self) -> None:
        """Start the cleanup thread if it's not already running."""
        if self._cleanup_thread is None or not self._cleanup_thread.is_alive():
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_loop, daemon=True
            )
            self._cleanup_thread.start()

    def _cleanup_loop(self) -> None:
        """Background thread for cleaning up expired sessions."""
        while True:
            time.sleep(self._cleanup_interval)
            self._cleanup_old_sessions()

    def close_all(self) -> None:
        """Close all active sessions."""
        for session_key in list(self._sessions.keys()):
            with self._locks[session_key]:
                self._remove_session(session_key)


session_manager = SSHSessionManager()
