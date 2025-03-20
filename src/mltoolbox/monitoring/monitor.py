import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set

from pydantic import BaseModel

from gpu_monitor.notifier.base import NotifierResponse
from logger import get_logger

from .backends import Backend, BackendFactory, BackendType
from .notifier import DiscordNotifier, SlackNotifier

logger = get_logger(__name__)


class InstanceConfig:
    """Configuration for a monitored instance."""

    def __init__(self, backend: Backend, instance_id: str, name: str = None):
        self.backend = backend
        self.instance_id = instance_id
        self.name = name or instance_id
        self.last_activity_time = datetime.now()
        self.last_heartbeat = datetime.now()  # Track last stats update


class InstanceStatusType(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"


class InstanceStatus(BaseModel):
    status: InstanceStatusType
    message: Optional[str] = None
    last_heartbeat: Optional[datetime] = None
    last_activity: Optional[datetime] = None


class ClusterMonitor:
    def __init__(
        self,
        idle_shutdown_minutes: int = 30,
        warning_minutes: int = 5,
        check_interval_seconds: int = 60,
        dry_run: bool = False,
        agent_url: str = "http://localhost:8000",
        slack_token: Optional[str] = None,
        slack_app_token: Optional[str] = None,
        slack_channel: Optional[str] = None,
        discord_token: Optional[str] = None,
        discord_channel_id: Optional[int] = None,
        notifier_type: str = "discord",
    ):
        self.idle_shutdown_minutes = idle_shutdown_minutes
        self.warning_minutes = warning_minutes
        self.check_interval = check_interval_seconds
        self.dry_run = dry_run
        self.agent_url = agent_url
        self.logger = logging.getLogger(__name__)
        self.known_agents: Set[str] = set()

        self.notifiers = []
        if notifier_type == "slack":
            assert (
                slack_token and slack_channel
            ), "Slack notifier requires both token and channel"
            notifier = SlackNotifier(slack_token, slack_app_token, slack_channel)
            notifier.set_shutdown_callback(self.handle_shutdown_response)
            self.notifiers.append(notifier)
        if notifier_type == "discord":
            assert (
                discord_token and discord_channel_id
            ), "Discord notifier requires both token and channel ID"
            notifier = DiscordNotifier(discord_token, discord_channel_id)
            notifier.set_shutdown_callback(self.handle_shutdown_response)
            self.notifiers.append(notifier)

        # Start notifiers
        for notifier in self.notifiers:
            asyncio.create_task(notifier.start())

        # Track stats per instance
        self.instances: Dict[str, InstanceConfig] = {}
        self.instance_stats: Dict[str, Dict] = defaultdict(dict)
        self.ws_base_url = agent_url.replace("http://", "ws://").replace(
            "https://", "wss://"
        )

    async def handle_shutdown_response(
        self, instance_id: str, response: NotifierResponse, user: str
    ):
        """Handle response from notification buttons"""
        if instance_id not in self.instances:
            logger.warning(f"Received response for unknown instance: {instance_id}")
            return

        if response == NotifierResponse.ACCEPT:
            # Immediate shutdown
            logger.info(f"Shutdown accepted for {instance_id} by {user}")
            await self.shutdown_instance(instance_id)

        elif response == NotifierResponse.DENY:
            # Cancel shutdown and reset timer
            logger.info(f"Shutdown denied for {instance_id} by {user}")
            if instance_id in self.shutdown_queue:
                del self.shutdown_queue[instance_id]
            # Reset activity timer
            self.instances[instance_id].last_activity_time = datetime.now()

    async def get_instance_status(self, instance_id: str) -> InstanceStatus:
        instance = self.instances.get(instance_id)
        if not instance:
            return InstanceStatus(
                status=InstanceStatus.status.OFFLINE,
                message="Unknown instance",
                last_heartbeat=None,
                last_activity=None,
            )

        now = datetime.now()
        heartbeat_elapsed = (now - instance.last_heartbeat).total_seconds()

        if heartbeat_elapsed > self.check_interval:
            status = InstanceStatusType.OFFLINE
            message = f"No heartbeat received in {heartbeat_elapsed} seconds"
        else:
            status = InstanceStatusType.ONLINE
            message = f"Last update received {heartbeat_elapsed} seconds ago"

        return InstanceStatus(
            status=status,
            message=message,
            last_heartbeat=instance.last_heartbeat,
            last_activity=instance.last_activity_time,
        )

    async def register_agent(
        self,
        instance_id: str,
        backend_type: str,
        backend_api_key: str,
        name: Optional[str] = None,
    ):
        """Register a new agent/instance with the monitor."""
        try:
            # Convert string backend type to enum
            backend_enum = BackendType(backend_type.lower())

            # Create backend instance using factory
            backend = BackendFactory.create_backend(
                backend_type=backend_enum, api_key=backend_api_key
            )

            # Create instance config
            instance_config = InstanceConfig(
                backend=backend, instance_id=instance_id, name=name
            )

            # Add to tracked instances
            self.instances[instance_id] = instance_config
            self.instance_stats[instance_id] = {}

            self.logger.info(f"Successfully registered instance {instance_id} ({name})")
            return True

        except ValueError as e:
            self.logger.error(f"Failed to register instance {instance_id}: {e}")
            raise ValueError(f"Invalid backend type: {backend_type}")
        except Exception as e:
            self.logger.error(f"Failed to register instance {instance_id}: {e}")
            raise

    async def notify_users(
        self, instance_id: str, users: List[str], minutes_remaining: int
    ) -> None:
        """Send shutdown warnings through all configured notifiers."""
        for notifier in self.notifiers:
            await notifier.send_shutdown_warning(instance_id, users, minutes_remaining)

    async def shutdown_instance(self, instance_id: str):
        """Shutdown specific instance using its backend."""
        instance = self.instances[instance_id]

        if self.dry_run:
            self.logger.warning(
                f"DRY RUN: Would shutdown instance {instance.name} ({instance_id})"
            )
            del self.instances[instance_id]
            return

        try:
            self.logger.info(
                f"Initiating shutdown for instance {instance.name} ({instance_id})"
            )
            response = instance.backend.stop_instance(instance_id)
            del self.instances[instance_id]
            self.logger.info(f"Shutdown response: {response}")
        except Exception as e:
            self.logger.error(f"Failed to shutdown instance {instance_id}: {e}")
            del self.instances[instance_id]
            raise

    async def check_active_processes(self, stats: Dict) -> bool:
        """Check if there are any active GPU processes."""
        try:
            gpu_stats = stats.get("gpu_stats", [])
            if not gpu_stats:
                return False

            # Check if any GPU has significant utilization
            for gpu in gpu_stats:
                if (
                    gpu.get("gpu_utilization", 0) > 5
                    or gpu.get("memory_utilization", 0) > 5
                ):
                    self.logger.info(f"Active GPU processes detected: {gpu}")
                    return True

            return False
        except Exception as e:
            self.logger.error(f"Error checking GPU processes: {e}")
            return False

    async def get_ssh_sessions(self, stats: Dict) -> List[str]:
        """Get list of users with active SSH sessions."""
        try:
            ssh_stats = stats.get("ssh_stats", [])
            users = [
                session.get("username")
                for session in ssh_stats
                if session.get("username")
            ]
            return list(set(users))  # Remove duplicates
        except Exception as e:
            self.logger.error(f"Error getting SSH sessions: {e}")
            return []

    async def check_user_activity(self, stats: Dict) -> bool:
        """
        Check if a user has recent activity by monitoring CPU usage.
        Returns True if there's significant activity.
        """
        try:
            cpu_stats = stats.get("cpu_stats", {})
            if not cpu_stats:
                return False

            # Consider system active if CPU utilization is above threshold
            cpu_utilization = cpu_stats.get("cpu_utilization", 0)
            if cpu_utilization > 10:  # 10% CPU usage threshold
                self.logger.info(f"Active CPU usage detected: {cpu_utilization}%")
                return True

            return False
        except Exception as e:
            self.logger.error(f"Error checking user activity: {e}")
            return False

    async def check_ray_activity(self, stats: Dict) -> bool:
        """Check if there's any active Ray cluster activity."""
        try:
            ray_stats = stats.get("ray_stats", {})
            if not ray_stats:
                return False

            # Check for active jobs
            jobs = ray_stats.get("jobs", [])
            active_jobs = [job for job in jobs if job.get("status") == "RUNNING"]
            if active_jobs:
                self.logger.info(f"Active Ray jobs detected: {len(active_jobs)}")
                return True

            # Check for active actors
            actors = ray_stats.get("actors", {}).get("details", [])
            if actors:
                self.logger.info(f"Active Ray actors detected: {len(actors)}")
                return True

            # Check for running tasks
            tasks = ray_stats.get("tasks", {}).get("running", [])
            if tasks:
                self.logger.info(f"Active Ray tasks detected: {len(tasks)}")
                return True

            return False
        except Exception as e:
            self.logger.error(f"Error checking Ray activity: {e}")
            return False

    async def check_instance_activity(self, stats: Dict) -> bool:
        """
        Comprehensive check for instance activity across GPU, CPU, and Ray.
        Returns True if there's significant activity.
        """
        try:
            # Check GPU processes first (highest priority)
            gpu_active = await self.check_active_processes(stats)
            if gpu_active:
                self.logger.info("Active GPU processes detected")
                return True

            # Check Ray cluster activity
            ray_active = await self.check_ray_activity(stats)
            if ray_active:
                self.logger.info("Active Ray cluster detected")
                return True

            # Check CPU activity (might indicate Jupyter notebook usage)
            cpu_active = await self.check_user_activity(stats)
            if cpu_active:
                self.logger.info("Active CPU usage detected")
                return True

            return False
        except Exception as e:
            self.logger.error(f"Error checking instance activity: {e}")
            return False

    async def process_stats(self, instance_id: str, stat_type: str, data: dict):
        """Process incoming stats from an agent."""
        if instance_id not in self.instances:
            self.logger.warning(f"Received stats for unknown instance: {instance_id}")
            return

        self.instance_stats[instance_id][f"{stat_type}_stats"] = data
        self.instances[instance_id].last_heartbeat = datetime.now()

    async def monitor_loop(self):
        """Main monitoring loop for all instances."""
        self.shutdown_queue = {}  # Track instances pending shutdown: {instance_id: (start_time, message_ids)}

        while True:
            try:
                # Process pending shutdowns first
                for instance_id, (start_time, message_ids) in list(
                    self.shutdown_queue.items()
                ):
                    if instance_id not in self.instances:
                        continue

                    elapsed_time = (datetime.now() - start_time).total_seconds() / 60
                    if elapsed_time >= self.warning_minutes:
                        try:
                            logger.info(
                                f"Warning period elapsed for {instance_id}, initiating shutdown"
                            )
                            # Update messages across all notifiers
                            for notifier in self.notifiers:
                                if message_ids.get(notifier.__class__.__name__):
                                    await notifier.update_message(
                                        message_ids[notifier.__class__.__name__],
                                        f"⚠️ **Instance Shutdown** ⚠️\nInitiating shutdown for instance {instance_id}...",
                                    )

                            # Perform shutdown
                            await self.shutdown_instance(instance_id)

                            # Final message update
                            for notifier in self.notifiers:
                                if message_ids.get(notifier.__class__.__name__):
                                    await notifier.update_message(
                                        message_ids[notifier.__class__.__name__],
                                        f"✅ **Shutdown Complete** ✅\nInstance {instance_id} has been shut down.",
                                    )
                        except Exception as e:
                            logger.error(
                                f"Failed to shutdown instance {instance_id}: {e}"
                            )
                            # Update messages with error
                            for notifier in self.notifiers:
                                if message_ids.get(notifier.__class__.__name__):
                                    await notifier.update_message(
                                        message_ids[notifier.__class__.__name__],
                                        f"❌ **Shutdown Failed** ❌\nFailed to shutdown instance {instance_id}: {str(e)}",
                                    )
                        finally:
                            del self.shutdown_queue[instance_id]

                # Check for new instances that need shutdown
                for instance_id, instance in list(self.instances.items()):
                    if instance_id in self.shutdown_queue:
                        continue  # Skip instances already pending shutdown

                    stats = self.instance_stats[instance_id]
                    ssh_users = await self.get_ssh_sessions(stats)

                    # Comprehensive activity check
                    has_activity = await self.check_instance_activity(stats)

                    if has_activity:
                        instance.last_activity_time = datetime.now()
                        continue

                    # If no activity detected, check idle time
                    idle_time = datetime.now() - instance.last_activity_time
                    idle_minutes = idle_time.total_seconds() / 60

                    if idle_minutes >= self.idle_shutdown_minutes:
                        # Initiate shutdown sequence
                        message_ids = {}

                        # Send warnings through all configured notifiers
                        for notifier in self.notifiers:
                            message_id = await notifier.send_shutdown_warning(
                                instance_id, ssh_users, self.warning_minutes
                            )
                            if message_id:
                                message_ids[notifier.__class__.__name__] = message_id

                        if (
                            message_ids
                        ):  # Only queue if at least one notification was sent
                            self.shutdown_queue[instance_id] = (
                                datetime.now(),
                                message_ids,
                            )
                            logger.info(
                                f"Instance {instance_id} queued for shutdown in {self.warning_minutes} minutes"
                            )

            except Exception as e:
                logger.error(f"Error in monitor loop: {e}", exc_info=True)

            await asyncio.sleep(self.check_interval)
