"""Structured KB ingestion — benchmark/pricing data, NOT news.

This path feeds the knowledge base directly with structured facts (model pricing,
context windows, benchmark scores) and deliberately bypasses Claude: numbers are
data, not news to analyze, so running them through the LLM would waste budget.

OpenRouter exposes a public, key-free models+pricing endpoint
(https://openrouter.ai/api/v1/models) covering most frontier and open models —
the best single source for live cross-model pricing, which powers the
"value-for-money" leaderboard. We match each OpenRouter entry to a tracked KB
model by alias and update its price + context window; untracked models are
skipped to keep the KB focused on the entities the user cares about.

Parsing and matching are pure functions (unit-tested with injected payloads);
the network fetch is isolated and fail-soft so a transient outage never crashes
the run.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from ai_junkie_updates.intelligence.entity_linker import _alias_hit, _normalize
from ai_junkie_updates.intelligence.knowledge_base import knowledge_base
from ai_junkie_updates.utils.logger import get_logger

log = get_logger(__name__)

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


def parse_openrouter_models(payload: dict) -> List[dict]:
    """Extract a normalized list of model dicts from an OpenRouter API payload.

    OpenRouter prices are per-token strings; we convert to USD per 1M tokens.
    Returns: [{or_id, name, context_window, input_per_mtok, output_per_mtok}].
    """
    out: List[dict] = []
    for entry in payload.get("data", []) or []:
        pricing = entry.get("pricing", {}) or {}
        try:
            prompt = pricing.get("prompt")
            completion = pricing.get("completion")
            inp = float(prompt) * 1_000_000 if prompt not in (None, "") else None
            out_ = float(completion) * 1_000_000 if completion not in (None, "") else None
        except (TypeError, ValueError):
            inp = out_ = None
        ctx = entry.get("context_length")
        out.append(
            {
                "or_id": entry.get("id", ""),
                "name": entry.get("name", entry.get("id", "")),
                "context_window": int(ctx) if isinstance(ctx, (int, float)) else None,
                "input_per_mtok": inp,
                "output_per_mtok": out_,
            }
        )
    return out


def match_model(or_entry: dict, kb_models) -> Optional[object]:
    """Match an OpenRouter entry to a tracked KB model by longest matching alias.

    Builds a haystack from the OpenRouter name + id and finds the KB model whose
    most specific alias appears in it. Longest-alias-wins reduces false matches
    (e.g. prefers "claude opus 4.8" over the bare "claude").
    """
    haystack = _normalize(f"{or_entry.get('name','')} {or_entry.get('or_id','')}")
    best = None
    best_len = 0
    for m in kb_models:
        aliases = [m.display_name, m.id, *(m.aliases or [])]
        for alias in aliases:
            if alias and _alias_hit(haystack, alias) and len(alias) > best_len:
                best, best_len = m, len(alias)
    return best


class OpenRouterIngestor:
    """Ingest OpenRouter model pricing/context into the KB."""

    def __init__(self, kb=None) -> None:
        self._kb = kb or knowledge_base

    async def ingest(self, payload: dict) -> dict:
        """Match payload entries to tracked models and update price/context.

        Returns a summary with matched/priced/unmatched counts.
        """
        entries = parse_openrouter_models(payload)
        models = await self._kb.list_models()
        matched, priced = 0, 0
        seen_models = set()

        for e in entries:
            m = match_model(e, models)
            if m is None:
                continue
            matched += 1
            # Update context window only if we don't already have one.
            if e["context_window"] and not m.context_window:
                await self._kb.upsert_model(
                    id=m.id, display_name=m.display_name, context_window=e["context_window"]
                )
            # Record a price observation if pricing is present and unseen this run.
            if (e["input_per_mtok"] is not None or e["output_per_mtok"] is not None) \
                    and m.id not in seen_models:
                await self._kb.add_price(
                    model_id=m.id,
                    input_per_mtok=e["input_per_mtok"],
                    output_per_mtok=e["output_per_mtok"],
                    source_url=OPENROUTER_MODELS_URL,
                    effective_date=datetime.now(timezone.utc),
                )
                priced += 1
                seen_models.add(m.id)

        log.info("openrouter_ingested", entries=len(entries), matched=matched, priced=priced)
        return {"entries": len(entries), "matched": matched, "priced": priced}

    async def fetch_payload(self) -> Optional[dict]:
        """Fetch the OpenRouter models payload (fail-soft, returns None on error)."""
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    OPENROUTER_MODELS_URL,
                    headers={"User-Agent": "AIJunkieUpdates/1.0"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        log.warning("openrouter_fetch_error", status=resp.status)
                        return None
                    return await resp.json()
        except Exception as exc:
            log.warning("openrouter_fetch_exception", error=str(exc))
            return None

    async def run_once(self) -> dict:
        """Fetch and ingest. No-ops gracefully when the fetch fails."""
        payload = await self.fetch_payload()
        if not payload:
            return {"entries": 0, "matched": 0, "priced": 0}
        return await self.ingest(payload)


openrouter_ingestor = OpenRouterIngestor()


# ---------------------------------------------------------------------------
# Benchmark leaderboard ingestion (LMArena / HF Open LLM Leaderboard)
# ---------------------------------------------------------------------------
# These public leaderboards have NO stable official API. Their data lives behind
# HF Spaces and the on-page/JSON format drifts without notice, so this path is
# deliberately:
#   * fail-soft   — any fetch/parse error returns nothing, never crashes a run
#   * pure-parse  — parsing is a standalone function unit-tested with fixtures
#   * provenance-stamped — every score row records source_url + captured_at, and
#                   leaderboards surface a methodology "as of <date>" so stale or
#                   missing data is visible, never silently presented as current.
# Parsers accept the "rows" shape these Spaces commonly expose:
#   {"headers"|"columns": [...], "data": [[...], ...]} (a Gradio dataframe), or a
#   plain list of row dicts. We extract (model_label, score) pairs only.

# Heuristic column-name hints for locating the model and the score in a row.
_MODEL_KEYS = ("model", "model name", "model_name", "name", "submission")
_SCORE_KEYS_BY_BENCHMARK = {
    # benchmark_id -> ordered candidate score-column hints (first match wins)
    "lmarena-overall": ("arena score", "arena elo", "elo", "rating", "score"),
    "swe-bench-verified": ("resolved", "score", "% resolved", "pass@1", "accuracy"),
    "aider-polyglot": ("percent", "pass rate", "score", "accuracy"),
    "gpqa-diamond": ("gpqa", "score", "accuracy"),
    "mmlu-pro": ("mmlu-pro", "mmlu", "score", "accuracy"),
    "tau-bench": ("tau", "score", "pass^1", "accuracy"),
}


def _coerce_float(value) -> Optional[float]:
    """Parse a score cell that may be a number or a string like '72.5%'/'1400'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace("%", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _normalize_rows(payload) -> List[dict]:
    """Coerce the various leaderboard shapes into a list of row dicts."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        # Gradio dataframe: {"headers"|"columns": [...], "data": [[...], ...]}
        headers = payload.get("headers") or payload.get("columns")
        data = payload.get("data") or payload.get("rows")
        if headers and isinstance(data, list):
            out = []
            for row in data:
                if isinstance(row, dict):
                    out.append(row)
                elif isinstance(row, (list, tuple)):
                    out.append({headers[i]: row[i] for i in range(min(len(headers), len(row)))})
            return out
        # Nested under a common key.
        for key in ("data", "results", "leaderboard", "models"):
            inner = payload.get(key)
            if isinstance(inner, (list, dict)) and inner is not payload:
                return _normalize_rows(inner)
    return []


def parse_leaderboard(payload, benchmark_id: str) -> List[dict]:
    """Extract [{model_label, score}] from a leaderboard payload.

    Pure function — the heart of the (fragile) ingestion, fully unit-testable.
    Locates the model column and the most relevant score column by name hints,
    case-insensitively. Rows without a resolvable model+score are skipped.
    """
    rows = _normalize_rows(payload)
    if not rows:
        return []
    score_hints = _SCORE_KEYS_BY_BENCHMARK.get(benchmark_id, ("score", "accuracy", "rating"))

    # Resolve column names once from the first row's keys (case-insensitive).
    keys = list(rows[0].keys())
    lower = {k.lower().strip(): k for k in keys}

    def pick(hints):
        for h in hints:
            if h in lower:
                return lower[h]
        # substring fallback
        for h in hints:
            for lk, orig in lower.items():
                if h in lk:
                    return orig
        return None

    model_col = pick(_MODEL_KEYS)
    score_col = pick(score_hints)
    if model_col is None or score_col is None:
        return []

    out: List[dict] = []
    for r in rows:
        label = r.get(model_col)
        score = _coerce_float(r.get(score_col))
        if label and score is not None:
            out.append({"model_label": str(label), "score": score})
    return out


class BenchmarkIngestor:
    """Ingest public leaderboard scores into the KB (fragile, fail-soft).

    Configure sources as (benchmark_id, url) pairs; each fetched payload is parsed
    and alias-matched to tracked models. Scores for untracked models are skipped.
    """

    # (benchmark_id, source_url). URLs point at the JSON the HF Spaces serve;
    # these MOVE — when they break, ingestion fails soft and leaderboards keep
    # showing the last good "as of" data rather than nothing.
    SOURCES = [
        ("lmarena-overall", "https://lmarena.ai/data/leaderboard.json"),
        ("swe-bench-verified", "https://www.swebench.com/data/leaderboard.json"),
    ]

    def __init__(self, kb=None) -> None:
        self._kb = kb or knowledge_base

    async def ingest_payload(self, payload, benchmark_id: str) -> dict:
        """Parse a single leaderboard payload and store matched scores."""
        parsed = parse_leaderboard(payload, benchmark_id)
        if not parsed:
            return {"benchmark": benchmark_id, "parsed": 0, "stored": 0}
        models = await self._kb.list_models()
        stored = 0
        seen = set()
        # Rank by score order as given (already leaderboard-ordered if sorted).
        ranked = sorted(parsed, key=lambda x: x["score"], reverse=True)
        for rank, row in enumerate(ranked, start=1):
            m = match_model({"name": row["model_label"], "or_id": ""}, models)
            if m is None or m.id in seen:
                continue
            await self._kb.add_score(
                model_id=m.id,
                benchmark_id=benchmark_id,
                score=row["score"],
                rank=rank,
                source_url=next((u for b, u in self.SOURCES if b == benchmark_id), None),
            )
            stored += 1
            seen.add(m.id)
        log.info("benchmark_ingested", benchmark=benchmark_id,
                 parsed=len(parsed), stored=stored)
        return {"benchmark": benchmark_id, "parsed": len(parsed), "stored": stored}

    async def _fetch(self, url: str) -> Optional[object]:
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"User-Agent": "AIJunkieUpdates/1.0"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        log.warning("benchmark_fetch_error", url=url, status=resp.status)
                        return None
                    return await resp.json(content_type=None)
        except Exception as exc:
            log.warning("benchmark_fetch_exception", url=url, error=str(exc))
            return None

    async def run_once(self) -> dict:
        """Fetch + ingest every configured benchmark source (fail-soft each)."""
        total = {"sources": 0, "stored": 0}
        for benchmark_id, url in self.SOURCES:
            payload = await self._fetch(url)
            if not payload:
                continue
            res = await self.ingest_payload(payload, benchmark_id)
            total["sources"] += 1
            total["stored"] += res["stored"]
        return total


benchmark_ingestor = BenchmarkIngestor()
