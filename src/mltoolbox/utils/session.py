import os
import subprocess
import threading
import time

import click
import paramiko

from .logger import get_logger


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
            cls._instance._agent_initialized = False
            cls._instance._agent_lock = threading.Lock()
        return cls._instance

    def __init__(self):
        # Skip initialization if already done
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

    def ensure_ssh_agent(self) -> bool:
        """Ensure SSH agent is running. Returns True if agent is available."""
        logger = get_logger()

        with self._agent_lock:
            if self._agent_initialized:
                # Verify agent is still running
                try:
                    result = subprocess.run(
                        ["ssh-add", "-l"],
                        capture_output=True,
                        text=True,
                        env=os.environ.copy(),
                    )
                    if result.returncode == 0:
                        return True
                    # Agent died, need to restart
                    logger.debug("SSH agent no longer running, will restart")
                    self._agent_initialized = False
                except Exception as e:
                    logger.debug(f"Error checking SSH agent: {e}")
                    self._agent_initialized = False

            # Check if agent is already running (from environment or system)
            # First check if environment variables are set and socket exists
            sock_path = os.environ.get("SSH_AUTH_SOCK")
            if sock_path:
                # Verify socket file actually exists
                if os.path.exists(sock_path):
                    try:
                        result = subprocess.run(
                            ["ssh-add", "-l"],
                            capture_output=True,
                            text=True,
                            env=os.environ.copy(),
                        )
                        if result.returncode == 0:
                            self._agent_initialized = True
                            return True
                    except Exception:
                        pass
                else:
                    # Socket doesn't exist, clear the env var
                    logger.debug(
                        f"SSH_AUTH_SOCK points to non-existent file: {sock_path}"
                    )
                    os.environ.pop("SSH_AUTH_SOCK", None)
                    os.environ.pop("SSH_AGENT_PID", None)

            # Try checking without env vars (might use system agent)
            try:
                result = subprocess.run(
                    ["ssh-add", "-l"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    self._agent_initialized = True
                    return True
            except Exception:
                pass

            # Start new agent
            logger.debug("Starting SSH agent...")
            try:
                agent_output = subprocess.run(
                    ["ssh-agent", "-s"],
                    capture_output=True,
                    text=True,
                )
                if agent_output.returncode == 0:
                    # Parse and export SSH_AUTH_SOCK and SSH_AGENT_PID
                    # ssh-agent outputs: SSH_AUTH_SOCK=/path; export SSH_AUTH_SOCK;
                    sock_path = None
                    pid = None
                    for line in agent_output.stdout.splitlines():
                        # Handle format: SSH_AUTH_SOCK=/path; export SSH_AUTH_SOCK;
                        if line.startswith("SSH_AUTH_SOCK="):
                            # Extract path before semicolon
                            sock_path = (
                                line.split("=", 1)[1].split(";")[0].strip().strip("'\"")
                            )
                            os.environ["SSH_AUTH_SOCK"] = sock_path
                        elif line.startswith("SSH_AGENT_PID="):
                            # Extract PID before semicolon
                            pid = (
                                line.split("=", 1)[1].split(";")[0].strip().strip("'\"")
                            )
                            os.environ["SSH_AGENT_PID"] = pid
                        # Also handle export format just in case
                        elif line.startswith("export SSH_AUTH_SOCK="):
                            sock_path = line.split("=", 1)[1].strip().strip("'\"")
                            os.environ["SSH_AUTH_SOCK"] = sock_path
                        elif line.startswith("export SSH_AGENT_PID="):
                            pid = line.split("=", 1)[1].strip().strip("'\"")
                            os.environ["SSH_AGENT_PID"] = pid

                    if not sock_path:
                        logger.warning(
                            "Failed to parse SSH_AUTH_SOCK from ssh-agent output"
                        )
                        logger.debug(f"ssh-agent output: {agent_output.stdout}")
                        return False

                    # Verify socket file exists - if it does, agent is running
                    # Give it a moment to create the socket file
                    for _ in range(5):  # Try up to 5 times with small delay
                        if os.path.exists(sock_path):
                            self._agent_initialized = True
                            logger.debug(
                                f"SSH agent started successfully (socket: {sock_path})"
                            )
                            return True
                        time.sleep(0.1)  # Wait 100ms

                    # If socket still doesn't exist, check if PID is running
                    if pid:
                        try:
                            # Check if process is running (Unix-specific)
                            os.kill(
                                int(pid), 0
                            )  # Signal 0 just checks if process exists
                            # Process exists, socket should be there - mark as initialized anyway
                            self._agent_initialized = True
                            logger.debug(
                                f"SSH agent process running (PID: {pid}), socket: {sock_path}"
                            )
                            return True
                        except (OSError, ValueError):
                            pass

                    logger.warning(f"SSH agent socket file does not exist: {sock_path}")
                    return False
                else:
                    error_msg = (
                        agent_output.stderr.strip()
                        if agent_output.stderr
                        else "Unknown error"
                    )
                    logger.warning(f"Failed to start SSH agent: {error_msg}")
                    return False
            except Exception as e:
                logger.warning(f"Exception starting SSH agent: {e}")
                return False

            return False

    def reset_agent_state(self) -> None:
        """Reset agent initialization state (useful when agent dies)."""
        with self._agent_lock:
            self._agent_initialized = False

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
            logger = get_logger()
            logger.step(f"Establishing new SSH session to {hostname}")
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

    def reload_session(
        self, hostname: str, username: str, **connect_kwargs
    ) -> paramiko.SSHClient:
        """Force reload a session to pick up new group memberships or environment changes."""
        session_key = self._get_session_key(hostname, username)

        logger = get_logger()
        logger.step(f"Reloading SSH session for {username}@{hostname}")

        # Remove the existing session if it exists
        if session_key in self._sessions:
            with self._locks.get(session_key, threading.Lock()):
                self._remove_session(session_key)
            logger.success("Previous session closed")

        # Let get_session create a new connection
        return self.get_session(hostname, username, **connect_kwargs)


session_manager = SSHSessionManager()
