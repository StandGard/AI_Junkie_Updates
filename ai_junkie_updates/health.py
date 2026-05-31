"""Lightweight health-check HTTP server for always-on monitoring.

Exposes two endpoints on a configurable port so a process supervisor, container
healthcheck, or uptime monitor can verify the system is alive and has a populated
knowledge base:

  GET /health   -> 200 {"status": "ok", ...}      (liveness)
  GET /ready     -> 200 when the KB is seeded, else 503  (readiness)

Runs as a supervised asyncio task inside the main app (same loop as the agents),
mirroring the Discord agent's embedded-aiohttp-server pattern. Fail-soft: if the
port is unavailable, the rest of the system still runs.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from aiohttp import web

from ai_junkie_updates.settings import settings
from ai_junkie_updates.utils.logger import get_logger

log = get_logger(__name__)

_START_TIME = time.monotonic()


class HealthServer:
    """Tiny aiohttp server serving /health and /ready."""

    def __init__(self, port: int | None = None) -> None:
        self._port = port if port is not None else settings.HEALTH_CHECK_PORT
        self._runner: web.AppRunner | None = None

    async def _health(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "ok",
                "uptime_seconds": round(time.monotonic() - _START_TIME, 1),
                "time": datetime.now(timezone.utc).isoformat(),
            }
        )

    async def _ready(self, request: web.Request) -> web.Response:
        """Ready once the KB has models (i.e. seeding completed)."""
        try:
            from ai_junkie_updates.intelligence.knowledge_base import knowledge_base

            models = await knowledge_base.list_models()
            companies = await knowledge_base.list_companies()
            boards = await knowledge_base.list_leaderboards()
            ready = len(models) > 0
            payload = {
                "ready": ready,
                "models": len(models),
                "companies": len(companies),
                "leaderboards": len(boards),
            }
            return web.json_response(payload, status=200 if ready else 503)
        except Exception as exc:
            return web.json_response({"ready": False, "error": str(exc)}, status=503)

    async def start(self) -> None:
        """Start the health server (fail-soft on bind errors)."""
        if not settings.HEALTH_CHECK_ENABLED:
            return
        try:
            app = web.Application()
            app.router.add_get("/health", self._health)
            app.router.add_get("/ready", self._ready)
            self._runner = web.AppRunner(app)
            await self._runner.setup()
            site = web.TCPSite(self._runner, "0.0.0.0", self._port)
            await site.start()
            log.info("health_server_started", port=self._port)
        except Exception as exc:
            log.warning("health_server_failed", error=str(exc))

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()


health_server = HealthServer()
