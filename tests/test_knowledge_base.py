"""Knowledge-base schema, DAO upserts/queries, and the entity seed."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_schema_tables_created(database):
    from sqlalchemy import inspect as sa_inspect

    expected = {"companies", "models", "model_prices", "benchmarks", "benchmark_scores",
                "capabilities", "events", "tools", "leaderboards", "updates", "seen_fingerprints"}
    async with database._engine.begin() as conn:
        tables = set(await conn.run_sync(lambda c: sa_inspect(c).get_table_names()))
        cols = await conn.run_sync(lambda c: {x["name"] for x in sa_inspect(c).get_columns("updates")})
    assert expected.issubset(tables)
    assert {"event_id", "entity_ids"}.issubset(cols)


@pytest.mark.asyncio
async def test_seed_counts_and_idempotency(kb):
    counts = await kb.seed_from_yaml()
    assert counts["companies"] == 14
    assert counts["models"] == 12
    assert counts["tools"] == 8
    assert counts["benchmarks"] == 6
    # Re-seed must not duplicate.
    await kb.seed_from_yaml()
    assert len(await kb.list_companies()) == 14
    assert len(await kb.list_models()) == 12


@pytest.mark.asyncio
async def test_alias_lookups(seeded_kb):
    assert (await seeded_kb.find_company_by_alias("Claude Code")).id == "anthropic"
    assert (await seeded_kb.find_company_by_alias("ChatGPT")).id == "openai"
    # "Claude Design" is an Anthropic capability alias, not a separate product.
    assert (await seeded_kb.find_company_by_alias("Claude Design")).id == "anthropic"
    assert (await seeded_kb.find_model_by_alias("opus 4.8")).id == "claude-opus-4-8"
    assert await seeded_kb.find_company_by_alias("nonsense-xyz") is None


@pytest.mark.asyncio
async def test_price_history_latest(seeded_kb):
    await seeded_kb.add_price(model_id="claude-opus-4-8", input_per_mtok=5.0, output_per_mtok=25.0)
    await seeded_kb.add_price(model_id="claude-opus-4-8", input_per_mtok=4.0, output_per_mtok=20.0)
    latest = await seeded_kb.latest_price("claude-opus-4-8")
    assert latest.input_per_mtok == 4.0


@pytest.mark.asyncio
async def test_latest_scores_per_model(seeded_kb):
    await seeded_kb.add_score(model_id="claude-opus-4-8", benchmark_id="swe-bench-verified", score=70.0)
    await seeded_kb.add_score(model_id="gpt-5", benchmark_id="swe-bench-verified", score=68.0)
    await seeded_kb.add_score(model_id="claude-opus-4-8", benchmark_id="swe-bench-verified", score=74.5)
    latest = await seeded_kb.latest_scores_for_benchmark("swe-bench-verified")
    assert set(latest) == {"claude-opus-4-8", "gpt-5"}
    assert latest["claude-opus-4-8"].score == 74.5


@pytest.mark.asyncio
async def test_tools_for_use_case(seeded_kb):
    coding = {t.id for t in await seeded_kb.tools_for_use_case("coding")}
    assert {"claude-code", "cursor", "github-copilot"} <= coding
    video = {t.id for t in await seeded_kb.tools_for_use_case("video")}
    assert "runway" in video


@pytest.mark.asyncio
async def test_events_and_briefed_flag(seeded_kb):
    eid = await seeded_kb.create_event(
        title="GPT-5 launched", event_type="MODEL_RELEASE",
        entity_ids=["openai"], model_ids=["gpt-5"], item_ids=["u1"], significance_score=88,
    )
    assert (await seeded_kb.get_event(eid)).significance_score == 88
    unbriefed = await seeded_kb.unbriefed_events(min_significance=80)
    assert any(e.id == eid for e in unbriefed)
    await seeded_kb.mark_events_briefed([eid])
    assert all(e.id != eid for e in await seeded_kb.unbriefed_events(min_significance=80))


@pytest.mark.asyncio
async def test_schema_upgrade_adds_columns():
    """ensure_kb_schema() adds event_id/entity_ids to a pre-existing updates table."""
    import sqlite3
    import tempfile

    from sqlalchemy import inspect as sa_inspect
    from ai_junkie_updates.core.database import DatabaseManager

    path = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    raw = sqlite3.connect(path)
    raw.execute("CREATE TABLE updates (id TEXT PRIMARY KEY, headline TEXT, fingerprint TEXT)")
    raw.commit()
    raw.close()

    db = DatabaseManager(url=f"sqlite+aiosqlite:///{path}")
    await db.init_db()
    async with db._engine.begin() as conn:
        before = await conn.run_sync(lambda c: {x["name"] for x in sa_inspect(c).get_columns("updates")})
    assert not {"event_id", "entity_ids"} & before
    await db.ensure_kb_schema()
    await db.ensure_kb_schema()  # idempotent re-run
    async with db._engine.begin() as conn:
        after = await conn.run_sync(lambda c: {x["name"] for x in sa_inspect(c).get_columns("updates")})
    assert {"event_id", "entity_ids"}.issubset(after)
    await db.close()
