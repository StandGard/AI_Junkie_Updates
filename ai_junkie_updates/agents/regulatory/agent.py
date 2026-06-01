"""Regulatory agent — polls government and regulatory body websites for AI policy news."""

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
from ai_junkie_updates.utils.fingerprint import generate_fingerprint


class RegulatoryAgent(BaseAgent):
    """Collect regulatory and policy updates from government websites."""

    def __init__(self) -> None:
        super().__init__(
            source_type=SourceType.REGULATORY,
            source_name="regulatory",
            poll_interval_seconds=settings.POLL_INTERVAL_SECONDS,
        )
        self._sources = load_sources("regulatory")

    async def collect(self) -> List[RawItem]:
        """Fetch regulatory pages and extract new documents/announcements."""
        items: List[RawItem] = []

        async with aiohttp.ClientSession() as session:
            for src in self._sources:
                url = src.get("url", "")
                name = src.get("name", url)
                selector = src.get("article_selector", "article, .press-release, .news-item, li")
                title_selector = src.get("title_selector", "h2, h3, a")
                if not url:
                    continue

                try:
                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=30),
                        headers={"User-Agent": "AIJunkieUpdates/1.0"},
                    ) as resp:
                        if resp.status != 200:
                            self.log.warning("regulatory_fetch_error", url=url, status=resp.status)
                            continue
                        html = await resp.text()
                except Exception as exc:
                    self.log.error("regulatory_fetch_exception", url=url, error=str(exc))
                    continue

                soup = BeautifulSoup(html, "lxml")
                elements = soup.select(selector)[:10]

                for el in elements:
                    title_el = el.select_one(title_selector)
                    title = title_el.get_text(strip=True) if title_el else ""
                    body = el.get_text(separator="\n", strip=True)

                    if not body or len(body) < 20:
                        continue

                    # Extract link
                    link = ""
                    link_el = el.select_one("a[href]")
                    if link_el and link_el.get("href"):
                        href = link_el["href"]
                        if href.startswith("http"):
                            link = href
                        elif href.startswith("/"):
                            from urllib.parse import urlparse
                            parsed = urlparse(url)
                            link = f"{parsed.scheme}://{parsed.netloc}{href}"

                    cache_key = f"reg:{name}:{generate_fingerprint(title[:80] or body[:80])}"
                    if cache.exists(cache_key):
                        continue

                    raw_content = f"Source: {name}\n{title}\n\n{body}" if title else body

                    items.append(
                        RawItem(
                            source_type=SourceType.REGULATORY,
                            source_name=name,
                            source_url=link,
                            raw_content=raw_content,
                            metadata={"regulatory_source": name, "page_url": url},
                        )
                    )
                    cache.set(cache_key, True, ttl=86400)

                await asyncio.sleep(2)  # respectful delay for government sites

        return items
