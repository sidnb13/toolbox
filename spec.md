# MLToolbox v3.0 Architecture Specification

**Vision**: A lightweight, extensible ML development infrastructure toolkit that's editor-agnostic, cloud-agnostic, and built on clean abstractions rather than hardcoded logic.

**Philosophy**:
- Tool, not framework - compose primitives, don't dictate workflow
- Local relay for rich dev experience, but CLI works standalone
- Server-side agent for easy container access (no complex docker commands)
- Configuration as code, not hardcoded templates
- Plugin-based extensions, not monolithic features

---

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Multi-Backend Provisioning](#multi-backend-provisioning)
3. [Relay Architecture](#relay-architecture)
4. [Server-Side Agent](#server-side-agent)
5. [Configuration System](#configuration-system)
6. [Editor Agnostic Design](#editor-agnostic-design)
7. [Migration Path](#migration-path)

---

## Architecture Overview

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ Local Machine                                               │
│                                                             │
│  ┌────────────────┐      ┌──────────────────────────────┐  │
│  │ mltoolbox CLI  │─────>│ Relay Container (optional)   │  │
│  │ (thin client)  │ HTTP │                              │  │
│  └────────────────┘      │ - FastAPI server             │  │
│         │                │ - WebSocket manager          │  │
│         │ (or direct)    │ - State + metrics            │  │
│         │                │ - Provisioning orchestrator  │  │
│         ▼                └────────┬─────────────────────┘  │
│  ┌────────────────┐              │                         │
│  │ Backend Plugins│              │ WebSocket/SSH           │
│  │ - Lambda       │              │                         │
│  │ - Shadeform    │              │                         │
│  │ - AWS/GCP/etc  │              │                         │
│  └────────────────┘              │                         │
└──────────────────────────────────┼─────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────┐
│ Remote GPU Instance (provisioned via backend)               │
│                                                             │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Host OS (Ubuntu, etc.)                             │    │
│  │                                                    │    │
│  │  ┌──────────────────────────────────────────────┐ │    │
│  │  │ mltoolbox-agent (server-side CLI)            │ │    │
│  │  │ - Lightweight daemon                         │ │    │
│  │  │ - Manages containers                         │ │    │
│  │  │ - Metrics collection                         │ │    │
│  │  │ - Easy shell access: `mlt shell`             │ │    │
│  │  └──────────────────────────────────────────────┘ │    │
│  │                                                    │    │
│  │  ┌──────────────────────────────────────────────┐ │    │
│  │  │ Project Container                            │ │    │
│  │  │ - User's ML environment                      │ │    │
│  │  │ - Configured via mltoolbox.yaml              │ │    │
│  │  │ - Works with devcontainer.json (optional)    │ │    │
│  │  │ - Works with plain Dockerfile (optional)     │ │    │
│  │  │                                              │ │    │
│  │  │  SSH server on port 2222 ──┐                │ │    │
│  │  │  (for Zed, VSCode SSH)     │                │ │    │
│  │  └────────────────────────────┼────────────────┘ │    │
│  │                                │                   │    │
│  └────────────────────────────────┼───────────────────┘    │
│                                   │                        │
│         ┌─────────────────────────┘                        │
│         ▼                                                  │
│  Port forwarding: 2222 → 2222 (container SSH)             │
│                   8265 → 8265 (Ray dashboard)              │
└─────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Separation of Concerns**
   - Provisioning: Backend plugins handle instance lifecycle
   - Environment: Configuration system defines containers
   - Connection: Relay/Agent handle communication
   - Editor: Tooling adapts to editor, not vice versa

2. **Graceful Degradation**
   - CLI works standalone (direct SSH)
   - Relay optional (adds rich features)
   - Agent optional (fallback to docker exec)
   - Plugins optional (core functionality independent)

3. **Configuration Over Convention**
   - User-defined configs, not hardcoded templates
   - Extensible schema with sensible defaults
   - Override anything at any level

---

## Multi-Backend Provisioning

### Backend Interface

All provisioning backends implement a common interface:

```python
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class InstanceSpec:
    """User's requirements for an instance"""
    gpu_type: str  # "A100", "H100", "4090", etc.
    gpu_count: int = 1
    cpu_count: Optional[int] = None
    ram_gb: Optional[int] = None
    disk_gb: int = 100
    region: Optional[str] = None
    spot: bool = False

@dataclass
class AvailableInstance:
    """Instance available from backend"""
    backend_name: str
    instance_type: str
    gpu_type: str
    gpu_count: int
    price_per_hour: float
    region: str
    available_count: int
    backend_specific: Dict[str, Any]  # For provider-specific fields

@dataclass
class ProvisionedInstance:
    """Running instance"""
    backend_name: str
    instance_id: str
    ip_address: str
    ssh_port: int = 22
    username: str = "ubuntu"
    ssh_key_path: str
    status: str  # "pending", "running", "terminated"
    metadata: Dict[str, Any]

class ProvisioningBackend(ABC):
    """Abstract interface for cloud providers"""

    @abstractmethod
    async def list_available(self, spec: InstanceSpec) -> List[AvailableInstance]:
        """List instances matching spec"""
        pass

    @abstractmethod
    async def provision(
        self,
        instance_type: str,
        ssh_key: str,
        tags: Optional[Dict[str, str]] = None
    ) -> ProvisionedInstance:
        """Provision a new instance"""
        pass

    @abstractmethod
    async def terminate(self, instance_id: str) -> bool:
        """Terminate instance"""
        pass

    @abstractmethod
    async def get_status(self, instance_id: str) -> ProvisionedInstance:
        """Get instance status"""
        pass

    @abstractmethod
    async def get_pricing(self, instance_type: str) -> float:
        """Get current pricing ($/hour)"""
        pass
```

### Concrete Implementations

```python
# Plugins structure
src/mltoolbox/backends/
├── __init__.py
├── base.py                    # Abstract interface
├── lambda_labs.py             # Lambda Labs implementation
├── shadeform.py               # Shadeform implementation
├── aws_spot.py                # AWS EC2 Spot
├── gcp_preemptible.py         # GCP Preemptible
├── vast_ai.py                 # Vast.ai
└── runpod.py                  # RunPod

# Each backend is self-contained
class LambdaLabsBackend(ProvisioningBackend):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = LambdaLabsClient(api_key)

    async def list_available(self, spec: InstanceSpec) -> List[AvailableInstance]:
        raw_instances = await self.client.list_instances()
        return [
            AvailableInstance(
                backend_name="lambda",
                instance_type=inst["instance_type"],
                gpu_type=inst["gpu_type"],
                gpu_count=inst["gpu_count"],
                price_per_hour=inst["price"],
                region=inst["region"],
                available_count=inst["available"],
                backend_specific=inst
            )
            for inst in raw_instances
            if self._matches_spec(inst, spec)
        ]

    async def provision(self, instance_type: str, ssh_key: str, **kwargs):
        result = await self.client.provision(instance_type, ssh_key)
        return ProvisionedInstance(
            backend_name="lambda",
            instance_id=result["id"],
            ip_address=result["ip"],
            username="ubuntu",
            ssh_key_path=ssh_key,
            status="running",
            metadata=result
        )
```

### Smart Provisioning

```python
class ProvisioningOrchestrator:
    """Finds best instance across all backends"""

    def __init__(self, backends: Dict[str, ProvisioningBackend]):
        self.backends = backends

    async def find_best(
        self,
        spec: InstanceSpec,
        strategy: str = "price"  # or "availability", "performance"
    ) -> tuple[str, AvailableInstance]:
        """
        Query all backends, return best match

        Strategy:
        - price: Cheapest per hour
        - availability: Most available right now
        - performance: Best GPU/CPU combo
        """
        all_available = []
        for name, backend in self.backends.items():
            try:
                instances = await backend.list_available(spec)
                all_available.extend(instances)
            except Exception as e:
                logger.warning(f"Backend {name} failed: {e}")

        if not all_available:
            raise NoInstancesAvailableError(spec)

        if strategy == "price":
            best = min(all_available, key=lambda x: x.price_per_hour)
        elif strategy == "availability":
            best = max(all_available, key=lambda x: x.available_count)
        # ... other strategies

        return best.backend_name, best

    async def provision_best(self, spec: InstanceSpec, **kwargs):
        """Find and provision in one call"""
        backend_name, instance = await self.find_best(spec)
        backend = self.backends[backend_name]
        return await backend.provision(instance.instance_type, **kwargs)
```

### CLI Interface

```bash
# Configure backends
mltoolbox backend add lambda --api-key $LAMBDA_KEY
mltoolbox backend add shadeform --api-key $SHADEFORM_KEY
mltoolbox backend list

# Search across all backends
mltoolbox search --gpu A100 --region us-west
# Output:
# Backend      Type              GPU      Price/hr  Available
# lambda       gpu_1x_a100_sxm4  1×A100   $1.29     3
# shadeform    a100_1x_pcie      1×A100   $1.15     12
# aws_spot     p4d.24xlarge      8×A100   $8.20     spot (bid)

# Provision (auto-selects best)
mltoolbox provision --gpu A100 --strategy price
# → Provisions shadeform a100_1x_pcie ($1.15/hr)

# Or specify backend
mltoolbox provision --backend lambda --type gpu_1x_a100_sxm4

# Terminate
mltoolbox terminate <instance-id>

# List your instances across all backends
mltoolbox instances
# Backend      ID           Status    GPU      Region     Cost (24h)
# lambda       abc123       running   1×A100   us-west-1  $30.96
# shadeform    xyz789       running   1×H100   us-east-1  $52.80
```

### Auto-Provisioning Integration

```yaml
# mltoolbox.yaml - project config
auto_provision:
  enabled: true

  # Specify requirements
  requirements:
    gpu_type: A100
    gpu_count: 1
    min_ram_gb: 64
    region: us-west

  # Provisioning strategy
  strategy: price  # or availability, performance

  # Optional: preferred backends (in order)
  prefer_backends:
    - shadeform
    - lambda

  # Auto-setup after provision
  setup:
    - git clone {{ repo_url }}
    - mltoolbox agent install  # Install server-side agent
    - mltoolbox env setup       # Setup container from config

# Integration with instancebot
watch:
  enabled: true
  instance_types:
    - gpu_1x_a100_sxm4
  on_available:
    - provision: true
    - setup: true
    - notify: slack
```

---

## Relay Architecture

### Why Relay?

The relay container provides:
1. **Persistent connections** - No SSH handshake overhead
2. **State management** - Single source of truth
3. **Real-time streaming** - Logs, metrics, events
4. **Async operations** - Non-blocking sync, provision, etc.
5. **Web interface** - Bonus dashboard
6. **Multi-client** - Multiple terminals share state

### Relay Container

```python
# FastAPI server inside Docker container
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
import asyncio

app = FastAPI()

class RelayManager:
    """Manages connections to remote agents"""

    def __init__(self):
        self.connections: Dict[str, WebSocketConnection] = {}
        self.state_db = StateDB()  # SQLite or Redis

    async def connect_to_remote(self, remote_id: str, host: str, port: int):
        """Establish WebSocket connection to remote agent"""
        ws = await websocket_client.connect(f"ws://{host}:{port}/agent")
        self.connections[remote_id] = ws

        # Start background tasks
        asyncio.create_task(self._stream_metrics(remote_id))
        asyncio.create_task(self._stream_logs(remote_id))

    async def execute_command(self, remote_id: str, cmd: dict):
        """Send command to remote agent"""
        ws = self.connections[remote_id]
        await ws.send_json(cmd)
        return await ws.receive_json()

relay = RelayManager()

# API endpoints
@app.post("/connect")
async def connect(remote_id: str, host: str, port: int = 7777):
    """Connect to remote agent"""
    await relay.connect_to_remote(remote_id, host, port)
    return {"status": "connected"}

@app.post("/sync")
async def sync(remote_id: str, source: str, dest: str):
    """Trigger sync (non-blocking)"""
    task_id = await relay.execute_command(remote_id, {
        "action": "sync",
        "source": source,
        "dest": dest
    })
    return {"task_id": task_id, "status": "started"}

@app.get("/sync/{task_id}/status")
async def sync_status(task_id: str):
    """Check sync progress"""
    return relay.state_db.get_task_status(task_id)

@app.websocket("/stream/logs/{remote_id}")
async def stream_logs(websocket: WebSocket, remote_id: str):
    """Stream logs from remote to client"""
    await websocket.accept()
    async for log_line in relay.get_log_stream(remote_id):
        await websocket.send_text(log_line)

@app.websocket("/stream/metrics/{remote_id}")
async def stream_metrics(websocket: WebSocket, remote_id: str):
    """Stream GPU/system metrics"""
    await websocket.accept()
    async for metrics in relay.get_metrics_stream(remote_id):
        await websocket.send_json(metrics)

# Web dashboard
app.mount("/dashboard", StaticFiles(directory="static"), name="static")
```

### Relay Container Lifecycle

```bash
# Start relay (runs in Docker)
mltoolbox relay start
# → Runs container: ghcr.io/sidbaskaran/mltoolbox-relay:latest
# → Exposes: localhost:7776 (API), localhost:7777 (WebSocket)
# → Mounts: ~/.config/mltoolbox (for state/config)

# CLI auto-detects relay
mltoolbox connect myserver
# → CLI checks: Is relay running at localhost:7776?
# → If yes: POST to relay API
# → If no: Fall back to direct SSH

# Stop relay
mltoolbox relay stop

# View relay logs
mltoolbox relay logs
```

### Protocol: CLI ↔ Relay ↔ Agent

```
┌─────────────┐                ┌───────────────┐               ┌──────────────┐
│ CLI         │                │ Relay         │               │ Remote Agent │
└──────┬──────┘                └───────┬───────┘               └──────┬───────┘
       │                               │                              │
       │ POST /sync                    │                              │
       ├──────────────────────────────>│                              │
       │                               │                              │
       │ {"task_id": "abc123"}         │ WS: {"action": "sync"}       │
       │<──────────────────────────────┤─────────────────────────────>│
       │                               │                              │
       │                               │ WS: {"progress": "10%"}      │
       │                               │<─────────────────────────────┤
       │                               │                              │
       │ GET /sync/abc123/status       │                              │
       ├──────────────────────────────>│                              │
       │                               │                              │
       │ {"status": "running", ...}    │                              │
       │<──────────────────────────────┤                              │
       │                               │                              │
       │ WS /stream/logs               │ WS: {"log": "..."}           │
       ├──────────────────────────────>│<─────────────────────────────┤
       │ (streaming logs)              │ (forwarding)                 │
       │<──────────────────────────────┤                              │
```

---

## Server-Side Agent

### Problem Statement

**Current**: To access container, you need complex commands:
```bash
ssh myserver
docker exec -it myproject-dev /bin/bash
# Or even worse with docker-compose
```

**Goal**: Simple, editor-agnostic access:
```bash
# From host
mlt shell            # Enter container
mlt run pytest       # Run command in container
mlt logs --follow    # Stream container logs

# Works from any editor:
# - VSCode Remote SSH → connects to host → mlt shell
# - Zed Remote SSH → same thing
# - Plain SSH → same thing
```

### Agent Architecture

```python
# Lightweight daemon on remote host
# Installed via: curl -sSL install.mltoolbox.dev | bash

class MLToolboxAgent:
    """Server-side agent running on remote host"""

    def __init__(self, config_path: str = "/etc/mltoolbox/agent.yaml"):
        self.config = load_config(config_path)
        self.docker_client = docker.from_env()
        self.ws_server = WebSocketServer(port=7777)  # For relay
        self.metrics_collector = MetricsCollector()

    async def start(self):
        """Start agent daemon"""
        # Start WebSocket server for relay connection
        asyncio.create_task(self.ws_server.start())

        # Start metrics collection
        asyncio.create_task(self.metrics_collector.start())

        # Watch for container events
        asyncio.create_task(self.watch_containers())

    async def handle_relay_command(self, cmd: dict):
        """Handle commands from relay"""
        action = cmd["action"]

        if action == "sync":
            return await self.sync(cmd["source"], cmd["dest"])
        elif action == "exec":
            return await self.exec_in_container(cmd["command"])
        elif action == "logs":
            return await self.stream_logs(cmd.get("follow", False))
        # ... more actions

    def get_active_container(self) -> str:
        """Get the project container (from config or auto-detect)"""
        if self.config.container_name:
            return self.config.container_name

        # Auto-detect: Find container with mltoolbox label
        containers = self.docker_client.containers.list()
        for c in containers:
            if "mltoolbox.project" in c.labels:
                return c.name

        raise NoActiveContainerError()
```

### Agent CLI (server-side)

```bash
# Lightweight CLI installed on remote host
# Binary at: /usr/local/bin/mlt (or mltoolbox-agent)

$ mlt shell
# → Automatically finds project container
# → Runs: docker exec -it <container> /bin/zsh (or bash)

$ mlt run "pytest tests/"
# → Runs in container context

$ mlt logs -f
# → docker logs -f <container>

$ mlt status
# Container: myproject-dev (running)
# GPU:       1×A100 (45% utilized)
# Memory:    23.4GB / 64GB
# Uptime:    2h 34m

$ mlt metrics
# GPU 0:  45% | 23.4GB / 40GB | 67°C
# CPU:    12% (8 cores)
# RAM:    45% (64GB total)
# Disk:   234GB / 1TB

$ mlt sync pull
# Triggers rsync from container to host (if needed)

$ mlt ssh-keygen
# Generates SSH key for container, enables SSH access
```

### Container SSH Access

The agent ensures containers expose SSH:

```yaml
# When setting up container, agent injects:
services:
  project:
    # ... existing config
    ports:
      - "2222:22"  # Container SSH port

    # Agent adds at runtime:
    volumes:
      - ~/.ssh/authorized_keys:/root/.ssh/authorized_keys:ro

# Then SSH directly into container:
ssh -p 2222 root@myserver

# This works with:
# - VSCode Remote SSH (just configure port 2222)
# - Zed Remote SSH
# - Any SSH-based editor
```

### Agent Configuration

```yaml
# /etc/mltoolbox/agent.yaml
project:
  name: myproject
  container_name: myproject-dev  # Or auto-detect

  # Container config (replaces hardcoded templates)
  image: ghcr.io/sidbaskaran/ml-base:py3.12-cuda

  # Or use existing Dockerfile/compose
  dockerfile: ./Dockerfile
  compose_file: ./docker-compose.yml

relay:
  enabled: true
  port: 7777
  auth_token: ${MLTOOLBOX_RELAY_TOKEN}

ssh:
  enabled: true
  port: 2222
  shell: /bin/zsh

metrics:
  collect_interval: 10s
  gpu: true
  disk: true
  network: true

logging:
  level: INFO
  rotate: true
  max_size: 100MB
```

---

## Configuration System

### Problem: Hardcoded Templates Are Rigid

**Current approach**:
- `.env.j2`, `Dockerfile.j2`, `docker-compose.yml.j2` are hardcoded
- Limited flexibility
- Can't easily adapt to different workflows
- Difficult to extend

**New approach**: Configuration as code with sensible defaults

### Config Schema

```yaml
# mltoolbox.yaml - Lives in project root
# Replaces hardcoded templates

version: "3.0"

project:
  name: myproject

environment:
  # Flexible environment config
  base_image: ghcr.io/sidbaskaran/ml-base:py3.12-cuda

  # Or bring your own
  dockerfile: ./Dockerfile

  # Or use devcontainer.json
  devcontainer: .devcontainer/devcontainer.json

  # Environment variables (no more .env.j2 template)
  env:
    WANDB_PROJECT: myproject
    HF_HOME: /workspace/.cache/huggingface
    # Reference secrets (stored securely)
    WANDB_API_KEY: ${secret:wandb_api_key}

  # Mounts
  volumes:
    - ./data:/workspace/data
    - ~/.gitconfig:/root/.gitconfig:ro
    - ${HOME}/.ssh:/root/.ssh:ro

  # Ports
  ports:
    - "8888:8888"  # Jupyter
    - "6006:6006"  # TensorBoard
    - "2222:22"    # Container SSH

  # GPU config
  gpu:
    count: 1
    driver_version: ">=525.0"

  # Network mode
  network_mode: bridge  # or host

# Ray (optional)
ray:
  enabled: true
  dashboard_port: 8265

# Sync config (replaces gitignore/dockerignore parsing)
sync:
  exclude:
    - "*.pyc"
    - "__pycache__/"
    - "*.ipynb_checkpoints"
    - ".git/"
    - "data/raw/"  # Large datasets
    - "checkpoints/*.pth"

  include_overrides:
    - "configs/*.yaml"  # Always sync configs

  # Sync strategy
  strategy: rsync  # or rclone, git

  # Watch for changes (if relay enabled)
  watch: true
  debounce: 2s

# Provisioning (optional)
provision:
  auto: false  # Auto-provision if no instance

  requirements:
    gpu_type: A100
    gpu_count: 1
    region: us-west

  strategy: price

  backends:
    lambda:
      enabled: true
      api_key: ${secret:lambda_api_key}

    shadeform:
      enabled: true
      api_key: ${secret:shadeform_api_key}

# Hooks (optional)
hooks:
  on_connect:
    - echo "Connected to {{ remote.host }}"
    - git pull

  on_sync:
    - echo "Synced {{ sync.files_changed }} files"

  on_container_start:
    - pip install -e .
    - pre-commit install

# Plugins (optional)
plugins:
  - wandb-integration
  - slack-notifications
```

### Config Resolution

```python
class ConfigLoader:
    """Loads and merges configs from multiple sources"""

    def load(self, project_dir: Path) -> Config:
        """
        Priority (highest to lowest):
        1. CLI arguments
        2. Environment variables
        3. mltoolbox.yaml (project)
        4. ~/.config/mltoolbox/config.yaml (user)
        5. /etc/mltoolbox/config.yaml (system)
        6. Defaults
        """
        configs = [
            self.load_defaults(),
            self.load_system_config(),
            self.load_user_config(),
            self.load_project_config(project_dir),
            self.load_env_overrides(),
            self.load_cli_overrides(),
        ]

        # Deep merge
        return merge_configs(*configs)

    def resolve_secrets(self, config: Config) -> Config:
        """
        Resolve ${secret:name} references

        Secrets stored in:
        - ~/.config/mltoolbox/secrets.yaml (encrypted)
        - Environment variables
        - OS keychain (macOS/Linux)
        """
        for key, value in config.env.items():
            if isinstance(value, str) and value.startswith("${secret:"):
                secret_name = value[9:-1]  # Extract name
                config.env[key] = self.get_secret(secret_name)

        return config
```

### Backward Compatibility

```python
# Auto-migrate from old structure
if Path(".env").exists() and not Path("mltoolbox.yaml").exists():
    logger.info("Detected legacy config, migrating...")

    # Parse old .env file
    env_vars = parse_dotenv(".env")

    # Parse old Dockerfile if present
    dockerfile_config = parse_dockerfile("Dockerfile") if Path("Dockerfile").exists() else {}

    # Generate mltoolbox.yaml
    config = generate_config_from_legacy(env_vars, dockerfile_config)

    config.save("mltoolbox.yaml")

    logger.info("✓ Migrated to mltoolbox.yaml")
    logger.info("  Review and customize: mltoolbox.yaml")
    logger.info("  Old files preserved (safe to delete after verification)")
```

---

## Editor Agnostic Design

### The Problem

Different editors have different remote development approaches:
- **VSCode**: Dev Containers (docker-in-docker) or Remote SSH
- **Zed**: Remote SSH only
- **Cursor**: Same as VSCode
- **JetBrains**: Gateway (JetBrains Client/Server)
- **Vim/Emacs**: SSH + tmux

### The Solution: Server-Side Agent + Container SSH

```
┌────────────────────────────────────────────────────────┐
│ Editor (Any)                                           │
│                                                        │
│  VSCode / Zed / Cursor / JetBrains / etc.             │
│                                                        │
└────────────────┬───────────────────────────────────────┘
                 │ SSH (port 22)
                 ▼
┌────────────────────────────────────────────────────────┐
│ Remote Host                                            │
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │ mltoolbox-agent                                  │ │
│  │ - `mlt shell` for easy access                    │ │
│  └──────────────────────────────────────────────────┘ │
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │ Container (sshd on port 2222)                    │ │
│  │ - Can SSH directly: ssh -p 2222 root@host       │ │
│  │ - Or via agent: mlt shell                        │ │
│  └──────────────────────────────────────────────────┘ │
│                                                        │
│  Port forwarding: 2222 → 2222 (optional)              │
└────────────────────────────────────────────────────────┘
```

### VSCode Dev Container Compatibility

```jsonc
// .devcontainer/devcontainer.json
{
  "name": "ML Project",
  "image": "ghcr.io/sidbaskaran/ml-base:py3.12-cuda",

  // mltoolbox reads this and respects it
  "customizations": {
    "vscode": {
      "extensions": ["ms-python.python", "ms-toolsai.jupyter"]
    }
  },

  "mounts": [
    "source=${localWorkspaceFolder},target=/workspace,type=bind"
  ],

  "runArgs": ["--gpus", "all"],

  "postCreateCommand": "pip install -e ."
}
```

**How mltoolbox uses this**:
```bash
# If devcontainer.json exists, use it
mltoolbox env setup
# → Reads .devcontainer/devcontainer.json
# → Builds/pulls image
# → Respects mounts, runArgs, etc.
# → Runs postCreateCommand

# VSCode can also use it directly (no conflict)
```

### Zed Remote SSH Support

```toml
# Zed config: ~/.config/zed/settings.json
{
  "ssh_connections": [
    {
      "host": "myserver",
      "port": 22,
      "user": "ubuntu",

      // After SSH, run `mlt shell` to enter container
      "startup_command": "mlt shell"
    }
  ]
}
```

**Or SSH directly into container**:
```toml
{
  "ssh_connections": [
    {
      "host": "myserver",
      "port": 2222,  // Container SSH port
      "user": "root"
    }
  ]
}
```

### JetBrains Gateway Support

Gateway connects via SSH, then spins up IDE server. Works seamlessly:
```bash
# Gateway SSHs to host, then:
mlt shell
# Now in container, Gateway IDE server starts
```

### Plain SSH + tmux

```bash
# Traditional workflow still works
ssh myserver
mlt shell
tmux attach
# Vim/Emacs/etc. as usual
```

---

## Migration Path

### Phase 1: Foundation (v3.0-alpha)

**Goals**:
- New config system (mltoolbox.yaml)
- Refactor away from hardcoded templates
- Server-side agent (basic)
- Backward compatibility maintained

**Changes**:
```bash
# Old way still works
mltoolbox remote connect myserver

# New way (if mltoolbox.yaml exists)
mltoolbox connect myserver
# → Reads mltoolbox.yaml for config
# → Uses agent if installed on remote
# → Falls back to old behavior if not
```

**Migration tool**:
```bash
mltoolbox migrate
# → Converts .env + Dockerfile → mltoolbox.yaml
# → Preserves old files (non-destructive)
# → Warns about manual review needed
```

### Phase 2: Multi-Backend Provisioning (v3.1)

**Goals**:
- Backend plugin system
- Lambda Labs + Shadeform implementations
- Smart provisioning
- Auto-provision integration

**New commands**:
```bash
mltoolbox backend add lambda --api-key xxx
mltoolbox search --gpu A100
mltoolbox provision --gpu A100 --strategy price
```

### Phase 3: Relay Architecture (v3.2)

**Goals**:
- Optional relay container
- WebSocket communication
- Real-time streaming
- Web dashboard

**New workflow**:
```bash
# Opt-in relay
mltoolbox relay start

# CLI automatically uses relay if available
mltoolbox sync myserver
# → Non-blocking, progress in background

# Stream logs
mltoolbox logs --follow
# → WebSocket streaming, faster than SSH

# Web UI
open http://localhost:7776/dashboard
```

### Phase 4: Advanced Features (v3.3+)

- Plugin ecosystem
- Experiment tracking integration
- Cost tracking
- Advanced auto-provisioning
- Metrics and observability
- Multi-project workspaces

---

## Technical Decisions

### Why FastAPI for Relay?
- Modern async framework
- WebSocket support built-in
- Auto-generated OpenAPI docs
- Easy to extend with plugins
- Good performance

### Why WebSocket over gRPC?
- Simpler for browser-based dashboard
- Firewall-friendly (HTTP upgrade)
- Good enough performance for our use case
- Easier debugging (can inspect with browser tools)

### Why SQLite for State?
- No external dependencies
- Good enough for single-user tool
- Easy backup (just copy file)
- Can upgrade to Postgres/Redis later if needed

### Why YAML for Config?
- Human-readable
- Comments support
- Standard in devops tools
- Good Python libraries (PyYAML, ruamel.yaml)

### Why Server-Side Agent vs. Agentless?
- Better UX (mlt shell vs. complex docker commands)
- Enables real-time features (metrics, logs)
- Minimal overhead (lightweight daemon)
- Optional (falls back to SSH)

---

## Open Questions

1. **Secret management**: Use OS keychain, encrypted file, or external service (Vault)?
2. **Relay discovery**: How does CLI find relay? (localhost:7776 convention? Config file?)
3. **Multi-relay**: Support multiple relay containers for different projects?
4. **Agent installation**: Auto-install agent on first connect, or require manual install?
5. **Container registry**: Keep using GHCR, or support multiple (Docker Hub, private registries)?
6. **Versioning**: How to handle agent/relay version mismatches?
7. **Offline mode**: How much should work without internet?

---

## Success Metrics

**v3.0 is successful if**:
- Existing workflows continue to work (backward compatibility)
- New users can get started in <5 minutes
- Config system is more flexible than templates
- Server-side agent provides clear UX improvement
- Documentation is comprehensive

**v3.x is successful if**:
- Users prefer multi-backend provisioning over manual
- Relay provides noticeable performance improvement
- Ecosystem grows (community plugins)
- Tool is editor-agnostic (confirmed by Zed/JetBrains users)
- Total LOC decreases (better abstractions = less code)

---

## Next Steps

1. **Prototype**: Build proof-of-concept for relay architecture
2. **Design**: Finalize config schema (get feedback)
3. **Implement**: Start with Phase 1 (foundation)
4. **Test**: Ensure backward compatibility
5. **Document**: Write migration guide
6. **Release**: v3.0-alpha for early adopters
