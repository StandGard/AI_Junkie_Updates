"""RSS agent — polls RSS feed URLs and returns new entries."""

from __future__ import annotations

from typing import List

import aiohttp
import feedparser

from ai_junkie_updates.agents.base_agent import BaseAgent, load_sources
from ai_junkie_updates.constants import SourceType
from ai_junkie_updates.core.cache import cache
from ai_junkie_updates.core.models import RawItem
from ai_junkie_updates.settings import settings


class RSSAgent(BaseAgent):
    """Collect new entries from configured RSS feeds."""

    def __init__(self) -> None:
        super().__init__(
            source_type=SourceType.RSS,
            source_name="rss",
            poll_interval_seconds=settings.POLL_INTERVAL_SECONDS,
        )
        # YouTube channels are plain RSS (youtube.com/feeds/videos.xml?channel_id=…),
        # and X/Twitter accounts are routed through an RSS bridge (RSSHub/Nitter).
        # Both are standard feeds, so they ride the same proven RSS path — no
        # separate agents needed. The X bridge is best-effort (instances are
        # flaky); failures fail-soft per the base agent's error handling.
        self._sources = (
            load_sources("rss")
            + load_sources("youtube")
            + load_sources("rss_bridge")
        )

    async def collect(self) -> List[RawItem]:
        """Fetch all configured RSS feeds and return new entries as RawItems."""
        items: List[RawItem] = []

        async with aiohttp.ClientSession() as session:
            for src in self._sources:
                url = src.get("url", "")
                name = src.get("name", url)
                if not url:
                    continue
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status != 200:
                            self.log.warning("rss_fetch_error", url=url, status=resp.status)
                            continue
                        body = await resp.text()
                except Exception as exc:
                    self.log.error("rss_fetch_exception", url=url, error=str(exc))
                    continue

                feed = feedparser.parse(body)
                for entry in feed.entries:
                    entry_id = entry.get("id") or entry.get("link") or entry.get("title", "")
                    cache_key = f"rss:{entry_id}"
                    if cache.exists(cache_key):
                        continue

                    title = entry.get("title", "")
                    summary = entry.get("summary", "")
                    content = entry.get("content", [{}])
                    body_text = content[0].get("value", "") if content else ""
                    link = entry.get("link", "")

                    raw_text = f"{title}\n\n{body_text or summary}"

                    items.append(
                        RawItem(
                            source_type=SourceType.RSS,
                            source_name=name,
                            source_url=link,
                            raw_content=raw_text,
                            metadata={"entry_id": entry_id, "feed_url": url},
                        )
                    )
                    cache.set(cache_key, True, ttl=86400)

        return items
