"""Per-agent collect() tests with mocked HTTP — runnable without network.

Each agent's collect() reaches out to the network, which this sandbox blocks.
These tests replace the network boundary (aiohttp.ClientSession) with a fake
that returns a realistic response body for the source in question, then assert
the agent parses it into correctly-typed RawItems. This exercises the real
parsing paths — feedparser on real RSS XML, BeautifulSoup on real HTML, JSON
shape handling — without any live connection.

Run directly (no pytest required):

    python tests/test_agents_offline.py

Exits non-zero if any check fails.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys
from contextlib import contextmanager
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from ai_junkie_updates.constants import SourceType  # noqa: E402
from ai_junkie_updates.core.cache import cache  # noqa: E402

_results: list[tuple[str, bool]] = []


def _check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok))
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{suffix}")


# ---------------------------------------------------------------------------
# Fake aiohttp.ClientSession
# ---------------------------------------------------------------------------

def _make_fake_session(router):
    """Build a fake ClientSession class whose .get/.post return router(url)."""

    class _FakeResp:
        def __init__(self, spec: dict) -> None:
            self._spec = spec

        @property
        def status(self) -> int:
            return self._spec.get("status", 200)

        async def text(self) -> str:
            return self._spec.get("text", "")

        async def json(self):
            return self._spec.get("json")

        async def read(self) -> bytes:
            return self._spec.get("text", "").encode()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class _FakeSession:
        def __init__(self, *a, **k) -> None:
            pass

        def get(self, url, **k):
            return _FakeResp(router(url))

        def post(self, url, **k):
            return _FakeResp(router(url))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    return _FakeSession, _FakeSession  # (class, also usable as instance factory)


@contextmanager
def _mocked_http(router):
    """Patch aiohttp.ClientSession + neutralize asyncio.sleep for the block."""
    fake_cls, _ = _make_fake_session(router)

    async def _no_sleep(*a, **k):
        return None

    with patch("aiohttp.ClientSession", fake_cls), patch("asyncio.sleep", _no_sleep):
        yield


# ---------------------------------------------------------------------------
# Realistic response fixtures
# ---------------------------------------------------------------------------

RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Test AI Feed</title>
  <item>
    <title>OpenAI ships GPT-5</title>
    <link>https://example.com/gpt5</link>
    <guid>rss-guid-1</guid>
    <description>OpenAI announced GPT-5 today.</description>
  </item>
</channel></rss>"""

GITHUB_RELEASES = [
    {
        "id": 12345,
        "tag_name": "v2.0.0",
        "name": "Transformers 2.0",
        "body": "Adds GPT-5 support and bug fixes.",
        "html_url": "https://github.com/huggingface/transformers/releases/tag/v2.0.0",
    }
]

REDDIT_JSON = {
    "data": {
        "children": [
            {
                "data": {
                    "id": "abc123",
                    "title": "New open-source LLM released",
                    "selftext": "Benchmarks look great.",
                    "permalink": "/r/LocalLLaMA/comments/abc123/new_llm/",
                    "author": "researcher",
                    "score": 420,
                }
            }
        ]
    }
}

WEBPAGE_HTML = """<html><head><title>OpenAI News</title></head>
<body><nav>menu</nav><main><h1>GPT-5 launch</h1>
<p>OpenAI released its new flagship model today.</p></main>
<footer>footer</footer></body></html>"""

PODCAST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>The AI Podcast</title>
  <item>
    <title>Episode 42: The future of LLMs</title>
    <link>https://example.com/ep42</link>
    <guid>pod-guid-1</guid>
    <description>A deep dive into large language models.</description>
    <pubDate>Mon, 01 Jan 2026 00:00:00 GMT</pubDate>
  </item>
</channel></rss>"""

CHANGELOG_HTML = """<html><body>
<h2>v1.2.3</h2><p>Added GPT-5 support to the API.</p>
<h2>v1.2.2</h2><p>Fixed a streaming bug.</p>
</body></html>"""

# Press release HTML matching PR Newswire's configured selectors
PR_HTML = """<html><body>
<div class="newsreleaseconsolidatelink">
  <h3>AI Startup Raises $100M Series B</h3>
  <a href="/news/ai-startup-100m">read</a>
</div>
</body></html>"""

# Regulatory HTML matching FTC's configured selectors (.views-row / h3 a)
REG_HTML = """<html><body>
<div class="views-row">
  <h3><a href="/news/ftc-ai-probe">FTC Opens Inquiry into AI Pricing</a></h3>
  <p>The FTC announced today an investigation into algorithmic pricing.</p>
</div>
</body></html>"""

TWITTER_JSON = {
    "data": [
        {"id": "t1", "author_id": "u1", "text": "GPT-5 is now available", "created_at": "x"}
    ],
    "includes": {"users": [{"id": "u1", "username": "OpenAI"}]},
}

ONCHAIN_JSON = [
    {"id": "evt1", "type": "subnet_registered", "description": "New AI subnet registered"}
]

API_FEED_JSON = {
    "entities": [{"id": "cb1", "title": "AI Co raises $50M", "description": "Series A"}],
    "items": [{"id": "pb1", "name": "AI Startup", "description": "stealth"}],
    "articles": [{"id": "na1", "title": "AI breakthrough", "description": "news"}],
}

TELEGRAM_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>OpenAI Channel</title>
  <item>
    <title>Model update</title>
    <link>https://t.me/openai/123</link>
    <guid>tg-guid-1</guid>
    <description>We shipped a new model.</description>
  </item>
</channel></rss>"""


# ---------------------------------------------------------------------------
# Per-agent tests
# ---------------------------------------------------------------------------

async def test_rss():
    from ai_junkie_updates.agents.rss.agent import RSSAgent
    cache._store.clear()
    with _mocked_http(lambda u: {"text": RSS_XML}):
        items = await RSSAgent().collect()
    # All feeds share one guid -> dedup collapses to a single item.
    ok = len(items) == 1 and items[0].source_type == SourceType.RSS
    _check("rss parses feedparser entry + dedupes by guid", ok, f"{len(items)} item(s)")
    _check("rss item carries title in content",
           bool(items) and "GPT-5" in items[0].raw_content)


async def test_github():
    from ai_junkie_updates.agents.github.agent import GitHubAgent
    cache._store.clear()
    agent = GitHubAgent()
    # One item per configured repo (cache key is github:{repo}:{release_id}).
    with _mocked_http(lambda u: {"json": GITHUB_RELEASES}):
        first = await agent.collect()
        second = await agent.collect()  # all releases now cached
    n_repos = len(agent._sources)
    _check("github yields one item per repo", len(first) == n_repos, f"{len(first)} of {n_repos}")
    _check("github dedupes on re-poll (cache hit)", second == [], f"{len(second)} on 2nd poll")
    _check("github item includes tag + repo",
           bool(first) and "v2.0.0" in first[0].raw_content and "transformers" in first[0].source_name)


async def test_reddit():
    from ai_junkie_updates.agents.reddit.agent import RedditAgent
    cache._store.clear()
    agent = RedditAgent()
    # One item per configured subreddit (cache key is reddit:{subreddit}:{post_id}).
    with _mocked_http(lambda u: {"json": REDDIT_JSON}):
        first = await agent.collect()
        second = await agent.collect()  # all posts now cached
    n_subs = len(agent._sources)
    ok_types = all(i.source_type == SourceType.REDDIT for i in first)
    _check("reddit yields one item per subreddit",
           len(first) == n_subs and ok_types, f"{len(first)} of {n_subs}")
    _check("reddit dedupes on re-poll (cache hit)", second == [], f"{len(second)} on 2nd poll")
    _check("reddit item has title + permalink url",
           bool(first) and "open-source LLM" in first[0].raw_content
           and first[0].source_url.endswith("/new_llm/"))


async def test_web_scraper():
    from ai_junkie_updates.agents.web_scraper.agent import WebScraperAgent
    cache._store.clear()
    with _mocked_http(lambda u: {"text": WEBPAGE_HTML}):
        items = await WebScraperAgent().collect()
    ok = len(items) >= 1 and all(i.source_type == SourceType.WEB_SCRAPER for i in items)
    _check("web_scraper extracts text via BeautifulSoup", ok, f"{len(items)} item(s)")
    _check("web_scraper strips nav/footer, keeps body",
           bool(items) and "flagship model" in items[0].raw_content
           and "menu" not in items[0].raw_content)


async def test_podcast():
    from ai_junkie_updates.agents.podcast.agent import PodcastAgent
    cache._store.clear()
    with _mocked_http(lambda u: {"text": PODCAST_XML}):
        items = await PodcastAgent().collect()
    ok = len(items) >= 1 and all(i.source_type == SourceType.PODCAST for i in items)
    _check("podcast parses episode RSS", ok, f"{len(items)} item(s)")
    _check("podcast item names show + episode",
           bool(items) and "Episode 42" in items[0].raw_content)


async def test_changelog():
    from ai_junkie_updates.agents.changelog.agent import ChangelogAgent
    cache._store.clear()
    with _mocked_http(lambda u: {"text": CHANGELOG_HTML}):
        items = await ChangelogAgent().collect()
    ok = len(items) >= 1 and all(i.source_type == SourceType.CHANGELOG for i in items)
    _check("changelog splits entries by version header", ok, f"{len(items)} item(s)")
    _check("changelog entry captures version text",
           bool(items) and any("v1.2.3" in i.raw_content for i in items))


async def test_press_releases():
    from ai_junkie_updates.agents.press_releases.agent import PressReleasesAgent
    cache._store.clear()
    with _mocked_http(lambda u: {"text": PR_HTML}):
        items = await PressReleasesAgent().collect()
    ok = len(items) >= 1 and all(i.source_type == SourceType.PRESS_RELEASE for i in items)
    _check("press_releases selects articles by CSS selector", ok, f"{len(items)} item(s)")
    _check("press_releases builds absolute link from relative href",
           bool(items) and any("/news/ai-startup-100m" in (i.source_url or "") for i in items))


async def test_regulatory():
    from ai_junkie_updates.agents.regulatory.agent import RegulatoryAgent
    cache._store.clear()
    with _mocked_http(lambda u: {"text": REG_HTML}):
        items = await RegulatoryAgent().collect()
    ok = len(items) >= 1 and all(i.source_type == SourceType.REGULATORY for i in items)
    _check("regulatory selects gov articles by selector", ok, f"{len(items)} item(s)")
    _check("regulatory item has title text",
           bool(items) and any("FTC" in i.raw_content for i in items))


async def test_twitter():
    from ai_junkie_updates.agents.twitter.agent import TwitterAgent
    cache._store.clear()
    with _mocked_http(lambda u: {"json": TWITTER_JSON}):
        items = await TwitterAgent().collect()
    ok = len(items) >= 1 and all(i.source_type == SourceType.TWITTER for i in items)
    _check("twitter parses API v2 search response", ok, f"{len(items)} item(s)")
    _check("twitter resolves author username + builds tweet url",
           bool(items) and "OpenAI" in items[0].source_name
           and "status/t1" in items[0].source_url)


async def test_onchain():
    from ai_junkie_updates.agents.onchain.agent import OnchainAgent
    cache._store.clear()
    with _mocked_http(lambda u: {"json": ONCHAIN_JSON}):
        items = await OnchainAgent().collect()
    ok = len(items) >= 1 and all(i.source_type == SourceType.ONCHAIN for i in items)
    _check("onchain parses event list JSON", ok, f"{len(items)} item(s)")
    _check("onchain item records event type",
           bool(items) and "subnet_registered" in items[0].raw_content)


async def test_api_feed():
    from ai_junkie_updates.agents.api_feed.agent import APIFeedAgent
    cache._store.clear()
    with _mocked_http(lambda u: {"json": API_FEED_JSON}):
        items = await APIFeedAgent().collect()
    ok = len(items) >= 1 and all(i.source_type == SourceType.API_FEED for i in items)
    _check("api_feed extracts entries via content_path", ok, f"{len(items)} item(s)")
    _check("api_feed handles title/name fallback",
           bool(items) and any("AI Co raises" in i.raw_content for i in items))


async def test_telegram_channels():
    from ai_junkie_updates.agents.telegram_channels.agent import TelegramChannelsAgent
    cache._store.clear()
    agent = TelegramChannelsAgent()  # config list is empty; test the RSS path directly
    fake_cls, _ = _make_fake_session(lambda u: {"text": TELEGRAM_RSS_XML})
    session = fake_cls()
    items = await agent._collect_rss(session, {"rss_url": "https://rss.example/openai"}, "OpenAI Channel")
    ok = len(items) == 1 and items[0].source_type == SourceType.TELEGRAM_CHANNEL
    _check("telegram_channels parses RSS-bridge feed", ok, f"{len(items)} item(s)")
    _check("telegram_channels item carries channel name",
           bool(items) and items[0].source_name == "OpenAI Channel")


async def test_discord():
    from ai_junkie_updates.agents.discord.agent import DiscordAgent
    agent = DiscordAgent()

    class _FakeRequest:
        def __init__(self, data):
            self._data = data
        async def json(self):
            return self._data

    req = _FakeRequest({
        "server_name": "OpenAI",
        "channel_name": "announcements",
        "author": "sama",
        "content": "GPT-5 is out",
        "message_id": "1",
        "message_url": "https://discord.com/channels/1/2/3",
    })
    resp = await agent._handle_webhook(req)
    ok = resp.status == 200 and len(agent._inbox) == 1
    _check("discord webhook handler ingests POSTed message", ok, f"{len(agent._inbox)} queued")
    _check("discord item formats server/channel/author",
           bool(agent._inbox) and "OpenAI" in agent._inbox[0].source_name
           and "sama" in agent._inbox[0].raw_content)
    # Empty content should be ignored (HTTP 204, nothing queued)
    agent._inbox.clear()
    resp2 = await agent._handle_webhook(_FakeRequest({"content": ""}))
    _check("discord ignores empty content", resp2.status == 204 and not agent._inbox)


TESTS = [
    test_rss, test_github, test_reddit, test_web_scraper, test_podcast,
    test_changelog, test_press_releases, test_regulatory, test_twitter,
    test_onchain, test_api_feed, test_telegram_channels, test_discord,
]


async def _run() -> None:
    for t in TESTS:
        print(f"\n{t.__name__}:")
        try:
            await t()
        except Exception as exc:  # a thrown exception is a failed test, not a crash
            _check(f"{t.__name__} raised {type(exc).__name__}", False, str(exc))


def main() -> int:
    asyncio.run(_run())
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n=== AGENT COLLECT TESTS: {passed}/{total} checks passed ===")
    if passed != total:
        for name, ok in _results:
            if not ok:
                print("  FAILED:", name)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
