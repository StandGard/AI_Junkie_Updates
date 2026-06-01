"""Live dry-run harness — collect from real sources WITHOUT calling Claude or
Telegram, and print what would have been analyzed.

This is the safe way to confirm that real feeds actually parse into RawItems
before spending Claude tokens or sending Telegram messages. It runs each
selected agent's real collect() once and prints a summary; the analyze/filter/
deliver stages are skipped entirely.

Usage:
    # Collect from every agent once:
    python -m scripts.dry_run

    # Only specific agents:
    python -m scripts.dry_run rss github reddit

    # Show the first N chars of each item's content:
    python -m scripts.dry_run --preview 200 rss

Notes:
- Requires only the runtime dependencies (no API keys needed for credential-
  free agents like rss, github, reddit, web_scraper, changelog, podcast,
  press_releases, regulatory). Credentialed agents (twitter, api_feed) will
  simply collect nothing unless their env vars / sources.yaml are configured.
- Honours the same sources.yaml and env-var expansion as the real system.
"""

from __future__ import annotations

import argparse
import asyncio

# Dry-run must never deliver or analyze, so we set placeholder credentials to
# satisfy Settings() without ever exercising the Claude/Telegram clients.
import os
import sys

os.environ.setdefault("AIJU_ANTHROPIC_API_KEY", "dry-run-no-call")
os.environ.setdefault("AIJU_TELEGRAM_BOT_TOKEN", "dry-run-no-call")

from ai_junkie_updates.agents.api_feed.agent import APIFeedAgent
from ai_junkie_updates.agents.changelog.agent import ChangelogAgent
from ai_junkie_updates.agents.github.agent import GitHubAgent
from ai_junkie_updates.agents.podcast.agent import PodcastAgent
from ai_junkie_updates.agents.press_releases.agent import PressReleasesAgent
from ai_junkie_updates.agents.reddit.agent import RedditAgent
from ai_junkie_updates.agents.regulatory.agent import RegulatoryAgent
from ai_junkie_updates.agents.rss.agent import RSSAgent
from ai_junkie_updates.agents.telegram_channels.agent import TelegramChannelsAgent
from ai_junkie_updates.agents.twitter.agent import TwitterAgent
from ai_junkie_updates.agents.web_scraper.agent import WebScraperAgent

AGENT_FACTORIES = {
    "rss": RSSAgent,
    "github": GitHubAgent,
    "reddit": RedditAgent,
    "web_scraper": WebScraperAgent,
    "changelog": ChangelogAgent,
    "podcast": PodcastAgent,
    "press_releases": PressReleasesAgent,
    "regulatory": RegulatoryAgent,
    "telegram_channels": TelegramChannelsAgent,
    "twitter": TwitterAgent,
    "api_feed": APIFeedAgent,
}


async def run_agent(name: str, preview: int) -> int:
    factory = AGENT_FACTORIES[name]
    agent = factory()
    print(f"\n=== {name} ===")
    try:
        items = await agent.collect()
    except Exception as exc:  # pragma: no cover - operational tool
        print(f"  ERROR during collect(): {type(exc).__name__}: {exc}")
        return 0

    print(f"  collected {len(items)} item(s)")
    for i, item in enumerate(items[:10], 1):
        line = f"  [{i}] {item.source_name} -> {item.source_url or '(no url)'}"
        print(line)
        if preview:
            snippet = " ".join(item.raw_content.split())[:preview]
            print(f"        {snippet}")
    if len(items) > 10:
        print(f"  ... and {len(items) - 10} more")
    return len(items)


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Live dry-run: collect only.")
    parser.add_argument(
        "agents",
        nargs="*",
        help="Agent names to run (default: all). Choices: "
        + ", ".join(AGENT_FACTORIES),
    )
    parser.add_argument(
        "--preview",
        type=int,
        default=0,
        help="Print the first N characters of each item's content.",
    )
    args = parser.parse_args(argv)

    names = args.agents or list(AGENT_FACTORIES)
    unknown = [n for n in names if n not in AGENT_FACTORIES]
    if unknown:
        print(f"Unknown agent(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Available: {', '.join(AGENT_FACTORIES)}", file=sys.stderr)
        return 2

    total = 0
    for name in names:
        total += await run_agent(name, args.preview)

    print(f"\nTOTAL collected across {len(names)} agent(s): {total}")
    print("(Dry-run: no Claude analysis and no Telegram delivery were performed.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
