"""Tests for the async DatabaseManager against an in-memory SQLite database.

A single shared in-memory connection (StaticPool) is used so that separate
sessions observe the same database within a test.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from ai_junkie_updates.constants import DeliveryChannel, PipelineStatus
from ai_junkie_updates.core.database import DatabaseManager
from ai_junkie_updates.core.models import Base
from tests.conftest import make_update_item


@pytest_asyncio.fixture
async def db():
    """A DatabaseManager backed by a shared in-memory SQLite database."""
    manager = DatabaseManager.__new__(DatabaseManager)
    manager._url = "sqlite+aiosqlite://"
    manager._engine = create_async_engine(
        "sqlite+aiosqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    manager._session_factory = async_sessionmaker(manager._engine, expire_on_commit=False)
    async with manager._engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield manager
    await manager.close()


async def test_save_and_get_item(db):
    item = make_update_item(score=77, tags=["a", "b"])
    await db.save_item(item)

    fetched = await db.get_item(item.id)
    assert fetched is not None
    assert fetched.id == item.id
    assert fetched.score == 77
    assert fetched.tags == ["a", "b"]


async def test_get_missing_item_returns_none(db):
    assert await db.get_item("nope") is None


async def test_save_item_is_upsert(db):
    item = make_update_item(score=50)
    await db.save_item(item)

    item.score = 95
    item.headline = "Updated headline"
    await db.save_item(item)  # same id -> update, not duplicate insert

    fetched = await db.get_item(item.id)
    assert fetched.score == 95
    assert fetched.headline == "Updated headline"

    recent = await db.get_recent_items(hours=24, limit=100)
    assert len([r for r in recent if r.id == item.id]) == 1


async def test_fingerprint_exists(db):
    item = make_update_item()
    item.fingerprint = "deadbeefcafef00d"
    await db.save_item(item)

    assert await db.fingerprint_exists("deadbeefcafef00d") is True
    assert await db.fingerprint_exists("does-not-exist") is False


async def test_update_status(db):
    item = make_update_item()
    await db.save_item(item)

    delivered_at = datetime.now(timezone.utc)
    await db.update_status(
        item.id,
        PipelineStatus.DELIVERED,
        delivery_channel=DeliveryChannel.HIGH_PRIORITY,
        delivered_at=delivered_at,
    )

    fetched = await db.get_item(item.id)
    assert fetched.pipeline_status == PipelineStatus.DELIVERED
    assert fetched.delivery_channel == DeliveryChannel.HIGH_PRIORITY


async def test_get_recent_items_respects_window(db):
    recent = make_update_item()
    recent.id = "recent"
    recent.collected_at = datetime.now(timezone.utc)

    old = make_update_item()
    old.id = "old"
    old.collected_at = datetime.now(timezone.utc) - timedelta(hours=48)

    await db.save_item(recent)
    await db.save_item(old)

    within_24h = await db.get_recent_items(hours=24, limit=100)
    ids = {r.id for r in within_24h}
    assert "recent" in ids
    assert "old" not in ids
