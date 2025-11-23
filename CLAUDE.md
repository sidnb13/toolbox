# CLAUDE.md - AI Assistant Guide for Toolbox Repository

**Last Updated**: 2025-11-16
**Version**: 2.1.1.dev1
**Repository**: https://github.com/sidbaskaran/toolbox

---

## Table of Contents
1. [Project Overview](#project-overview)
2. [Codebase Architecture](#codebase-architecture)
3. [Development Workflows](#development-workflows)
4. [Key Conventions and Patterns](#key-conventions-and-patterns)
5. [Common Tasks](#common-tasks)
6. [Important File Locations](#important-file-locations)
7. [Testing and Quality](#testing-and-quality)
8. [Git and CI/CD](#git-and-cicd)
9. [Troubleshooting Guide](#troubleshooting-guide)

---

## Project Overview

### What is Toolbox?

**toolbox** is a monorepo of research utilities designed to streamline machine learning development workflows. It automates tedious DevOps tasks, allowing ML researchers to focus on experimentation rather than infrastructure management.

### Three Core Tools

1. **mltoolbox** - ML development environment management system
   - Remote development with SSH/Docker orchestration
   - GPU setup and NVIDIA Container Toolkit management
   - Project synchronization with intelligent file filtering
   - Ray distributed computing integration
   - Multi-architecture support (x86_64 CUDA, ARM64 GH200)

2. **instancebot** - GPU instance availability monitor
   - Polls Lambda Labs API for available GPU instances
   - Slack notifications for instance availability
   - Configurable filtering (type, region, GPU count)
   - Tracks instance appearance/disappearance with uptime

3. **ai-commit** - AI-powered commit message generator
   - Map-reduce diff summarization
   - Conventional commits format (feat:, fix:, etc.)
   - Breaking change detection
   - Context from README and recent commits
   - Pre-commit hook integration

### Target Users

- ML researchers working with remote GPU servers
- Teams managing multiple remote development environments
- Researchers syncing large datasets with cloud storage
- Anyone needing automated, reproducible ML environments

---

## Codebase Architecture

### Directory Structure

```
/home/user/toolbox/
├── .github/
│   └── workflows/
│       └── build_base.yml          # CI/CD for base Docker images
│
├── src/
│   ├── ai_commit/                  # AI commit message generator
│   │   ├── cli.py                  # CLI entry point
│   │   ├── llm_backend_async.py    # Async LLM interface
│   │   ├── map_reduce_summarizer.py # Map-reduce algorithm
│   │   └── pyproject.toml          # Separate package config
│   │
│   ├── instancebot/                # Lambda Labs GPU monitor
│   │   ├── cli.py                  # CLI wrapper
│   │   └── lambda_watchdog.py      # Core monitoring logic
│   │
│   └── mltoolbox/                  # Main ML toolbox
│       ├── base/                   # Base Docker images
│       │   ├── Dockerfile.cuda     # x86_64 CUDA image
│       │   ├── Dockerfile.gh200    # ARM64 GH200 image
│       │   ├── Dockerfile.ray-head # Ray head node
│       │   └── scripts/            # Container scripts
│       │
│       ├── cli/                    # CLI commands
│       │   ├── __init__.py         # Main CLI group
│       │   ├── init.py             # Project initialization
│       │   └── remote.py           # Remote dev commands (919 lines)
│       │
│       ├── templates/              # Jinja2 templates
│       │   ├── .env.j2             # Environment variables
│       │   ├── Dockerfile.j2       # Project Dockerfile
│       │   └── docker-compose.yml.j2
│       │
│       └── utils/                  # Core utilities
│           ├── db.py               # SQLite database (350 lines)
│           ├── docker.py           # Docker management (611 lines)
│           ├── enhanced_docker.py  # Enhanced operations
│           ├── helpers.py          # SSH helpers (286 lines)
│           ├── logger.py           # Rich logging
│           ├── remote.py           # Sync/rclone (975 lines)
│           ├── session.py          # SSH sessions
│           ├── subprocess_helper.py
│           └── templates.py        # Template rendering
│
├── pyproject.toml                  # Package metadata
├── uv.lock                         # Locked dependencies
├── .pre-commit-config.yaml         # Git hooks
├── .pre-commit-hooks.yaml          # ai-commit hook definition
└── .gitignore                      # Standard Python ignores
```

### Module Responsibilities

#### mltoolbox.cli.remote (919 lines)
**Primary orchestrator for remote development workflows**

Key responsibilities:
- SSH config generation and management
- Docker container lifecycle on remote hosts
- Port forwarding (Ray dashboard, custom ports)
- Integration point for all utilities (sync, docker, db, remote)
- Command implementations: connect, sync, datasync, fetch, attach, list-remotes, remove

Location: `/home/user/toolbox/src/mltoolbox/cli/remote.py`

#### mltoolbox.utils.docker (611 lines)
**Container and GPU management**

Key responsibilities:
- NVIDIA Container Toolkit installation/verification
- Docker group setup and permission management
- Ray head node deployment and orchestration
- GPU access testing and validation
- Container start/build with health checks
- Network mode configuration (bridge, host)

Location: `/home/user/toolbox/src/mltoolbox/utils/docker.py`

#### mltoolbox.utils.remote (975 lines)
**File synchronization and remote setup**

Key responsibilities:
- Rsync-based project syncing with intelligent filtering
- Gitignore/dockerignore parsing and pattern matching
- Rclone integration for cloud storage (Google Drive, S3, B2)
- SSH key setup and agent management
- Environment file (.env) management and merging
- Host availability checking
- Remote directory creation and permissions

Location: `/home/user/toolbox/src/mltoolbox/utils/remote.py`

#### mltoolbox.utils.db (350 lines)
**State management and persistence**

Key responsibilities:
- SQLAlchemy ORM with SQLite backend
- Tracks remotes (alias, host, username, identity file, port)
- Tracks projects (name, container, port mappings)
- Many-to-many remote-project relationships
- Fuzzy search by alias or hostname
- Database initialization and migrations

Database location: `~/.config/mltoolbox/mltoolbox.db`

Location: `/home/user/toolbox/src/mltoolbox/utils/db.py`

#### mltoolbox.utils.helpers (286 lines)
**SSH execution and remote commands**

Key responsibilities:
- Paramiko-based SSH session management
- PTY allocation for interactive commands
- Live output streaming for Docker/rsync
- Comprehensive error reporting with Rich panels
- Command exit code handling

Location: `/home/user/toolbox/src/mltoolbox/utils/helpers.py`

#### ai_commit.map_reduce_summarizer (288 lines)
**Commit message generation with map-reduce**

Key responsibilities:
- Split git diffs by file for parallel processing
- Async LLM calls for individual file summaries
- Reduce phase: aggregate summaries into commit message
- Conventional commits format enforcement
- Breaking change detection (BREAKING CHANGE:)
- Context gathering from README and recent commits

Location: `/home/user/toolbox/src/ai_commit/map_reduce_summarizer.py`

#### instancebot.lambda_watchdog (383 lines)
**GPU instance monitoring**

Key responsibilities:
- Poll Lambda Labs API for instance availability
- Filter by instance type, region, GPU count range
- Slack webhook notifications with rich formatting
- Track instance appearance/disappearance
- Calculate instance uptime
- Configurable polling interval

Location: `/home/user/toolbox/src/instancebot/lambda_watchdog.py`

---

## Development Workflows

### Setting Up Development Environment

```bash
# Clone repository
git clone https://github.com/sidbaskaran/toolbox.git
cd toolbox

# Install with UV (recommended)
pip install uv
uv pip install -e ".[all,dev]"

# Or with pip
pip install -e ".[all,dev]"

# Install pre-commit hooks
pre-commit install
```

### Zed Editor Integration for Remote Development

When developing on remote hosts with Docker containers, Zed editor needs access to Python packages for LSP features (autocomplete, linting, type checking). Since packages are installed inside the container for proper CUDA/PyTorch support, mltoolbox uses the `mlt` tool to provide transparent LSP proxying with automatic path translation.

#### How It Works

1. **LSP Tools in Container**: `ruff` and `basedpyright` are installed inside the Docker container with your project dependencies

2. **mlt Tool**: A lightweight CLI tool (`mlt-toolbox` package) installed on the remote host provides:
   - Smart LSP wrapper (`mlt lsp-auto`) - auto-detects local vs remote context
   - LSP proxy functionality (`mlt lsp-proxy`) - direct container proxy
   - Automatic path translation between host and container
   - Container auto-detection
   - Helper commands (`mlt attach`, `mlt status`, `mlt sync-lsp`)

3. **Path Translation**: `mlt` automatically reads `docker-compose.yml` to understand path mappings and translates file paths in LSP messages bidirectionally

4. **Zed Configuration**: The `.zed/settings.json` file points directly to `mlt` commands

#### Automatic Setup

Everything is configured automatically when you run `mltoolbox remote connect`:

1. **mlt installation**: `pip install mlt-toolbox` on the remote host
2. **`.zed/settings.json`**: Created in your project root with `mlt` LSP configuration
3. **Path mappings**: Automatically detected from `docker-compose.yml`

#### Zed Settings Reference

Your `.zed/settings.json` contains (works both locally and remotely):

```json
{
  "lsp": {
    "ruff": {
      "binary": {
        "path": "mlt",
        "arguments": ["lsp-auto", "ruff", "server"]
      }
    },
    "basedpyright": {
      "binary": {
        "path": "mlt",
        "arguments": ["lsp-auto", "basedpyright-langserver", "--stdio"]
      }
    }
  }
}
```

**Note**: `lsp-auto` automatically detects context:
- Local (no docker-compose.yml): Direct passthrough to local LSP tools
- Remote (has docker-compose.yml): Uses `lsp-proxy` with path translation

#### Manual Testing

```bash
# On remote host, check mlt is installed
which mlt

# Test container detection
mlt container

# Check project status
mlt status

# Test LSP commands
mlt lsp-auto ruff --version    # Auto-detects context
mlt lsp-proxy ruff server      # Direct proxy (manual testing)

# Attach to container
mlt attach
```

#### Benefits

- **Full package access**: LSP sees all packages installed in container
- **Proper CUDA environment**: PyTorch/CUDA packages work correctly
- **Automatic path translation**: Host paths ↔ container paths handled transparently
- **No duplicate installations**: Single source of truth in container
- **Clean architecture**: No wrapper scripts, just one `mlt` binary
- **Auto-detection**: Finds container based on project name or CONTAINER_NAME env var

#### Troubleshooting

**LSP not working:**
1. Check `mlt` is installed: `which mlt`
2. Check container is running: `mlt status` or `docker ps`
3. Test container detection: `mlt container`
4. Check Zed settings: `cat .zed/settings.json`
5. Verify LSP tools in container: `docker exec <container> which ruff basedpyright-langserver`
6. Restart Zed or reload window

**Path translation issues:**
- `mlt` reads path mappings from `docker-compose.yml`
- Verify your `docker-compose.yml` has the project volume mount
- Check with: `docker inspect <container> | grep Mounts -A 20`

**Container not found:**
- `mlt` tries: CONTAINER_NAME env var → .env file → docker ps auto-detect
- Set explicitly: `export CONTAINER_NAME=myproject-main`
- Or ensure container name matches project directory name

**mlt not installed:**
```bash
# On remote host
pip install mlt-toolbox

# Or with specific version
pip install mlt-toolbox==0.1.0
```

### Branch Strategy

- **Main branch**: Stable releases
- **Feature branches**: Prefix with `claude/` for AI-assisted development
- **Branch naming**: `claude/claude-md-<session-id>` (enforced by git hooks)

### Creating a New Feature

1. **Create feature branch**
   ```bash
   git checkout -b claude/feature-name-<session-id>
   ```

2. **Make changes** following code conventions

3. **Run pre-commit hooks**
   ```bash
   pre-commit run --all-files
   ```

4. **Commit with AI assistance**
   - Pre-commit hook automatically generates commit message
   - Review and edit if needed
   - Follows conventional commits format

5. **Push to remote**
   ```bash
   git push -u origin claude/feature-name-<session-id>
   ```

### Adding a New CLI Command

#### For mltoolbox

1. **Create command function** in appropriate file:
   - `/home/user/toolbox/src/mltoolbox/cli/init.py` for project initialization
   - `/home/user/toolbox/src/mltoolbox/cli/remote.py` for remote operations
   - Or create new file in `/home/user/toolbox/src/mltoolbox/cli/`

2. **Use Click decorators**:
   ```python
   import click
   from mltoolbox.utils.logger import get_logger

   logger = get_logger(__name__)

   @click.command()
   @click.argument('arg_name')
   @click.option('--flag', is_flag=True, help='Description')
   @click.pass_context
   def my_command(ctx, arg_name, flag):
       """Command description for --help"""
       logger.info(f"Executing command with {arg_name}")
       # Implementation
   ```

3. **Register with CLI group** in `/home/user/toolbox/src/mltoolbox/cli/__init__.py`:
   ```python
   from mltoolbox.cli.my_module import my_command

   @click.group()
   def cli():
       pass

   cli.add_command(my_command)
   ```

4. **Test locally**:
   ```bash
   mltoolbox my-command --help
   mltoolbox my-command test-arg --flag
   ```

#### For instancebot or ai-commit

Similar pattern, but modify respective CLI files:
- `/home/user/toolbox/src/instancebot/cli.py`
- `/home/user/toolbox/src/ai_commit/cli.py`

### Adding a New Utility Function

1. **Choose appropriate module**:
   - Docker operations → `/home/user/toolbox/src/mltoolbox/utils/docker.py`
   - SSH/remote → `/home/user/toolbox/src/mltoolbox/utils/helpers.py`
   - File sync → `/home/user/toolbox/src/mltoolbox/utils/remote.py`
   - Database → `/home/user/toolbox/src/mltoolbox/utils/db.py`
   - Logging → `/home/user/toolbox/src/mltoolbox/utils/logger.py`

2. **Follow existing patterns**:
   ```python
   from mltoolbox.utils.logger import get_logger

   logger = get_logger(__name__)

   def my_utility_function(param: str, optional: bool = False) -> dict:
       """
       Brief description.

       Args:
           param: Description of param
           optional: Description of optional param

       Returns:
           dict: Description of return value

       Raises:
           ValueError: When invalid param
       """
       logger.debug(f"Processing {param}")

       try:
           # Implementation
           result = {"status": "success"}
           logger.info("Operation completed")
           return result
       except Exception as e:
           logger.error(f"Error: {e}", exc_info=True)
           raise
   ```

3. **Import and use** in CLI commands or other utilities

### Modifying Base Docker Images

Base images are in `/home/user/toolbox/src/mltoolbox/base/`:

1. **Edit appropriate Dockerfile**:
   - `Dockerfile.cuda` - x86_64 CUDA base image
   - `Dockerfile.gh200` - ARM64 GH200 base image
   - `Dockerfile.ray-head` - Ray head node image

2. **Update scripts** in `/home/user/toolbox/src/mltoolbox/base/scripts/` if needed:
   - `entrypoint.sh` - Container entrypoint
   - `ray-init.sh` - Ray initialization

3. **Test locally**:
   ```bash
   cd src/mltoolbox/base
   docker build -f Dockerfile.cuda -t test-cuda .
   docker run --rm -it test-cuda /bin/bash
   ```

4. **CI/CD automatically builds** on push to master or changes in `src/mltoolbox/base/`
   - Publishes to `ghcr.io/[owner]/ml-base:py{version}-{variant}`
   - Matrix build: Python 3.10, 3.11, 3.12

### Modifying Templates

Templates are in `/home/user/toolbox/src/mltoolbox/templates/`:

1. **Edit Jinja2 templates**:
   - `.env.j2` - Environment variables
   - `Dockerfile.j2` - Project Dockerfile
   - `docker-compose.yml.j2` - Docker Compose config

2. **Template variables** available:
   ```jinja2
   {{ project_name }}           # Project name
   {{ python_version }}         # e.g., "3.12.12"
   {{ variant }}                # "cuda" or "gh200"
   {{ ray_enabled }}            # boolean
   {{ host_ray_client_port }}   # Ray dashboard port
   {{ wandb_project }}          # W&B project name
   {{ git_email }}              # User git email
   {{ git_name }}               # User git name
   ```

3. **Test template rendering** in `/home/user/toolbox/src/mltoolbox/utils/templates.py`:
   ```python
   from mltoolbox.utils.templates import render_template

   content = render_template("Dockerfile.j2", {
       "project_name": "test",
       "python_version": "3.12.12",
       "variant": "cuda"
   })
   ```

4. **Templates are used** by `mltoolbox init` command

---

## Key Conventions and Patterns

### Code Style

- **Linter**: Ruff (configured in `.pre-commit-config.yaml`)
- **Formatter**: Ruff format
- **Rules**: E, F, I, UP (errors, pyflakes, imports, pyupgrade)
- **Ignored**: E501 (line length - flexible for readability)
- **Line length**: No strict limit, use judgment for readability
- **Import sorting**: Automatic via ruff (I rules)

### Import Organization

Standard order (enforced by ruff):
```python
# 1. Standard library
import os
import subprocess
from pathlib import Path

# 2. Third-party
import click
from dotenv import load_dotenv
from sqlalchemy.orm import joinedload

# 3. Local
from mltoolbox.utils.db import DB, Remote
from mltoolbox.utils.docker import check_docker_installed
from mltoolbox.utils.logger import get_logger
```

### Logging Conventions

Use Rich logging framework:

```python
from mltoolbox.utils.logger import get_logger

logger = get_logger(__name__)  # Use __name__ for module-specific logger

# Log levels
logger.debug("Detailed debug information")
logger.info("General information")
logger.warning("Warning message")
logger.error("Error occurred", exc_info=True)  # Include traceback

# Rich panel for important info
from rich.console import Console
from rich.panel import Panel

console = Console()
console.print(Panel("Important message", title="Title", border_style="green"))

# Progress spinners
from rich.spinner import Spinner

with console.status("[bold green]Processing...") as status:
    # Long-running operation
    pass
```

### Error Handling

```python
# Specific exceptions first, general last
try:
    result = risky_operation()
except FileNotFoundError as e:
    logger.error(f"File not found: {e}")
    raise
except subprocess.CalledProcessError as e:
    logger.error(f"Command failed: {e.cmd}", exc_info=True)
    raise
except Exception as e:
    logger.error(f"Unexpected error: {e}", exc_info=True)
    raise

# Use context managers for cleanup
with open(file_path) as f:
    content = f.read()

# Database sessions
with DB() as db:
    remote = db.get_remote_by_alias("myserver")
```

### Click Command Patterns

```python
@click.command()
@click.argument('required_arg')
@click.option('--optional', default=None, help='Optional parameter')
@click.option('--flag', is_flag=True, help='Boolean flag')
@click.option('--choice', type=click.Choice(['a', 'b', 'c']), help='Choices')
@click.pass_context  # Access parent context
def command(ctx, required_arg, optional, flag, choice):
    """
    Command description shown in --help.

    Supports multi-line descriptions with blank lines.
    """
    # Access global flags from context
    debug = ctx.obj.get('DEBUG', False)
    dryrun = ctx.obj.get('DRYRUN', False)

    if dryrun:
        logger.info("Dry run mode - no changes will be made")
        return

    # Implementation
```

### Database Patterns

```python
from mltoolbox.utils.db import DB, Remote, Project

# Context manager for automatic session cleanup
with DB() as db:
    # Query
    remote = db.get_remote_by_alias("myserver")

    # Create
    new_remote = Remote(
        alias="newserver",
        host="192.168.1.100",
        username="user",
        identity_file="~/.ssh/id_rsa",
        port=22
    )
    db.session.add(new_remote)
    db.session.commit()

    # Update
    remote.port = 2222
    db.session.commit()

    # Delete
    db.session.delete(remote)
    db.session.commit()

    # Relationships
    projects = remote.projects  # Many-to-many
```

### SSH Command Execution

```python
from mltoolbox.utils.helpers import remote_cmd

# Execute remote command with live output
exit_code = remote_cmd(
    host="192.168.1.100",
    username="user",
    command="docker ps -a",
    identity_file="~/.ssh/id_rsa",
    port=22,
    pty=True  # For interactive commands
)

if exit_code != 0:
    logger.error(f"Command failed with exit code {exit_code}")
    raise subprocess.CalledProcessError(exit_code, "docker ps -a")
```

### File Synchronization

```python
from mltoolbox.utils.remote import sync_project_to_host

# Sync with intelligent filtering
sync_project_to_host(
    remote_host="192.168.1.100",
    remote_user="user",
    remote_path="/home/user/project",
    local_path="/local/project",
    exclude_patterns=["*.pyc", "__pycache__", ".git"],
    identity_file="~/.ssh/id_rsa",
    port=22,
    dry_run=False
)
```

### Template Rendering

```python
from mltoolbox.utils.templates import render_template, render_and_write

# Render template to string
content = render_template("Dockerfile.j2", {
    "project_name": "myproject",
    "python_version": "3.12.12"
})

# Render and write to file
render_and_write(
    template_name="docker-compose.yml.j2",
    output_path="/path/to/docker-compose.yml",
    context={
        "project_name": "myproject",
        "ray_enabled": True
    }
)
```

### Type Hints

Use type hints for function signatures:

```python
from pathlib import Path
from typing import Optional, List, Dict, Any

def sync_files(
    source: Path,
    destination: str,
    patterns: List[str],
    options: Optional[Dict[str, Any]] = None
) -> int:
    """Sync files with patterns."""
    # Implementation
    return 0  # exit code
```

### Constants and Configuration

```python
# Use UPPER_CASE for constants
DEFAULT_PORT = 22
DEFAULT_PYTHON_VERSION = "3.12.12"
SUPPORTED_VARIANTS = ["cuda", "gh200"]

# Environment variables
from dotenv import load_dotenv
import os

load_dotenv()  # Load from .env file

API_KEY = os.getenv("API_KEY")
WANDB_PROJECT = os.getenv("WANDB_PROJECT", "default-project")
```

---

## Common Tasks

### Task 1: Add Support for a New Python Version

**Files to modify**:
1. `/home/user/toolbox/pyproject.toml` - Update `requires-python` and classifiers
2. `/home/user/toolbox/.github/workflows/build_base.yml` - Add to build matrix
3. `/home/user/toolbox/src/mltoolbox/base/Dockerfile.cuda` - Add pyenv install steps
4. `/home/user/toolbox/src/mltoolbox/base/Dockerfile.gh200` - Add pyenv install steps

**Steps**:
```bash
# 1. Update pyproject.toml
# Change: requires-python = ">=3.10"
# To: requires-python = ">=3.10,<3.14"

# 2. Update build_base.yml
# Add to matrix: python-version: ["3.10", "3.11", "3.12", "3.13"]

# 3. Update Dockerfiles
# Add: RUN pyenv install 3.13.0 && ...

# 4. Test locally
docker build -f src/mltoolbox/base/Dockerfile.cuda -t test .

# 5. Commit and push
git add .
git commit -m "feat: add support for Python 3.13"
git push
```

### Task 2: Add a New Remote Command

**Example**: Add `mltoolbox remote logs` command to view container logs

**File to modify**: `/home/user/toolbox/src/mltoolbox/cli/remote.py`

**Implementation**:
```python
@remote.command()
@click.argument("host_or_alias")
@click.option("--port", default=22, help="SSH port")
@click.option("--follow", "-f", is_flag=True, help="Follow log output")
@click.option("--tail", default=100, help="Number of lines to show")
@click.pass_context
def logs(ctx, host_or_alias, port, follow, tail):
    """View container logs from remote host."""
    debug = ctx.obj.get("DEBUG", False)
    logger = get_logger(__name__, debug=debug)

    with DB() as db:
        # Find remote
        remote = db.get_remote_by_alias(host_or_alias)
        if not remote:
            logger.error(f"Remote '{host_or_alias}' not found")
            raise click.Abort()

        # Get project
        project = next((p for p in remote.projects), None)
        if not project:
            logger.error(f"No project found for remote '{host_or_alias}'")
            raise click.Abort()

        # Build command
        follow_flag = "-f" if follow else ""
        command = f"docker logs {follow_flag} --tail {tail} {project.container_name}"

        logger.info(f"Fetching logs from {remote.alias}...")

        # Execute
        exit_code = remote_cmd(
            host=remote.host,
            username=remote.username,
            command=command,
            identity_file=remote.identity_file,
            port=port,
            pty=True
        )

        if exit_code != 0:
            logger.error("Failed to fetch logs")
            raise click.Abort()
```

**Test**:
```bash
mltoolbox remote logs myserver --tail 50
mltoolbox remote logs myserver --follow
```

### Task 3: Add a New Template Variable

**Example**: Add `{{ github_token }}` to templates

**Files to modify**:
1. `/home/user/toolbox/src/mltoolbox/templates/.env.j2`
2. `/home/user/toolbox/src/mltoolbox/cli/init.py` (or wherever template is rendered)

**Steps**:

1. **Update template** (`src/mltoolbox/templates/.env.j2`):
   ```jinja2
   # GitHub
   GITHUB_TOKEN={{ github_token }}
   ```

2. **Update rendering logic**:
   ```python
   from mltoolbox.utils.templates import render_and_write

   github_token = os.getenv("GITHUB_TOKEN", "")

   render_and_write(
       ".env.j2",
       output_path=".env",
       context={
           "github_token": github_token,
           # ... other variables
       }
   )
   ```

3. **Test**:
   ```bash
   export GITHUB_TOKEN="ghp_xxxxx"
   mltoolbox init test-project
   cat test-project/.env  # Verify GITHUB_TOKEN is present
   ```

### Task 4: Add Integration with a New Cloud Storage Provider

**Example**: Add Dropbox support to `datasync` command

**File to modify**: `/home/user/toolbox/src/mltoolbox/utils/remote.py`

**Implementation**:

1. **Add rclone configuration helper**:
   ```python
   def setup_dropbox_rclone(host, username, identity_file, port=22):
       """Setup rclone for Dropbox on remote host."""
       logger = get_logger(__name__)

       # Check if already configured
       check_cmd = "rclone listremotes | grep -q '^dropbox:'"
       exit_code = remote_cmd(host, username, check_cmd, identity_file, port)

       if exit_code == 0:
           logger.info("Dropbox already configured")
           return

       logger.info("Configuring Dropbox...")

       # Interactive rclone config
       config_cmd = "rclone config create dropbox dropbox"
       remote_cmd(host, username, config_cmd, identity_file, port, pty=True)
   ```

2. **Update datasync command** in `/home/user/toolbox/src/mltoolbox/cli/remote.py`:
   ```python
   @click.option(
       "--provider",
       type=click.Choice(["gdrive", "s3", "b2", "dropbox"]),
       default="gdrive",
       help="Cloud storage provider"
   )
   def datasync(ctx, direction, host_or_alias, provider, ...):
       # ... existing code ...

       if provider == "dropbox":
           setup_dropbox_rclone(remote.host, remote.username,
                               remote.identity_file, port)
           remote_name = "dropbox:"

       # ... rest of implementation
   ```

### Task 5: Add a New Base Image Variant

**Example**: Add ROCm support for AMD GPUs

**Steps**:

1. **Create new Dockerfile** (`src/mltoolbox/base/Dockerfile.rocm`):
   ```dockerfile
   FROM rocm/dev-ubuntu-22.04:latest

   # Install Python build dependencies
   RUN apt-get update && apt-get install -y \
       build-essential \
       curl \
       git \
       # ... rest similar to Dockerfile.cuda

   # Install ROCm-specific packages
   RUN apt-get install -y rocm-dev rocm-libs

   # ... rest of setup
   ```

2. **Update CI/CD** (`.github/workflows/build_base.yml`):
   ```yaml
   matrix:
     variant: [cuda, gh200, rocm]
     python-version: ["3.10", "3.11", "3.12"]
     include:
       - variant: rocm
         platform: linux/amd64
         dockerfile: Dockerfile.rocm
   ```

3. **Update CLI** to support `--variant rocm`:
   ```python
   @click.option(
       "--variant",
       type=click.Choice(["cuda", "gh200", "rocm"]),
       default="cuda"
   )
   ```

4. **Update templates** to handle ROCm-specific configuration

### Task 6: Debug SSH Connection Issues

**Common scenarios**:

1. **Check SSH config**:
   ```bash
   cat ~/.config/mltoolbox/ssh/config
   cat ~/.ssh/config | grep -A 10 "Include.*mltoolbox"
   ```

2. **Test SSH manually**:
   ```bash
   ssh -i ~/.ssh/id_rsa -p 22 user@host
   ```

3. **Enable debug logging**:
   ```bash
   mltoolbox --debug remote connect host
   ```

4. **Check database state**:
   ```bash
   sqlite3 ~/.config/mltoolbox/mltoolbox.db "SELECT * FROM remotes;"
   ```

5. **Check remote Docker**:
   ```bash
   mltoolbox remote attach host
   # Then inside container:
   docker ps
   docker logs <container>
   ```

### Task 7: Add New Environment Variables to Projects

**Files to modify**:
1. `/home/user/toolbox/src/mltoolbox/templates/.env.j2`
2. `/home/user/toolbox/src/mltoolbox/cli/init.py`

**Example**: Add Hugging Face Hub token

```jinja2
# In .env.j2
HF_TOKEN={{ hf_token }}
HF_HOME={{ hf_home }}
```

```python
# In init.py or remote.py
hf_token = os.getenv("HF_TOKEN", "")
hf_home = os.getenv("HF_HOME", "/workspace/.cache/huggingface")

context = {
    "hf_token": hf_token,
    "hf_home": hf_home,
    # ... other vars
}
```

---

## Important File Locations

### Configuration Files

| File | Location | Purpose |
|------|----------|---------|
| Main config | `/home/user/toolbox/pyproject.toml` | Package metadata, dependencies |
| Lock file | `/home/user/toolbox/uv.lock` | Locked dependencies |
| Pre-commit | `/home/user/toolbox/.pre-commit-config.yaml` | Git hooks configuration |
| Gitignore | `/home/user/toolbox/.gitignore` | Git ignore patterns |

### Runtime State

| File | Location | Purpose |
|------|----------|---------|
| Database | `~/.config/mltoolbox/mltoolbox.db` | Remote/project tracking |
| SSH config | `~/.config/mltoolbox/ssh/config` | Generated SSH configuration |
| Rclone config | `~/.config/rclone/rclone.conf` | Cloud storage configuration |

### Source Code

| Component | Location | Lines | Key Responsibilities |
|-----------|----------|-------|---------------------|
| Remote CLI | `/home/user/toolbox/src/mltoolbox/cli/remote.py` | 919 | Remote orchestration |
| Docker utils | `/home/user/toolbox/src/mltoolbox/utils/docker.py` | 611 | Container management |
| Sync utils | `/home/user/toolbox/src/mltoolbox/utils/remote.py` | 975 | File synchronization |
| Database | `/home/user/toolbox/src/mltoolbox/utils/db.py` | 350 | State persistence |
| SSH helpers | `/home/user/toolbox/src/mltoolbox/utils/helpers.py` | 286 | Remote execution |
| AI commit | `/home/user/toolbox/src/ai_commit/map_reduce_summarizer.py` | 288 | Commit messages |
| Instancebot | `/home/user/toolbox/src/instancebot/lambda_watchdog.py` | 383 | GPU monitoring |

### Templates

| Template | Location | Purpose |
|----------|----------|---------|
| Environment | `/home/user/toolbox/src/mltoolbox/templates/.env.j2` | Project env vars |
| Dockerfile | `/home/user/toolbox/src/mltoolbox/templates/Dockerfile.j2` | Project container |
| Compose | `/home/user/toolbox/src/mltoolbox/templates/docker-compose.yml.j2` | Container orchestration |

### Base Images

| Image | Location | Purpose |
|-------|----------|---------|
| CUDA | `/home/user/toolbox/src/mltoolbox/base/Dockerfile.cuda` | x86_64 GPU base |
| GH200 | `/home/user/toolbox/src/mltoolbox/base/Dockerfile.gh200` | ARM64 GPU base |
| Ray head | `/home/user/toolbox/src/mltoolbox/base/Dockerfile.ray-head` | Ray cluster |

### Scripts

| Script | Location | Purpose |
|--------|----------|---------|
| Entrypoint | `/home/user/toolbox/src/mltoolbox/base/scripts/entrypoint.sh` | Container startup |
| Ray init | `/home/user/toolbox/src/mltoolbox/base/scripts/ray-init.sh` | Ray initialization |

---

## Testing and Quality

### Pre-commit Hooks

**Configured in**: `/home/user/toolbox/.pre-commit-config.yaml`

**Hooks**:
1. **Ruff linting**
   - Auto-fix with `--unsafe-fixes`
   - Rules: E (errors), F (pyflakes), I (imports), UP (pyupgrade)
   - Ignores: E501 (line length)
   - Excludes: `.ipynb` files

2. **Ruff formatting**
   - Auto-formats code
   - Excludes: `.ipynb` files

3. **ai-commit**
   - Generates commit messages
   - Word limit: 30 words
   - Conventional commits format

**Manual execution**:
```bash
# Run all hooks
pre-commit run --all-files

# Run specific hook
pre-commit run ruff --all-files
pre-commit run ai-commit --all-files

# Update hooks
pre-commit autoupdate
```

### Linting

```bash
# Run ruff linting
ruff check src/

# Auto-fix issues
ruff check --fix src/

# Check specific rules
ruff check --select=E,F src/
```

### Formatting

```bash
# Format code
ruff format src/

# Check formatting without changes
ruff format --check src/
```

### Testing

**Note**: This is a research-oriented project with no formal test suite currently.

**Manual testing workflow**:

1. **Test CLI commands**:
   ```bash
   mltoolbox --help
   mltoolbox init test-project --python-version 3.12.12
   ls -la test-project/
   ```

2. **Test remote operations**:
   ```bash
   mltoolbox --debug --dryrun remote connect testhost
   ```

3. **Test Docker builds**:
   ```bash
   cd src/mltoolbox/base
   docker build -f Dockerfile.cuda -t test-cuda .
   docker run --rm test-cuda python --version
   ```

4. **Test templates**:
   ```bash
   python -c "
   from mltoolbox.utils.templates import render_template
   print(render_template('Dockerfile.j2', {
       'project_name': 'test',
       'python_version': '3.12.12'
   }))
   "
   ```

### Code Quality Checklist

Before committing:
- [ ] Run `pre-commit run --all-files`
- [ ] Check for print statements (use logger instead)
- [ ] Verify error handling with try/except
- [ ] Add docstrings to new functions
- [ ] Update CLAUDE.md if adding major features
- [ ] Test CLI commands manually
- [ ] Check for hardcoded paths (use Path or os.path)
- [ ] Verify logging uses appropriate levels

---

## Git and CI/CD

### Branch Protection

**Main branch**: Protected, requires clean pre-commit hooks

**Feature branches**: Must start with `claude/` and end with session ID for AI-assisted work

### Commit Message Format

**Conventional commits** enforced by ai-commit hook:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Formatting, missing semi-colons, etc.
- `refactor`: Code change that neither fixes bug nor adds feature
- `perf`: Performance improvement
- `test`: Adding tests
- `chore`: Updating build tasks, package manager configs, etc.

**Breaking changes**:
```
feat: change API endpoint structure

BREAKING CHANGE: API endpoints now use /api/v2/ prefix
```

**Examples**:
```
feat(mltoolbox): add support for ROCm GPU variant
fix(docker): resolve NVIDIA toolkit installation on Ubuntu 24.04
docs: update CLAUDE.md with new remote command examples
refactor(remote): simplify SSH config generation logic
```

### CI/CD Pipeline

**Workflow**: `/home/user/toolbox/.github/workflows/build_base.yml`

**Triggers**:
- Push to `master` branch
- Manual workflow dispatch
- Changes to `src/mltoolbox/base/**`

**Build Matrix**:
```yaml
variant: [cuda, gh200]
python-version: ["3.10", "3.11", "3.12"]
platform:
  - cuda: linux/amd64
  - gh200: linux/arm64
```

**Steps**:
1. Checkout code
2. Set up Docker Buildx (multi-arch support)
3. Install NVIDIA Container Toolkit
4. Build base image for each variant/Python version
5. Push to GitHub Container Registry
   - Format: `ghcr.io/[owner]/ml-base:py{version}-{variant}`
   - Example: `ghcr.io/sidbaskaran/ml-base:py3.12-cuda`

**Published images**:
- `ghcr.io/sidbaskaran/ml-base:py3.10-cuda`
- `ghcr.io/sidbaskaran/ml-base:py3.11-cuda`
- `ghcr.io/sidbaskaran/ml-base:py3.12-cuda`
- `ghcr.io/sidbaskaran/ml-base:py3.10-gh200`
- `ghcr.io/sidbaskaran/ml-base:py3.11-gh200`
- `ghcr.io/sidbaskaran/ml-base:py3.12-gh200`

### Git Workflow for AI Assistants

```bash
# 1. Ensure on correct branch
git status
git branch  # Should be on claude/claude-md-<session-id>

# 2. Stage changes
git add <files>

# 3. Commit (ai-commit hook auto-generates message)
git commit

# 4. Review and edit commit message if needed
# ai-commit provides a draft, you can modify before finalizing

# 5. Push with retry logic
git push -u origin <branch-name>

# If push fails with 403, verify branch name starts with 'claude/'
# and ends with matching session ID

# 6. Retry on network errors (exponential backoff)
# Wait 2s, retry
# Wait 4s, retry
# Wait 8s, retry
# Wait 16s, retry
```

### Pull Request Process

1. **Push feature branch**:
   ```bash
   git push -u origin claude/feature-name-<session-id>
   ```

2. **Create PR** (via GitHub web interface or CLI):
   ```bash
   # If gh CLI available
   gh pr create --title "feat: add new feature" \
                --body "Description of changes"
   ```

3. **PR template** (recommended):
   ```markdown
   ## Summary
   - Brief description of changes
   - Why this change is needed

   ## Changes
   - [ ] Modified file X
   - [ ] Added new feature Y
   - [ ] Updated documentation

   ## Testing
   - [ ] Manual testing performed
   - [ ] Pre-commit hooks pass
   - [ ] No regressions

   ## Screenshots (if applicable)
   ```

4. **Review and merge**:
   - Ensure CI passes (base image builds)
   - Pre-commit hooks must pass
   - Review code for style consistency
   - Squash commits if needed

---

## Troubleshooting Guide

### Common Issues and Solutions

#### Issue 1: "Remote not found" error

**Symptom**:
```
Error: Remote 'myserver' not found
```

**Solutions**:
1. List all remotes:
   ```bash
   mltoolbox remote list-remotes
   ```

2. Check database:
   ```bash
   sqlite3 ~/.config/mltoolbox/mltoolbox.db "SELECT * FROM remotes;"
   ```

3. Re-add remote:
   ```bash
   mltoolbox remote connect 192.168.1.100 --alias myserver
   ```

#### Issue 2: SSH connection failures

**Symptom**:
```
Error: Failed to connect to remote host
```

**Solutions**:
1. Verify SSH manually:
   ```bash
   ssh -i ~/.ssh/id_rsa -p 22 user@host
   ```

2. Check SSH config:
   ```bash
   cat ~/.config/mltoolbox/ssh/config
   ```

3. Verify identity file:
   ```bash
   ls -la ~/.ssh/id_rsa
   chmod 600 ~/.ssh/id_rsa  # Fix permissions
   ```

4. Test with debug:
   ```bash
   mltoolbox --debug remote connect host
   ```

5. Check SSH agent:
   ```bash
   ssh-add -l
   ssh-add ~/.ssh/id_rsa
   ```

#### Issue 3: Docker container won't start

**Symptom**:
```
Error: Container failed to start
```

**Solutions**:
1. Check Docker status on remote:
   ```bash
   ssh user@host "docker ps -a"
   ```

2. View container logs:
   ```bash
   ssh user@host "docker logs container-name"
   ```

3. Check NVIDIA runtime:
   ```bash
   ssh user@host "docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi"
   ```

4. Rebuild container:
   ```bash
   mltoolbox remote connect host --force-rebuild
   ```

5. Check disk space:
   ```bash
   ssh user@host "df -h"
   ```

#### Issue 4: GPU not accessible in container

**Symptom**:
```
Error: CUDA not available
nvidia-smi: command not found
```

**Solutions**:
1. Verify NVIDIA Container Toolkit:
   ```bash
   ssh user@host "nvidia-ctk --version"
   ```

2. Install toolkit:
   ```bash
   # On remote host
   distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
   curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
   curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
     sudo tee /etc/apt/sources.list.d/nvidia-docker.list
   sudo apt-get update
   sudo apt-get install -y nvidia-container-toolkit
   sudo systemctl restart docker
   ```

3. Verify GPU on host:
   ```bash
   ssh user@host "nvidia-smi"
   ```

4. Check container runtime:
   ```bash
   ssh user@host "docker run --rm --gpus all ubuntu nvidia-smi"
   ```

#### Issue 5: File sync not working

**Symptom**:
```
Error: rsync failed
```

**Solutions**:
1. Test rsync manually:
   ```bash
   rsync -avz --dry-run /local/path/ user@host:/remote/path/
   ```

2. Check exclude patterns:
   ```bash
   cat .gitignore
   cat .dockerignore
   ```

3. Verify remote path exists:
   ```bash
   ssh user@host "ls -la /remote/path"
   ```

4. Check permissions:
   ```bash
   ssh user@host "mkdir -p /remote/path && chmod 755 /remote/path"
   ```

5. Use debug mode:
   ```bash
   mltoolbox --debug remote sync myserver
   ```

#### Issue 6: Port forwarding not working

**Symptom**:
```
Error: Cannot access Ray dashboard at localhost:8265
```

**Solutions**:
1. Check forwarded ports:
   ```bash
   ssh user@host "docker port container-name"
   ```

2. Verify SSH tunnel:
   ```bash
   ssh -L 8265:localhost:8265 user@host
   ```

3. Check if port is in use locally:
   ```bash
   lsof -i :8265
   ```

4. Try different port:
   ```bash
   mltoolbox remote connect host --host-ray-dashboard-port 8266
   ```

5. Check container ports:
   ```bash
   ssh user@host "docker exec container-name netstat -tuln"
   ```

#### Issue 7: Pre-commit hook failures

**Symptom**:
```
ruff....................................................................Failed
```

**Solutions**:
1. Run ruff manually:
   ```bash
   ruff check src/
   ```

2. Auto-fix issues:
   ```bash
   ruff check --fix src/
   ruff format src/
   ```

3. Skip hooks temporarily (not recommended):
   ```bash
   git commit --no-verify
   ```

4. Update pre-commit:
   ```bash
   pre-commit autoupdate
   pre-commit install
   ```

#### Issue 8: ai-commit not generating messages

**Symptom**:
```
Error: Failed to generate commit message
```

**Solutions**:
1. Check API keys:
   ```bash
   echo $OPENAI_API_KEY
   echo $TOGETHER_API_KEY
   ```

2. Set API key:
   ```bash
   export OPENAI_API_KEY="sk-..."
   ```

3. Test manually:
   ```bash
   ai-commit --dry-run
   ```

4. Check model availability:
   ```bash
   # In ai_commit config
   AI_COMMIT_MODEL="gpt-4-turbo"
   ```

5. Bypass if needed:
   ```bash
   git commit -m "manual message" --no-verify
   ```

#### Issue 9: Template rendering errors

**Symptom**:
```
Error: Template variable 'project_name' undefined
```

**Solutions**:
1. Check template variables:
   ```python
   from mltoolbox.utils.templates import render_template

   print(render_template("Dockerfile.j2", {
       "project_name": "test",  # Ensure all required vars
       "python_version": "3.12.12",
       "variant": "cuda"
   }))
   ```

2. Verify template file exists:
   ```bash
   ls -la src/mltoolbox/templates/
   ```

3. Check Jinja2 syntax:
   ```bash
   cat src/mltoolbox/templates/Dockerfile.j2
   ```

#### Issue 10: Database corruption

**Symptom**:
```
Error: database disk image is malformed
```

**Solutions**:
1. Backup database:
   ```bash
   cp ~/.config/mltoolbox/mltoolbox.db ~/.config/mltoolbox/mltoolbox.db.bak
   ```

2. Try to recover:
   ```bash
   sqlite3 ~/.config/mltoolbox/mltoolbox.db "PRAGMA integrity_check;"
   ```

3. Recreate database:
   ```bash
   rm ~/.config/mltoolbox/mltoolbox.db
   # Database will be recreated on next mltoolbox command
   ```

4. Re-add remotes:
   ```bash
   mltoolbox remote connect host --alias myserver
   ```

### Debug Mode

Enable debug logging for all commands:

```bash
# Set environment variable
export LOG_LEVEL=DEBUG

# Or use --debug flag
mltoolbox --debug remote connect host

# Or use --dryrun for testing
mltoolbox --dryrun remote connect host
```

### Getting Help

1. **Check command help**:
   ```bash
   mltoolbox --help
   mltoolbox remote --help
   mltoolbox remote connect --help
   ```

2. **Review logs**:
   - Check console output for error messages
   - Look for Rich panels with error details
   - Check container logs: `docker logs container-name`

3. **Verify environment**:
   ```bash
   # Check Python version
   python --version

   # Check installed packages
   pip list | grep toolbox

   # Check Docker
   docker --version
   docker ps
   ```

4. **GitHub Issues**:
   - Search existing issues: https://github.com/sidbaskaran/toolbox/issues
   - Open new issue with:
     - Command executed
     - Full error message
     - Environment details (OS, Python version, Docker version)
     - Debug output (`--debug` flag)

---

## AI Assistant Best Practices

### When Working with This Codebase

1. **Always check existing patterns** before implementing new features
   - Look at similar functions in the same module
   - Follow established error handling patterns
   - Use consistent logging style

2. **Use Rich for user interaction**
   - Panels for important information
   - Spinners for long-running operations
   - Tables for structured data
   - Color coding for status (green=success, red=error, yellow=warning)

3. **Respect the database schema**
   - Don't modify schema without migration strategy
   - Use DB context manager for all database operations
   - Handle SQLAlchemy relationships properly

4. **Test SSH operations carefully**
   - Always use identity_file and port parameters
   - Handle PTY allocation for interactive commands
   - Stream output for long-running commands
   - Check exit codes and raise on errors

5. **File synchronization considerations**
   - Parse gitignore/dockerignore before syncing
   - Use rsync for efficiency
   - Provide progress feedback
   - Support dry-run mode

6. **Docker best practices**
   - Verify NVIDIA toolkit before GPU operations
   - Handle multiple architectures (x86_64, ARM64)
   - Use health checks for container readiness
   - Clean up unused images/containers

7. **Template modifications**
   - Preserve existing template structure
   - Document new variables in templates
   - Test rendering before committing
   - Handle missing variables gracefully

8. **Error messages**
   - Be specific and actionable
   - Include context (what was attempted)
   - Suggest solutions when possible
   - Use Rich panels for complex errors

### Code Review Checklist

When reviewing or generating code:

- [ ] Follows existing import organization
- [ ] Uses logger instead of print
- [ ] Has proper error handling with try/except
- [ ] Includes docstrings for new functions
- [ ] Uses type hints where appropriate
- [ ] Handles edge cases (missing files, network errors)
- [ ] Provides user feedback for long operations
- [ ] Uses context managers for resources
- [ ] Follows Click patterns for CLI commands
- [ ] Updates CLAUDE.md for major changes

### Understanding the Codebase

**Entry point flow**:
```
User command
    ↓
Click CLI (cli/__init__.py)
    ↓
Command implementation (cli/remote.py, cli/init.py)
    ↓
Utilities (utils/*)
    ↓
External systems (SSH, Docker, Database)
```

**Data flow for remote connect**:
```
1. Parse arguments (Click)
2. Load/create remote in DB (utils/db.py)
3. Verify SSH connectivity (utils/helpers.py)
4. Setup SSH config (utils/remote.py)
5. Install NVIDIA toolkit if needed (utils/docker.py)
6. Sync project files (utils/remote.py)
7. Build/start container (utils/docker.py)
8. Setup port forwarding
9. Attach to container
```

**Configuration precedence**:
```
1. Command-line arguments
2. Environment variables
3. .env file
4. Database stored values
5. Default values
```

### Common Gotchas

1. **SSH key permissions**: Must be 600, not 644 or 755
2. **Docker group**: User must be in docker group on remote
3. **NVIDIA toolkit**: Must be installed before GPU access
4. **Port conflicts**: Check if ports are already in use
5. **Path separators**: Use Path or os.path for cross-platform compatibility
6. **Database sessions**: Always use context manager (with DB())
7. **Template variables**: All must be provided or have defaults
8. **Rsync patterns**: Exclude patterns use gitignore syntax
9. **Container networks**: Host vs bridge mode affects port mappings
10. **Python versions**: Must be installed via pyenv in base image

---

## Appendix

### Environment Variables Reference

```bash
# Weights & Biases
WANDB_PROJECT=my-project
WANDB_ENTITY=my-team
WANDB_API_KEY=xxxxx

# Git Configuration
GIT_EMAIL=user@example.com
GIT_NAME="User Name"
GITHUB_TOKEN=ghp_xxxxx

# Python/ML
HF_HOME=/workspace/.cache/huggingface
HF_TOKEN=hf_xxxxx
LOG_LEVEL=INFO

# Project
PROJECT_NAME=my-project
CONTAINER_NAME=my-project-dev

# Ray
HOST_RAY_CLIENT_PORT=8265

# SSH
SSH_KEY_NAME=id_rsa

# AI Commit
OPENAI_API_KEY=sk-xxxxx
TOGETHER_API_KEY=xxxxx
AI_COMMIT_MSG_WORD_LIMIT=30
AI_COMMIT_MODEL=gpt-4-turbo
AI_COMMIT_EXTRA_CONTEXT="This is a research codebase"

# Instance Bot
LAMBDA_LABS_API_KEY=xxxxx
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxxxx
```

### Useful Commands Reference

```bash
# Development
uv pip install -e ".[all,dev]"
pre-commit install
pre-commit run --all-files

# MLToolbox
mltoolbox init myproject --python-version 3.12.12 --ray
mltoolbox remote connect 192.168.1.100 --alias myserver
mltoolbox remote sync myserver
mltoolbox remote datasync up myserver --local-dir ./data
mltoolbox remote attach myserver
mltoolbox remote list-remotes
mltoolbox remote remove myserver

# Instance Bot
instancebot --api-key $API_KEY --slack-webhook $WEBHOOK \
            --type gpu_1x_a100_sxm4 --region us-west-2

# AI Commit
ai-commit install-hook
ai-commit --dry-run

# Docker
docker build -f src/mltoolbox/base/Dockerfile.cuda -t test .
docker run --rm --gpus all test nvidia-smi
docker ps -a
docker logs container-name

# Database
sqlite3 ~/.config/mltoolbox/mltoolbox.db
SELECT * FROM remotes;
SELECT * FROM projects;
SELECT * FROM remote_project;

# Git
git status
git add .
git commit  # ai-commit hook runs
git push -u origin branch-name
```

### Additional Resources

- **Repository**: https://github.com/sidbaskaran/toolbox
- **Docker Hub**: https://github.com/orgs/sidbaskaran/packages
- **Base Images**: ghcr.io/sidbaskaran/ml-base:py{version}-{variant}
- **Click Documentation**: https://click.palletsprojects.com/
- **Rich Documentation**: https://rich.readthedocs.io/
- **SQLAlchemy**: https://docs.sqlalchemy.org/
- **Paramiko**: https://www.paramiko.org/
- **Rclone**: https://rclone.org/docs/

---

**End of CLAUDE.md**

*This file is maintained to help AI assistants understand and work effectively with the toolbox codebase. Keep it updated as the codebase evolves.*
