"""Web scraper agent — fetches monitored web pages and extracts content."""

from __future__ import annotations

import asyncio
from typing import List

import aiohttp
from bs4 import BeautifulSoup

from ai_junkie_updates.agents.base_agent import BaseAgent, load_sources
from ai_junkie_updates.constants import SourceType
from ai_junkie_updates.core.models import RawItem
from ai_junkie_updates.settings import settings


class WebScraperAgent(BaseAgent):
    """Scrape monitored web pages for new AI industry content."""

    def __init__(self) -> None:
        super().__init__(
            source_type=SourceType.WEB_SCRAPER,
            source_name="web_scraper",
            poll_interval_seconds=settings.POLL_INTERVAL_SECONDS,
        )
        self._sources = load_sources("web_scraper")

    async def collect(self) -> List[RawItem]:
        """Fetch each configured URL, extract title + body text."""
        items: List[RawItem] = []

        async with aiohttp.ClientSession() as session:
            for src in self._sources:
                url = src.get("url", "")
                name = src.get("name", url)
                crawl_delay = src.get("crawl_delay", 2)
                if not url:
                    continue
                try:
                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=30),
                        headers={"User-Agent": "AIJunkieUpdates/1.0"},
                    ) as resp:
                        if resp.status != 200:
                            self.log.warning("web_fetch_error", url=url, status=resp.status)
                            continue
                        html = await resp.text()
                except Exception as exc:
                    self.log.error("web_fetch_exception", url=url, error=str(exc))
                    continue

                soup = BeautifulSoup(html, "lxml")

                # Remove script and style elements
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()

                title = soup.title.string.strip() if soup.title and soup.title.string else ""
                body_text = soup.get_text(separator="\n", strip=True)

                raw_content = f"{title}\n\n{body_text}" if title else body_text

                items.append(
                    RawItem(
                        source_type=SourceType.WEB_SCRAPER,
                        source_name=name,
                        source_url=url,
                        raw_content=raw_content,
                        metadata={"url": url},
                    )
                )

                # Respect crawl delay between requests
                await asyncio.sleep(crawl_delay)

        return items
