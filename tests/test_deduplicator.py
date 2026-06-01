"""Tests for the Deduplicator pipeline stage (cache fast-path + DB fallback)."""

from __future__ import annotations

from ai_junkie_updates.pipeline import deduplicator as dedup_mod
from ai_junkie_updates.pipeline.deduplicator import Deduplicator

from tests.conftest import make_raw_item

# Cache isolation is handled by the autouse _isolate_cache fixture in conftest.


async def test_first_sighting_not_duplicate(monkeypatch):
    # DB reports nothing seen before.
    async def _no(_fp):
        return False

    monkeypatch.setattr(dedup_mod.db, "fingerprint_exists", _no)
    d = Deduplicator()
    item = make_raw_item(raw_content="unique content A")
    assert await d.is_duplicate(item) is False
    # fingerprint set as a side effect
    assert item.fingerprint is not None


async def test_second_sighting_hits_cache(monkeypatch):
    calls = {"n": 0}

    async def _count(_fp):
        calls["n"] += 1
        return False

    monkeypatch.setattr(dedup_mod.db, "fingerprint_exists", _count)
    d = Deduplicator()
    a = make_raw_item(raw_content="same content")
    b = make_raw_item(raw_content="same content")

    assert await d.is_duplicate(a) is False  # first: cached
    assert await d.is_duplicate(b) is True    # second: cache fast-path
    assert calls["n"] == 1  # DB consulted only once (fast-path on second)


async def test_db_fallback_detects_duplicate(monkeypatch):
    async def _yes(_fp):
        return True

    monkeypatch.setattr(dedup_mod.db, "fingerprint_exists", _yes)
    d = Deduplicator()
    item = make_raw_item(raw_content="seen in a previous run")
    assert await d.is_duplicate(item) is True


async def test_distinct_content_not_duplicate(monkeypatch):
    async def _no(_fp):
        return False

    monkeypatch.setattr(dedup_mod.db, "fingerprint_exists", _no)
    d = Deduplicator()
    a = make_raw_item(raw_content="content one")
    b = make_raw_item(raw_content="content two")
    assert await d.is_duplicate(a) is False
    assert await d.is_duplicate(b) is False
    assert a.fingerprint != b.fingerprint
