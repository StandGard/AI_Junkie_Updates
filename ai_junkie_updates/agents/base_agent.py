"""Abstract base agent that all source agents extend."""

from __future__ import annotations

import asyncio
import importlib
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ai_junkie_updates.constants import PipelineStatus, SourceType
from ai_junkie_updates.core.claude_client import claude_client
from ai_junkie_updates.core.models import RawItem
from ai_junkie_updates.pipeline.deduplicator import Deduplicator
from ai_junkie_updates.pipeline.filter_engine import FilterEngine
from ai_junkie_updates.pipeline.normalizer import Normalizer
from ai_junkie_updates.pipeline.router import router
from ai_junkie_updates.utils.logger import get_logger

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

log = get_logger(__name__)


# Matches ${VAR} or $VAR placeholders for environment substitution.
_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}|\$(\w+)")


def _expand_env(value: Any) -> Any:
    """Recursively expand ${VAR}/$VAR references in strings using the environment.

    Credentials in sources.yaml are written as ``${TWITTER_BEARER_TOKEN}`` etc.
    so they are not committed in plaintext. Without this expansion the literal
    placeholder string is sent to the API. Unlike ``os.path.expandvars``, an
    unset variable expands to an empty string so that credential-less sources
    are correctly treated as unconfigured (and skipped) rather than sending the
    literal placeholder.
    """
    if isinstance(value, str):
        return _ENV_VAR_PATTERN.sub(
            lambda m: os.environ.get(m.group(1) or m.group(2), ""), value
        )
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def load_sources(agent_key: str) -> List[Dict[str, Any]]:
    """Load the source list for a given agent from sources.yaml.

    Any ``${VAR}`` placeholders in the config are expanded from environment
    variables so credentials can be kept out of the committed YAML.
    """
    sources_path = CONFIG_DIR / "sources.yaml"
    with open(sources_path, "r") as fh:
        data = yaml.safe_load(fh) or {}
    return _expand_env(data.get(agent_key, []))


def load_agent_prompt(agent_module: str) -> Optional[str]:
    """Load the ``AGENT_CONTEXT_PROMPT`` from a sibling ``prompt`` module.

    ``agent_module`` is the dotted module path of the agent (typically
    ``type(self).__module__``, e.g. ``ai_junkie_updates.agents.twitter.agent``).
    Returns the prompt string, or ``None`` if no prompt module/constant exists.
    """
    prompt_module = agent_module.rsplit(".", 1)[0] + ".prompt"
    try:
        module = importlib.import_module(prompt_module)
    except ImportError:
        return None
    prompt = getattr(module, "AGENT_CONTEXT_PROMPT", None)
    return prompt.strip() if isinstance(prompt, str) and prompt.strip() else None


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
        self._context_prompt = load_agent_prompt(type(self).__module__)
        self._running = True
        self.log = get_logger(f"agent.{source_name}")

    @abstractmethod
    async def collect(self) -> List[RawItem]:
        """Collect raw items from the source. Subclasses must implement."""
        ...

    async def run(self, collection_semaphore: "asyncio.Semaphore | None" = None) -> None:
        """Infinite loop: collect → normalize → deduplicate → analyze → filter → route.

        If ``collection_semaphore`` is provided it bounds how many agents may
        perform an active work cycle (collect + process) at the same time. The
        semaphore is held only for the duration of the cycle and released while
        the agent sleeps, so every agent keeps running concurrently — only the
        amount of simultaneous work is capped.
        """
        self.log.info("agent_started", source_type=self.source_type.value)
        while self._running:
            try:
                if collection_semaphore is not None:
                    async with collection_semaphore:
                        await self._run_cycle()
                else:
                    await self._run_cycle()
            except asyncio.CancelledError:
                self.log.info("agent_cancelled")
                break
            except Exception as exc:
                self.log.error("agent_loop_error", error=str(exc))

            await asyncio.sleep(self.poll_interval)

    async def _run_cycle(self) -> None:
        """Run a single collect-and-process cycle."""
        items = await self.collect()
        self.log.info("items_collected", count=len(items))
        for item in items:
            await self._process_item(item)

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

            # Analyze via Claude (with source-specific context guidance)
            update_item = await claude_client.analyze(
                raw_item, context_prompt=self._context_prompt
            )

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
