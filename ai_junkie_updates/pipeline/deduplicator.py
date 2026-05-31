"""Deduplicator — prevents the same content from being processed twice."""

from __future__ import annotations

from ai_junkie_updates.core.cache import cache
from ai_junkie_updates.core.database import db
from ai_junkie_updates.core.models import RawItem
from ai_junkie_updates.utils.fingerprint import generate_fingerprint
from ai_junkie_updates.utils.logger import get_logger

log = get_logger(__name__)

FINGERPRINT_TTL = 86400  # 24 hours


class Deduplicator:
    """Check for duplicate content using xxhash fingerprints."""

    async def is_duplicate(self, raw_item: RawItem) -> bool:
        """Return True if this content has been seen before.

        Sets raw_item.fingerprint as a side effect.
        """
        fp = generate_fingerprint(raw_item.raw_content)
        raw_item.fingerprint = fp

        # Fast path: in-memory cache
        cache_key = f"fp:{fp}"
        if cache.exists(cache_key):
            log.debug("duplicate_found_cache", fingerprint=fp, item_id=raw_item.id)
            return True

        # Slow path: database. Check both the delivered/dropped records and the
        # persistent seen-set, which survives restarts so feed re-emissions are
        # never re-analyzed by Claude.
        if await db.fingerprint_exists(fp) or await db.seen_fingerprint_exists(fp):
            cache.set(cache_key, True, ttl=FINGERPRINT_TTL)
            log.debug("duplicate_found_db", fingerprint=fp, item_id=raw_item.id)
            return True

        # First sighting — record it persistently and cache it.
        await db.mark_fingerprint_seen(fp)
        cache.set(cache_key, True, ttl=FINGERPRINT_TTL)
        return False
