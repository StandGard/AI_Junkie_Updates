"""Router — delivers updates to the correct Telegram channel with batching."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List

from ai_junkie_updates.constants import DeliveryChannel, PipelineStatus
from ai_junkie_updates.core.database import db
from ai_junkie_updates.core.models import UpdateItem
from ai_junkie_updates.delivery.telegram_bot import telegram_bot
from ai_junkie_updates.utils.logger import get_logger

log = get_logger(__name__)

GENERAL_FLUSH_INTERVAL = 300  # 5 minutes
GENERAL_FLUSH_SIZE = 10
WATCHLIST_FLUSH_INTERVAL = 900  # 15 minutes


class Router:
    """Route analysed items to the correct delivery channel with batching."""

    def __init__(self) -> None:
        self._general_queue: List[UpdateItem] = []
        self._watchlist_queue: List[UpdateItem] = []
        self._general_task: asyncio.Task | None = None
        self._watchlist_task: asyncio.Task | None = None

    def start_flush_loops(self) -> None:
        """Start background tasks that periodically flush batched queues."""
        self._general_task = asyncio.create_task(self._flush_general_loop())
        self._watchlist_task = asyncio.create_task(self._flush_watchlist_loop())

    async def stop(self) -> None:
        """Flush remaining items and cancel background tasks."""
        await self._flush_general()
        await self._flush_watchlist()
        for task in (self._general_task, self._watchlist_task):
            if task and not task.done():
                task.cancel()

    async def route(self, item: UpdateItem) -> None:
        """Route an item based on its delivery_channel."""
        channel = item.delivery_channel

        if channel == DeliveryChannel.CRITICAL_ALERTS:
            await self._deliver(item)
        elif channel == DeliveryChannel.HIGH_PRIORITY:
            await self._deliver(item)
        elif channel == DeliveryChannel.GENERAL:
            self._general_queue.append(item)
            if len(self._general_queue) >= GENERAL_FLUSH_SIZE:
                await self._flush_general()
        elif channel == DeliveryChannel.WATCHLIST:
            self._watchlist_queue.append(item)
        elif channel == DeliveryChannel.DROPPED:
            item.pipeline_status = PipelineStatus.DROPPED
            await db.save_item(item)
            log.info("item_dropped", item_id=item.id, score=item.score)

    async def _deliver(self, item: UpdateItem) -> None:
        """Send a single item and update its status in the database."""
        try:
            await telegram_bot.send(item)
            item.pipeline_status = PipelineStatus.DELIVERED
            item.delivered_at = datetime.now(timezone.utc)
            await db.save_item(item)
            log.info(
                "item_delivered",
                item_id=item.id,
                channel=item.delivery_channel.value if item.delivery_channel else "unknown",
                score=item.score,
            )
        except Exception as exc:
            log.error("delivery_failed", item_id=item.id, error=str(exc))
            await db.save_item(item)

    async def _flush_general(self) -> None:
        """Flush the general queue."""
        items, self._general_queue = self._general_queue[:], []
        for item in items:
            await self._deliver(item)

    async def _flush_watchlist(self) -> None:
        """Flush the watchlist queue."""
        items, self._watchlist_queue = self._watchlist_queue[:], []
        for item in items:
            await self._deliver(item)

    async def _flush_general_loop(self) -> None:
        """Periodically flush the general queue."""
        while True:
            await asyncio.sleep(GENERAL_FLUSH_INTERVAL)
            if self._general_queue:
                await self._flush_general()

    async def _flush_watchlist_loop(self) -> None:
        """Periodically flush the watchlist queue."""
        while True:
            await asyncio.sleep(WATCHLIST_FLUSH_INTERVAL)
            if self._watchlist_queue:
                await self._flush_watchlist()


router = Router()
