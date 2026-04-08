"""Press releases agent — scrapes PR newswire and company press pages."""

from __future__ import annotations

import asyncio
from typing import List

import aiohttp
from bs4 import BeautifulSoup

from ai_junkie_updates.agents.base_agent import BaseAgent, load_sources
from ai_junkie_updates.constants import SourceType
from ai_junkie_updates.core.cache import cache
from ai_junkie_updates.core.models import RawItem
from ai_junkie_updates.settings import settings


class PressReleasesAgent(BaseAgent):
    """Collect press releases from PR newswires and company press pages."""

    def __init__(self) -> None:
        super().__init__(
            source_type=SourceType.PRESS_RELEASE,
            source_name="press_releases",
            poll_interval_seconds=settings.POLL_INTERVAL_SECONDS,
        )
        self._sources = load_sources("press_releases")

    async def collect(self) -> List[RawItem]:
        """Fetch and parse press release pages for new articles."""
        items: List[RawItem] = []

        async with aiohttp.ClientSession() as session:
            for src in self._sources:
                url = src.get("url", "")
                name = src.get("name", url)
                selector = src.get("article_selector", "article")
                title_selector = src.get("title_selector", "h2")
                link_selector = src.get("link_selector", "a")
                if not url:
                    continue

                try:
                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=30),
                        headers={"User-Agent": "AIJunkieUpdates/1.0"},
                    ) as resp:
                        if resp.status != 200:
                            self.log.warning("pr_fetch_error", url=url, status=resp.status)
                            continue
                        html = await resp.text()
                except Exception as exc:
                    self.log.error("pr_fetch_exception", url=url, error=str(exc))
                    continue

                soup = BeautifulSoup(html, "lxml")
                articles = soup.select(selector)[:10]

                for article in articles:
                    title_el = article.select_one(title_selector)
                    title = title_el.get_text(strip=True) if title_el else ""
                    link_el = article.select_one(link_selector)
                    link = ""
                    if link_el and link_el.get("href"):
                        href = link_el["href"]
                        if href.startswith("http"):
                            link = href
                        elif href.startswith("/"):
                            # Build absolute URL from base
                            from urllib.parse import urlparse
                            parsed = urlparse(url)
                            link = f"{parsed.scheme}://{parsed.netloc}{href}"

                    body = article.get_text(separator="\n", strip=True)
                    cache_key = f"pr:{name}:{hash(title[:100])}"
                    if cache.exists(cache_key):
                        continue

                    raw_content = f"{title}\n\n{body}" if title else body

                    items.append(
                        RawItem(
                            source_type=SourceType.PRESS_RELEASE,
                            source_name=name,
                            source_url=link,
                            raw_content=raw_content,
                            metadata={"press_source": name, "url": url},
                        )
                    )
                    cache.set(cache_key, True, ttl=86400)

                await asyncio.sleep(1)  # polite delay between sources

        return items
