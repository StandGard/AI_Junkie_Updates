"""OpenRouter pricing ingest and benchmark leaderboard ingest."""

from __future__ import annotations

import pytest

from ai_junkie_updates.intelligence.ingest import (
    BenchmarkIngestor,
    OpenRouterIngestor,
    _coerce_float,
    _normalize_rows,
    match_model,
    parse_leaderboard,
    parse_openrouter_models,
)

OPENROUTER_PAYLOAD = {"data": [
    {"id": "anthropic/claude-opus-4.8", "name": "Anthropic: Claude Opus 4.8",
     "context_length": 200000, "pricing": {"prompt": "0.000005", "completion": "0.000025"}},
    {"id": "openai/gpt-5", "name": "OpenAI: GPT-5",
     "context_length": 400000, "pricing": {"prompt": "0.000005", "completion": "0.00002"}},
    {"id": "deepseek/deepseek-r1", "name": "DeepSeek: R1",
     "context_length": 128000, "pricing": {"prompt": "0.0000003", "completion": "0.000001"}},
    {"id": "some/unknown-model", "name": "Random Unknown Model",
     "context_length": 8000, "pricing": {"prompt": "0.000001", "completion": "0.000002"}},
]}

GRADIO_LEADERBOARD = {
    "headers": ["Rank", "Model", "Arena Score", "Votes"],
    "data": [
        [1, "Claude Opus 4.8", 1401, 50000],
        [2, "GPT-5", 1395, 48000],
        [3, "Gemini 2", 1380, 30000],
        [4, "Some Untracked Model", 1300, 1000],
    ],
}


# ------------------------------------------------------------------ openrouter
def test_parse_openrouter_conversion():
    parsed = parse_openrouter_models(OPENROUTER_PAYLOAD)
    assert len(parsed) == 4
    opus = next(p for p in parsed if "opus" in p["or_id"].lower())
    assert opus["input_per_mtok"] == pytest.approx(5.0)
    assert opus["output_per_mtok"] == pytest.approx(25.0)
    assert opus["context_window"] == 200000


@pytest.mark.asyncio
async def test_openrouter_ingest(seeded_kb):
    summary = await OpenRouterIngestor(kb=seeded_kb).ingest(OPENROUTER_PAYLOAD)
    assert summary["matched"] == 3  # unknown model skipped
    assert summary["priced"] == 3
    assert (await seeded_kb.latest_price("claude-opus-4-8")).output_per_mtok == 25.0
    assert (await seeded_kb.get_model("claude-opus-4-8")).context_window == 200000


@pytest.mark.asyncio
async def test_openrouter_fetch_failsoft(seeded_kb):
    class Bad(OpenRouterIngestor):
        async def fetch_payload(self):
            return None

    assert await Bad(kb=seeded_kb).run_once() == {"entries": 0, "matched": 0, "priced": 0}


# ------------------------------------------------------------------ benchmarks
def test_coerce_float():
    assert _coerce_float("72.5%") == 72.5
    assert _coerce_float("1,400") == 1400.0
    assert _coerce_float(1395) == 1395.0
    assert _coerce_float("n/a") is None


def test_normalize_and_parse_leaderboard():
    rows = _normalize_rows(GRADIO_LEADERBOARD)
    assert len(rows) == 4 and rows[0]["Model"] == "Claude Opus 4.8"
    assert _normalize_rows(12345) == []

    parsed = parse_leaderboard(GRADIO_LEADERBOARD, "lmarena-overall")
    assert parsed[0] == {"model_label": "Claude Opus 4.8", "score": 1401.0}
    # list-of-dicts with percent strings
    dicts = [{"model": "Claude Opus 4.8", "Resolved": "72.5%"},
             {"model": "GPT-5", "Resolved": "68.0%"}]
    p2 = parse_leaderboard(dicts, "swe-bench-verified")
    assert p2[0]["score"] == 72.5
    assert parse_leaderboard({"foo": "bar"}, "lmarena-overall") == []


@pytest.mark.asyncio
async def test_benchmark_ingest_and_provenance(seeded_kb):
    res = await BenchmarkIngestor(kb=seeded_kb).ingest_payload(GRADIO_LEADERBOARD, "lmarena-overall")
    assert res["stored"] == 3  # untracked skipped
    scores = await seeded_kb.latest_scores_for_benchmark("lmarena-overall")
    assert scores["claude-opus-4-8"].score == 1401.0
    assert scores["claude-opus-4-8"].rank == 1
    assert "lmarena" in (scores["claude-opus-4-8"].source_url or "")


def test_match_model(seeded_kb_sync_helper=None):
    # pure matcher needs only the alias data; build minimal stand-ins
    class M:
        def __init__(self, id, name, aliases):
            self.id, self.display_name, self.aliases = id, name, aliases

    models = [M("claude-opus-4-8", "Claude Opus 4.8", ["Claude Opus", "Opus 4.8"]),
              M("gpt-5", "GPT-5", ["GPT-5"])]
    assert match_model({"name": "Anthropic: Claude Opus 4.8", "or_id": ""}, models).id == "claude-opus-4-8"
    assert match_model({"name": "Totally Unknown", "or_id": ""}, models) is None
