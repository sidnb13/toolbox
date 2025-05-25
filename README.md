# toolbox

Containerization and setup tools for bootstrapping my ML research projects.

## Features

- **Modern dependency management** with [uv](https://github.com/astral-sh/uv) and `pyproject.toml`
- **Containerized development** with Docker and Docker Compose
- **Multiple PyTorch variants** (CPU, CUDA, CUDA nightly) with automatic index management
- **Ray integration** for distributed computing
- **Project templating** with sensible ML defaults

## Quick Start

Install ai commit hook:

```bash
curl -s https://raw.githubusercontent.com/sidnb13/toolbox/refs/heads/master/utils/download.sh | bash
```

Initialize a new ML project:

```bash
mltoolbox init my-project
cd my-project

# Install dependencies with CUDA support (default)
uv sync --locked --extra cuda --extra dev

# Or install with CPU-only PyTorch
uv sync --locked --extra cpu --extra dev

# Start development container
mltoolbox container start
```

## Dependency Management

This toolbox uses **uv** for fast, reliable dependency management. All dependencies are defined in `pyproject.toml` with the following extras available:

- `dev` - Development tools (Jupyter, IPython, pre-commit)
- `cuda` - PyTorch with CUDA support
- `cpu` - PyTorch CPU-only
- `cuda-nightly` - PyTorch nightly builds with CUDA
- `ray` - Ray distributed computing framework

### Managing Dependencies

```bash
# Sync all dependencies with CUDA and dev tools
uv sync --locked --extra cuda --extra dev

# Add a new dependency
uv add numpy>=1.24.0

# Add a development dependency
uv add --dev pytest

# Update all dependencies
uv lock --upgrade
```

### Variant Management

Use the variant commands to manage different PyTorch installations:

```bash
# List available extras
mltoolbox variant list-extras

# Install specific PyTorch variant
mltoolbox variant install-torch cuda

# Sync with specific extras
mltoolbox variant sync --extra cuda --extra dev
```

## Backlog

- Skypilot integration to spin up instances from cli
- Use a per-project config file for advanced configuration
- integration with ray job queue and gpuboard project for observability
- cleaner, less hardcoded defaults for dockerfiles, etc.
- Rich devcontainer support

```