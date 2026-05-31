"""Intelligence job scheduling, retention, and source-config integrity."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

import pytest

from ai_junkie_updates.core.models import UpdateRecord
from ai_junkie_updates.intelligence.jobs import IntelligenceJobs


# --------------------------------------------------------- calendar scheduling
def test_seconds_until_daily():
    now = datetime(2026, 5, 31, 6, 0, 0, tzinfo=timezone.utc)
    # Next 08:00 today is 2h away.
    assert IntelligenceJobs.seconds_until(8, now=now) == 2 * 3600
    # If we're past 08:00, it rolls to tomorrow.
    now2 = datetime(2026, 5, 31, 9, 0, 0, tzinfo=timezone.utc)
    assert IntelligenceJobs.seconds_until(8, now=now2) == 23 * 3600


def test_seconds_until_weekly():
    # 2026-05-31 is a Sunday (weekday 6). Next Monday (0) 08:00 is ~1 day + 8h.
    now = datetime(2026, 5, 31, 0, 0, 0, tzinfo=timezone.utc)
    secs = IntelligenceJobs.seconds_until(8, weekday=0, now=now)
    assert secs == (24 + 8) * 3600


# ------------------------------------------------------------------ retention
@pytest.mark.asyncio
async def test_retention_prunes_only_eventlinked_old_items(database):
    now = datetime.now(timezone.utc)

    def mk(age_days, event_id):
        return UpdateRecord(
            id=str(uuid.uuid4()), source_type="rss", source_name="rss",
            is_relevant=True, category="MODEL_RELEASE", urgency="LOW", score=10,
            headline="h", summary="s", reasoning="r", tags="",
            collected_at=now - timedelta(days=age_days),
            analyzed_at=now - timedelta(days=age_days),
            pipeline_status="ANALYZED", event_id=event_id,
        )

    async with database.session_factory() as s:
        s.add(mk(90, "evt-1"))   # old + clustered  -> pruned
        s.add(mk(90, None))      # old but unclustered -> kept
        s.add(mk(5, "evt-2"))    # recent + clustered -> kept
        await s.commit()

    deleted = await database.prune_old_items(days=60)
    assert deleted == 1

    from sqlalchemy import select, func
    async with database.session_factory() as s:
        remaining = (await s.execute(select(func.count()).select_from(UpdateRecord))).scalar_one()
    assert remaining == 2

    # Disabled when days <= 0.
    assert await database.prune_old_items(days=0) == 0


# ------------------------------------------------------------- config integrity
def test_new_source_types_exist():
    from ai_junkie_updates.constants import SourceType
    assert SourceType.YOUTUBE.value == "youtube"
    assert SourceType.BENCHMARK.value == "benchmark"


def test_sources_config_has_new_blocks():
    from ai_junkie_updates.agents.base_agent import load_sources
    assert len(load_sources("youtube")) >= 1
    assert len(load_sources("rss_bridge")) >= 1
    # status pages live under api_feed
    api = load_sources("api_feed")
    assert any("Status" in s.get("name", "") for s in api)


def test_rss_agent_merges_all_feed_blocks():
    """RSS agent consumes rss + youtube + rss_bridge sources.

    feedparser fails to import in some envs (sgmllib3k build issue, see CLAUDE.md),
    so verify the merge against the agent source via static inspection rather than
    instantiating the feedparser-dependent agent.
    """
    from pathlib import Path
    import ai_junkie_updates
    from ai_junkie_updates.agents.base_agent import load_sources

    # Read the agent source as text — importing it would pull in feedparser.
    agent_path = Path(ai_junkie_updates.__file__).parent / "agents" / "rss" / "agent.py"
    src = agent_path.read_text()
    for block in ("rss", "youtube", "rss_bridge"):
        assert f'load_sources("{block}")' in src
    # All three configured blocks are loadable.
    assert load_sources("youtube") and load_sources("rss_bridge")
