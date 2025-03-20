from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, List, Optional


class NotifierResponse(str, Enum):
    ACCEPT = "accept"
    DENY = "deny"
    PENDING = "pending"


@dataclass
class ShutdownRequest:
    instance_id: str
    message_id: str
    platform: str
    start_time: datetime = field(default_factory=datetime.now)
    response: NotifierResponse = NotifierResponse.PENDING
    responder: Optional[str] = None
    original_message: Optional[str] = None
    timeout_minutes: int = 5  # Add timeout

    def is_timed_out(self) -> bool:
        """Check if the request has timed out."""
        return (datetime.now() - self.start_time).total_seconds() > (
            self.timeout_minutes * 60
        )


class BaseNotifier(ABC):
    """Abstract base class for notification systems."""

    def __init__(self):
        self.shutdown_callback = None
        self.shutdown_requests = {}  # Store all shutdown requests
        self.active_instance_warnings = {}  # Track active warnings per instance

    def set_shutdown_callback(
        self, callback: Callable[[str, NotifierResponse, str], Awaitable[None]]
    ):
        """Set callback for shutdown responses"""
        self.shutdown_callback = callback

    @abstractmethod
    async def start(self) -> None:
        """Initialize the notification service."""
        pass

    async def send_shutdown_warning(
        self, instance_id: str, users: List[str], minutes_remaining: int
    ) -> Optional[Any]:
        """Send a shutdown warning with interactive buttons."""
        # Check if there's already an active warning for this instance
        if instance_id in self.active_instance_warnings:
            existing_message_id = self.active_instance_warnings[instance_id]
            if existing_message_id in self.shutdown_requests:
                # Update existing warning instead of creating a new one
                message = (
                    f"⚠️ *Instance Shutdown Warning* ⚠️\n"
                    f"Instance {instance_id} will shut down in {minutes_remaining} minutes due to inactivity.\n"
                    f"Active users: {', '.join(users)}\n"
                    f"Please save your work and log out if you're done."
                )
                await self.update_message(existing_message_id, message)
                return existing_message_id

        # If no active warning exists, create a new one
        message_id = await self._send_new_warning(instance_id, users, minutes_remaining)
        if message_id:
            self.active_instance_warnings[instance_id] = message_id
        return message_id

    @abstractmethod
    async def _send_new_warning(
        self, instance_id: str, users: List[str], minutes_remaining: int
    ) -> Optional[Any]:
        """Internal method to send a new warning message."""
        pass

    @abstractmethod
    async def update_message(
        self, message_id: str, content: str, is_final: bool = False
    ) -> bool:
        """Update an existing message."""
        pass

    async def handle_response(
        self, message_id: str, response: NotifierResponse, user: str
    ) -> None:
        """Handle user response to shutdown warning."""
        if message_id in self.shutdown_requests:
            request = self.shutdown_requests[message_id]
            request.response = response
            request.responder = user

            # Remove from active warnings since it's been responded to
            if request.instance_id in self.active_instance_warnings:
                del self.active_instance_warnings[request.instance_id]

            # Call the shutdown callback if set
            if self.shutdown_callback:
                await self.shutdown_callback(request.instance_id, response, user)

            # Update message with response
            status = "accepted" if response == NotifierResponse.ACCEPT else "denied"
            await self.update_message(
                message_id,
                f"{request.original_message}\n\n" f"**Shutdown {status}** by {user}",
            )

            del self.shutdown_requests[message_id]
