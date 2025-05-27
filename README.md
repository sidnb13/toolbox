# toolbox

Monorepo with containerization and setup tools for bootstrapping my ML research projects.

## Features

- **Modern dependency management** with [uv](https://github.com/astral-sh/uv) and `pyproject.toml`
- **Containerized development** with Docker and Docker Compose
- **Multiple PyTorch variants** (CPU, CUDA, CUDA nightly) with automatic index management
- **Ray integration** for distributed computing
- **Project templating** with sensible ML defaults

## Backlog

- Use a per-project config file for advanced configuration
- integration with ray job queue and gpuboard project for observability

```
