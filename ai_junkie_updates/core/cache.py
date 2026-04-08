"""In-memory TTL cache for fast deduplication and short-lived lookups."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from ai_junkie_updates.settings import settings


class TTLCache:
    """Thread-safe in-memory cache with per-key TTL expiry."""

    def __init__(self, default_ttl: Optional[int] = None) -> None:
        self._default_ttl: int = default_ttl or settings.CACHE_TTL_SECONDS
        # Stores (value, expiry_timestamp)
        self._store: Dict[str, Tuple[Any, float]] = {}

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store a value with an optional per-key TTL override."""
        self._cleanup()
        expiry = time.monotonic() + (ttl if ttl is not None else self._default_ttl)
        self._store[key] = (value, expiry)

    def get(self, key: str) -> Optional[Any]:
        """Return stored value or None if missing / expired."""
        self._cleanup()
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expiry = entry
        if time.monotonic() > expiry:
            del self._store[key]
            return None
        return value

    def exists(self, key: str) -> bool:
        """Return True if the key is present and not expired."""
        return self.get(key) is not None

    def delete(self, key: str) -> None:
        """Remove a key from the cache."""
        self._store.pop(key, None)

    def cleanup(self) -> None:
        """Public alias — remove all expired entries."""
        self._cleanup()

    def _cleanup(self) -> None:
        """Remove all expired entries (called lazily on set/get)."""
        now = time.monotonic()
        expired_keys = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired_keys:
            del self._store[k]


cache = TTLCache()
