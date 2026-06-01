"""Integration tests for agent collect() methods with mocked HTTP.

These exercise the real aiohttp -> feedparser / BeautifulSoup / JSON parsing
stack against realistic response payloads, intercepted at the aiohttp layer by
aioresponses. No network access is required, so they are CI-safe.

Each test patches the agent's ``_sources`` so it does not depend on the live
contents of sources.yaml.
"""

from __future__ import annotations

import re

import pytest
from aioresponses import aioresponses

from ai_junkie_updates.constants import SourceType

# ---------------------------------------------------------------------------
# Realistic sample payloads
# ---------------------------------------------------------------------------

RSS_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Example AI Blog</title>
  <item>
    <title>Acme releases Model X</title>
    <link>https://example.com/model-x</link>
    <guid>https://example.com/model-x</guid>
    <description>Acme today announced Model X, a new frontier model.</description>
  </item>
  <item>
    <title>Acme raises Series B</title>
    <link>https://example.com/series-b</link>
    <guid>https://example.com/series-b</guid>
    <description>Acme has raised $50M in Series B funding.</description>
  </item>
</channel></rss>"""

GITHUB_RELEASES = [
    {
        "id": 1001,
        "tag_name": "v2.0.0",
        "name": "v2.0.0 — Major release",
        "body": "Adds multi-GPU inference and a new quantization format.",
        "html_url": "https://github.com/acme/tool/releases/tag/v2.0.0",
    },
    {
        "id": 1002,
        "tag_name": "v1.9.0",
        "name": "v1.9.0",
        "body": "Bug fixes.",
        "html_url": "https://github.com/acme/tool/releases/tag/v1.9.0",
    },
]

REDDIT_JSON = {
    "data": {
        "children": [
            {
                "data": {
                    "id": "abc123",
                    "title": "New open-source LLM released",
                    "selftext": "We just open-sourced our 7B model.",
                    "permalink": "/r/MachineLearning/comments/abc123/new_llm/",
                    "author": "researcher",
                    "score": 412,
                }
            }
        ]
    }
}

API_FEED_JSON = {
    "articles": [
        {
            "id": "art-1",
            "title": "AI startup acquired",
            "description": "BigCo acquires AI startup for $1B.",
            "url": "https://news.example.com/art-1",
        }
    ]
}

WEB_PAGE_HTML = """<html><head><title>Acme News</title></head>
<body><nav>menu</nav><main><h1>Acme launches API v3</h1>
<p>The new API adds streaming and tool use.</p></main>
<footer>copyright</footer><script>var x=1;</script></body></html>"""

PODCAST_FEED = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>AI Talks</title>
  <item>
    <title>Episode 42: Interview with a lab founder</title>
    <link>https://podcast.example.com/42</link>
    <guid>https://podcast.example.com/42</guid>
    <description>A wide-ranging interview about frontier models.</description>
    <pubDate>Mon, 01 Jan 2026 00:00:00 GMT</pubDate>
  </item>
</channel></rss>"""


# ---------------------------------------------------------------------------
# RSS agent
# ---------------------------------------------------------------------------

async def test_rss_collect_parses_entries():
    from ai_junkie_updates.agents.rss.agent import RSSAgent

    agent = RSSAgent()
    agent._sources = [{"name": "Example AI Blog", "url": "https://feeds.example.com/ai"}]

    with aioresponses() as m:
        m.get("https://feeds.example.com/ai", status=200, body=RSS_FEED)
        items = await agent.collect()

    assert len(items) == 2
    assert all(i.source_type == SourceType.RSS for i in items)
    headlines = " ".join(i.raw_content for i in items)
    assert "Model X" in headlines and "Series B" in headlines
    assert items[0].source_url == "https://example.com/model-x"


async def test_rss_collect_dedups_via_cache():
    from ai_junkie_updates.agents.rss.agent import RSSAgent

    agent = RSSAgent()
    agent._sources = [{"name": "Example AI Blog", "url": "https://feeds.example.com/ai"}]

    with aioresponses() as m:
        m.get("https://feeds.example.com/ai", status=200, body=RSS_FEED)
        first = await agent.collect()
    with aioresponses() as m:
        m.get("https://feeds.example.com/ai", status=200, body=RSS_FEED)
        second = await agent.collect()  # same entries -> cache suppresses

    assert len(first) == 2
    assert second == []


async def test_rss_collect_handles_http_error():
    from ai_junkie_updates.agents.rss.agent import RSSAgent

    agent = RSSAgent()
    agent._sources = [{"name": "Broken", "url": "https://feeds.example.com/bad"}]
    with aioresponses() as m:
        m.get("https://feeds.example.com/bad", status=500)
        items = await agent.collect()
    assert items == []


# ---------------------------------------------------------------------------
# GitHub agent
# ---------------------------------------------------------------------------

async def test_github_collect_parses_releases():
    from ai_junkie_updates.agents.github.agent import GitHubAgent

    agent = GitHubAgent()
    agent._sources = [{"repo": "acme/tool"}]
    with aioresponses() as m:
        m.get(
            re.compile(r"https://api\.github\.com/repos/acme/tool/releases.*"),
            status=200,
            payload=GITHUB_RELEASES,
        )
        items = await agent.collect()

    assert len(items) == 2
    assert all(i.source_type == SourceType.GITHUB for i in items)
    assert items[0].source_name == "github/acme/tool"
    assert "v2.0.0" in items[0].raw_content
    assert items[0].metadata["tag"] == "v2.0.0"


# ---------------------------------------------------------------------------
# Reddit agent
# ---------------------------------------------------------------------------

async def test_reddit_collect_parses_posts():
    from ai_junkie_updates.agents.reddit.agent import RedditAgent

    agent = RedditAgent()
    agent._sources = [{"subreddit": "MachineLearning"}]
    with aioresponses() as m:
        m.get(
            re.compile(r"https://www\.reddit\.com/r/MachineLearning/new\.json.*"),
            status=200,
            payload=REDDIT_JSON,
        )
        items = await agent.collect()

    assert len(items) == 1
    item = items[0]
    assert item.source_type == SourceType.REDDIT
    assert item.source_name == "r/MachineLearning"
    assert "open-source LLM" in item.raw_content
    assert item.source_url.endswith("/r/MachineLearning/comments/abc123/new_llm/")


# ---------------------------------------------------------------------------
# API feed agent
# ---------------------------------------------------------------------------

async def test_api_feed_collect_extracts_via_content_path():
    from ai_junkie_updates.agents.api_feed.agent import APIFeedAgent

    agent = APIFeedAgent()
    agent._sources = [
        {"name": "News API", "url": "https://api.example.com/news", "content_path": "articles"}
    ]
    with aioresponses() as m:
        m.get(
            re.compile(r"https://api\.example\.com/news.*"),
            status=200,
            payload=API_FEED_JSON,
        )
        items = await agent.collect()

    assert len(items) == 1
    assert items[0].source_type == SourceType.API_FEED
    assert "acquired" in items[0].raw_content
    assert items[0].source_url == "https://news.example.com/art-1"


# ---------------------------------------------------------------------------
# Web scraper agent
# ---------------------------------------------------------------------------

async def test_web_scraper_collect_extracts_text():
    from ai_junkie_updates.agents.web_scraper.agent import WebScraperAgent

    agent = WebScraperAgent()
    agent._sources = [{"name": "Acme News", "url": "https://acme.example.com/news", "crawl_delay": 0}]
    with aioresponses() as m:
        m.get("https://acme.example.com/news", status=200, body=WEB_PAGE_HTML)
        items = await agent.collect()

    assert len(items) == 1
    content = items[0].raw_content
    assert "Acme launches API v3" in content
    # script / footer / nav noise should be stripped
    assert "var x=1" not in content
    assert "copyright" not in content


# ---------------------------------------------------------------------------
# Podcast agent
# ---------------------------------------------------------------------------

async def test_podcast_collect_parses_episodes():
    from ai_junkie_updates.agents.podcast.agent import PodcastAgent

    agent = PodcastAgent()
    agent._sources = [{"name": "AI Talks", "url": "https://podcast.example.com/feed"}]
    with aioresponses() as m:
        m.get("https://podcast.example.com/feed", status=200, body=PODCAST_FEED)
        items = await agent.collect()

    assert len(items) == 1
    assert items[0].source_type == SourceType.PODCAST
    assert "Episode 42" in items[0].raw_content
    assert "AI Talks" in items[0].source_name


# ---------------------------------------------------------------------------
# Twitter agent (credential gating)
# ---------------------------------------------------------------------------

async def test_twitter_collect_skips_without_token():
    from ai_junkie_updates.agents.twitter.agent import TwitterAgent

    agent = TwitterAgent()
    # No bearer_token -> agent should short-circuit and collect nothing.
    agent._sources = [{"accounts": ["OpenAI"]}]
    items = await agent.collect()
    assert items == []


async def test_twitter_collect_parses_tweets_with_token():
    from ai_junkie_updates.agents.twitter.agent import TwitterAgent

    agent = TwitterAgent()
    agent._sources = [{"bearer_token": "tok", "accounts": ["OpenAI"]}]
    payload = {
        "data": [{"id": "9", "author_id": "1", "text": "We shipped a new model."}],
        "includes": {"users": [{"id": "1", "username": "OpenAI"}]},
    }
    with aioresponses() as m:
        m.get(
            re.compile(r"https://api\.twitter\.com/2/tweets/search/recent.*"),
            status=200,
            payload=payload,
        )
        items = await agent.collect()

    assert len(items) == 1
    assert items[0].source_type == SourceType.TWITTER
    assert "shipped a new model" in items[0].raw_content
    assert items[0].metadata["author"] == "OpenAI"
