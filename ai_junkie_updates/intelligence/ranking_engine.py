"""Ranking engine — computes a leaderboard per use-case.

This is the heart of the "performance advisor": for each use-case (coding,
agents, video, research, value-for-money, overall, ...) it produces an ordered
ranking of models from a deterministic blend of three signals:

  * benchmark  — min-max normalised scores on the use-case's benchmarks
                 (from the KB `benchmark_scores` table, latest per model)
  * recency    — exponential decay on release_date (keeps fresh models visible)
  * price      — cheaper blended $/Mtok scores higher (favours value)

Weights come from ``config/ranking.yaml`` and are reloaded each run, so the user
can retune priorities without code changes. The maths is deterministic and
defensible; an optional one-line, evidence-cited rationale is attached per model.
The result is written to the materialized ``leaderboards`` table, which the
Telegram commands read directly (no LLM at query time).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from ai_junkie_updates.intelligence.knowledge_base import knowledge_base
from ai_junkie_updates.utils.logger import get_logger

log = get_logger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "ranking.yaml"


def _minmax(values: Dict[str, float]) -> Dict[str, float]:
    """Min-max normalise a {key: value} map to [0,1]. Flat input → all 0.5."""
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi - lo < 1e-9:
        return {k: 0.5 for k in values}
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


class RankingEngine:
    """Compute and persist per-use-case leaderboards from KB data."""

    def __init__(self, kb=None, config_path: Optional[Path] = None) -> None:
        self._kb = kb or knowledge_base
        self._config_path = config_path or CONFIG_PATH

    def _load_config(self) -> dict:
        with open(self._config_path, "r") as fh:
            return yaml.safe_load(fh) or {}

    # ----------------------------------------------------------------- signals
    def _recency_scores(self, models, half_life_days: float) -> Dict[str, float]:
        """Exponential-decay recency in [0,1] from each model's release_date."""
        now = datetime.now(timezone.utc)
        out: Dict[str, float] = {}
        for m in models:
            rd = m.release_date
            if rd is None:
                out[m.id] = 0.3  # unknown release date → mild prior, not zero
                continue
            if rd.tzinfo is None:
                rd = rd.replace(tzinfo=timezone.utc)
            age_days = max(0.0, (now - rd).total_seconds() / 86400.0)
            out[m.id] = 0.5 ** (age_days / max(half_life_days, 1.0))
        return out

    async def _benchmark_scores(self, benchmark_ids: List[str]) -> Dict[str, float]:
        """Average min-max-normalised score per model across the given benchmarks."""
        if not benchmark_ids:
            return {}
        per_model_norm: Dict[str, List[float]] = {}
        for bid in benchmark_ids:
            latest = await self._kb.latest_scores_for_benchmark(bid)
            if not latest:
                continue
            raw = {mid: s.score for mid, s in latest.items()}
            for mid, norm in _minmax(raw).items():
                per_model_norm.setdefault(mid, []).append(norm)
        return {mid: sum(v) / len(v) for mid, v in per_model_norm.items() if v}

    async def _price_scores(self, model_ids: List[str]) -> Dict[str, float]:
        """Cheaper = higher. Blended $/Mtok (1*input + 3*output), inverted+normalised."""
        blended: Dict[str, float] = {}
        for mid in model_ids:
            price = await self._kb.latest_price(mid)
            if price is None:
                continue
            inp = price.input_per_mtok if price.input_per_mtok is not None else None
            out = price.output_per_mtok if price.output_per_mtok is not None else None
            if inp is None and out is None:
                continue
            # Weight output more heavily (typical usage skews output-token cost).
            cost = (inp or 0) * 1.0 + (out or 0) * 3.0
            blended[mid] = cost
        if not blended:
            return {}
        norm_cost = _minmax(blended)
        # Invert: low cost → high value score.
        return {mid: 1.0 - v for mid, v in norm_cost.items()}

    # ----------------------------------------------------------------- compute
    async def compute_use_case(self, use_case: str, cfg: dict) -> List[dict]:
        """Return the ordered ranking (list of dicts) for a single use-case."""
        defaults = cfg.get("defaults", {})
        uc_cfg = cfg.get("use_cases", {}).get(use_case, {})
        half_life = float(cfg.get("recency_half_life_days", 120))

        w_b = float(uc_cfg.get("w_benchmark", defaults.get("w_benchmark", 0.6)))
        w_r = float(uc_cfg.get("w_recency", defaults.get("w_recency", 0.25)))
        w_p = float(uc_cfg.get("w_price", defaults.get("w_price", 0.15)))
        wsum = (w_b + w_r + w_p) or 1.0
        w_b, w_r, w_p = w_b / wsum, w_r / wsum, w_p / wsum

        models = [m for m in await self._kb.list_models() if m.status != "deprecated"]
        model_ids = [m.id for m in models]

        bench = await self._benchmark_scores(uc_cfg.get("benchmarks", []))
        recency = self._recency_scores(models, half_life)
        price = await self._price_scores(model_ids)

        # Candidate set: models with at least one contributing signal.
        candidates = set(recency) | set(bench) | set(price)

        ranking: List[dict] = []
        for mid in candidates:
            b = bench.get(mid)
            r = recency.get(mid)
            p = price.get(mid)
            # Redistribute weight of any missing signal across present ones so a
            # model isn't penalised for missing data it can't have (e.g. no price).
            parts = []
            if b is not None:
                parts.append((w_b, b))
            if r is not None:
                parts.append((w_r, r))
            if p is not None:
                parts.append((w_p, p))
            if not parts:
                continue
            wtot = sum(w for w, _ in parts) or 1.0
            score = sum(w * v for w, v in parts) / wtot

            ranking.append(
                {
                    "model_id": mid,
                    "score": round(score, 4),
                    "components": {
                        "benchmark": None if b is None else round(b, 3),
                        "recency": None if r is None else round(r, 3),
                        "price": None if p is None else round(p, 3),
                    },
                }
            )

        ranking.sort(key=lambda x: x["score"], reverse=True)
        # Assign ranks and a deterministic rationale.
        name_by_id = {m.id: m.display_name for m in models}
        for i, row in enumerate(ranking, start=1):
            row["rank"] = i
            row["display_name"] = name_by_id.get(row["model_id"], row["model_id"])
            row["rationale"] = self._rationale(row)
        return ranking

    def _rationale(self, row: dict) -> str:
        """One-line, component-driven explanation (no LLM)."""
        c = row["components"]
        bits = []
        if c["benchmark"] is not None:
            level = "top" if c["benchmark"] >= 0.75 else "strong" if c["benchmark"] >= 0.5 else "mid"
            bits.append(f"{level} benchmarks")
        if c["recency"] is not None and c["recency"] >= 0.6:
            bits.append("recently released")
        if c["price"] is not None and c["price"] >= 0.66:
            bits.append("low cost")
        return ", ".join(bits) if bits else "limited data"

    async def run_once(self) -> dict:
        """Compute every configured use-case leaderboard and persist them."""
        cfg = self._load_config()
        use_cases = list(cfg.get("use_cases", {}).keys())
        written = 0
        for uc in use_cases:
            ranking = await self.compute_use_case(uc, cfg)
            note = (
                f"weights b/r/p per ranking.yaml; benchmarks="
                f"{cfg['use_cases'][uc].get('benchmarks', [])}; "
                f"as of {datetime.now(timezone.utc).date().isoformat()}"
            )
            await self._kb.set_leaderboard(use_case=uc, ranking=ranking, methodology_note=note)
            written += 1
        log.info("ranking_done", use_cases=written)
        return {"use_cases": written}


ranking_engine = RankingEngine()
