"""Async database manager using SQLAlchemy async engine."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ai_junkie_updates.constants import DeliveryChannel, PipelineStatus
from ai_junkie_updates.core.models import Base, SeenFingerprint, UpdateItem, UpdateRecord
from ai_junkie_updates.core import kb_models  # noqa: F401  (registers KB tables on Base.metadata)
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

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Expose the session factory for data-access layers (e.g. KnowledgeBase)."""
        return self._session_factory

    async def init_db(self) -> None:
        """Create all tables if they do not exist."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        log.info("database_initialized", url=self._url)

    async def ensure_kb_schema(self) -> None:
        """Idempotently add intelligence-layer columns to the existing `updates`
        table. ``create_all`` creates new tables but never alters existing ones,
        so pre-existing databases need these columns added explicitly.
        """
        def _add_missing_columns(sync_conn) -> list:
            from sqlalchemy import inspect as sa_inspect

            existing = {c["name"] for c in sa_inspect(sync_conn).get_columns("updates")}
            added = []
            if "event_id" not in existing:
                sync_conn.exec_driver_sql("ALTER TABLE updates ADD COLUMN event_id VARCHAR")
                added.append("event_id")
            if "entity_ids" not in existing:
                sync_conn.exec_driver_sql("ALTER TABLE updates ADD COLUMN entity_ids TEXT")
                added.append("entity_ids")
            return added

        async with self._engine.begin() as conn:
            added = await conn.run_sync(_add_missing_columns)
        if added:
            log.info("updates_columns_added", columns=added)

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

    async def get_unlinked_items(self, hours: int = 48, limit: int = 200) -> list[dict]:
        """Return recent items not yet entity-linked (``entity_ids IS NULL``).

        Returns lightweight dicts (not ORM rows) so callers can work outside the
        session. Items are returned regardless of relevance and marked once via
        ``set_item_entities`` so they are never re-scanned.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        async with self._session_factory() as session:
            stmt = (
                select(UpdateRecord)
                .where(
                    UpdateRecord.entity_ids.is_(None),
                    UpdateRecord.analyzed_at >= cutoff,
                )
                .order_by(UpdateRecord.analyzed_at.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [
                {
                    "id": r.id,
                    "source_name": r.source_name,
                    "source_type": r.source_type,
                    "headline": r.headline,
                    "summary": r.summary,
                    "tags": r.tags.split(",") if r.tags else [],
                    "category": r.category,
                    "score": r.score,
                    "is_relevant": r.is_relevant,
                    "analyzed_at": r.analyzed_at,
                }
                for r in rows
            ]

    async def set_item_entities(self, item_id: str, entity_ids_json: str) -> None:
        """Persist the JSON-encoded entity-link result onto an update row."""
        async with self._session_factory() as session:
            rec = await session.get(UpdateRecord, item_id)
            if rec is not None:
                rec.entity_ids = entity_ids_json
                await session.commit()

    async def get_linked_items(
        self, hours: int = 48, limit: int = 500, eventless_only: bool = False
    ) -> list[dict]:
        """Return recent entity-linked items, with ``entity_ids`` parsed from JSON.

        Used by clustering. When ``eventless_only`` is True, only items not yet
        assigned to an event (``event_id IS NULL``) are returned.
        """
        import json as _json

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        async with self._session_factory() as session:
            stmt = select(UpdateRecord).where(
                UpdateRecord.entity_ids.is_not(None),
                UpdateRecord.analyzed_at >= cutoff,
            )
            if eventless_only:
                stmt = stmt.where(UpdateRecord.event_id.is_(None))
            stmt = stmt.order_by(UpdateRecord.analyzed_at.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            out = []
            for r in rows:
                try:
                    entities = _json.loads(r.entity_ids) if r.entity_ids else {}
                except (ValueError, TypeError):
                    entities = {}
                out.append(
                    {
                        "id": r.id,
                        "source_name": r.source_name,
                        "headline": r.headline,
                        "summary": r.summary,
                        "tags": r.tags.split(",") if r.tags else [],
                        "category": r.category,
                        "score": r.score,
                        "is_relevant": r.is_relevant,
                        "analyzed_at": r.analyzed_at,
                        "entities": entities,
                    }
                )
            return out

    async def set_item_event(self, item_id: str, event_id: str) -> None:
        """Link an update row to a clustered event."""
        async with self._session_factory() as session:
            rec = await session.get(UpdateRecord, item_id)
            if rec is not None:
                rec.event_id = event_id
                await session.commit()

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
