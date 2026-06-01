"""API feed agent — consumes structured JSON/API feeds with pagination support."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import aiohttp

from ai_junkie_updates.agents.base_agent import BaseAgent, load_sources
from ai_junkie_updates.constants import SourceType
from ai_junkie_updates.core.cache import cache
from ai_junkie_updates.core.models import RawItem
from ai_junkie_updates.settings import settings
from ai_junkie_updates.utils.fingerprint import generate_fingerprint


class APIFeedAgent(BaseAgent):
    """Collect structured data from JSON API feeds."""

    def __init__(self) -> None:
        super().__init__(
            source_type=SourceType.API_FEED,
            source_name="api_feed",
            poll_interval_seconds=settings.POLL_INTERVAL_SECONDS,
        )
        self._sources = load_sources("api_feed")

    async def collect(self) -> List[RawItem]:
        """Fetch data from each configured API feed."""
        items: List[RawItem] = []

        async with aiohttp.ClientSession() as session:
            for src in self._sources:
                api_url = src.get("url", "")
                name = src.get("name", api_url)
                api_key = src.get("api_key", "")
                content_path = src.get("content_path", "")
                pagination = src.get("pagination")
                if not api_url:
                    continue

                headers: Dict[str, str] = {"User-Agent": "AIJunkieUpdates/1.0"}
                if api_key:
                    headers["X-Api-Key"] = api_key

                params: Dict[str, Any] = dict(src.get("params", {}))

                try:
                    page = 1
                    max_pages = 3
                    while page <= max_pages:
                        if pagination and page > 1:
                            page_key = pagination.get("page_param", "page")
                            params[page_key] = page

                        async with session.get(
                            api_url,
                            headers=headers,
                            params=params,
                            timeout=aiohttp.ClientTimeout(total=30),
                        ) as resp:
                            if resp.status != 200:
                                self.log.warning(
                                    "api_feed_error", name=name, status=resp.status
                                )
                                break
                            data = await resp.json()

                        entries = self._extract_entries(data, content_path)
                        if not entries:
                            break

                        for entry in entries:
                            entry_id = str(
                                entry.get("id")
                                or entry.get("url")
                                or generate_fingerprint(str(entry)[:200])
                            )
                            cache_key = f"api:{name}:{entry_id}"
                            if cache.exists(cache_key):
                                continue

                            title = entry.get("title", entry.get("name", ""))
                            description = entry.get(
                                "description",
                                entry.get("summary", entry.get("content", str(entry))),
                            )
                            entry_url = entry.get("url", entry.get("link", ""))

                            raw_content = f"{title}\n\n{description}" if title else str(description)

                            items.append(
                                RawItem(
                                    source_type=SourceType.API_FEED,
                                    source_name=name,
                                    source_url=entry_url if isinstance(entry_url, str) else "",
                                    raw_content=raw_content,
                                    metadata={
                                        "feed_name": name,
                                        "entry_id": entry_id,
                                    },
                                )
                            )
                            cache.set(cache_key, True, ttl=86400)

                        if not pagination:
                            break
                        page += 1

                except Exception as exc:
                    self.log.error("api_feed_exception", name=name, error=str(exc))

        return items

    def _extract_entries(self, data: Any, content_path: str) -> List[Dict[str, Any]]:
        """Navigate the response JSON using a dot-separated content_path."""
        if not content_path:
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                # Try common keys
                for key in ("data", "results", "items", "articles", "entries"):
                    if key in data and isinstance(data[key], list):
                        return data[key]
            return [data] if isinstance(data, dict) else []

        obj: Any = data
        for part in content_path.split("."):
            if isinstance(obj, dict):
                obj = obj.get(part, [])
            else:
                return []

        return obj if isinstance(obj, list) else [obj] if isinstance(obj, dict) else []
