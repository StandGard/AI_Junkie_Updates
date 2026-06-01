"""Changelog agent — polls changelog and release notes pages for new entries."""

from __future__ import annotations

import re
from typing import List

import aiohttp
from bs4 import BeautifulSoup

from ai_junkie_updates.agents.base_agent import BaseAgent, load_sources
from ai_junkie_updates.constants import SourceType
from ai_junkie_updates.core.cache import cache
from ai_junkie_updates.core.models import RawItem
from ai_junkie_updates.settings import settings
from ai_junkie_updates.utils.fingerprint import generate_fingerprint

# Patterns that commonly delimit changelog entries
VERSION_PATTERN = re.compile(
    r"^(?:#{1,3}\s+)?(?:v?\d+\.\d+(?:\.\d+)?|20\d{2}[-/]\d{2}[-/]\d{2})",
    re.MULTILINE,
)


class ChangelogAgent(BaseAgent):
    """Collect new changelog entries from monitored release notes pages."""

    def __init__(self) -> None:
        super().__init__(
            source_type=SourceType.CHANGELOG,
            source_name="changelog",
            poll_interval_seconds=settings.POLL_INTERVAL_SECONDS,
        )
        self._sources = load_sources("changelog")

    async def collect(self) -> List[RawItem]:
        """Fetch changelog pages and split into individual entries."""
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
                            self.log.warning("changelog_fetch_error", url=url, status=resp.status)
                            continue
                        html = await resp.text()
                except Exception as exc:
                    self.log.error("changelog_fetch_exception", url=url, error=str(exc))
                    continue

                soup = BeautifulSoup(html, "lxml")
                for tag in soup(["script", "style", "nav", "footer"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)

                # Split text into entries by version/date headers
                entries = self._split_entries(text)

                for entry_text in entries:
                    entry_key = f"changelog:{name}:{generate_fingerprint(entry_text[:200])}"
                    if cache.exists(entry_key):
                        continue

                    items.append(
                        RawItem(
                            source_type=SourceType.CHANGELOG,
                            source_name=name,
                            source_url=url,
                            raw_content=entry_text,
                            metadata={"changelog_url": url},
                        )
                    )
                    cache.set(entry_key, True, ttl=86400)

        return items

    def _split_entries(self, text: str) -> List[str]:
        """Split changelog text into individual entries using version/date headers."""
        splits = list(VERSION_PATTERN.finditer(text))
        if not splits:
            # No recognisable headers — treat the whole page as one entry
            return [text] if text.strip() else []

        entries: List[str] = []
        for i, match in enumerate(splits):
            start = match.start()
            end = splits[i + 1].start() if i + 1 < len(splits) else len(text)
            entry = text[start:end].strip()
            if entry:
                entries.append(entry)

        # Only return the first 5 entries to avoid flooding the pipeline
        return entries[:5]
