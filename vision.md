# MLToolbox v3.0 Vision & Refactoring Plan

**Problem**: Current codebase has accumulated technical debt through hardcoded logic, rigid templates, and monolithic implementations that make extension and maintenance difficult.

**Goal**: Transform mltoolbox from a "hacky collection of scripts" into a "composable toolkit with clean abstractions."

---

## Current Pain Points

### 1. Hardcoded Templates
```python
# Current: templates are static Jinja2 files
src/mltoolbox/templates/
├── .env.j2                    # Hardcoded env vars
├── Dockerfile.j2              # Rigid Dockerfile structure
└── docker-compose.yml.j2      # Fixed compose config

# Problems:
# - Can't easily customize without forking
# - Limited to predefined variables
# - No way to inject custom logic
# - Difficult to support different workflows (e.g., devcontainer users)
```

### 2. Monolithic CLI Commands
```python
# remote.py is 919 lines with tons of responsibilities:
@remote.command()
def connect(...):  # Does EVERYTHING
    # 1. Parse args
    # 2. DB operations
    # 3. SSH setup
    # 4. Docker operations
    # 5. Sync logic
    # 6. Port forwarding
    # 7. Container attach

# Problems:
# - Hard to test individual pieces
# - Difficult to reuse logic
# - Changes ripple across codebase
# - No clear separation of concerns
```

### 3. Scattered Configuration
```python
# Config is spread everywhere:
# - CLI arguments
# - .env files
# - Database
# - Hardcoded defaults in code
# - Environment variables

# No single source of truth
# No schema validation
# Difficult to reason about precedence
```

### 4. Tight Coupling
```python
# remote.py imports from everywhere:
from mltoolbox.utils.db import DB, Remote
from mltoolbox.utils.docker import (
    check_nvidia_toolkit,
    ensure_docker_group,
    start_or_build_container,
    # ... many more
)
from mltoolbox.utils.helpers import remote_cmd
from mltoolbox.utils.remote import (
    sync_project_to_host,
    setup_ssh_config,
    # ... many more
)

# Changes in utils/ can break CLI
# Hard to understand dependencies
# Circular dependencies lurking
```

### 5. No Extension Points
```python
# Want to add a feature? Must modify core files.
# No plugin system
# No hooks
# No way to customize without forking
```

---

## Refactoring Principles

### 1. **Dependency Inversion**
High-level modules shouldn't depend on low-level modules. Both should depend on abstractions.

**Before**:
```python
# CLI directly uses Docker client
def connect(...):
    docker_client = docker.from_env()
    container = docker_client.containers.run(...)
```

**After**:
```python
# CLI depends on abstract interface
def connect(..., container_manager: ContainerManager):
    container = container_manager.start_container(config)

# Concrete implementation injected
class DockerContainerManager(ContainerManager):
    def start_container(self, config):
        ...
```

### 2. **Single Responsibility**
Each module/class/function should have one reason to change.

**Before**:
```python
def connect(...):  # Does 10 different things
    setup_ssh()
    setup_docker()
    sync_files()
    start_container()
    forward_ports()
    attach()
```

**After**:
```python
# Orchestrator composes smaller units
class ConnectionOrchestrator:
    def __init__(
        self,
        ssh_manager: SSHManager,
        sync_manager: SyncManager,
        container_manager: ContainerManager,
        port_forwarder: PortForwarder,
    ):
        self.ssh = ssh_manager
        self.sync = sync_manager
        self.containers = container_manager
        self.ports = port_forwarder

    def connect(self, config: ConnectionConfig):
        self.ssh.setup(config.remote)
        self.sync.sync_to_remote(config.sync)
        container = self.containers.start(config.container)
        self.ports.forward(config.ports)
        return container
```

### 3. **Configuration as Data**
Configuration should be declarative, validated, and composable.

**Before**:
```python
# Hardcoded Jinja2 template
# .env.j2:
WANDB_PROJECT={{ wandb_project }}
GIT_EMAIL={{ git_email }}
```

**After**:
```yaml
# mltoolbox.yaml (validated against schema)
environment:
  env:
    WANDB_PROJECT: myproject
    GIT_EMAIL: user@example.com

  # Or use profile
  profile: ml-research  # Loads predefined env vars

  # Or load from file
  env_file: .env

  # Or use secret references
  env:
    WANDB_API_KEY: ${secret:wandb_api_key}
```

### 4. **Plugin Architecture**
Core functionality is minimal, features are plugins.

**Before**:
```python
# Everything in core
# Want Ray support? Modify docker.py
# Want W&B integration? Modify remote.py
```

**After**:
```python
# Core provides hooks, plugins extend
class PluginManager:
    def __init__(self):
        self.plugins = []

    def register(self, plugin: Plugin):
        self.plugins.append(plugin)

    def run_hook(self, hook_name: str, context: dict):
        for plugin in self.plugins:
            if hasattr(plugin, hook_name):
                getattr(plugin, hook_name)(context)

# Plugin example
class RayPlugin(Plugin):
    def on_container_start(self, context):
        if context.config.ray.enabled:
            self.start_ray_head(context.container)

# In CLI
plugin_manager.run_hook("on_container_start", {
    "container": container,
    "config": config,
})
```

---

## Refactored Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────┐
│ CLI Layer (thin)                                        │
│ - Argument parsing                                      │
│ - User interaction (Rich UI)                            │
│ - Delegates to orchestrators                            │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│ Orchestration Layer                                     │
│ - ConnectionOrchestrator                                │
│ - ProvisioningOrchestrator                              │
│ - SyncOrchestrator                                      │
│ - Composes services to implement workflows              │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│ Service Layer (business logic)                          │
│ - SSHManager                                            │
│ - ContainerManager (interface)                          │
│   ├── DockerContainerManager                            │
│   └── PodmanContainerManager (future)                   │
│ - SyncManager (interface)                               │
│   ├── RsyncSyncManager                                  │
│   └── RcloneSyncManager                                 │
│ - ConfigLoader                                          │
│ - SecretManager                                         │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│ Infrastructure Layer                                    │
│ - SSH client (Paramiko)                                 │
│ - Docker client                                         │
│ - Database (SQLAlchemy)                                 │
│ - File system                                           │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ Plugin System (cross-cutting)                           │
│ - Ray plugin                                            │
│ - W&B plugin                                            │
│ - Slack notifications                                   │
│ - Custom user plugins                                   │
└─────────────────────────────────────────────────────────┘
```

### Directory Structure (Refactored)

```
src/mltoolbox/
├── cli/
│   ├── __init__.py              # Entry point, minimal logic
│   ├── commands/
│   │   ├── connect.py           # Just parses args, delegates
│   │   ├── provision.py
│   │   ├── sync.py
│   │   └── configure.py
│   └── ui/                      # Rich UI components
│       ├── progress.py
│       ├── panels.py
│       └── tables.py
│
├── orchestrators/               # High-level workflows
│   ├── __init__.py
│   ├── connection.py            # ConnectionOrchestrator
│   ├── provisioning.py          # ProvisioningOrchestrator
│   └── sync.py                  # SyncOrchestrator
│
├── services/                    # Business logic
│   ├── __init__.py
│   ├── ssh/
│   │   ├── __init__.py
│   │   ├── manager.py           # SSHManager
│   │   └── config.py            # SSH config generation
│   ├── containers/
│   │   ├── __init__.py
│   │   ├── base.py              # ContainerManager interface
│   │   ├── docker.py            # DockerContainerManager
│   │   └── gpu.py               # GPU setup (NVIDIA toolkit)
│   ├── sync/
│   │   ├── __init__.py
│   │   ├── base.py              # SyncManager interface
│   │   ├── rsync.py             # RsyncSyncManager
│   │   └── rclone.py            # RcloneSyncManager
│   ├── config/
│   │   ├── __init__.py
│   │   ├── loader.py            # ConfigLoader
│   │   ├── schema.py            # Pydantic schemas
│   │   └── validator.py         # Config validation
│   └── secrets/
│       ├── __init__.py
│       ├── manager.py           # SecretManager
│       └── backends/
│           ├── keyring.py       # OS keychain
│           └── encrypted_file.py
│
├── backends/                    # Provisioning backends
│   ├── __init__.py
│   ├── base.py                  # ProvisioningBackend interface
│   ├── lambda_labs.py
│   ├── shadeform.py
│   └── registry.py              # Backend registry
│
├── plugins/                     # Plugin system
│   ├── __init__.py
│   ├── base.py                  # Plugin interface
│   ├── manager.py               # PluginManager
│   ├── builtin/                 # Built-in plugins
│   │   ├── ray.py
│   │   ├── wandb.py
│   │   └── gpu_metrics.py
│   └── loader.py                # Load external plugins
│
├── models/                      # Data models
│   ├── __init__.py
│   ├── config.py                # Configuration models (Pydantic)
│   ├── remote.py                # Remote model
│   ├── container.py             # Container model
│   └── instance.py              # Cloud instance model
│
├── utils/                       # Utilities (reduced)
│   ├── __init__.py
│   ├── logger.py
│   ├── subprocess.py
│   └── filesystem.py
│
└── db/                          # Database (SQLAlchemy)
    ├── __init__.py
    ├── models.py                # ORM models
    ├── session.py               # Session management
    └── migrations/              # Alembic migrations
```

---

## Key Refactorings

### 1. Configuration System

**Goal**: Replace hardcoded templates with flexible, validated configuration.

```python
# models/config.py - Pydantic for validation
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, List

class EnvironmentConfig(BaseModel):
    """Environment configuration"""

    # Base image or Dockerfile
    base_image: Optional[str] = None
    dockerfile: Optional[Path] = None
    devcontainer: Optional[Path] = None  # Support devcontainer.json

    # Environment variables
    env: Dict[str, str] = Field(default_factory=dict)
    env_file: Optional[Path] = None

    # Volumes
    volumes: List[str] = Field(default_factory=list)

    # Ports
    ports: List[str] = Field(default_factory=list)

    # GPU
    gpu_count: int = 1

    @validator('base_image', 'dockerfile', 'devcontainer')
    def validate_image_source(cls, v, values):
        """Ensure exactly one image source is specified"""
        sources = [values.get('base_image'), values.get('dockerfile'), v]
        if sum(x is not None for x in sources) != 1:
            raise ValueError("Specify exactly one: base_image, dockerfile, or devcontainer")
        return v

class SyncConfig(BaseModel):
    """Sync configuration"""
    exclude: List[str] = Field(default_factory=list)
    include_overrides: List[str] = Field(default_factory=list)
    strategy: str = "rsync"
    watch: bool = False

class MLToolboxConfig(BaseModel):
    """Root configuration"""
    version: str = "3.0"
    project: ProjectConfig
    environment: EnvironmentConfig
    sync: SyncConfig
    ray: Optional[RayConfig] = None
    provision: Optional[ProvisionConfig] = None
    hooks: Optional[HooksConfig] = None
    plugins: List[str] = Field(default_factory=list)

# services/config/loader.py
class ConfigLoader:
    """Loads and validates configuration"""

    def load(self, project_dir: Path) -> MLToolboxConfig:
        # Load from mltoolbox.yaml
        config_path = project_dir / "mltoolbox.yaml"

        if not config_path.exists():
            # Try to find devcontainer.json
            devcontainer = project_dir / ".devcontainer" / "devcontainer.json"
            if devcontainer.exists():
                return self.from_devcontainer(devcontainer)

            # Try to find Dockerfile
            dockerfile = project_dir / "Dockerfile"
            if dockerfile.exists():
                return self.from_dockerfile(dockerfile)

            # Use defaults
            return self.from_defaults(project_dir)

        # Parse YAML
        with open(config_path) as f:
            data = yaml.safe_load(f)

        # Validate with Pydantic
        config = MLToolboxConfig(**data)

        # Resolve secrets
        config = self.resolve_secrets(config)

        # Merge with user/system configs
        config = self.merge_configs(config)

        return config

    def from_devcontainer(self, path: Path) -> MLToolboxConfig:
        """Generate config from devcontainer.json"""
        with open(path) as f:
            devcontainer = json.load(f)

        return MLToolboxConfig(
            project=ProjectConfig(name=devcontainer.get("name", "project")),
            environment=EnvironmentConfig(
                base_image=devcontainer.get("image"),
                dockerfile=devcontainer.get("dockerFile"),
                volumes=devcontainer.get("mounts", []),
                # ... map other fields
            ),
            # ... rest of config with sensible defaults
        )
```

**Migration**:
```bash
$ mltoolbox migrate

Found legacy configuration:
  ✓ .env
  ✓ Dockerfile
  ✓ docker-compose.yml

Generating mltoolbox.yaml...

✓ mltoolbox.yaml created

Review and customize:
  $ cat mltoolbox.yaml
  $ mltoolbox config validate

Legacy files preserved (safe to delete after verification)
```

### 2. Service Layer Abstraction

**Goal**: Extract business logic into testable, reusable services.

```python
# services/containers/base.py
from abc import ABC, abstractmethod
from typing import Optional

class ContainerManager(ABC):
    """Abstract interface for container management"""

    @abstractmethod
    async def start_container(
        self,
        config: EnvironmentConfig,
        name: str,
    ) -> Container:
        """Start or create container"""
        pass

    @abstractmethod
    async def stop_container(self, container_id: str):
        """Stop container"""
        pass

    @abstractmethod
    async def exec_in_container(
        self,
        container_id: str,
        command: str,
    ) -> tuple[int, str]:
        """Execute command in container"""
        pass

    @abstractmethod
    async def get_logs(
        self,
        container_id: str,
        follow: bool = False,
    ) -> AsyncIterator[str]:
        """Get container logs"""
        pass

# services/containers/docker.py
class DockerContainerManager(ContainerManager):
    """Docker implementation"""

    def __init__(self, ssh_manager: Optional[SSHManager] = None):
        """
        Args:
            ssh_manager: If provided, manage remote Docker, else local
        """
        self.ssh = ssh_manager
        if ssh_manager:
            # Remote Docker via SSH
            self.client = docker.DockerClient(
                base_url=f"ssh://{ssh_manager.connection_string}"
            )
        else:
            # Local Docker
            self.client = docker.from_env()

    async def start_container(
        self,
        config: EnvironmentConfig,
        name: str,
    ) -> Container:
        # Check if container exists
        try:
            container = self.client.containers.get(name)
            if container.status != "running":
                container.start()
            return Container(id=container.id, name=name)
        except docker.errors.NotFound:
            pass

        # Build image if needed
        if config.dockerfile:
            image = await self._build_image(config.dockerfile)
        else:
            image = config.base_image

        # Create container
        container = self.client.containers.run(
            image,
            name=name,
            environment=config.env,
            volumes=self._parse_volumes(config.volumes),
            ports=self._parse_ports(config.ports),
            device_requests=self._gpu_device_requests(config.gpu_count),
            detach=True,
        )

        return Container(id=container.id, name=name)

    async def exec_in_container(
        self,
        container_id: str,
        command: str,
    ) -> tuple[int, str]:
        container = self.client.containers.get(container_id)
        exit_code, output = container.exec_run(command)
        return exit_code, output.decode()

    async def get_logs(
        self,
        container_id: str,
        follow: bool = False,
    ) -> AsyncIterator[str]:
        container = self.client.containers.get(container_id)
        for line in container.logs(stream=follow):
            yield line.decode()

# services/sync/base.py
class SyncManager(ABC):
    """Abstract interface for file sync"""

    @abstractmethod
    async def sync(
        self,
        source: Path,
        destination: str,
        config: SyncConfig,
    ) -> SyncResult:
        """Sync files from source to destination"""
        pass

# services/sync/rsync.py
class RsyncSyncManager(SyncManager):
    """Rsync implementation"""

    def __init__(self, ssh_manager: SSHManager):
        self.ssh = ssh_manager

    async def sync(
        self,
        source: Path,
        destination: str,
        config: SyncConfig,
    ) -> SyncResult:
        # Build rsync command
        exclude_args = [f"--exclude={p}" for p in config.exclude]
        include_args = [f"--include={p}" for p in config.include_overrides]

        cmd = [
            "rsync",
            "-avz",
            "--progress",
            *exclude_args,
            *include_args,
            "-e", f"ssh -i {self.ssh.identity_file} -p {self.ssh.port}",
            str(source) + "/",
            f"{self.ssh.username}@{self.ssh.host}:{destination}/",
        ]

        # Execute
        result = await run_command(cmd)

        return SyncResult(
            success=result.returncode == 0,
            files_transferred=self._parse_rsync_output(result.stdout),
        )
```

**Usage**:
```python
# CLI is now much simpler
@click.command()
async def connect(host: str, config_path: Path):
    # Load config
    config = ConfigLoader().load(config_path)

    # Create services
    ssh_manager = SSHManager(host, config.remote)
    container_manager = DockerContainerManager(ssh_manager)
    sync_manager = RsyncSyncManager(ssh_manager)

    # Orchestrate
    orchestrator = ConnectionOrchestrator(
        ssh_manager,
        container_manager,
        sync_manager,
    )

    # Execute
    connection = await orchestrator.connect(config)

    console.print(f"✓ Connected to {connection.container.name}")
```

**Testing**:
```python
# Now easy to test in isolation
async def test_docker_container_manager():
    # Mock SSH manager
    ssh_mock = Mock(spec=SSHManager)

    # Create manager
    manager = DockerContainerManager(ssh_mock)

    # Test
    config = EnvironmentConfig(base_image="python:3.12")
    container = await manager.start_container(config, "test-container")

    assert container.name == "test-container"

# Test orchestrator with mocked services
async def test_connection_orchestrator():
    ssh_mock = Mock(spec=SSHManager)
    container_mock = Mock(spec=ContainerManager)
    sync_mock = Mock(spec=SyncManager)

    orchestrator = ConnectionOrchestrator(ssh_mock, container_mock, sync_mock)

    config = ConnectionConfig(...)
    await orchestrator.connect(config)

    # Verify calls
    ssh_mock.setup.assert_called_once()
    sync_mock.sync.assert_called_once()
    container_mock.start_container.assert_called_once()
```

### 3. Plugin System

**Goal**: Make features extensible without modifying core.

```python
# plugins/base.py
class Plugin(ABC):
    """Base class for plugins"""

    name: str
    version: str

    def on_config_loaded(self, config: MLToolboxConfig):
        """Hook: After config is loaded"""
        pass

    def on_container_start(self, container: Container, config: MLToolboxConfig):
        """Hook: After container is started"""
        pass

    def on_container_stop(self, container: Container):
        """Hook: Before container is stopped"""
        pass

    def on_sync_complete(self, sync_result: SyncResult):
        """Hook: After sync completes"""
        pass

    def on_provision_complete(self, instance: ProvisionedInstance):
        """Hook: After instance is provisioned"""
        pass

# plugins/builtin/ray.py
class RayPlugin(Plugin):
    name = "ray"
    version = "1.0.0"

    def on_container_start(self, container: Container, config: MLToolboxConfig):
        if not config.ray or not config.ray.enabled:
            return

        logger.info("Starting Ray head node...")

        # Execute in container
        container_manager.exec_in_container(
            container.id,
            f"ray start --head --port={config.ray.port} --dashboard-port={config.ray.dashboard_port}"
        )

        logger.info(f"✓ Ray dashboard: http://localhost:{config.ray.dashboard_port}")

# plugins/builtin/wandb.py
class WandBPlugin(Plugin):
    name = "wandb"
    version = "1.0.0"

    def on_container_start(self, container: Container, config: MLToolboxConfig):
        if "WANDB_API_KEY" not in config.environment.env:
            return

        # Verify W&B is configured
        exit_code, output = container_manager.exec_in_container(
            container.id,
            "wandb login --relogin"
        )

        if exit_code == 0:
            logger.info("✓ W&B authenticated")

    def on_sync_complete(self, sync_result: SyncResult):
        # Optionally sync wandb runs
        if hasattr(sync_result, "wandb_runs"):
            logger.info(f"Synced {len(sync_result.wandb_runs)} W&B runs")

# plugins/manager.py
class PluginManager:
    def __init__(self):
        self.plugins: Dict[str, Plugin] = {}

    def register(self, plugin: Plugin):
        self.plugins[plugin.name] = plugin

    def load_builtin_plugins(self):
        """Load built-in plugins"""
        self.register(RayPlugin())
        self.register(WandBPlugin())

    def load_external_plugins(self, plugin_paths: List[Path]):
        """Load plugins from external files"""
        for path in plugin_paths:
            module = import_module(path)
            for item in dir(module):
                obj = getattr(module, item)
                if isinstance(obj, type) and issubclass(obj, Plugin):
                    self.register(obj())

    def run_hook(self, hook_name: str, *args, **kwargs):
        """Run hook on all plugins"""
        for plugin in self.plugins.values():
            if hasattr(plugin, hook_name):
                try:
                    getattr(plugin, hook_name)(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Plugin {plugin.name} failed on {hook_name}: {e}")
```

**User-defined plugin**:
```python
# ~/.config/mltoolbox/plugins/slack_notifications.py
from mltoolbox.plugins import Plugin
import requests

class SlackNotificationPlugin(Plugin):
    name = "slack-notifications"
    version = "1.0.0"

    def __init__(self):
        self.webhook_url = os.getenv("SLACK_WEBHOOK_URL")

    def on_provision_complete(self, instance: ProvisionedInstance):
        if not self.webhook_url:
            return

        requests.post(self.webhook_url, json={
            "text": f"✓ Instance provisioned: {instance.instance_id} ({instance.ip_address})"
        })

    def on_container_start(self, container: Container, config: MLToolboxConfig):
        if not self.webhook_url:
            return

        requests.post(self.webhook_url, json={
            "text": f"✓ Container started: {container.name}"
        })
```

**Load plugins**:
```yaml
# mltoolbox.yaml
plugins:
  - ray               # Built-in
  - wandb             # Built-in
  - slack-notifications  # User-defined (from ~/.config/mltoolbox/plugins/)
```

### 4. Dependency Injection

**Goal**: Decouple components, make testing easier.

```python
# Instead of global singletons:
# ❌ BAD
from mltoolbox.utils.db import DB

def some_function():
    with DB() as db:
        remote = db.get_remote_by_alias("myserver")

# ✅ GOOD: Inject dependencies
class RemoteService:
    def __init__(self, db_session: Session):
        self.db = db_session

    def get_remote(self, alias: str) -> Remote:
        return self.db.query(Remote).filter_by(alias=alias).first()

# In CLI, create dependency tree
def create_app() -> App:
    # Database
    db_engine = create_engine("sqlite:///.config/mltoolbox/mltoolbox.db")
    session_factory = sessionmaker(bind=db_engine)

    # Services
    remote_service = RemoteService(session_factory())
    ssh_manager = SSHManager()
    container_manager = DockerContainerManager(ssh_manager)

    # Orchestrators
    connection_orchestrator = ConnectionOrchestrator(
        ssh_manager,
        container_manager,
        # ... inject all dependencies
    )

    # App
    return App(
        connection_orchestrator=connection_orchestrator,
        # ... other orchestrators
    )

# In tests, inject mocks
def test_remote_service():
    mock_session = Mock()
    service = RemoteService(mock_session)
    # Easy to test!
```

---

## Server-Side Agent Design

**Goal**: Lightweight CLI on remote host for easy container access.

```python
# Installed on remote host: /usr/local/bin/mlt

# agent/cli.py - Server-side CLI
import click

@click.group()
def cli():
    """MLToolbox server-side agent"""
    pass

@cli.command()
def shell():
    """Enter container shell"""
    agent = get_agent()  # Load from /etc/mltoolbox/agent.yaml
    container = agent.get_active_container()

    # Detect shell
    shell = agent.detect_shell(container)  # zsh, bash, fish

    # Exec
    os.execvp("docker", ["docker", "exec", "-it", container.name, shell])

@cli.command()
@click.argument("command", nargs=-1)
def run(command):
    """Run command in container"""
    agent = get_agent()
    container = agent.get_active_container()

    cmd = " ".join(command)
    exit_code = os.system(f"docker exec {container.name} {cmd}")
    sys.exit(exit_code)

@cli.command()
@click.option("--follow", "-f", is_flag=True)
def logs(follow):
    """View container logs"""
    agent = get_agent()
    container = agent.get_active_container()

    follow_flag = "-f" if follow else ""
    os.execvp("docker", ["docker", "logs", follow_flag, container.name])

@cli.command()
def status():
    """Show container status"""
    agent = get_agent()
    container = agent.get_active_container()

    # Get metrics
    stats = agent.get_container_stats(container)
    gpu_stats = agent.get_gpu_stats()

    # Display with Rich
    console.print(Panel(f"""
    Container: {container.name} ({container.status})
    GPU:       {gpu_stats.gpu_count}×{gpu_stats.gpu_type} ({gpu_stats.utilization}% utilized)
    Memory:    {stats.memory_used} / {stats.memory_total}
    Uptime:    {stats.uptime}
    """))

@cli.command()
def daemon():
    """Start agent daemon (WebSocket server for relay)"""
    agent = get_agent()
    asyncio.run(agent.start_daemon())

# agent/core.py
class Agent:
    """Server-side agent"""

    def __init__(self, config_path: Path = Path("/etc/mltoolbox/agent.yaml")):
        self.config = self.load_config(config_path)
        self.docker = docker.from_env()
        self.ws_server = None

    def get_active_container(self) -> Container:
        """Get the active project container"""
        if self.config.container_name:
            try:
                return self.docker.containers.get(self.config.container_name)
            except docker.errors.NotFound:
                raise NoActiveContainerError(f"Container {self.config.container_name} not found")

        # Auto-detect: find container with mltoolbox label
        containers = self.docker.containers.list()
        for c in containers:
            if "mltoolbox.project" in c.labels:
                return c

        raise NoActiveContainerError("No active mltoolbox container found")

    async def start_daemon(self):
        """Start WebSocket server for relay communication"""
        self.ws_server = WebSocketServer(port=self.config.relay.port)

        @self.ws_server.on("sync")
        async def handle_sync(data):
            # Handle sync request from relay
            source = data["source"]
            dest = data["dest"]
            # Run rsync...
            return {"status": "complete"}

        @self.ws_server.on("exec")
        async def handle_exec(data):
            container = self.get_active_container()
            exit_code, output = container.exec_run(data["command"])
            return {"exit_code": exit_code, "output": output}

        await self.ws_server.start()
```

**Installation**:
```bash
# Auto-installed by mltoolbox
mltoolbox remote connect myserver
# → Detects agent not installed
# → "Install mltoolbox agent on remote? [Y/n]"
# → Downloads and installs /usr/local/bin/mlt

# Or manual
curl -sSL https://install.mltoolbox.dev | bash
```

**Usage from any editor**:
```bash
# VSCode Remote SSH
# 1. Connect to host via SSH
# 2. Open terminal in VSCode
# 3. Run: mlt shell
# → Now in container!

# Zed Remote SSH
# Same thing

# Plain SSH
ssh myserver
mlt shell
# Easy!
```

---

## Implementation Roadmap

### Phase 0: Planning & Design
- [x] Write spec.md
- [x] Write vision.md
- [ ] Get feedback from users
- [ ] Finalize config schema
- [ ] Design plugin API

### Phase 1: Foundation (v3.0-alpha1)
- [ ] Create new config system
  - [ ] Define Pydantic models
  - [ ] Implement ConfigLoader
  - [ ] Support devcontainer.json
  - [ ] Migration tool (templates → mltoolbox.yaml)
- [ ] Refactor service layer
  - [ ] Extract ContainerManager interface
  - [ ] Extract SyncManager interface
  - [ ] Extract SSHManager
- [ ] Implement dependency injection
  - [ ] Create App factory
  - [ ] Wire dependencies
- [ ] Maintain backward compatibility
  - [ ] Old commands still work
  - [ ] Deprecation warnings

**Success criteria**: Existing workflows work, new config system optional

### Phase 2: Plugin System (v3.0-alpha2)
- [ ] Implement plugin architecture
  - [ ] Plugin base class
  - [ ] PluginManager
  - [ ] Hook system
- [ ] Port built-in features to plugins
  - [ ] Ray plugin
  - [ ] W&B plugin
  - [ ] GPU metrics plugin
- [ ] Plugin loader
  - [ ] Load from ~/.config/mltoolbox/plugins/
  - [ ] Plugin discovery
- [ ] Documentation
  - [ ] Plugin development guide
  - [ ] Example plugins

**Success criteria**: Ray/W&B work as plugins, users can write custom plugins

### Phase 3: Server-Side Agent (v3.0-beta1)
- [ ] Implement agent
  - [ ] Agent CLI (mlt)
  - [ ] Auto-detection logic
  - [ ] WebSocket server (for relay)
- [ ] Installer
  - [ ] One-line install script
  - [ ] Auto-install on connect
- [ ] Container SSH setup
  - [ ] SSH server in containers
  - [ ] Key management
- [ ] Editor integration docs
  - [ ] VSCode guide
  - [ ] Zed guide
  - [ ] JetBrains guide

**Success criteria**: `mlt shell` works, editors can connect via SSH

### Phase 4: Multi-Backend Provisioning (v3.0-beta2)
- [ ] Backend interface
  - [ ] Define ProvisioningBackend
  - [ ] Implement Lambda Labs
  - [ ] Implement Shadeform
- [ ] Orchestrator
  - [ ] ProvisioningOrchestrator
  - [ ] Smart selection (price, availability)
- [ ] CLI
  - [ ] backend add/list
  - [ ] search
  - [ ] provision
- [ ] Integration
  - [ ] Auto-setup after provision
  - [ ] Connect seamlessly

**Success criteria**: Can provision from Lambda/Shadeform, auto-setup works

### Phase 5: Relay Architecture (v3.0-rc1)
- [ ] Implement relay container
  - [ ] FastAPI server
  - [ ] WebSocket manager
  - [ ] State management
- [ ] Protocol
  - [ ] CLI ↔ Relay API
  - [ ] Relay ↔ Agent WebSocket
- [ ] Features
  - [ ] Async operations
  - [ ] Real-time logs/metrics
  - [ ] Web dashboard (basic)
- [ ] CLI integration
  - [ ] Auto-detect relay
  - [ ] Fallback to direct SSH

**Success criteria**: Relay provides noticeable UX improvement

### Phase 6: Polish & Release (v3.0)
- [ ] Documentation
  - [ ] Complete user guide
  - [ ] API reference
  - [ ] Plugin development guide
  - [ ] Migration guide
- [ ] Testing
  - [ ] Unit tests (>80% coverage)
  - [ ] Integration tests
  - [ ] Manual testing
- [ ] Performance
  - [ ] Benchmark vs v2.x
  - [ ] Optimize hot paths
- [ ] Release
  - [ ] Changelog
  - [ ] Release notes
  - [ ] Blog post

---

## Success Metrics

### Code Quality
- **LOC**: Total lines of code should decrease (better abstractions)
- **Test coverage**: >80% for core services
- **Cyclomatic complexity**: Max 10 per function
- **Dependencies**: Minimal coupling between modules

### User Experience
- **Setup time**: <5 minutes for new users
- **Command simplicity**: No command should require >5 flags for common use
- **Error messages**: 100% of errors should suggest recovery action
- **Documentation**: Every feature documented with examples

### Performance
- **Sync time**: <10s for typical project (vs baseline)
- **Connection time**: <5s for connect command (vs baseline)
- **Memory**: Relay container <200MB RAM
- **Startup**: Agent daemon starts in <1s

### Extensibility
- **Plugin API**: Stable, documented, versioned
- **Community plugins**: Goal of 5+ plugins from community
- **Backends**: Goal of 3+ provisioning backends

---

## Open Questions

1. **Config format**: YAML vs TOML vs Python DSL?
   - **Recommendation**: YAML (familiar, good tooling, human-readable)

2. **Plugin distribution**: PyPI vs custom registry?
   - **Recommendation**: PyPI (use entry points for discovery)

3. **Agent installation**: Auto-install vs manual?
   - **Recommendation**: Auto-install with confirmation prompt

4. **State management**: SQLite vs file-based vs remote?
   - **Recommendation**: Start with SQLite, make pluggable for future

5. **Versioning**: How to handle agent/relay version mismatches?
   - **Recommendation**: Semantic versioning, warn on mismatch

6. **Secrets**: OS keychain vs encrypted file vs external service?
   - **Recommendation**: OS keychain (keyring library), fallback to encrypted file

---

## Anti-Patterns to Avoid

1. **Over-abstraction**: Don't create abstractions for things that won't change
   - ✅ DO: Abstract container backends (Docker vs Podman)
   - ❌ DON'T: Abstract string formatting

2. **Premature optimization**: Start simple, optimize when needed
   - ✅ DO: Use SQLite until we hit scaling issues
   - ❌ DON'T: Start with complex distributed state management

3. **Feature creep**: Stay focused on core value prop
   - ✅ DO: Make remote ML dev easy
   - ❌ DON'T: Build a full ML platform (that's Skypilot)

4. **Breaking changes**: Preserve backward compatibility
   - ✅ DO: Deprecate with warnings, provide migration path
   - ❌ DON'T: Break existing workflows without warning

5. **Complexity**: Simple is better than clever
   - ✅ DO: Use vanilla Python where possible
   - ❌ DON'T: Introduce complex metaprogramming

---

## Conclusion

This refactoring transforms mltoolbox from a "collection of scripts" to a "professional toolkit":

**Before** (v2.x):
- Hardcoded templates
- Monolithic CLI commands
- Tight coupling
- Difficult to extend
- Testing is hard

**After** (v3.0):
- Flexible configuration system
- Clean service layer
- Plugin architecture
- Easy to extend
- Highly testable
- Editor-agnostic
- Cloud-agnostic

The key insight: **Provide abstractions and extension points, not more features.**

Let users compose primitives to build their workflows, rather than prescribing one true way.
