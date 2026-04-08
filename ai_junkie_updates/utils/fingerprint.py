"""Content fingerprinting using xxhash for fast deduplication."""

from __future__ import annotations

import xxhash


def generate_fingerprint(content: str) -> str:
    """Return an xxh64 hex digest of the given content string."""
    return xxhash.xxh64(content.encode("utf-8")).hexdigest()
