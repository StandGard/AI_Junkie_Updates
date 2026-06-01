"""End-to-end pipeline test: RawItem -> normalize -> dedup -> (mocked Claude)
-> filter -> route -> (mocked Telegram) + real in-memory DB persistence.

Claude and Telegram are the only mocked boundaries; everything in between is
the real pipeline code running through BaseAgent._process_item.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from ai_junkie_updates.agents.base_agent import BaseAgent
from ai_junkie_updates.constants import (
    DeliveryChannel,
    PipelineStatus,
    SourceType,
    UpdateCategory,
    UrgencyLevel,
)
from ai_junkie_updates.core import claude_client as cc_mod
from ai_junkie_updates.core.database import DatabaseManager
from ai_junkie_updates.core.models import Base, RawItem, UpdateItem
from ai_junkie_updates.pipeline import deduplicator as dedup_mod
from ai_junkie_updates.pipeline import router as router_mod

from tests.conftest import make_raw_item


# --- a concrete, do-nothing agent we can feed items into directly ----------

class _TestAgent(BaseAgent):
    def __init__(self):
        super().__init__(SourceType.RSS, "rss/test", poll_interval_seconds=300)

    async def collect(self):  # pragma: no cover - not used directly
        return []


class _RecordingBot:
    """Stand-in for telegram_bot that records what it was asked to send."""

    def __init__(self):
        self.sent: list[UpdateItem] = []

    async def send(self, item: UpdateItem) -> None:
        self.sent.append(item)


def _fake_analyze(score: int, is_relevant: bool = True, tags=None):
    """Build a claude_client.analyze replacement returning a fixed verdict."""

    async def _analyze(raw_item: RawItem, context_prompt: str | None = None) -> UpdateItem:
        return UpdateItem(
            id=raw_item.id,
            source_type=raw_item.source_type,
            source_name=raw_item.source_name,
            source_url=raw_item.source_url,
            is_relevant=is_relevant,
            category=UpdateCategory.MODEL_RELEASE,
            urgency=UrgencyLevel.HIGH,
            score=score,
            headline="Headline",
            summary="Summary.",
            reasoning="Reason.",
            tags=tags if tags is not None else ["test"],
            collected_at=raw_item.collected_at,
            pipeline_status=PipelineStatus.ANALYZED,
            fingerprint=raw_item.fingerprint,
        )

    return _analyze


@pytest_asyncio.fixture
async def wired(monkeypatch):
    """Wire an in-memory DB + recording Telegram bot into the router singleton."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db = DatabaseManager.__new__(DatabaseManager)
    db._url = "sqlite+aiosqlite://"
    db._engine = engine
    db._session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    bot = _RecordingBot()

    # Both the router and the deduplicator hold their own module-level `db`
    # reference; patch both so the whole pipeline uses the in-memory DB.
    monkeypatch.setattr(router_mod, "db", db)
    monkeypatch.setattr(dedup_mod, "db", db)
    monkeypatch.setattr(router_mod, "telegram_bot", bot)

    # Reset the shared router singleton's queues for this test.
    router_mod.router._general_queue.clear()
    router_mod.router._watchlist_queue.clear()

    yield {"db": db, "bot": bot, "router": router_mod.router}

    await db.close()


async def test_high_score_item_delivered_and_persisted(wired, monkeypatch):
    monkeypatch.setattr(cc_mod.claude_client, "analyze", _fake_analyze(score=85))
    agent = _TestAgent()
    item = make_raw_item(raw_content="A high-impact model launch")

    await agent._process_item(item)

    bot = wired["bot"]
    assert len(bot.sent) == 1
    assert bot.sent[0].delivery_channel == DeliveryChannel.HIGH_PRIORITY

    stored = await wired["db"].get_item(item.id)
    assert stored is not None
    assert stored.pipeline_status == PipelineStatus.DELIVERED
    assert stored.delivered_at is not None


async def test_critical_score_routes_to_critical_channel(wired, monkeypatch):
    monkeypatch.setattr(cc_mod.claude_client, "analyze", _fake_analyze(score=97))
    agent = _TestAgent()
    await agent._process_item(make_raw_item(raw_content="Frontier model released"))

    assert wired["bot"].sent[0].delivery_channel == DeliveryChannel.CRITICAL_ALERTS


async def test_irrelevant_item_dropped_not_sent(wired, monkeypatch):
    monkeypatch.setattr(
        cc_mod.claude_client, "analyze", _fake_analyze(score=0, is_relevant=False)
    )
    agent = _TestAgent()
    item = make_raw_item(raw_content="off-topic chatter")

    await agent._process_item(item)

    assert wired["bot"].sent == []  # never delivered
    stored = await wired["db"].get_item(item.id)
    assert stored is not None
    assert stored.pipeline_status == PipelineStatus.DROPPED


async def test_general_item_is_batched_then_flushed(wired, monkeypatch):
    monkeypatch.setattr(cc_mod.claude_client, "analyze", _fake_analyze(score=55))
    agent = _TestAgent()
    await agent._process_item(make_raw_item(raw_content="A worth-knowing update"))

    router = wired["router"]
    bot = wired["bot"]
    # Below the batch-size threshold -> queued, not yet sent.
    assert len(router._general_queue) == 1
    assert bot.sent == []

    await router._flush_general()
    assert len(bot.sent) == 1
    assert bot.sent[0].delivery_channel == DeliveryChannel.GENERAL


async def test_duplicate_item_skips_claude_and_delivery(wired, monkeypatch):
    calls = {"n": 0}
    base = _fake_analyze(score=85)

    async def counting_analyze(raw_item, context_prompt=None):
        calls["n"] += 1
        return await base(raw_item, context_prompt)

    monkeypatch.setattr(cc_mod.claude_client, "analyze", counting_analyze)
    agent = _TestAgent()

    a = make_raw_item(raw_content="identical content")
    b = make_raw_item(raw_content="identical content")  # same fingerprint
    await agent._process_item(a)
    await agent._process_item(b)

    # Second item is a duplicate: Claude and Telegram are skipped for it.
    assert calls["n"] == 1
    assert len(wired["bot"].sent) == 1


async def test_watchlist_item_requires_match(wired, monkeypatch):
    # Score 45 is in the watchlist band (40-49); only delivered on a match.
    monkeypatch.setattr(
        cc_mod.claude_client, "analyze", _fake_analyze(score=45, tags=["openai"])
    )
    agent = _TestAgent()
    await agent._process_item(make_raw_item(raw_content="niche openai update"))

    router = wired["router"]
    # "openai" is on the default watchlist -> queued to the watchlist channel.
    assert len(router._watchlist_queue) == 1
    await router._flush_watchlist()
    assert wired["bot"].sent[0].delivery_channel == DeliveryChannel.WATCHLIST
