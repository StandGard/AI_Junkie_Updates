"""Intelligence-layer orchestration — periodic asyncio jobs.

Brings the six intelligence modules to life as a running system. Each job is an
independent ``asyncio`` task on its own timer, following the same resilience
pattern as ``BaseAgent.run()``: errors are caught and logged, never crashing the
loop. The jobs:

  * link_cluster_loop   — entity-link new items, then cluster them into events
                          (frequent, cheap, no LLM beyond what triage already did)
  * ranking_loop        — recompute all leaderboards (periodic; pure DB maths)
  * synthesis_loop      — generate advisor briefs for new significant events and
                          deliver them to Telegram (strong model; rate-bounded by
                          significance threshold + interval)
  * digest_loop         — build and deliver the periodic digest

Delivery reuses the existing outbound ``telegram_bot`` and its rate limiting.
Synthesis/digest are gated by ``settings.ENABLE_SYNTHESIS`` so the system can run
in collection-only mode for cost control.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

from ai_junkie_updates.intelligence.clustering import clusterer
from ai_junkie_updates.intelligence.entity_linker import entity_linker
from ai_junkie_updates.intelligence.ingest import benchmark_ingestor, openrouter_ingestor
from ai_junkie_updates.intelligence.knowledge_base import knowledge_base
from ai_junkie_updates.intelligence.ranking_engine import ranking_engine
from ai_junkie_updates.intelligence.synthesis import synthesizer
from ai_junkie_updates.settings import settings
from ai_junkie_updates.utils.logger import get_logger

log = get_logger(__name__)


class IntelligenceJobs:
    """Owns and supervises the periodic intelligence tasks."""

    def __init__(self, deliver=None) -> None:
        self._tasks: List[asyncio.Task] = []
        self._running = True
        # Injectable delivery hook (defaults to Telegram); takes a text string.
        self._deliver = deliver or self._deliver_telegram

    # ------------------------------------------------------------- delivery hook
    async def _deliver_telegram(self, text: str, channel=None) -> None:
        """Send a synthesized brief/digest to Telegram (best-effort, fail-soft)."""
        try:
            from ai_junkie_updates.constants import DeliveryChannel
            from ai_junkie_updates.delivery.telegram_bot import telegram_bot

            await telegram_bot.send_text(
                channel or DeliveryChannel.GENERAL, text
            )
        except Exception as exc:
            log.warning("intel_delivery_failed", error=str(exc))

    # -------------------------------------------------------------- job bodies
    async def run_link_cluster(self) -> dict:
        link = await entity_linker.run_once()
        cluster = await clusterer.run_once()
        return {"link": link, "cluster": cluster}

    async def run_ingest(self) -> dict:
        """Refresh structured KB data: OpenRouter pricing + benchmark scores.

        Both are fail-soft; benchmark leaderboards are fragile (no official API)
        so a parse/fetch failure simply leaves the last good scores in place.
        """
        prices = await openrouter_ingestor.run_once()
        benches = await benchmark_ingestor.run_once()
        return {"prices": prices, "benchmarks": benches}

    async def run_ranking(self) -> dict:
        # Refresh pricing + benchmark scores just before recomputing rankings so
        # every leaderboard reflects the latest available data.
        await self.run_ingest()
        return await ranking_engine.run_once()

    async def run_synthesis(self) -> dict:
        """Brief new significant events and deliver them."""
        events = await knowledge_base.unbriefed_events(
            min_significance=settings.BRIEF_MIN_SIGNIFICANCE
        )
        if not events:
            return {"briefed": 0}
        brief = await synthesizer.brief_for_events(events)
        if brief:
            from ai_junkie_updates.constants import DeliveryChannel

            # Route by the top event's significance: critical-tier events go to
            # the high-priority channel, the rest to general.
            top = max(e.significance_score for e in events)
            channel = (
                DeliveryChannel.HIGH_PRIORITY if top >= 90 else DeliveryChannel.GENERAL
            )
            await self._deliver(brief, channel)
        await knowledge_base.mark_events_briefed([e.id for e in events])
        return {"briefed": len(events)}

    async def run_digest(self) -> dict:
        digest = await synthesizer.build_digest()
        if digest:
            await self._deliver(digest)
        return {"digest": 1}

    # ------------------------------------------------------------------- loops
    async def _loop(self, name: str, coro_factory, interval: int,
                    initial_delay: float = 0.0) -> None:
        """Generic resilient timer loop (mirrors BaseAgent.run resilience)."""
        if initial_delay:
            await asyncio.sleep(initial_delay)
        while self._running:
            try:
                result = await coro_factory()
                log.info("intel_job_ran", job=name, **(result or {}))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("intel_job_error", job=name, error=str(exc))
            await asyncio.sleep(interval)

    def start(self) -> None:
        """Launch all intelligence loops as background tasks."""
        self._tasks.append(
            asyncio.create_task(
                self._loop(
                    "link_cluster",
                    self.run_link_cluster,
                    settings.LINK_CLUSTER_INTERVAL_SECONDS,
                    initial_delay=30,
                ),
                name="intel-link-cluster",
            )
        )
        self._tasks.append(
            asyncio.create_task(
                self._loop(
                    "ranking",
                    self.run_ranking,
                    settings.RANKING_INTERVAL_SECONDS,
                    initial_delay=60,
                ),
                name="intel-ranking",
            )
        )
        if settings.ENABLE_SYNTHESIS:
            self._tasks.append(
                asyncio.create_task(
                    self._loop(
                        "synthesis",
                        self.run_synthesis,
                        settings.SYNTHESIS_INTERVAL_SECONDS,
                        initial_delay=120,
                    ),
                    name="intel-synthesis",
                )
            )
            self._tasks.append(
                asyncio.create_task(
                    self._loop(
                        "digest",
                        self.run_digest,
                        settings.DIGEST_INTERVAL_SECONDS,
                        initial_delay=settings.DIGEST_INTERVAL_SECONDS,
                    ),
                    name="intel-digest",
                )
            )
        log.info("intelligence_jobs_started", count=len(self._tasks),
                 synthesis_enabled=settings.ENABLE_SYNTHESIS)

    async def stop(self) -> None:
        """Cancel all intelligence loops."""
        self._running = False
        for t in self._tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)


intelligence_jobs = IntelligenceJobs()
