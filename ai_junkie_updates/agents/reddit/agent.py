"""Reddit agent — polls subreddits using the public JSON API."""

from __future__ import annotations

from typing import List

import aiohttp

from ai_junkie_updates.agents.base_agent import BaseAgent, load_sources
from ai_junkie_updates.constants import SourceType
from ai_junkie_updates.core.cache import cache
from ai_junkie_updates.core.models import RawItem
from ai_junkie_updates.settings import settings


class RedditAgent(BaseAgent):
    """Collect new posts from monitored subreddits via the public JSON API."""

    def __init__(self) -> None:
        super().__init__(
            source_type=SourceType.REDDIT,
            source_name="reddit",
            poll_interval_seconds=settings.POLL_INTERVAL_SECONDS,
        )
        self._sources = load_sources("reddit")

    async def collect(self) -> List[RawItem]:
        """Fetch new posts from each configured subreddit."""
        items: List[RawItem] = []
        headers = {"User-Agent": "AIJunkieUpdates/1.0"}

        async with aiohttp.ClientSession(headers=headers) as session:
            for src in self._sources:
                subreddit = src.get("subreddit", "")
                if not subreddit:
                    continue
                url = f"https://www.reddit.com/r/{subreddit}/new.json"
                try:
                    async with session.get(
                        url,
                        params={"limit": 25},
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        if resp.status != 200:
                            self.log.warning(
                                "reddit_fetch_error", subreddit=subreddit, status=resp.status
                            )
                            continue
                        data = await resp.json()

                    for child in data.get("data", {}).get("children", []):
                        post = child.get("data", {})
                        post_id = post.get("id", "")
                        cache_key = f"reddit:{subreddit}:{post_id}"
                        if cache.exists(cache_key):
                            continue

                        title = post.get("title", "")
                        selftext = post.get("selftext", "")
                        permalink = post.get("permalink", "")
                        post_url = f"https://www.reddit.com{permalink}" if permalink else ""
                        author = post.get("author", "unknown")

                        raw_content = f"{title}\n\n{selftext}" if selftext else title

                        items.append(
                            RawItem(
                                source_type=SourceType.REDDIT,
                                source_name=f"r/{subreddit}",
                                source_url=post_url,
                                raw_content=raw_content,
                                metadata={
                                    "subreddit": subreddit,
                                    "post_id": post_id,
                                    "author": author,
                                    "score": post.get("score", 0),
                                },
                            )
                        )
                        cache.set(cache_key, True, ttl=86400)

                except Exception as exc:
                    self.log.error(
                        "reddit_fetch_exception", subreddit=subreddit, error=str(exc)
                    )

        return items
