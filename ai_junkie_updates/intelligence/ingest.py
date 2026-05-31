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
