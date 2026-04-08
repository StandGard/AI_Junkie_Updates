"""On-chain agent — polls blockchain APIs for AI-related events."""

from __future__ import annotations

from typing import Any, Dict, List

import aiohttp

from ai_junkie_updates.agents.base_agent import BaseAgent, load_sources
from ai_junkie_updates.constants import SourceType
from ai_junkie_updates.core.cache import cache
from ai_junkie_updates.core.models import RawItem
from ai_junkie_updates.settings import settings


class OnchainAgent(BaseAgent):
    """Collect AI-related on-chain events from configured blockchain APIs."""

    def __init__(self) -> None:
        super().__init__(
            source_type=SourceType.ONCHAIN,
            source_name="onchain",
            poll_interval_seconds=settings.POLL_INTERVAL_SECONDS,
        )
        self._sources = load_sources("onchain")

    async def collect(self) -> List[RawItem]:
        """Fetch events from each configured on-chain data source."""
        items: List[RawItem] = []

        async with aiohttp.ClientSession() as session:
            for src in self._sources:
                api_url = src.get("api_url", "")
                name = src.get("name", "")
                api_key = src.get("api_key", "")
                if not api_url:
                    continue

                headers: Dict[str, str] = {"User-Agent": "AIJunkieUpdates/1.0"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"

                params: Dict[str, Any] = src.get("params", {})

                try:
                    async with session.get(
                        api_url,
                        headers=headers,
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        if resp.status != 200:
                            self.log.warning(
                                "onchain_fetch_error", source=name, status=resp.status
                            )
                            continue
                        data = await resp.json()

                    events = data if isinstance(data, list) else data.get("data", data.get("events", []))
                    if not isinstance(events, list):
                        events = [events]

                    for event in events:
                        event_id = str(
                            event.get("id")
                            or event.get("hash")
                            or event.get("tx_hash")
                            or hash(str(event))
                        )
                        cache_key = f"onchain:{name}:{event_id}"
                        if cache.exists(cache_key):
                            continue

                        event_type = event.get("type", event.get("event_type", "unknown"))
                        description = event.get("description", event.get("summary", str(event)))
                        tx_hash = event.get("hash", event.get("tx_hash", ""))

                        raw_content = (
                            f"Network: {name}\n"
                            f"Event type: {event_type}\n"
                            f"Transaction: {tx_hash}\n\n"
                            f"{description}"
                        )

                        items.append(
                            RawItem(
                                source_type=SourceType.ONCHAIN,
                                source_name=name,
                                source_url=src.get("explorer_url", ""),
                                raw_content=raw_content,
                                metadata={
                                    "network": name,
                                    "event_id": event_id,
                                    "tx_hash": tx_hash,
                                },
                            )
                        )
                        cache.set(cache_key, True, ttl=86400)

                except Exception as exc:
                    self.log.error("onchain_fetch_exception", source=name, error=str(exc))

        return items
