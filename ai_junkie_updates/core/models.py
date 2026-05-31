"""Pydantic models and SQLAlchemy ORM model for the update pipeline."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase

from ai_junkie_updates.constants import (
    DeliveryChannel,
    PipelineStatus,
    SourceType,
    UpdateCategory,
    UrgencyLevel,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid4() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class RawItem(BaseModel):
    """Raw content collected by an agent before analysis."""

    id: str = Field(default_factory=_uuid4)
    source_type: SourceType
    source_name: str
    source_url: Optional[str] = None
    raw_content: str
    collected_at: datetime = Field(default_factory=_utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    fingerprint: Optional[str] = None


class UpdateItem(BaseModel):
    """Structured update produced by Claude analysis."""

    id: str
    source_type: SourceType
    source_name: str
    source_url: Optional[str] = None
    is_relevant: bool
    category: UpdateCategory
    urgency: UrgencyLevel
    score: int = Field(ge=0, le=100)
    headline: str
    summary: str
    reasoning: str
    tags: List[str] = Field(default_factory=list)
    collected_at: datetime
    analyzed_at: datetime = Field(default_factory=_utcnow)
    pipeline_status: PipelineStatus = PipelineStatus.ANALYZED
    delivery_channel: Optional[DeliveryChannel] = None
    delivered_at: Optional[datetime] = None
    fingerprint: Optional[str] = None


# ---------------------------------------------------------------------------
# SQLAlchemy ORM model
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


class UpdateRecord(Base):
    """Persistent record mapping UpdateItem to the 'updates' table."""

    __tablename__ = "updates"

    id = Column(String, primary_key=True)
    source_type = Column(String, nullable=False)
    source_name = Column(String, nullable=False)
    source_url = Column(String, nullable=True)
    is_relevant = Column(Boolean, nullable=False, default=False)
    category = Column(String, nullable=False)
    urgency = Column(String, nullable=False)
    score = Column(Integer, nullable=False, default=0)
    headline = Column(Text, nullable=False, default="")
    summary = Column(Text, nullable=False, default="")
    reasoning = Column(Text, nullable=False, default="")
    tags = Column(Text, nullable=False, default="")  # stored as comma-separated
    collected_at = Column(DateTime, nullable=False)
    analyzed_at = Column(DateTime, nullable=False)
    pipeline_status = Column(String, nullable=False, default=PipelineStatus.ANALYZED.value)
    delivery_channel = Column(String, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    fingerprint = Column(String, nullable=True, index=True)
    # Intelligence-layer links (populated by entity_linker / clustering).
    event_id = Column(String, nullable=True, index=True)
    entity_ids = Column(Text, nullable=True)  # JSON-encoded list of entity slugs

    def to_update_item(self) -> UpdateItem:
        """Convert ORM record back to an UpdateItem."""
        return UpdateItem(
            id=self.id,
            source_type=SourceType(self.source_type),
            source_name=self.source_name,
            source_url=self.source_url,
            is_relevant=self.is_relevant,
            category=UpdateCategory(self.category),
            urgency=UrgencyLevel(self.urgency),
            score=self.score,
            headline=self.headline,
            summary=self.summary,
            reasoning=self.reasoning,
            tags=self.tags.split(",") if self.tags else [],
            collected_at=self.collected_at,
            analyzed_at=self.analyzed_at,
            pipeline_status=PipelineStatus(self.pipeline_status),
            delivery_channel=DeliveryChannel(self.delivery_channel) if self.delivery_channel else None,
            delivered_at=self.delivered_at,
            fingerprint=self.fingerprint,
        )

    @classmethod
    def from_update_item(cls, item: UpdateItem) -> "UpdateRecord":
        """Create an ORM record from an UpdateItem."""
        return cls(
            id=item.id,
            source_type=item.source_type.value,
            source_name=item.source_name,
            source_url=item.source_url,
            is_relevant=item.is_relevant,
            category=item.category.value,
            urgency=item.urgency.value,
            score=item.score,
            headline=item.headline,
            summary=item.summary,
            reasoning=item.reasoning,
            tags=",".join(item.tags),
            collected_at=item.collected_at,
            analyzed_at=item.analyzed_at,
            pipeline_status=item.pipeline_status.value,
            delivery_channel=item.delivery_channel.value if item.delivery_channel else None,
            delivered_at=item.delivered_at,
            fingerprint=item.fingerprint,
        )


class SeenFingerprint(Base):
    """Persistent record that a content fingerprint has been seen.

    Written at first sighting (before analysis) so that feed re-emissions after a
    process restart are recognised as duplicates and never re-sent to Claude. The
    in-memory cache is wiped on restart; this table survives it.
    """

    __tablename__ = "seen_fingerprints"

    fingerprint = Column(String, primary_key=True)
    seen_at = Column(DateTime, nullable=False, default=_utcnow)
