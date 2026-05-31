"""Health/readiness endpoint behaviour."""

from __future__ import annotations

import pytest

from ai_junkie_updates.health import HealthServer


class _FakeRequest:
    pass


@pytest.mark.asyncio
async def test_health_always_ok():
    resp = await HealthServer()._health(_FakeRequest())
    assert resp.status == 200
    assert b'"status": "ok"' in resp.body


@pytest.mark.asyncio
async def test_ready_reflects_kb_state(kb):
    """Not ready before seeding (no models); ready after."""
    server = HealthServer()
    not_ready = await server._ready(_FakeRequest())
    assert not_ready.status == 503

    await kb.seed_from_yaml()
    ready = await server._ready(_FakeRequest())
    assert ready.status == 200
    assert b'"ready": true' in ready.body
