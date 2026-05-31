"""Async database manager using SQLAlchemy async engine."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ai_junkie_updates.constants import DeliveryChannel, PipelineStatus
from ai_junkie_updates.core.models import Base, SeenFingerprint, UpdateItem, UpdateRecord
from ai_junkie_updates.settings import settings
from ai_junkie_updates.utils.logger import get_logger

log = get_logger(__name__)


class DatabaseManager:
    """Async database manager wrapping SQLAlchemy async engine."""

    def __init__(self, url: Optional[str] = None) -> None:
        self._url = url or settings.DATABASE_URL
        self._engine = create_async_engine(self._url, echo=False)
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

    async def init_db(self) -> None:
        """Create all tables if they do not exist."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        log.info("database_initialized", url=self._url)

    async def save_item(self, item: UpdateItem) -> None:
        """Insert or update an UpdateItem record."""
        async with self._session_factory() as session:
            existing = await session.get(UpdateRecord, item.id)
            if existing:
                record = UpdateRecord.from_update_item(item)
                for col in UpdateRecord.__table__.columns:
                    if col.name != "id":
                        setattr(existing, col.name, getattr(record, col.name))
            else:
                session.add(UpdateRecord.from_update_item(item))
            await session.commit()

    async def update_status(
        self,
        item_id: str,
        status: PipelineStatus,
        delivery_channel: Optional[DeliveryChannel] = None,
        delivered_at: Optional[datetime] = None,
    ) -> None:
        """Update pipeline status and optionally delivery info."""
        async with self._session_factory() as session:
            record = await session.get(UpdateRecord, item_id)
            if record:
                record.pipeline_status = status.value
                if delivery_channel is not None:
                    record.delivery_channel = delivery_channel.value
                if delivered_at is not None:
                    record.delivered_at = delivered_at
                await session.commit()

    async def get_item(self, item_id: str) -> Optional[UpdateItem]:
        """Fetch a single item by ID."""
        async with self._session_factory() as session:
            record = await session.get(UpdateRecord, item_id)
            if record:
                return record.to_update_item()
            return None

    async def get_recent_items(
        self, hours: int = 24, limit: int = 100
    ) -> list[UpdateItem]:
        """Fetch recent items within the given time window."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        async with self._session_factory() as session:
            stmt = (
                select(UpdateRecord)
                .where(UpdateRecord.collected_at >= cutoff)
                .order_by(UpdateRecord.collected_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [row.to_update_item() for row in result.scalars().all()]

    async def fingerprint_exists(self, fingerprint: str) -> bool:
        """Check whether a fingerprint already exists in the database."""
        async with self._session_factory() as session:
            stmt = select(UpdateRecord.id).where(
                UpdateRecord.fingerprint == fingerprint
            ).limit(1)
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    async def seen_fingerprint_exists(self, fingerprint: str) -> bool:
        """Check the persistent seen-set (survives restarts) for a fingerprint."""
        async with self._session_factory() as session:
            return await session.get(SeenFingerprint, fingerprint) is not None

    async def mark_fingerprint_seen(self, fingerprint: str) -> None:
        """Record a fingerprint in the persistent seen-set (idempotent, race-safe)."""
        async with self._session_factory() as session:
            if await session.get(SeenFingerprint, fingerprint) is not None:
                return
            session.add(SeenFingerprint(fingerprint=fingerprint))
            try:
                await session.commit()
            except Exception:
                # Another agent inserted the same fingerprint concurrently — fine.
                await session.rollback()

    async def close(self) -> None:
        """Dispose of the engine connection pool."""
        await self._engine.dispose()
        log.info("database_closed")


db = DatabaseManager()
