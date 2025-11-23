"""LSP proxy with path translation between host and container."""

import json
import subprocess
import sys
import threading

from mlt.config import get_all_path_mappings


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
    # Get path mappings (both project and library)
    project_mapping, library_mapping = get_all_path_mappings(project_dir)

    if not project_mapping:
        print(
            "[mlt] WARNING: Could not determine project path mapping from docker-compose.yml",
            file=sys.stderr,
        )
        print(
            "[mlt] LSP will work but paths may not be translated correctly",
            file=sys.stderr,
        )

    if project_mapping:
        proj_host, proj_container = project_mapping
        print(
            f"[mlt] Project mapping: {proj_host} <-> {proj_container}",
            file=sys.stderr,
        )
    else:
        proj_host, proj_container = None, None

    if library_mapping:
        lib_host, lib_container = library_mapping
        print(
            f"[mlt] Library mapping: {lib_host} <-> {lib_container}",
            file=sys.stderr,
        )
    else:
        lib_host, lib_container = None, None

    # Start LSP server in container
    docker_cmd = ["docker", "exec", "-i", container_name] + lsp_command

    # Debug output
    print(f"[mlt] Running command: {' '.join(docker_cmd)}", file=sys.stderr)
    print(f"[mlt] LSP command args: {lsp_command}", file=sys.stderr)

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

    def translate_host_to_container(text: str) -> str:
        """Translate host paths to container paths (both project and library)."""

        # Translate project paths
        if proj_host and proj_container:
            # Handle file:// URIs
            text = text.replace(f"file://{proj_host}", f"file://{proj_container}")
            # Handle plain paths
            text = text.replace(proj_host, proj_container)

        # Translate library paths
        if lib_host and lib_container:
            # Handle file:// URIs
            text = text.replace(f"file://{lib_host}", f"file://{lib_container}")
            # Handle plain paths
            text = text.replace(lib_host, lib_container)

        return text

    def translate_container_to_host(text: str) -> str:
        """Translate container paths to host paths (both project and library)."""

        # Translate library paths first (more specific, e.g., /usr/local/lib/...)
        if lib_container and lib_host:
            # Handle file:// URIs
            text = text.replace(f"file://{lib_container}", f"file://{lib_host}")
            # Handle plain paths
            text = text.replace(lib_container, lib_host)

        # Translate project paths
        if proj_container and proj_host:
            # Handle file:// URIs
            text = text.replace(f"file://{proj_container}", f"file://{proj_host}")
            # Handle plain paths
            text = text.replace(proj_container, proj_host)

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
