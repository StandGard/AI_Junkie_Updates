"""Telegram bot for delivering formatted updates to channels."""

from __future__ import annotations

import asyncio
import time
from typing import Dict

from telegram import Bot
from telegram.constants import ParseMode
from tenacity import retry, stop_after_attempt, wait_exponential

from ai_junkie_updates.constants import DeliveryChannel
from ai_junkie_updates.core.models import UpdateItem
from ai_junkie_updates.delivery.formatter import Formatter
from ai_junkie_updates.settings import settings
from ai_junkie_updates.utils.logger import get_logger

log = get_logger(__name__)

# Rate limit: max 20 messages per minute
RATE_LIMIT_WINDOW = 60.0
RATE_LIMIT_MAX = 20

# Telegram hard limit per message is 4096 chars; leave headroom.
MAX_MESSAGE_CHARS = 3800


def _split_message(text: str, limit: int = MAX_MESSAGE_CHARS) -> list[str]:
    """Split long text into <=limit chunks, preferring paragraph/line breaks."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        cut = window.rfind("\n\n")
        if cut < limit // 2:
            cut = window.rfind("\n")
        if cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


class TelegramBot:
    """Sends formatted messages to Telegram channels with rate limiting."""

    def __init__(self) -> None:
        self._bot: Bot | None = None
        self._formatter = Formatter()
        self._channel_map: Dict[DeliveryChannel, str] = {}
        self._send_times: list[float] = []

    def _ensure_bot(self) -> Bot:
        """Lazily create the Bot instance on first use (avoids token validation at import)."""
        if self._bot is None:
            self._bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
            self._channel_map = {
                DeliveryChannel.CRITICAL_ALERTS: settings.TELEGRAM_CHANNEL_CRITICAL,
                DeliveryChannel.HIGH_PRIORITY: settings.TELEGRAM_CHANNEL_HIGH,
                DeliveryChannel.GENERAL: settings.TELEGRAM_CHANNEL_GENERAL,
                DeliveryChannel.WATCHLIST: settings.TELEGRAM_CHANNEL_WATCHLIST,
            }
        return self._bot

    async def _rate_limit(self) -> None:
        """Block until we are within the rate limit window."""
        now = time.monotonic()
        # Remove timestamps older than the window
        self._send_times = [t for t in self._send_times if now - t < RATE_LIMIT_WINDOW]
        if len(self._send_times) >= RATE_LIMIT_MAX:
            wait_until = self._send_times[0] + RATE_LIMIT_WINDOW
            delay = wait_until - now
            if delay > 0:
                log.info("rate_limit_wait", delay_seconds=round(delay, 1))
                await asyncio.sleep(delay)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        reraise=True,
    )
    async def _send_message(self, channel_id: str, text: str) -> None:
        """Send a single HTML message to a Telegram channel."""
        bot = self._ensure_bot()
        await bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

    async def send_text(self, channel: DeliveryChannel, text: str) -> None:
        """Send a pre-formatted plain/HTML text block to a channel.

        Used by the intelligence layer to deliver synthesized briefs and digests
        (which are already prose, not UpdateItems). Long messages are split to
        respect Telegram's 4096-character limit. Reuses the same rate limiting.
        """
        channel_id = self._channel_map.get(channel) if self._channel_map else None
        # Ensure the bot/channel map is initialised even if send() ran first.
        if not channel_id:
            self._ensure_bot()
            channel_id = self._channel_map.get(channel)
        if not channel_id:
            log.warning("no_channel_configured", channel=channel.value)
            return

        for chunk in _split_message(text):
            await self._rate_limit()
            await self._send_message(channel_id, chunk)
            self._send_times.append(time.monotonic())
        log.info("telegram_text_sent", channel=channel.value, length=len(text))

    async def send(self, item: UpdateItem) -> None:
        """Format and send an update to the appropriate Telegram channel."""
        channel = item.delivery_channel
        if channel is None or channel == DeliveryChannel.DROPPED:
            return

        channel_id = self._channel_map.get(channel)
        if not channel_id:
            log.warning("no_channel_configured", channel=channel.value)
            return

        message = self._formatter.format_message(item)
        await self._rate_limit()
        await self._send_message(channel_id, message)
        self._send_times.append(time.monotonic())

        log.info(
            "telegram_sent",
            item_id=item.id,
            channel=channel.value,
            headline=item.headline[:80],
        )


telegram_bot = TelegramBot()
