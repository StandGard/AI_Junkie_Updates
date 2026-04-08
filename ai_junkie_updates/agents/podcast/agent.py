"""Podcast agent — polls podcast RSS feeds for new episodes."""

from __future__ import annotations

from typing import List

import aiohttp
import feedparser

from ai_junkie_updates.agents.base_agent import BaseAgent, load_sources
from ai_junkie_updates.constants import SourceType
from ai_junkie_updates.core.cache import cache
from ai_junkie_updates.core.models import RawItem
from ai_junkie_updates.settings import settings


class PodcastAgent(BaseAgent):
    """Collect new podcast episodes from configured RSS feeds."""

    def __init__(self) -> None:
        super().__init__(
            source_type=SourceType.PODCAST,
            source_name="podcast",
            poll_interval_seconds=settings.POLL_INTERVAL_SECONDS,
        )
        self._sources = load_sources("podcast")

    async def collect(self) -> List[RawItem]:
        """Fetch podcast RSS feeds and return new episodes as RawItems."""
        items: List[RawItem] = []

        async with aiohttp.ClientSession() as session:
            for src in self._sources:
                url = src.get("url", "")
                name = src.get("name", url)
                if not url:
                    continue

                try:
                    async with session.get(
                        url, timeout=aiohttp.ClientTimeout(total=30)
                    ) as resp:
                        if resp.status != 200:
                            self.log.warning("podcast_fetch_error", url=url, status=resp.status)
                            continue
                        body = await resp.text()
                except Exception as exc:
                    self.log.error("podcast_fetch_exception", url=url, error=str(exc))
                    continue

                feed = feedparser.parse(body)
                show_title = feed.feed.get("title", name)

                # Only check the latest 5 episodes per feed
                for entry in feed.entries[:5]:
                    entry_id = entry.get("id") or entry.get("link") or entry.get("title", "")
                    cache_key = f"podcast:{name}:{entry_id}"
                    if cache.exists(cache_key):
                        continue

                    title = entry.get("title", "")
                    description = entry.get("summary", entry.get("description", ""))
                    link = entry.get("link", "")
                    published = entry.get("published", "")

                    raw_content = (
                        f"Podcast: {show_title}\n"
                        f"Episode: {title}\n"
                        f"Published: {published}\n\n"
                        f"{description}"
                    )

                    items.append(
                        RawItem(
                            source_type=SourceType.PODCAST,
                            source_name=f"podcast/{show_title}",
                            source_url=link,
                            raw_content=raw_content,
                            metadata={
                                "show": show_title,
                                "episode_title": title,
                                "published": published,
                                "feed_url": url,
                            },
                        )
                    )
                    cache.set(cache_key, True, ttl=86400)

        return items
