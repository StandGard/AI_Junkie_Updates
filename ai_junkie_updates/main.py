"""Async entrypoint — boots the system, runs all 13 agents concurrently."""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import List

from ai_junkie_updates.bootstrap import bootstrap
from ai_junkie_updates.pipeline.router import router
from ai_junkie_updates.settings import settings
from ai_junkie_updates.utils.logger import get_logger

# Agent imports
from ai_junkie_updates.agents.twitter.agent import TwitterAgent
from ai_junkie_updates.agents.rss.agent import RSSAgent
from ai_junkie_updates.agents.web_scraper.agent import WebScraperAgent
from ai_junkie_updates.agents.changelog.agent import ChangelogAgent
from ai_junkie_updates.agents.github.agent import GitHubAgent
from ai_junkie_updates.agents.reddit.agent import RedditAgent
from ai_junkie_updates.agents.discord.agent import DiscordAgent
from ai_junkie_updates.agents.onchain.agent import OnchainAgent
from ai_junkie_updates.agents.telegram_channels.agent import TelegramChannelsAgent
from ai_junkie_updates.agents.press_releases.agent import PressReleasesAgent
from ai_junkie_updates.agents.podcast.agent import PodcastAgent
from ai_junkie_updates.agents.regulatory.agent import RegulatoryAgent
from ai_junkie_updates.agents.api_feed.agent import APIFeedAgent

log = get_logger(__name__)


def _build_agents() -> list:
    """Instantiate all 13 agents."""
    return [
        TwitterAgent(),
        RSSAgent(),
        WebScraperAgent(),
        ChangelogAgent(),
        GitHubAgent(),
        RedditAgent(),
        DiscordAgent(),
        OnchainAgent(),
        TelegramChannelsAgent(),
        PressReleasesAgent(),
        PodcastAgent(),
        RegulatoryAgent(),
        APIFeedAgent(),
    ]


async def main() -> None:
    """Boot the system and run all agents until interrupted."""
    singletons = await bootstrap()
    db = singletons["db"]

    agents = _build_agents()
    # Bounds how many agents may perform an active collect/process cycle at the
    # same time. Each agent still runs continuously — the semaphore is held only
    # during a cycle and released while the agent sleeps between polls.
    collection_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_AGENTS)

    # Start the router's batching flush loops
    router.start_flush_loops()

    log.info(
        "system_started",
        agent_count=len(agents),
        max_concurrent=settings.MAX_CONCURRENT_AGENTS,
    )

    # Set up graceful shutdown
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        log.info("shutdown_signal_received")
        shutdown_event.set()
        for agent in agents:
            agent.stop()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler for all signals
            pass

    # Launch all agents concurrently
    tasks: List[asyncio.Task] = [
        asyncio.create_task(
            agent.run(collection_semaphore),
            name=f"agent-{agent.source_name}",
        )
        for agent in agents
    ]

    # Wait for shutdown signal or all tasks to complete
    done, pending = await asyncio.wait(
        [asyncio.create_task(shutdown_event.wait()), *tasks],
        return_when=asyncio.FIRST_COMPLETED,
    )

    # Graceful shutdown
    log.info("shutting_down", pending_tasks=len(pending))
    for task in pending:
        task.cancel()

    await asyncio.gather(*pending, return_exceptions=True)
    await router.stop()
    await db.close()
    log.info("shutdown_complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
