"""Telegram channels agent — reads channel posts via RSS export feeds or Bot API."""

from __future__ import annotations

from typing import List

import aiohttp
import feedparser

from ai_junkie_updates.agents.base_agent import BaseAgent, load_sources
from ai_junkie_updates.constants import SourceType
from ai_junkie_updates.core.cache import cache
from ai_junkie_updates.core.models import RawItem
from ai_junkie_updates.settings import settings


class TelegramChannelsAgent(BaseAgent):
    """Collect posts from monitored Telegram channels.

    Uses RSS export feeds (e.g. via rsshub.app or similar) for public channels,
    or the Telegram Bot API for channels where the bot is a member.
    """

    def __init__(self) -> None:
        super().__init__(
            source_type=SourceType.TELEGRAM_CHANNEL,
            source_name="telegram_channels",
            poll_interval_seconds=settings.POLL_INTERVAL_SECONDS,
        )
        self._sources = load_sources("telegram_channels")

    async def collect(self) -> List[RawItem]:
        """Fetch new posts from each configured Telegram channel."""
        items: List[RawItem] = []

        async with aiohttp.ClientSession() as session:
            for src in self._sources:
                method = src.get("method", "rss")
                name = src.get("name", "unknown")

                if method == "rss":
                    items.extend(await self._collect_rss(session, src, name))
                elif method == "bot_api":
                    items.extend(await self._collect_bot_api(session, src, name))

        return items

    async def _collect_rss(
        self, session: aiohttp.ClientSession, src: dict, name: str
    ) -> List[RawItem]:
        """Collect via RSS feed URL for a public Telegram channel."""
        results: List[RawItem] = []
        rss_url = src.get("rss_url", "")
        if not rss_url:
            return results

        try:
            async with session.get(
                rss_url, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    self.log.warning("tg_rss_error", name=name, status=resp.status)
                    return results
                body = await resp.text()
        except Exception as exc:
            self.log.error("tg_rss_exception", name=name, error=str(exc))
            return results

        feed = feedparser.parse(body)
        for entry in feed.entries:
            entry_id = entry.get("id") or entry.get("link", "")
            cache_key = f"tg:{name}:{entry_id}"
            if cache.exists(cache_key):
                continue

            title = entry.get("title", "")
            summary = entry.get("summary", "")
            link = entry.get("link", "")
            raw_content = f"{title}\n\n{summary}" if title else summary

            results.append(
                RawItem(
                    source_type=SourceType.TELEGRAM_CHANNEL,
                    source_name=name,
                    source_url=link,
                    raw_content=raw_content,
                    metadata={"channel": name, "entry_id": entry_id},
                )
            )
            cache.set(cache_key, True, ttl=86400)

        return results

    async def _collect_bot_api(
        self, session: aiohttp.ClientSession, src: dict, name: str
    ) -> List[RawItem]:
        """Collect via Telegram Bot API getUpdates for channels where bot is a member."""
        results: List[RawItem] = []
        channel_id = src.get("channel_id", "")
        if not channel_id:
            return results

        bot_token = settings.TELEGRAM_BOT_TOKEN
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"

        try:
            async with session.get(
                url,
                params={"allowed_updates": '["channel_post"]', "limit": 20},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    self.log.warning("tg_bot_api_error", name=name, status=resp.status)
                    return results
                data = await resp.json()

            for update in data.get("result", []):
                post = update.get("channel_post", {})
                chat = post.get("chat", {})
                if str(chat.get("id", "")) != str(channel_id):
                    continue

                msg_id = post.get("message_id", "")
                cache_key = f"tg_bot:{channel_id}:{msg_id}"
                if cache.exists(cache_key):
                    continue

                text = post.get("text", "")
                if not text:
                    continue

                results.append(
                    RawItem(
                        source_type=SourceType.TELEGRAM_CHANNEL,
                        source_name=name,
                        source_url="",
                        raw_content=text,
                        metadata={
                            "channel_id": channel_id,
                            "message_id": str(msg_id),
                        },
                    )
                )
                cache.set(cache_key, True, ttl=86400)

        except Exception as exc:
            self.log.error("tg_bot_api_exception", name=name, error=str(exc))

        return results
