"""Tests for base_agent helpers: env-var expansion and prompt loading.

Covers the §4.2 (env expansion in sources) and §4.3 (per-source prompt
wiring) fixes.
"""

from __future__ import annotations

from ai_junkie_updates.agents.base_agent import (
    _expand_env,
    load_agent_prompt,
    load_sources,
    load_watchlist,
)

ALL_AGENT_MODULES = [
    "ai_junkie_updates.agents.twitter.agent",
    "ai_junkie_updates.agents.rss.agent",
    "ai_junkie_updates.agents.web_scraper.agent",
    "ai_junkie_updates.agents.changelog.agent",
    "ai_junkie_updates.agents.github.agent",
    "ai_junkie_updates.agents.reddit.agent",
    "ai_junkie_updates.agents.discord.agent",
    "ai_junkie_updates.agents.onchain.agent",
    "ai_junkie_updates.agents.telegram_channels.agent",
    "ai_junkie_updates.agents.press_releases.agent",
    "ai_junkie_updates.agents.podcast.agent",
    "ai_junkie_updates.agents.regulatory.agent",
    "ai_junkie_updates.agents.api_feed.agent",
]


class TestExpandEnv:
    def test_expands_set_variable(self, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "secret")
        assert _expand_env("${MY_TOKEN}") == "secret"
        assert _expand_env("$MY_TOKEN") == "secret"

    def test_unset_variable_becomes_empty(self, monkeypatch):
        monkeypatch.delenv("NOPE_TOKEN", raising=False)
        # Critical: empty (falsy) so credential-less sources get skipped,
        # rather than sending the literal placeholder to an API.
        assert _expand_env("${NOPE_TOKEN}") == ""

    def test_recurses_into_dicts_and_lists(self, monkeypatch):
        monkeypatch.setenv("T", "tok")
        src = [{"bearer_token": "${T}", "accounts": ["OpenAI"], "port": 8484}]
        out = _expand_env(src)
        assert out[0]["bearer_token"] == "tok"
        assert out[0]["accounts"] == ["OpenAI"]
        assert out[0]["port"] == 8484  # non-strings preserved

    def test_non_string_scalars_preserved(self):
        assert _expand_env(5) == 5
        assert _expand_env(None) is None
        assert _expand_env(True) is True


class TestLoadSources:
    def test_known_agent_key_returns_list(self):
        # rss is configured with several feeds in sources.yaml
        sources = load_sources("rss")
        assert isinstance(sources, list)
        assert len(sources) > 0
        assert all(isinstance(s, dict) for s in sources)

    def test_unknown_agent_key_returns_empty(self):
        assert load_sources("does_not_exist") == []

    def test_placeholders_expanded(self, monkeypatch):
        monkeypatch.setenv("TWITTER_BEARER_TOKEN", "live-token-123")
        sources = load_sources("twitter")
        # The literal "${TWITTER_BEARER_TOKEN}" must no longer be present.
        tokens = [s.get("bearer_token") for s in sources if "bearer_token" in s]
        assert tokens, "expected a twitter source with a bearer_token"
        assert all("${" not in str(t) for t in tokens)
        assert "live-token-123" in tokens


class TestLoadAgentPrompt:
    def test_all_agents_have_a_prompt(self):
        for module in ALL_AGENT_MODULES:
            prompt = load_agent_prompt(module)
            assert prompt, f"missing AGENT_CONTEXT_PROMPT for {module}"
            assert isinstance(prompt, str)

    def test_missing_prompt_module_returns_none(self):
        assert load_agent_prompt("ai_junkie_updates.core.claude_client") is None


class TestLoadWatchlist:
    def test_returns_flat_term_list(self):
        terms = load_watchlist()
        assert isinstance(terms, list)
        assert "OpenAI" in terms     # companies section
        assert "AGI" in terms        # topics section
