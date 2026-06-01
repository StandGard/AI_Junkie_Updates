"""Tests for model conversion between UpdateItem and the ORM UpdateRecord."""

from __future__ import annotations

import pytest

from ai_junkie_updates.constants import (
    DeliveryChannel,
    PipelineStatus,
    SourceType,
    UpdateCategory,
    UrgencyLevel,
)
from ai_junkie_updates.core.models import UpdateRecord

from tests.conftest import make_update_item


def test_round_trip_preserves_fields():
    item = make_update_item(score=82, tags=["openai", "gpt-5"])
    item.delivery_channel = DeliveryChannel.HIGH_PRIORITY

    record = UpdateRecord.from_update_item(item)
    restored = record.to_update_item()

    assert restored.id == item.id
    assert restored.score == 82
    assert restored.source_type == SourceType.RSS
    assert restored.category == UpdateCategory.MODEL_RELEASE
    assert restored.urgency == UrgencyLevel.HIGH
    assert restored.tags == ["openai", "gpt-5"]
    assert restored.delivery_channel == DeliveryChannel.HIGH_PRIORITY
    assert restored.pipeline_status == PipelineStatus.ANALYZED


def test_empty_tags_round_trip():
    item = make_update_item(tags=[])
    record = UpdateRecord.from_update_item(item)
    assert record.tags == ""
    assert record.to_update_item().tags == []


def test_none_delivery_channel_round_trip():
    item = make_update_item()
    item.delivery_channel = None
    record = UpdateRecord.from_update_item(item)
    assert record.delivery_channel is None
    assert record.to_update_item().delivery_channel is None


def test_score_bounds_validation():
    # Pydantic constrains score to 0..100.
    with pytest.raises(Exception):
        make_update_item(score=150)
