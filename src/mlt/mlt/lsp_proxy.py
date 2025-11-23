"""LSP proxy with path translation between host and container."""

import json
import subprocess
import sys
import threading

from mlt.config import get_path_mapping


def run_lsp_proxy(
    container_name: str, lsp_command: list[str], project_dir: str = "."
) -> int:
    """
    Run LSP server in container with transparent path translation.

    Args:
        container_name: Docker container name
        lsp_command: LSP command and arguments (e.g., ["ruff", "server"])
        project_dir: Project directory for path mapping

    Returns:
        Exit code from LSP server
    """
    # Get path mappings
    path_mapping = get_path_mapping(project_dir)
    if not path_mapping:
        print("[mlt] ⚠️  No path mapping (LSP may not work correctly)", file=sys.stderr)
        host_path, container_path = None, None
    else:
        host_path, container_path = path_mapping
        print(f"[mlt] {lsp_command[0]} → {container_name}", file=sys.stderr)

    # Start LSP server in container
    docker_cmd = ["docker", "exec", "-i", container_name] + lsp_command

    try:
        proc = subprocess.Popen(
            docker_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
    except Exception as e:
        print(f"[mlt] ERROR: Failed to start LSP in container: {e}", file=sys.stderr)
        return 1

    # Track if we've logged path translation (only log once)
    _logged_translation = {"host_to_container": False, "container_to_host": False}

    def translate_host_to_container(text: str) -> str:
        """Translate host paths to container paths."""
        if not host_path or not container_path:
            return text
        original = text
        # Handle file:// URIs
        text = text.replace(f"file://{host_path}", f"file://{container_path}")
        # Handle plain paths
        text = text.replace(host_path, container_path)
        if text != original and not _logged_translation["host_to_container"]:
            print(f"[mlt] ↑ {host_path} → {container_path}", file=sys.stderr)
            _logged_translation["host_to_container"] = True
        return text

    def translate_container_to_host(text: str) -> str:
        """Translate container paths to host paths."""
        if not host_path or not container_path:
            return text
        original = text
        # Handle file:// URIs
        text = text.replace(f"file://{container_path}", f"file://{host_path}")
        # Handle plain paths
        text = text.replace(container_path, host_path)
        if text != original and not _logged_translation["container_to_host"]:
            print(f"[mlt] ↓ {container_path} → {host_path}", file=sys.stderr)
            _logged_translation["container_to_host"] = True
        return text

    def forward_stdin():
        """Read from stdin (editor), translate paths, forward to container."""
        try:
            while True:
                # Read Content-Length header
                header = sys.stdin.buffer.readline()
                if not header:
                    break

                if header.startswith(b"Content-Length:"):
                    content_length = int(header.split(b":")[1].strip())
                    # Read empty line
                    sys.stdin.buffer.readline()
                    # Read content
                    content = sys.stdin.buffer.read(content_length)

                    # Translate paths in content
                    try:
                        msg = json.loads(content.decode("utf-8"))
                        msg_str = json.dumps(msg)
                        msg_str = translate_host_to_container(msg_str)
                        content = msg_str.encode("utf-8")
                        content_length = len(content)
                    except Exception:
                        pass  # If not valid JSON, pass through as-is

                    # Write to container
                    proc.stdin.write(
                        f"Content-Length: {content_length}\r\n\r\n".encode()
                    )
                    proc.stdin.write(content)
                    proc.stdin.flush()
        except Exception as e:
            print(f"[mlt] Error in stdin forwarding: {e}", file=sys.stderr)
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass

    def forward_stdout():
        """Read from container, translate paths, forward to stdout (editor)."""
        try:
            while True:
                # Read Content-Length header
                header = proc.stdout.readline()
                if not header:
                    break

                if header.startswith(b"Content-Length:"):
                    content_length = int(header.split(b":")[1].strip())
                    # Read empty line
                    proc.stdout.readline()
                    # Read content
                    content = proc.stdout.read(content_length)

                    # Translate paths in content
                    try:
                        msg = json.loads(content.decode("utf-8"))
                        msg_str = json.dumps(msg)
                        msg_str = translate_container_to_host(msg_str)
                        content = msg_str.encode("utf-8")
                        content_length = len(content)
                    except Exception:
                        pass  # If not valid JSON, pass through as-is

                    # Write to stdout
                    sys.stdout.buffer.write(
                        f"Content-Length: {content_length}\r\n\r\n".encode()
                    )
                    sys.stdout.buffer.write(content)
                    sys.stdout.buffer.flush()
        except Exception as e:
            print(f"[mlt] Error in stdout forwarding: {e}", file=sys.stderr)

    def forward_stderr():
        """Forward stderr as-is for debugging."""
        try:
            for line in proc.stderr:
                sys.stderr.buffer.write(line)
                sys.stderr.buffer.flush()
        except Exception:
            pass

    # Start forwarding threads
    stdin_thread = threading.Thread(target=forward_stdin, daemon=True)
    stdout_thread = threading.Thread(target=forward_stdout, daemon=True)
    stderr_thread = threading.Thread(target=forward_stderr, daemon=True)

    stdin_thread.start()
    stdout_thread.start()
    stderr_thread.start()

    # Wait for process to exit
    return_code = proc.wait()

    return return_code
