"""Abstract base agent that all source agents extend."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List

import yaml

from ai_junkie_updates.constants import SourceType, PipelineStatus
from ai_junkie_updates.core.claude_client import claude_client
from ai_junkie_updates.core.models import RawItem
from ai_junkie_updates.pipeline.deduplicator import Deduplicator
from ai_junkie_updates.pipeline.filter_engine import FilterEngine
from ai_junkie_updates.pipeline.normalizer import Normalizer
from ai_junkie_updates.pipeline.router import router
from ai_junkie_updates.utils.logger import get_logger

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

log = get_logger(__name__)


def load_sources(agent_key: str) -> List[Dict[str, Any]]:
    """Load the source list for a given agent from sources.yaml."""
    sources_path = CONFIG_DIR / "sources.yaml"
    with open(sources_path, "r") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get(agent_key, [])


def load_watchlist() -> List[str]:
    """Load the combined watchlist from watchlist.yaml."""
    watchlist_path = CONFIG_DIR / "watchlist.yaml"
    with open(watchlist_path, "r") as fh:
        data = yaml.safe_load(fh) or {}
    terms: List[str] = []
    for section in ("companies", "models", "topics"):
        terms.extend(data.get(section, []))
    return terms


class BaseAgent(ABC):
    """Abstract agent that collects items and runs the full pipeline."""

    def __init__(
        self,
        source_type: SourceType,
        source_name: str,
        poll_interval_seconds: int,
    ) -> None:
        self.source_type = source_type
        self.source_name = source_name
        self.poll_interval = poll_interval_seconds
        self._normalizer = Normalizer()
        self._deduplicator = Deduplicator()
        self._filter_engine = FilterEngine()
        self._watchlist = load_watchlist()
        self._running = True
        self.log = get_logger(f"agent.{source_name}")

    @abstractmethod
    async def collect(self) -> List[RawItem]:
        """Collect raw items from the source. Subclasses must implement."""
        ...

    async def run(self) -> None:
        """Infinite loop: collect → normalize → deduplicate → analyze → filter → route."""
        self.log.info("agent_started", source_type=self.source_type.value)
        while self._running:
            try:
                items = await self.collect()
                self.log.info("items_collected", count=len(items))
                for item in items:
                    await self._process_item(item)
            except asyncio.CancelledError:
                self.log.info("agent_cancelled")
                break
            except Exception as exc:
                self.log.error("agent_loop_error", error=str(exc))

            await asyncio.sleep(self.poll_interval)

    async def _process_item(self, raw_item: RawItem) -> None:
        """Run a single item through the full pipeline."""
        try:
            # Normalize
            raw_item = self._normalizer.normalize(raw_item)
            raw_item = raw_item.model_copy(
                update={"metadata": {**raw_item.metadata, "pipeline": PipelineStatus.NORMALIZED.value}}
            )

            # Deduplicate
            if await self._deduplicator.is_duplicate(raw_item):
                self.log.debug("item_duplicate", item_id=raw_item.id)
                return

            # Analyze via Claude
            update_item = await claude_client.analyze(raw_item)

            # Filter
            should_deliver, channel = self._filter_engine.should_deliver(
                update_item, self._watchlist
            )
            update_item.delivery_channel = channel
            update_item.pipeline_status = (
                PipelineStatus.FILTERED if should_deliver else PipelineStatus.DROPPED
            )

            # Route
            await router.route(update_item)

        except Exception as exc:
            self.log.error(
                "item_processing_error",
                item_id=raw_item.id,
                error=str(exc),
            )

    def stop(self) -> None:
        """Signal the agent to stop after the current cycle."""
        self._running = False
