"""Tests for the in-memory TTL cache."""

from __future__ import annotations

import time

from ai_junkie_updates.core.cache import TTLCache


def test_set_and_get():
    c = TTLCache(default_ttl=60)
    c.set("k", "v")
    assert c.get("k") == "v"
    assert c.exists("k") is True


def test_missing_key_returns_none():
    c = TTLCache(default_ttl=60)
    assert c.get("nope") is None
    assert c.exists("nope") is False


def test_expiry(monkeypatch):
    c = TTLCache(default_ttl=60)
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    c.set("k", "v", ttl=10)
    assert c.exists("k") is True
    now[0] += 11  # advance past TTL
    assert c.get("k") is None
    assert c.exists("k") is False


def test_per_key_ttl_override(monkeypatch):
    c = TTLCache(default_ttl=5)
    now = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    c.set("short", "v")          # default ttl 5
    c.set("long", "v", ttl=100)
    now[0] += 6
    assert c.get("short") is None
    assert c.get("long") == "v"


def test_delete():
    c = TTLCache(default_ttl=60)
    c.set("k", "v")
    c.delete("k")
    assert c.exists("k") is False
    # deleting a missing key is a no-op
    c.delete("missing")


def test_cleanup_removes_expired(monkeypatch):
    c = TTLCache(default_ttl=5)
    now = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    c.set("a", 1)
    c.set("b", 2, ttl=100)
    now[0] += 6
    c.cleanup()
    assert c.exists("a") is False
    assert c.exists("b") is True
