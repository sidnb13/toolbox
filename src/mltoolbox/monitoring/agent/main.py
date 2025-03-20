import asyncio
import json
import os
from contextlib import asynccontextmanager

import redis.asyncio as redis
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from logger import get_logger

from .agent import Agent

logger = get_logger(__name__)
load_dotenv(".env.agent")


# Global instances
redis_client: redis.Redis = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, agent

    # Initialize Redis client with Docker-friendly settings
    redis_params = {
        "host": os.getenv("REDIS_HOST", "redis"),
        "port": int(os.getenv("REDIS_PORT", 6379)),
        "db": int(os.getenv("REDIS_DB", 0)),
        "decode_responses": True,
        "retry_on_timeout": True,
        "socket_connect_timeout": 5,
        "health_check_interval": 30,
    }

    logger.info(f"Attempting Redis connection with params: {redis_params}")

    try:
        redis_client = redis.Redis(**redis_params)
        await redis_client.ping()
        logger.info("Successfully connected to Redis")
    except Exception as e:
        logger.error(f"Redis connection error: {str(e)}")
        logger.error("Connection details:")
        logger.error(f"Host: {redis_params['host']}")
        logger.error(f"Port: {redis_params['port']}")
        raise

    agent = Agent(
        monitor_url=os.getenv("MONITOR_URL"),
        instance_id=os.getenv("INSTANCE_ID"),
        backend_type=os.getenv("BACKEND_TYPE"),
        backend_api_key=os.getenv("BACKEND_API_KEY"),
        monitor_api_key=os.getenv("MONITOR_API_KEY"),
        name=os.getenv("INSTANCE_NAME"),
        redis_client=redis_client,
    )

    asyncio.create_task(agent.start())

    yield

    try:
        await agent.deregister()
        logger.info("Successfully deregistered agent")
    except Exception as e:
        logger.error(f"Failed to deregister agent: {e}")

    for task in asyncio.all_tasks():
        if task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    redis_client.close()


app = FastAPI(title="Instance Monitor API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws/stats/{instance_id}/{stat_type}")
async def websocket_stats(websocket: WebSocket, instance_id: str, stat_type: str):
    """Stream stats from Redis to connected clients."""
    # Validate instance_id matches this agent
    if instance_id != agent.instance_id:
        await websocket.close(code=4000, reason="Invalid instance ID")
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
        # Subscribe to the appropriate Redis channel
        pubsub = redis_client.pubsub()
        channel = f"stats/{instance_id}/{stat_type}"
        await pubsub.subscribe(channel)

        # Listen for messages
        while True:
            try:
                message = await pubsub.get_message(ignore_subscribe_messages=True)
                if message is not None:
                    data = json.loads(message["data"])
                    await websocket.send_json(data)
                await asyncio.sleep(0.1)  # Prevent busy waiting
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                break

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await pubsub.unsubscribe(channel)
        await websocket.close()


if __name__ == "__main__":
    uvicorn.run(
        "agent.main:app",
        host=os.getenv("AGENT_HOST", "0.0.0.0"),
        port=int(os.getenv("AGENT_PORT", "8000")),
        reload=True,
    )
