"""Discord agent — receives messages via webhook endpoints from Discord bots."""

from __future__ import annotations

import asyncio
from typing import List

from aiohttp import web

from ai_junkie_updates.agents.base_agent import BaseAgent, load_sources
from ai_junkie_updates.constants import SourceType
from ai_junkie_updates.core.models import RawItem
from ai_junkie_updates.settings import settings


class DiscordAgent(BaseAgent):
    """Receive Discord messages via webhook listener.

    Direct Discord scraping violates Discord ToS. This agent implements a
    webhook receiver that accepts POSTed messages from a Discord bot running
    in the user's Discord server.

    Expected POST body (JSON):
    {
        "server_name": "...",
        "channel_name": "...",
        "author": "...",
        "content": "...",
        "message_id": "...",
        "message_url": "..."
    }
    """

    def __init__(self) -> None:
        super().__init__(
            source_type=SourceType.DISCORD,
            source_name="discord",
            poll_interval_seconds=settings.POLL_INTERVAL_SECONDS,
        )
        self._sources = load_sources("discord")
        self._inbox: List[RawItem] = []
        self._server: web.AppRunner | None = None
        self._port = 8484

        # Determine port from sources config
        for src in self._sources:
            if src.get("webhook_port"):
                self._port = int(src["webhook_port"])
                break

    async def _start_webhook_server(self) -> None:
        """Start a lightweight HTTP server to receive Discord webhook POSTs."""
        app = web.Application()
        app.router.add_post("/discord/webhook", self._handle_webhook)
        self._server = web.AppRunner(app)
        await self._server.setup()
        site = web.TCPSite(self._server, "0.0.0.0", self._port)
        await site.start()
        self.log.info("discord_webhook_started", port=self._port)

    async def _handle_webhook(self, request: web.Request) -> web.Response:
        """Handle an incoming Discord message POST."""
        try:
            data = await request.json()
            content = data.get("content", "")
            if not content:
                return web.Response(status=204)

            server_name = data.get("server_name", "unknown")
            channel_name = data.get("channel_name", "unknown")
            author = data.get("author", "unknown")
            message_url = data.get("message_url", "")

            raw_content = (
                f"[{server_name} / #{channel_name}] {author}:\n{content}"
            )

            self._inbox.append(
                RawItem(
                    source_type=SourceType.DISCORD,
                    source_name=f"discord/{server_name}",
                    source_url=message_url,
                    raw_content=raw_content,
                    metadata={
                        "server": server_name,
                        "channel": channel_name,
                        "author": author,
                        "message_id": data.get("message_id", ""),
                    },
                )
            )
            return web.Response(status=200, text="ok")
        except Exception as exc:
            self.log.error("discord_webhook_error", error=str(exc))
            return web.Response(status=400)

    async def collect(self) -> List[RawItem]:
        """Return all messages received since the last collect() call."""
        # Start the webhook server on first collect
        if self._server is None:
            await self._start_webhook_server()

        items, self._inbox = self._inbox[:], []
        return items

    async def run(self) -> None:
        """Override run to ensure webhook server starts before polling."""
        if self._server is None:
            await self._start_webhook_server()
        await super().run()
