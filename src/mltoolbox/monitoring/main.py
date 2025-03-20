import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Security, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from logger import get_logger

from .auth import AuthManager
from .models import ApiKey, Base
from .monitor import ClusterMonitor

logger = get_logger(__name__)
load_dotenv(".env.monitor")


# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/gpumonitor")
try:
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Test the connection and create tables
    with engine.begin() as conn:
        Base.metadata.create_all(bind=engine)
        logger.info("Successfully connected to database and created tables")
except OperationalError as e:
    logger.error(f"Failed to connect to database: {e}")
    logger.error("Please ensure PostgreSQL is running and the DATABASE_URL is correct")
    raise


def initialize_db():
    """Initialize database with default API key if empty."""
    db = SessionLocal()
    try:
        # Check if any API keys exist
        existing_keys = db.query(ApiKey).count()
        if existing_keys == 0:
            # Create auth manager and generate new key
            auth_manager = AuthManager(db)
            api_key = auth_manager.create_api_key()

            logger.info("=" * 60)
            logger.info("Initialized database with default API key")
            logger.info(f"API Key: {api_key}")
            logger.info(
                "Please use this key in your agent's MONITOR_API_KEY environment variable"
            )
            logger.info("=" * 60)
        # Print out all API keys in database
        api_keys = db.query(ApiKey).all()
        if api_keys:
            logger.info("Current API keys in database:")
            for key in api_keys:
                logger.info(f"Key: {key.key}, Created: {key.created_at}")
        else:
            logger.info("No API keys found in database")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    finally:
        db.close()


try:
    initialize_db()
except Exception as e:
    logger.error(f"Database initialization failed: {e}")
    raise


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@asynccontextmanager
async def start_monitor(app: FastAPI):
    global monitor

    monitor = ClusterMonitor(
        idle_shutdown_minutes=float(os.getenv("IDLE_SHUTDOWN_MINUTES", 30)),
        warning_minutes=float(os.getenv("WARNING_MINUTES", 5)),
        check_interval_seconds=float(os.getenv("CHECK_INTERVAL_SECONDS", 60)),
        dry_run=os.getenv("DRY_RUN", "true").lower() == "true",
        agent_url=os.getenv("AGENT_URL", "http://localhost:8000"),
        slack_token=os.getenv("SLACK_BOT_TOKEN"),
        slack_app_token=os.getenv("SLACK_APP_TOKEN"),
        slack_channel=os.getenv("SLACK_CHANNEL"),
        discord_token=os.getenv("DISCORD_BOT_TOKEN"),
        discord_channel_id=int(os.getenv("DISCORD_CHANNEL_ID")),
        notifier_type=os.getenv("NOTIFIER_TYPE", "discord").lower(),
    )
    asyncio.create_task(monitor.monitor_loop())

    yield

    for task in asyncio.all_tasks():
        if task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="GPU Monitor", lifespan=start_monitor)
auth_manager = AuthManager(db_session=next(get_db()))

# Security
API_KEY_HEADER = APIKeyHeader(name="X-API-Key")
VALID_API_KEYS = {os.getenv("MONITOR_API_KEY")}  # Load from environment
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")  # Add this line

# Global monitor instance
monitor: Optional[ClusterMonitor] = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://gpuboard.sidbaskaran.com",
        "https://api.gpuboard.sidbaskaran.com",
        "http://localhost:3000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


# Add these new models at the top with the other imports
class MonitorSettings(BaseModel):
    idle_shutdown_minutes: Optional[int] = None
    warning_minutes: Optional[int] = None
    check_interval_seconds: Optional[int] = None
    dry_run: Optional[bool] = None


class SlackSettings(BaseModel):
    slack_token: str
    slack_channel: str


@app.get("/")
async def root():
    """Basic endpoint for health checks and API info."""
    return {
        "status": "running",
        "websocket_endpoints": ["/ws/stats/gpu", "/ws/stats/cpu", "/ws/stats/ssh"],
    }


@app.get("/settings")
async def get_settings(api_key: str = Security(API_KEY_HEADER)):
    """Get current monitor settings."""
    if api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return {
        "idle_shutdown_minutes": monitor.idle_shutdown_minutes,
        "warning_minutes": monitor.warning_minutes,
        "check_interval_seconds": monitor.check_interval,
        "dry_run": monitor.dry_run,
    }


@app.patch("/settings")
async def update_settings(
    settings: MonitorSettings, api_key: str = Security(API_KEY_HEADER)
):
    """Update monitor settings."""
    if api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key")

    if settings.idle_shutdown_minutes is not None:
        monitor.idle_shutdown_minutes = settings.idle_shutdown_minutes
    if settings.warning_minutes is not None:
        monitor.warning_minutes = settings.warning_minutes
    if settings.check_interval_seconds is not None:
        monitor.check_interval = settings.check_interval_seconds
    if settings.dry_run is not None:
        monitor.dry_run = settings.dry_run

    return await get_settings(api_key)


@app.get("/metrics")
async def get_metrics(api_key: str = Security(API_KEY_HEADER)):
    """Get current monitoring metrics."""
    if api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return {
        "total_instances": len(monitor.instances),
        "active_instances": sum(
            1
            for i in monitor.instances.values()
            if (datetime.now() - i.last_activity_time).total_seconds()
            < monitor.idle_shutdown_minutes * 60
        ),
        "instances_with_gpu_activity": sum(
            1
            for instance_id in monitor.instances
            if await monitor.check_active_processes(monitor.instance_stats[instance_id])
        ),
        "instances_with_users": sum(
            1
            for instance_id in monitor.instances
            if await monitor.get_ssh_sessions(monitor.instance_stats[instance_id])
        ),
    }


@app.get("/instances")
async def list_instances(api_key: str = Security(API_KEY_HEADER)):
    """List all registered instances and their current status."""
    if api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key")

    instances = {}
    for instance_id in monitor.instances:
        status = await monitor.get_instance_status(instance_id)
        instance = monitor.instances[instance_id]
        instances[instance_id] = {
            "name": instance.name,
            "status": status.status,
            "last_heartbeat": status.last_heartbeat,
            "last_activity": status.last_activity,
            "current_stats": monitor.instance_stats.get(instance_id, {}),
        }

    return instances


@app.get("/instances/{instance_id}")
async def get_instance(instance_id: str, api_key: str = Security(API_KEY_HEADER)):
    """Get detailed information about a specific instance."""
    if api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key")

    if instance_id not in monitor.instances:
        raise HTTPException(status_code=404, detail="Instance not found")

    status = await monitor.get_instance_status(instance_id)
    instance = monitor.instances[instance_id]

    return {
        "name": instance.name,
        "status": status.status,
        "last_heartbeat": status.last_heartbeat,
        "last_activity": status.last_activity,
        "current_stats": monitor.instance_stats.get(instance_id, {}),
    }


@app.post("/instances/{instance_id}/shutdown")
async def shutdown_instance(instance_id: str, api_key: str = Security(API_KEY_HEADER)):
    """Manually trigger instance shutdown."""
    if api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key")

    if instance_id not in monitor.instances:
        raise HTTPException(status_code=404, detail="Instance not found")

    try:
        await monitor.shutdown_instance(instance_id)
        return {"status": "shutdown_initiated", "instance_id": instance_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/instances/{instance_id}")
async def unregister_instance(
    instance_id: str, api_key: str = Security(API_KEY_HEADER)
):
    """Unregister an instance from monitoring."""
    if not auth_manager.verify_agent_key(api_key):
        raise HTTPException(status_code=403, detail="Invalid API key")

    if instance_id not in monitor.instances:
        raise HTTPException(status_code=404, detail="Instance not found")

    try:
        del monitor.instances[instance_id]
        del monitor.instance_stats[instance_id]
        return {"status": "unregistered", "instance_id": instance_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/api-key")
async def create_api_key(
    instance_id: str, admin_key: str = Header(..., alias="X-Admin-Key")
):
    """Generate a backend API key for a new instance"""
    if admin_key != ADMIN_API_KEY:  # Load from config
        raise HTTPException(status_code=403, detail="Invalid admin key")

    api_key = auth_manager.create_api_key(instance_id)
    return {"api_key": api_key}


@app.post("/register/{instance_id}")
async def register_agent(
    instance_id: str, agent_info: dict, api_key: str = Security(API_KEY_HEADER)
):
    """Register a new agent instance"""
    if not auth_manager.verify_agent_key(api_key):
        raise HTTPException(status_code=403, detail="Invalid API key")

    try:
        await monitor.register_agent(
            instance_id=instance_id,
            backend_type=agent_info["backend_type"],
            backend_api_key=agent_info["backend_api_key"],
            name=agent_info.get("name"),
        )
        return {
            "status": "registered",
            "instance_id": instance_id,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.websocket("/ws/stats/{instance_id}/{stat_type}")
async def websocket_stats(websocket: WebSocket, instance_id: str, stat_type: str):
    """Handle incoming stats from agents."""
    # Validate instance_id
    if instance_id not in monitor.instances:
        await websocket.close(code=4000, reason="Unknown instance ID")
        return

    # Validate stat type
    valid_types = {"gpu", "cpu", "ssh"}
    if stat_type not in valid_types:
        await websocket.close(
            code=4000, reason=f"Invalid stat type. Must be one of: {valid_types}"
        )
        return

    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_json()
            await monitor.process_stats(instance_id, stat_type, data)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await websocket.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("MONITOR_HOST", "localhost"),
        port=int(os.getenv("MONITOR_PORT", 8001)),
    )
