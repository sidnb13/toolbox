import asyncio
import logging
from typing import Callable, List, Optional

import discord
from discord.ext import commands
from discord.ui import Button, View

from .base import BaseNotifier, NotifierResponse, ShutdownRequest

logger = logging.getLogger(__name__)


class ShutdownView(View):
    def __init__(self, callback: Callable):
        super().__init__(timeout=None)
        self.callback = callback
        self.is_disabled = False

        # Accept button
        self.accept_button = Button(
            style=discord.ButtonStyle.green,
            label="Accept Shutdown",
            custom_id="accept_shutdown",
        )
        self.accept_button.callback = self.accept_clicked
        self.add_item(self.accept_button)

        # Deny button
        self.deny_button = Button(
            style=discord.ButtonStyle.red,
            label="Deny Shutdown",
            custom_id="deny_shutdown",
        )
        self.deny_button.callback = self.deny_clicked
        self.add_item(self.deny_button)

    def disable_buttons(self):
        """Disable all buttons in the view"""
        self.accept_button.disabled = True
        self.deny_button.disabled = True
        self.is_disabled = True

    async def accept_clicked(self, interaction: discord.Interaction):
        self.disable_buttons()
        await self.callback(interaction, NotifierResponse.ACCEPT)
        await interaction.response.edit_message(view=self)

    async def deny_clicked(self, interaction: discord.Interaction):
        self.disable_buttons()
        await self.callback(interaction, NotifierResponse.DENY)
        await interaction.response.edit_message(view=self)


class DiscordNotifier(BaseNotifier):
    def __init__(self, token: str, channel_id: int):
        super().__init__()  # Important: Call parent's init
        self.token = token
        self.channel_id = channel_id
        intents = discord.Intents.default()
        intents.message_content = False
        self.bot = commands.Bot(command_prefix="!", intents=intents)
        self.channel = None
        self._ready = asyncio.Event()

        @self.bot.event
        async def on_ready():
            self.channel = self.bot.get_channel(self.channel_id)
            if not self.channel:
                logger.error(
                    f"Could not find Discord channel with ID {self.channel_id}"
                )
            self._ready.set()
            logger.info(f"Discord bot connected as {self.bot.user}")

    async def _ensure_ready(self) -> None:
        """Wait for the bot to be ready."""
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=30)
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for Discord bot to become ready")
            raise

    async def start(self) -> None:
        """Initialize the Discord bot."""
        try:
            # Start the bot in the background
            asyncio.create_task(self.bot.start(self.token))
            await self._ensure_ready()
            logger.info("Discord bot started successfully")
        except Exception as e:
            logger.error(f"Failed to start Discord bot: {e}")
            raise

    async def _send_new_warning(
        self, instance_id: str, users: List[str], minutes_remaining: int
    ) -> Optional[str]:
        """Send a new shutdown warning with interactive buttons."""
        await self._ensure_ready()

        message_text = (
            "⚠️ **Instance Shutdown Warning** ⚠️\n"
            f"🖥️ Instance {instance_id} will shut down in ⏰ {minutes_remaining} minutes due to inactivity.\n"
            f"👥 Active users: {', '.join(users) if users else '∅'}\n"
            "💾 Please save your work and 🚪 log out if you're done."
        )

        try:
            view = ShutdownView(self._handle_interaction)
            message = await self.channel.send(content=message_text, view=view)
            message_id = str(message.id)

            # Track the shutdown request
            self.shutdown_requests[message_id] = ShutdownRequest(
                instance_id=instance_id,
                message_id=message_id,
                platform="discord",
                original_message=message_text,
            )

            return message_id
        except Exception as e:
            logger.error(f"Failed to send Discord shutdown warning: {e}")
            return None

    async def update_message(
        self, message_id: str, content: str, is_final: bool = False
    ) -> bool:
        """Update an existing message."""
        await self._ensure_ready()
        try:
            message = await self.channel.fetch_message(int(message_id))

            if is_final:
                view = None
            else:
                view = ShutdownView(self._handle_interaction)

            await message.edit(content=content, view=view)
            return True
        except Exception as e:
            logger.error(f"Failed to update Discord message: {e}")
            return False

    async def _handle_interaction(
        self, interaction: discord.Interaction, response: NotifierResponse
    ):
        """Internal method to handle button interactions."""
        message_id = str(interaction.message.id)
        user = f"{interaction.user.name}"  # Updated to use just the username
        await self.handle_response(message_id, response, user)
