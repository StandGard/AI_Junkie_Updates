"""Twitter/X agent — polls Twitter API v2 for AI industry accounts and search terms."""

from __future__ import annotations

from typing import Any, Dict, List

import aiohttp

from ai_junkie_updates.agents.base_agent import BaseAgent, load_sources
from ai_junkie_updates.constants import SourceType
from ai_junkie_updates.core.models import RawItem
from ai_junkie_updates.settings import settings


class TwitterAgent(BaseAgent):
    """Collect tweets from monitored accounts and search terms via Twitter API v2."""

    def __init__(self) -> None:
        super().__init__(
            source_type=SourceType.TWITTER,
            source_name="twitter",
            poll_interval_seconds=settings.POLL_INTERVAL_SECONDS,
        )
        self._sources = load_sources("twitter")
        self._api_base = "https://api.twitter.com/2"

    async def collect(self) -> List[RawItem]:
        """Fetch recent tweets matching configured accounts and search terms."""
        items: List[RawItem] = []
        bearer_token = None
        for src in self._sources:
            if src.get("bearer_token"):
                bearer_token = src["bearer_token"]
                break

        if not bearer_token:
            self.log.warning("twitter_no_bearer_token")
            return items

        headers = {"Authorization": f"Bearer {bearer_token}"}

        async with aiohttp.ClientSession(headers=headers) as session:
            # Search queries
            for src in self._sources:
                queries: List[str] = []
                if src.get("accounts"):
                    for account in src["accounts"]:
                        queries.append(f"from:{account}")
                # Individual founders/researchers/influencers are tracked the
                # same way as company accounts.
                if src.get("individuals"):
                    for handle in src["individuals"]:
                        queries.append(f"from:{handle}")
                if src.get("search_terms"):
                    queries.extend(src["search_terms"])

                for query in queries:
                    items.extend(await self._search_tweets(session, query))

        return items

    async def _search_tweets(
        self, session: aiohttp.ClientSession, query: str
    ) -> List[RawItem]:
        """Execute a single Twitter search query and return RawItems."""
        results: List[RawItem] = []
        params: Dict[str, Any] = {
            "query": query,
            "max_results": 10,
            "tweet.fields": "author_id,created_at,text",
            "expansions": "author_id",
            "user.fields": "username",
        }
        try:
            async with session.get(
                f"{self._api_base}/tweets/search/recent", params=params
            ) as resp:
                if resp.status != 200:
                    self.log.warning(
                        "twitter_api_error", status=resp.status, query=query
                    )
                    return results
                data = await resp.json()

            users = {}
            for user in data.get("includes", {}).get("users", []):
                users[user["id"]] = user.get("username", "unknown")

            for tweet in data.get("data", []):
                author = users.get(tweet.get("author_id"), "unknown")
                tweet_url = f"https://x.com/{author}/status/{tweet['id']}"
                results.append(
                    RawItem(
                        source_type=SourceType.TWITTER,
                        source_name=f"twitter/@{author}",
                        source_url=tweet_url,
                        raw_content=tweet.get("text", ""),
                        metadata={
                            "tweet_id": tweet["id"],
                            "author": author,
                            "query": query,
                        },
                    )
                )
        except Exception as exc:
            self.log.error("twitter_fetch_error", query=query, error=str(exc))

        return results
