"""Phase 0 guardrails: settings, claude_client wiring, dedup, pre-LLM gate."""

from __future__ import annotations

import json

import pytest

from ai_junkie_updates.constants import POLL_INTERVALS, SourceType
from ai_junkie_updates.core.models import RawItem
from ai_junkie_updates.pipeline.deduplicator import Deduplicator
from ai_junkie_updates.pipeline.filter_engine import FilterEngine
from ai_junkie_updates.settings import settings


def test_model_tiering_settings():
    assert settings.CLAUDE_TRIAGE_MODEL
    assert settings.CLAUDE_SYNTHESIS_MODEL
    assert settings.CLAUDE_TRIAGE_MODEL != settings.CLAUDE_SYNTHESIS_MODEL
    assert hasattr(settings, "TELEGRAM_ADMIN_CHAT_ID")


def test_per_source_poll_intervals():
    assert POLL_INTERVALS["rss"] >= 600
    assert POLL_INTERVALS["api_feed"] >= POLL_INTERVALS["rss"]


def test_pre_llm_gate():
    fe = FilterEngine()
    ai = RawItem(source_type=SourceType.RSS, source_name="rss",
                 raw_content="Anthropic released a new Claude model with better reasoning.")
    noise = RawItem(source_type=SourceType.REDDIT, source_name="r/x",
                    raw_content="My cat knocked a cup off the table this morning.")
    tiny = RawItem(source_type=SourceType.RSS, source_name="rss", raw_content="hi")
    assert fe.passes_pre_llm_gate(ai) is True
    assert fe.passes_pre_llm_gate(noise) is False
    assert fe.passes_pre_llm_gate(tiny) is False


@pytest.mark.asyncio
async def test_claude_client_caching_and_context(monkeypatch):
    """analyze() must send a cached SYSTEM_PROMPT block + appended context, on the triage model."""
    from ai_junkie_updates.core import claude_client as cc_mod

    captured = {}

    class FakeMsgs:
        async def create(self, **kw):
            captured.update(kw)
            payload = {"is_relevant": True, "category": "MODEL_RELEASE", "urgency": "HIGH",
                       "score": 80, "headline": "h", "summary": "s", "reasoning": "r",
                       "tags": ["openai"]}
            return type("R", (), {"content": [type("C", (), {"text": json.dumps(payload)})()]})()

    cc_mod.claude_client._client = type("FC", (), {"messages": FakeMsgs()})()

    item = RawItem(source_type=SourceType.RSS, source_name="rss",
                   raw_content="OpenAI released a new GPT model today.")
    result = await cc_mod.claude_client.analyze(item, context_prompt="RSS-CONTEXT-XYZ")

    sys = captured["system"]
    assert isinstance(sys, list)
    assert sys[0]["cache_control"]["type"] == "ephemeral"
    assert "AI Junkie Updates" in sys[0]["text"]
    assert any(b.get("text") == "RSS-CONTEXT-XYZ" for b in sys[1:])
    assert captured["model"] == settings.CLAUDE_TRIAGE_MODEL
    assert result.score == 80 and result.is_relevant


@pytest.mark.asyncio
async def test_restart_safe_dedup(database):
    """A re-emitted item is recognised as a duplicate even after a 'restart'."""
    from ai_junkie_updates.core.cache import cache

    content = "A unique AI announcement about Claude models."
    first = await Deduplicator().is_duplicate(
        RawItem(source_type=SourceType.RSS, source_name="rss", raw_content=content)
    )
    assert first is False

    # Simulate restart: wipe the in-memory cache, fresh deduplicator instance.
    cache._store.clear()
    second = await Deduplicator().is_duplicate(
        RawItem(source_type=SourceType.RSS, source_name="rss", raw_content=content)
    )
    assert second is True  # persistent seen-set survives the restart
