"""Shared fixtures and helpers for the test suite.

Required env vars are set before any ``ai_junkie_updates`` module is imported,
so ``Settings`` construction (and its lazy singletons) never trips the
validate_required hard-exit during collection.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

# Set required env BEFORE importing the package so Settings() is satisfied.
os.environ.setdefault("AIJU_ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("AIJU_TELEGRAM_BOT_TOKEN", "test-telegram-token")

from ai_junkie_updates.constants import (  # noqa: E402
    DeliveryChannel,
    PipelineStatus,
    SourceType,
    UpdateCategory,
    UrgencyLevel,
)
from ai_junkie_updates.core.models import RawItem, UpdateItem  # noqa: E402


def make_raw_item(
    *,
    source_type: SourceType = SourceType.RSS,
    source_name: str = "rss/test",
    source_url: str = "https://example.com/post",
    raw_content: str = "Some raw content",
    metadata: dict | None = None,
) -> RawItem:
    """Build a RawItem with sensible defaults for tests."""
    return RawItem(
        source_type=source_type,
        source_name=source_name,
        source_url=source_url,
        raw_content=raw_content,
        metadata=metadata or {},
    )


def make_update_item(
    *,
    score: int = 80,
    is_relevant: bool = True,
    category: UpdateCategory = UpdateCategory.MODEL_RELEASE,
    urgency: UrgencyLevel = UrgencyLevel.HIGH,
    source_name: str = "rss/test",
    tags: list[str] | None = None,
    headline: str = "Test headline",
    summary: str = "Test summary.",
    reasoning: str = "Because.",
) -> UpdateItem:
    """Build an UpdateItem with sensible defaults for tests."""
    return UpdateItem(
        id="test-id",
        source_type=SourceType.RSS,
        source_name=source_name,
        source_url="https://example.com/post",
        is_relevant=is_relevant,
        category=category,
        urgency=urgency,
        score=score,
        headline=headline,
        summary=summary,
        reasoning=reasoning,
        tags=tags if tags is not None else ["test"],
        collected_at=datetime.now(timezone.utc),
        pipeline_status=PipelineStatus.ANALYZED,
    )


@pytest.fixture
def raw_item() -> RawItem:
    return make_raw_item()


@pytest.fixture
def update_item() -> UpdateItem:
    return make_update_item()
