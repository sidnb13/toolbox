# mlt - ML Toolbox Remote Helper

A lightweight CLI tool for managing ML development containers and providing LSP proxy functionality with path translation.

## Installation

```bash
pip install mlt-toolbox
```

## Features

- **LSP Proxy**: Transparent path translation for LSP servers running in Docker containers
- **Container Management**: Quick attach and status commands
- **Auto-detection**: Automatically finds containers based on project context

## Usage

```bash
# LSP proxy (called by editors like Zed)
mlt lsp-proxy ruff server
mlt lsp-proxy basedpyright-langserver --stdio

# Attach to container
mlt attach [container-name]

# Show container for current project
mlt container

# Show status
mlt status
```

## How it works

`mlt` reads your `docker-compose.yml` to understand path mappings between host and container, then transparently translates file paths in LSP communication so that LSP servers running inside containers work seamlessly with editors on the host.
