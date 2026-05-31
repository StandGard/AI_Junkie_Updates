"""Offline pipeline test — runnable without network access.

This sandbox's network policy blocks all outbound hosts except the package
registry, and no API credentials are configured, so the live path
(collect -> Claude -> Telegram) cannot run here. This test instead exercises
the entire *in-process* pipeline against the real classes, mocking only the two
external boundaries:

  * Claude analysis  -> we construct the UpdateItem that ``analyze()`` would return
  * Telegram send    -> ``telegram_bot.send`` is monkeypatched to record calls

Everything else is real: Normalizer, Deduplicator (real SQLite + cache),
FilterEngine, Formatter, and Router (real batching + DB persistence).

Run directly (no pytest required):

    python tests/test_pipeline_offline.py

Exits non-zero if any check fails.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import tempfile

# Ensure the repo root is importable when run as `python tests/...`.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# A throwaway SQLite file must be configured BEFORE importing the package: the
# db/settings singletons read this at import time.
_TMP_DB = pathlib.Path(tempfile.gettempdir()) / "aiju_pipeline_test.db"
if _TMP_DB.exists():
    _TMP_DB.unlink()
os.environ["AIJU_DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP_DB}"

from datetime import datetime, timezone  # noqa: E402

from ai_junkie_updates.constants import (  # noqa: E402
    DeliveryChannel,
    PipelineStatus,
    SourceType,
    UpdateCategory,
    UrgencyLevel,
)
from ai_junkie_updates.core.database import db  # noqa: E402
from ai_junkie_updates.core.models import RawItem, UpdateItem  # noqa: E402
from ai_junkie_updates.delivery.formatter import Formatter  # noqa: E402
from ai_junkie_updates.pipeline import router as router_mod  # noqa: E402
from ai_junkie_updates.pipeline.deduplicator import Deduplicator  # noqa: E402
from ai_junkie_updates.pipeline.filter_engine import FilterEngine  # noqa: E402
from ai_junkie_updates.pipeline.normalizer import Normalizer  # noqa: E402

_results: list[tuple[str, bool]] = []


def _check(name: str, ok: bool) -> None:
    _results.append((name, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")


def _make_update(score: int, **overrides) -> UpdateItem:
    """Build an UpdateItem like the one Claude analysis would produce."""
    base = dict(
        id=overrides.pop("id", f"item-{score}"),
        source_type=SourceType.RSS,
        source_name="TechCrunch AI",
        source_url="https://example.com/openai-launches-gpt-5",
        is_relevant=True,
        category=UpdateCategory.MODEL_RELEASE,
        urgency=UrgencyLevel.HIGH,
        score=score,
        headline="OpenAI launches GPT-5",
        summary="OpenAI released GPT-5, a major new flagship model.",
        reasoning="Major release.",
        tags=["OpenAI", "GPT-5"],
        collected_at=datetime.now(timezone.utc),
    )
    base.update(overrides)
    return UpdateItem(**base)


async def _run() -> None:
    await db.init_db()

    norm = Normalizer()
    dedup = Deduplicator()
    filt = FilterEngine()
    fmt = Formatter()

    # --- 1. Normalizer: strips HTML and collapses whitespace -----------------
    raw = RawItem(
        source_type=SourceType.RSS,
        source_name="TechCrunch AI",
        source_url="https://example.com/openai-launches-gpt-5",
        raw_content="<p>OpenAI launches <b>GPT-5</b></p>\n\n   Big   new   model.   ",
        metadata={"entry_id": "abc123"},
    )
    n = norm.normalize(raw)
    _check("normalize strips HTML + collapses whitespace",
           "GPT-5" in n.raw_content and "<b>" not in n.raw_content and "   " not in n.raw_content)

    # --- 2. Deduplicator: real fingerprint + SQLite/cache roundtrip ----------
    first = await dedup.is_duplicate(n)
    second = await dedup.is_duplicate(n)
    _check("dedup: first occurrence is new", first is False)
    _check("dedup: fingerprint is set on item", bool(n.fingerprint))
    _check("dedup: identical repeat flagged duplicate", second is True)

    # --- 3. FilterEngine.should_deliver across every tier boundary -----------
    wl = ["gpt-5"]
    _check("filter 95 -> CRITICAL_ALERTS",
           filt.should_deliver(_make_update(95), wl) == (True, DeliveryChannel.CRITICAL_ALERTS))
    _check("filter 75 -> HIGH_PRIORITY",
           filt.should_deliver(_make_update(75), wl) == (True, DeliveryChannel.HIGH_PRIORITY))
    _check("filter 55 -> GENERAL",
           filt.should_deliver(_make_update(55), wl) == (True, DeliveryChannel.GENERAL))
    _check("filter 30 -> dropped",
           filt.should_deliver(_make_update(30), wl) == (False, DeliveryChannel.DROPPED))
    _check("filter 45 + watchlist tag -> WATCHLIST",
           filt.should_deliver(_make_update(45), wl) == (True, DeliveryChannel.WATCHLIST))
    _check("filter 45 + no watchlist match -> dropped",
           filt.should_deliver(_make_update(45, tags=["misc"], source_name="Blog"), wl)
           == (False, DeliveryChannel.DROPPED))
    _check("filter is_relevant=False -> dropped",
           filt.should_deliver(_make_update(95, is_relevant=False), wl)
           == (False, DeliveryChannel.DROPPED))

    # --- 4. Formatter renders a Telegram HTML message ------------------------
    msg = fmt.format_message(_make_update(95))
    _check("formatter renders headline + bold + link + score",
           "GPT-5" in msg and "<b>" in msg and "Read more" in msg and "Score: 95" in msg)

    # --- 5. Router: instant vs batched, with Telegram mocked + real DB -------
    sent: list[str] = []

    async def fake_send(item: UpdateItem) -> None:
        sent.append(item.id)

    router_mod.telegram_bot.send = fake_send  # patch the singleton's method
    router = router_mod.Router()

    crit = _make_update(95, id="crit-1", delivery_channel=DeliveryChannel.CRITICAL_ALERTS)
    await router.route(crit)
    saved = await db.get_item("crit-1")
    _check("router CRITICAL sends immediately", sent == ["crit-1"])
    _check("router CRITICAL persists DELIVERED status",
           saved is not None and saved.pipeline_status == PipelineStatus.DELIVERED)

    gen = _make_update(55, id="gen-1", delivery_channel=DeliveryChannel.GENERAL)
    await router.route(gen)
    _check("router GENERAL queues without sending",
           sent == ["crit-1"] and len(router._general_queue) == 1)
    await router._flush_general()
    _check("router flush drains GENERAL queue and sends",
           sent == ["crit-1", "gen-1"] and len(router._general_queue) == 0)

    drop = _make_update(10, id="drop-1", is_relevant=False,
                        delivery_channel=DeliveryChannel.DROPPED)
    await router.route(drop)
    saved_drop = await db.get_item("drop-1")
    _check("router DROPPED persists without sending",
           sent == ["crit-1", "gen-1"]
           and saved_drop is not None
           and saved_drop.pipeline_status == PipelineStatus.DROPPED)

    await db.close()


def main() -> int:
    asyncio.run(_run())
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n=== OFFLINE PIPELINE: {passed}/{total} checks passed ===")
    if _TMP_DB.exists():
        _TMP_DB.unlink()
    if passed != total:
        for name, ok in _results:
            if not ok:
                print("  FAILED:", name)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
