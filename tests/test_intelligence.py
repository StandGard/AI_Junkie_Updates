"""Entity linking, clustering, ranking, and synthesis."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from ai_junkie_updates.core.models import UpdateRecord


def _mk(headline, tags="", summary="", score=80, cat="MODEL_RELEASE", age_h=0, source="rss",
        entity_ids=None):
    now = datetime.now(timezone.utc) - timedelta(hours=age_h)
    rec = UpdateRecord(
        id=str(uuid.uuid4()), source_type="rss", source_name=source,
        is_relevant=True, category=cat, urgency="HIGH", score=score,
        headline=headline, summary=summary, reasoning="r", tags=tags,
        collected_at=now, analyzed_at=now, pipeline_status="ANALYZED",
    )
    if entity_ids is not None:
        rec.entity_ids = json.dumps(entity_ids)
    return rec


async def _add(database, *recs):
    async with database.session_factory() as s:
        for r in recs:
            s.add(r)
        await s.commit()


# --------------------------------------------------------------- entity linker
@pytest.mark.asyncio
async def test_entity_linker(database, seeded_kb):
    from ai_junkie_updates.intelligence.entity_linker import EntityLinker

    await _add(
        database,
        _mk("OpenAI releases GPT-5 with better reasoning", tags="openai,gpt-5"),
        _mk("Anthropic ships Claude Code update", tags="anthropic,claude-code",
            summary="The Claude Code CLI gets subagents."),
        _mk("Google's Gemini 2 now supports video", tags="gemini"),
        _mk("My local HTML and ML tutorial roundup", tags="tutorial"),  # false-positive guard
        _mk("Cooking pasta on a Sunday afternoon", tags="food"),
    )

    summary = await EntityLinker(kb=seeded_kb).run_once()
    assert summary["scanned"] == 5
    assert summary["linked"] == 3  # the 3 AI items

    async def entities_for(substr):
        from sqlalchemy import select
        async with database.session_factory() as s:
            recs = (await s.execute(select(UpdateRecord))).scalars().all()
        for r in recs:
            if substr in r.headline:
                return json.loads(r.entity_ids) if r.entity_ids else None
        return None

    gpt = await entities_for("GPT-5")
    assert "openai" in gpt["companies"] and "gpt-5" in gpt["models"]  # model implies company
    cc = await entities_for("Claude Code")
    assert "claude-code" in cc["tools"] and "anthropic" in cc["companies"]
    html = await entities_for("HTML and ML")
    assert html == {"companies": [], "models": [], "tools": []}  # no short-alias false positive

    # Idempotent: re-run scans nothing.
    assert (await EntityLinker(kb=seeded_kb).run_once())["scanned"] == 0


# ------------------------------------------------------------------ clustering
@pytest.mark.asyncio
async def test_clustering_merges_and_separates(database, seeded_kb):
    from sqlalchemy import select
    from ai_junkie_updates.core import kb_models as kb
    from ai_junkie_updates.intelligence.clustering import Clusterer

    gpt5 = {"companies": ["openai"], "models": ["gpt-5"], "tools": []}
    await _add(
        database,
        _mk("OpenAI releases GPT-5 with major reasoning gains", "openai,gpt-5,release",
            score=92, entity_ids=gpt5),
        _mk("GPT-5 released by OpenAI, big reasoning improvements", "gpt-5,reasoning",
            score=85, age_h=2, source="r/MachineLearning", entity_ids=gpt5),
        _mk("OpenAI launches GPT-5 reasoning model", "openai,gpt-5", score=80, age_h=5,
            source="youtube", entity_ids=gpt5),
        _mk("OpenAI hires new policy chief in Europe", "openai,leadership,policy",
            score=55, cat="LEADERSHIP_CHANGE",
            entity_ids={"companies": ["openai"], "models": [], "tools": []}),
    )

    summary = await Clusterer().run_once(kb=seeded_kb)
    assert summary["items"] == 4
    assert summary["events"] == 2  # GPT-5 (3 merged) + leadership (separate)

    async with database.session_factory() as s:
        events = (await s.execute(select(kb.Event))).scalars().all()
    big = max(events, key=lambda e: len(e.item_ids))
    assert len(big.item_ids) == 3
    assert big.significance_score == 92
    assert any("policy chief" in e.title for e in events)  # not merged into GPT-5


# --------------------------------------------------------------- ranking engine
@pytest.mark.asyncio
async def test_ranking_engine(seeded_kb):
    from ai_junkie_updates.intelligence.ranking_engine import RankingEngine

    now = datetime.now(timezone.utc)
    await seeded_kb.upsert_model(id="claude-opus-4-8", display_name="Claude Opus 4.8",
                                 release_date=now - timedelta(days=10))
    await seeded_kb.upsert_model(id="gpt-5", display_name="GPT-5", release_date=now - timedelta(days=200))
    await seeded_kb.upsert_model(id="deepseek-r1", display_name="DeepSeek-R1",
                                 release_date=now - timedelta(days=60))
    await seeded_kb.add_score(model_id="claude-opus-4-8", benchmark_id="swe-bench-verified", score=80)
    await seeded_kb.add_score(model_id="gpt-5", benchmark_id="swe-bench-verified", score=72)
    await seeded_kb.add_score(model_id="deepseek-r1", benchmark_id="swe-bench-verified", score=60)
    await seeded_kb.add_score(model_id="claude-opus-4-8", benchmark_id="lmarena-overall", score=1400)
    await seeded_kb.add_score(model_id="deepseek-r1", benchmark_id="lmarena-overall", score=1350)
    await seeded_kb.add_price(model_id="claude-opus-4-8", input_per_mtok=5.0, output_per_mtok=25.0)
    await seeded_kb.add_price(model_id="deepseek-r1", input_per_mtok=0.3, output_per_mtok=1.0)

    R = RankingEngine(kb=seeded_kb)
    cfg = R._load_config()

    coding = await R.compute_use_case("coding", cfg)
    assert coding[0]["model_id"] == "claude-opus-4-8"
    assert all(coding[i]["score"] >= coding[i + 1]["score"] for i in range(len(coding) - 1))

    # Price signal: deepseek's value score beats its overall score.
    value = await R.compute_use_case("value", cfg)
    overall = await R.compute_use_case("overall", cfg)
    ds_value = next(r["score"] for r in value if r["model_id"] == "deepseek-r1")
    ds_overall = next(r["score"] for r in overall if r["model_id"] == "deepseek-r1")
    assert ds_value > ds_overall

    # run_once persists every configured board.
    res = await R.run_once()
    assert res["use_cases"] == 10
    assert (await seeded_kb.get_leaderboard("coding")).ranking_json[0]["model_id"] == "claude-opus-4-8"


# ------------------------------------------------------------------- synthesis
@pytest.mark.asyncio
async def test_switch_recommendations(seeded_kb):
    from ai_junkie_updates.intelligence.synthesis import Synthesizer

    profile = {"priorities": ["coding", "research", "agents"],
               "current_models": {"coding": "gpt-5", "research": "claude-opus-4-8"},
               "switch_margin": 0.08}
    await seeded_kb.set_leaderboard(use_case="coding", ranking=[
        {"model_id": "claude-opus-4-8", "display_name": "Claude Opus 4.8", "score": 0.95, "rank": 1, "rationale": "top"},
        {"model_id": "gpt-5", "display_name": "GPT-5", "score": 0.80, "rank": 2, "rationale": "strong"}])
    await seeded_kb.set_leaderboard(use_case="research", ranking=[
        {"model_id": "claude-opus-4-8", "display_name": "Claude Opus 4.8", "score": 0.90, "rank": 1, "rationale": "top"}])
    await seeded_kb.set_leaderboard(use_case="agents", ranking=[
        {"model_id": "claude-opus-4-8", "display_name": "Claude Opus 4.8", "score": 0.88, "rank": 1, "rationale": "top"}])

    recs = {r["use_case"]: r for r in await Synthesizer(kb=seeded_kb).compute_switch_recommendations(profile)}
    assert recs["coding"]["from"] == "gpt-5" and recs["coding"]["to"] == "claude-opus-4-8"
    assert "research" not in recs  # already on the leader
    assert recs["agents"]["from"] is None  # no current pick → recommend leader


@pytest.mark.asyncio
async def test_switch_margin_guard(seeded_kb):
    from ai_junkie_updates.intelligence.synthesis import Synthesizer

    profile = {"priorities": ["coding"], "current_models": {"coding": "gpt-5"}, "switch_margin": 0.08}
    await seeded_kb.set_leaderboard(use_case="coding", ranking=[
        {"model_id": "claude-opus-4-8", "display_name": "Claude Opus 4.8", "score": 0.85, "rank": 1, "rationale": "top"},
        {"model_id": "gpt-5", "display_name": "GPT-5", "score": 0.80, "rank": 2, "rationale": "strong"}])
    recs = await Synthesizer(kb=seeded_kb).compute_switch_recommendations(profile)
    assert "coding" not in {r["use_case"] for r in recs}  # gap 0.05 < margin 0.08


@pytest.mark.asyncio
async def test_synthesis_fallback_on_model_error(seeded_kb):
    from ai_junkie_updates.intelligence.synthesis import Synthesizer

    eid = await seeded_kb.create_event(title="GPT-5 launched", summary="OpenAI shipped GPT-5.",
                                       event_type="MODEL_RELEASE", entity_ids=["openai"],
                                       model_ids=["gpt-5"], item_ids=["u1"], significance_score=90)
    ev = await seeded_kb.get_event(eid)

    class BoomClient:
        async def synthesize(self, *a, **k):
            raise RuntimeError("no api key")

    fb = await Synthesizer(kb=seeded_kb, client=BoomClient()).brief_for_events([ev], {})
    assert "GPT-5 launched" in fb  # deterministic fallback, not a crash
