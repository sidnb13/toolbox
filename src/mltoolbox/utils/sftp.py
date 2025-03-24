import os
from pathlib import Path
from typing import Union, List


from mltoolbox.utils.session import session_manager
from mltoolbox.utils.helpers import RemoteConfig, get_ssh_config


class SFTPClient:
    """SFTP client that uses the existing SSH session manager."""

    def __init__(self, remote_config: RemoteConfig, reload_session: bool = False):
        """Initialize SFTP client using the shared SSH session.

        Args:
            remote_config: Remote configuration with host, username, etc.
            reload_session: Whether to force reload the SSH session
        """
        self.remote_config = remote_config
        self.sftp = None
        self.ssh = None
        self._reload = reload_session

    def __enter__(self):
        """Connect to remote host when entering context."""
        # Parse SSH config if the host looks like an alias
        ssh_config = get_ssh_config(self.remote_config.host)
        actual_hostname = ssh_config.get("hostname", self.remote_config.host)
        actual_username = ssh_config.get("user", self.remote_config.username)

        # Get or reload SSH session
        if self._reload:
            self.ssh = session_manager.reload_session(actual_hostname, actual_username)
        else:
            connect_kwargs = {
                "timeout": 10,
                "look_for_keys": True,
                "allow_agent": True,
                "banner_timeout": 60,
            }

            identity_file = ssh_config.get("identityfile", [None])[0]
            if identity_file:
                connect_kwargs["key_filename"] = identity_file

            self.ssh = session_manager.get_session(
                actual_hostname, actual_username, **connect_kwargs
            )

        # Open SFTP channel from the session
        self.sftp = self.ssh.open_sftp()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Close SFTP channel when exiting context."""
        if self.sftp:
            self.sftp.close()
            self.sftp = None
            # Note: We don't close the SSH session since it's managed by session_manager

    def exec_command(self, command: str):
        """Execute a command on the remote system.

        Args:
            command: Command to execute

        Returns:
            tuple: (stdin, stdout, stderr)
        """
        return self.ssh.exec_command(command)

    def _expand_user_path(self, path: str) -> str:
        """Expand user path (~ prefix) on remote system.

        Args:
            path: Path potentially starting with ~

        Returns:
            str: Expanded path
        """
        if not path.startswith("~"):
            return path

        # Get the home directory from the remote system
        stdin, stdout, stderr = self.exec_command("echo $HOME")
        home_dir = stdout.read().decode().strip()

        # Replace ~ with home directory
        return path.replace("~", home_dir, 1)

    def ensure_dir(self, remote_path: str):
        """Ensure remote directory exists, creating it if necessary.

        Args:
            remote_path: Remote directory path
        """
        # Expand ~ if present
        if remote_path.startswith("~"):
            remote_path = self._expand_user_path(remote_path)

        # Check if path exists and is a directory
        try:
            stat = self.sftp.stat(remote_path)
            is_dir = stat.st_mode & 0o40000  # Check if it's a directory
            if not is_dir:
                raise ValueError(f"{remote_path} exists but is not a directory")
            return
        except FileNotFoundError:
            pass  # Directory doesn't exist, will create it

        # Create parent directories recursively
        parent = os.path.dirname(remote_path)
        if parent and parent != "/":
            self.ensure_dir(parent)

        # Create this directory
        try:
            self.sftp.mkdir(remote_path)
        except OSError as e:
            # Directory might have been created by another process
            if "Failure" not in str(e):  # Simple check for "already exists" errors
                raise

    def file_exists(self, remote_path: str) -> bool:
        """Check if a file exists on the remote system.

        Args:
            remote_path: Path to check

        Returns:
            bool: True if file exists, False otherwise
        """
        try:
            if remote_path.startswith("~"):
                remote_path = self._expand_user_path(remote_path)
            self.sftp.stat(remote_path)
            return True
        except FileNotFoundError:
            return False

    def read_file(self, remote_path: str) -> str:
        """Read a file from the remote system.

        Args:
            remote_path: Path to read

        Returns:
            str: File contents
        """
        if remote_path.startswith("~"):
            remote_path = self._expand_user_path(remote_path)

        try:
            with self.sftp.file(remote_path, "r") as f:
                return f.read().decode("utf-8")
        except FileNotFoundError:
            return ""

    def write_file(self, remote_path: str, content: Union[str, bytes]):
        """Write content to a file on the remote system.

        Args:
            remote_path: Path to write to
            content: Content to write (str or bytes)
        """
        if remote_path.startswith("~"):
            remote_path = self._expand_user_path(remote_path)

        # Ensure parent directory exists
        remote_dir = os.path.dirname(remote_path)
        self.ensure_dir(remote_dir)

        # Convert content to bytes if it's a string
        if isinstance(content, str):
            content = content.encode("utf-8")

        # Write the file
        with self.sftp.file(remote_path, "wb") as f:
            f.write(content)

    def upload_file(self, local_path: Union[str, Path], remote_path: str):
        """Upload a file to the remote host.

        Args:
            local_path: Path to local file
            remote_path: Path to remote file
        """
        if remote_path.startswith("~"):
            remote_path = self._expand_user_path(remote_path)

        # Ensure remote directory exists
        remote_dir = os.path.dirname(remote_path)
        self.ensure_dir(remote_dir)

        # Upload file
        self.sftp.put(str(local_path), remote_path)

    def download_file(self, remote_path: str, local_path: Union[str, Path]):
        """Download a file from the remote host.

        Args:
            remote_path: Path to remote file
            local_path: Path to local file
        """
        if remote_path.startswith("~"):
            remote_path = self._expand_user_path(remote_path)

        # Ensure local directory exists
        local_dir = os.path.dirname(str(local_path))
        os.makedirs(local_dir, exist_ok=True)

        # Download file
        self.sftp.get(remote_path, str(local_path))

    def list_dir(self, remote_path: str) -> List[str]:
        """List contents of a directory on the remote host.

        Args:
            remote_path: Path to remote directory

        Returns:
            List[str]: Directory contents
        """
        if remote_path.startswith("~"):
            remote_path = self._expand_user_path(remote_path)

        return self.sftp.listdir(remote_path)
