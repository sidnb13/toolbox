import asyncio
import logging
from typing import List, Optional

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError

from .base import BaseNotifier, NotifierResponse, ShutdownRequest

logger = logging.getLogger(__name__)


class SlackNotifier(BaseNotifier):
    def __init__(self, bot_token: str, app_token: str, channel: str):
        super().__init__()  # Important: call parent's __init__

        self.app = App(token=bot_token)
        self.socket_mode_handler = SocketModeHandler(self.app, app_token)
        self.channel_name = channel
        self.channel = None
        self.loop = None

        # Register synchronous Bolt event handlers that create async tasks
        @self.app.action("accept_shutdown")
        def handle_accept(ack, body):
            # Acknowledge immediately
            ack()
            # Create async task for handling the response
            message_id = body["container"]["message_ts"]
            user = body["user"]["username"]

            if self.loop and self.loop.is_running():
                self.loop.create_task(
                    self.handle_response(message_id, NotifierResponse.ACCEPT, user)
                )

        @self.app.action("deny_shutdown")
        def handle_deny(ack, body):
            # Acknowledge immediately
            ack()
            # Create async task for handling the response
            message_id = body["container"]["message_ts"]
            user = body["user"]["username"]

            if self.loop and self.loop.is_running():
                self.loop.create_task(
                    self.handle_response(message_id, NotifierResponse.DENY, user)
                )

    async def start(self) -> None:
        """Start the Slack notifier"""
        self.loop = asyncio.get_running_loop()

        # Look up the channel ID before starting
        try:
            response = self.app.client.conversations_list()
            for channel in response["channels"]:
                if channel["name"] == self.channel_name:
                    self.channel = channel["id"]
                    break
            if not self.channel:
                raise ValueError(f"Could not find channel: {self.channel_name}")
        except SlackApiError as e:
            logger.error(f"Failed to lookup channel: {e}")
            raise

        self.socket_mode_handler.connect()
        return True

    async def _send_new_warning(
        self, instance_id: str, users: List[str], minutes_remaining: int
    ) -> Optional[str]:
        """Implementation of abstract method to send a new warning message"""
        message_text = (
            f"⚠️ *Instance Shutdown Warning* ⚠️\n"
            f"Instance {instance_id} will shut down in {minutes_remaining} minutes due to inactivity.\n"
            f"Active users: {', '.join(users)}\n"
            f"Please save your work and log out if you're done."
        )

        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": message_text},
            },
            {
                "type": "actions",
                "block_id": f"shutdown_{instance_id}",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Accept Shutdown"},
                        "style": "primary",
                        "action_id": "accept_shutdown",
                        "value": instance_id,
                        "confirm": {
                            "title": {"type": "plain_text", "text": "Confirm Shutdown"},
                            "text": {
                                "type": "plain_text",
                                "text": "Are you sure you want to accept the shutdown?",
                            },
                            "confirm": {"type": "plain_text", "text": "Yes"},
                            "deny": {"type": "plain_text", "text": "No"},
                        },
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Deny Shutdown"},
                        "style": "danger",
                        "action_id": "deny_shutdown",
                        "value": instance_id,
                        "confirm": {
                            "title": {"type": "plain_text", "text": "Deny Shutdown"},
                            "text": {
                                "type": "plain_text",
                                "text": "Are you sure you want to deny the shutdown?",
                            },
                            "confirm": {"type": "plain_text", "text": "Yes"},
                            "deny": {"type": "plain_text", "text": "No"},
                        },
                    },
                ],
            },
        ]

        try:
            response = self.app.client.chat_postMessage(
                channel=self.channel, blocks=blocks, text="Instance shutdown warning"
            )
            message_id = response["ts"]

            # Store the shutdown request using parent class's dict
            self.shutdown_requests[message_id] = ShutdownRequest(
                instance_id=instance_id,
                message_id=message_id,
                platform="slack",
                original_message=message_text,
            )
            return message_id
        except SlackApiError as e:
            logger.error(f"Failed to send Slack warning: {e}")
            return None

    async def update_message(
        self, message_id: str, content: str, is_final: bool = False
    ) -> bool:
        """Implementation of abstract method to update a message"""
        try:
            blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": content}}]

            if not is_final:
                blocks.append(
                    {
                        "type": "actions",
                        "block_id": f"shutdown_{self.shutdown_requests[message_id].instance_id}",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Accept Shutdown",
                                },
                                "style": "primary",
                                "action_id": "accept_shutdown",
                                "value": self.shutdown_requests[message_id].instance_id,
                            },
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Deny Shutdown"},
                                "style": "danger",
                                "action_id": "deny_shutdown",
                                "value": self.shutdown_requests[message_id].instance_id,
                            },
                        ],
                    }
                )

            self.app.client.chat_update(
                channel=self.channel, ts=message_id, text=content, blocks=blocks
            )
            return True
        except SlackApiError as e:
            logger.error(f"Failed to update Slack message: {e}")
            return False
