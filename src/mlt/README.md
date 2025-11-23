# mlt - ML Toolbox Remote Helper

A lightweight CLI tool for managing ML development containers and providing LSP proxy functionality with path translation.

## Installation

```bash
pip install mlt-toolbox
```

## Features

- **Smart LSP Wrapper**: Auto-detects local vs remote context for seamless editing
- **LSP Proxy**: Transparent path translation for LSP servers running in Docker containers
- **Package Sync**: Automatic hardlink-based sync for LSP access to container packages
- **Container Management**: Quick attach and status commands
- **Auto-detection**: Automatically finds containers based on project context

## Usage

```bash
# Smart LSP wrapper (auto-detects local/remote)
mlt lsp-auto ruff server
mlt lsp-auto basedpyright-langserver --stdio

# Direct LSP proxy (manual container selection)
mlt lsp-proxy ruff server
mlt lsp-proxy basedpyright-langserver --stdio

# Package sync for LSP
mlt sync-lsp              # One-time sync
mlt sync-lsp --daemon     # Run as watchdog daemon

# Container management
mlt attach [container-name]
mlt container
mlt status
```

## How it works

`mlt` reads your `docker-compose.yml` to understand path mappings between host and container, then transparently translates file paths in LSP communication so that LSP servers running inside containers work seamlessly with editors on the host.
