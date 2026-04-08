"""GitHub agent — polls GitHub REST API for releases and events on monitored repos."""

from __future__ import annotations

from typing import List

import aiohttp

from ai_junkie_updates.agents.base_agent import BaseAgent, load_sources
from ai_junkie_updates.constants import SourceType
from ai_junkie_updates.core.cache import cache
from ai_junkie_updates.core.models import RawItem
from ai_junkie_updates.settings import settings


class GitHubAgent(BaseAgent):
    """Collect new releases from monitored GitHub repositories."""

    def __init__(self) -> None:
        super().__init__(
            source_type=SourceType.GITHUB,
            source_name="github",
            poll_interval_seconds=settings.POLL_INTERVAL_SECONDS,
        )
        self._sources = load_sources("github")
        self._api_base = "https://api.github.com"

    async def collect(self) -> List[RawItem]:
        """Fetch latest releases for each configured repository."""
        items: List[RawItem] = []
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "AIJunkieUpdates/1.0",
        }
        # Use a GitHub token if provided in sources config
        for src in self._sources:
            if src.get("token"):
                headers["Authorization"] = f"Bearer {src['token']}"
                break

        async with aiohttp.ClientSession(headers=headers) as session:
            for src in self._sources:
                repo = src.get("repo", "")
                if not repo:
                    continue
                try:
                    url = f"{self._api_base}/repos/{repo}/releases"
                    async with session.get(
                        url,
                        params={"per_page": 5},
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        if resp.status != 200:
                            self.log.warning(
                                "github_fetch_error", repo=repo, status=resp.status
                            )
                            continue
                        releases = await resp.json()

                    for release in releases:
                        release_id = release.get("id", "")
                        cache_key = f"github:{repo}:{release_id}"
                        if cache.exists(cache_key):
                            continue

                        tag = release.get("tag_name", "")
                        name = release.get("name", tag)
                        body = release.get("body", "")
                        html_url = release.get("html_url", "")

                        raw_content = f"Repository: {repo}\nRelease: {name} ({tag})\n\n{body}"

                        items.append(
                            RawItem(
                                source_type=SourceType.GITHUB,
                                source_name=f"github/{repo}",
                                source_url=html_url,
                                raw_content=raw_content,
                                metadata={
                                    "repo": repo,
                                    "tag": tag,
                                    "release_id": str(release_id),
                                },
                            )
                        )
                        cache.set(cache_key, True, ttl=86400)

                except Exception as exc:
                    self.log.error("github_fetch_exception", repo=repo, error=str(exc))

        return items
