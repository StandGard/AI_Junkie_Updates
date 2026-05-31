"""Async data-access layer over the knowledge-base tables.

The intelligence modules (entity_linker, clustering, ranking_engine, synthesis)
and the Telegram command bot all read/write the KB through this one class, so
access logic lives in a single place. Every write is an idempotent upsert, which
makes seeding and re-ingestion safe to re-run.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from sqlalchemy import select

from ai_junkie_updates.core import kb_models as kb
from ai_junkie_updates.core.database import db
from ai_junkie_updates.utils.logger import get_logger

log = get_logger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
SEED_FILE = CONFIG_DIR / "seed_entities.yaml"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _norm(text: Optional[str]) -> str:
    return (text or "").strip().lower()


class KnowledgeBase:
    """CRUD + query helpers for companies, models, prices, benchmarks, scores,
    capabilities, tools, events, and leaderboards."""

    def __init__(self, session_factory=None) -> None:
        self._sf = session_factory or db.session_factory

    # ------------------------------------------------------------------ companies
    async def upsert_company(
        self,
        *,
        id: str,
        name: str,
        aliases: Optional[List[str]] = None,
        category: Optional[str] = None,
        homepage_url: Optional[str] = None,
        twitter_handle: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> str:
        async with self._sf() as s:
            row = await s.get(kb.Company, id)
            now = _utcnow()
            if row is None:
                row = kb.Company(id=id, name=name, first_seen=now)
                s.add(row)
            row.name = name
            if aliases is not None:
                row.aliases = aliases
            if category is not None:
                row.category = category
            if homepage_url is not None:
                row.homepage_url = homepage_url
            if twitter_handle is not None:
                row.twitter_handle = twitter_handle
            if notes is not None:
                row.notes = notes
            row.last_seen = now
            await s.commit()
            return id

    async def get_company(self, id: str) -> Optional[kb.Company]:
        async with self._sf() as s:
            return await s.get(kb.Company, id)

    async def list_companies(self) -> List[kb.Company]:
        async with self._sf() as s:
            return list((await s.execute(select(kb.Company))).scalars().all())

    async def find_company_by_alias(self, term: str) -> Optional[kb.Company]:
        """Exact (normalized) match of a term against id / name / aliases."""
        t = _norm(term)
        for c in await self.list_companies():
            if t in {_norm(c.id), _norm(c.name)} | {_norm(a) for a in (c.aliases or [])}:
                return c
        return None

    # --------------------------------------------------------------------- models
    async def upsert_model(
        self,
        *,
        id: str,
        display_name: str,
        company_id: Optional[str] = None,
        family: Optional[str] = None,
        version: Optional[str] = None,
        release_date: Optional[datetime] = None,
        modality: Optional[List[str]] = None,
        context_window: Optional[int] = None,
        is_open_source: Optional[bool] = None,
        status: Optional[str] = None,
        aliases: Optional[List[str]] = None,
    ) -> str:
        async with self._sf() as s:
            row = await s.get(kb.Model, id)
            if row is None:
                row = kb.Model(id=id, display_name=display_name)
                s.add(row)
            row.display_name = display_name
            if company_id is not None:
                row.company_id = company_id
            if family is not None:
                row.family = family
            if version is not None:
                row.version = version
            if release_date is not None:
                row.release_date = release_date
            if modality is not None:
                row.modality = modality
            if context_window is not None:
                row.context_window = context_window
            if is_open_source is not None:
                row.is_open_source = is_open_source
            if status is not None:
                row.status = status
            if aliases is not None:
                row.aliases = aliases
            row.last_updated = _utcnow()
            await s.commit()
            return id

    async def get_model(self, id: str) -> Optional[kb.Model]:
        async with self._sf() as s:
            return await s.get(kb.Model, id)

    async def list_models(self) -> List[kb.Model]:
        async with self._sf() as s:
            return list((await s.execute(select(kb.Model))).scalars().all())

    async def models_by_company(self, company_id: str) -> List[kb.Model]:
        async with self._sf() as s:
            stmt = select(kb.Model).where(kb.Model.company_id == company_id)
            return list((await s.execute(stmt)).scalars().all())

    async def find_model_by_alias(self, term: str) -> Optional[kb.Model]:
        t = _norm(term)
        for m in await self.list_models():
            if t in {_norm(m.id), _norm(m.display_name)} | {_norm(a) for a in (m.aliases or [])}:
                return m
        return None

    # --------------------------------------------------------------------- prices
    async def add_price(
        self,
        *,
        model_id: str,
        input_per_mtok: Optional[float] = None,
        output_per_mtok: Optional[float] = None,
        currency: str = "USD",
        source_url: Optional[str] = None,
        effective_date: Optional[datetime] = None,
    ) -> None:
        async with self._sf() as s:
            s.add(
                kb.ModelPrice(
                    model_id=model_id,
                    input_per_mtok=input_per_mtok,
                    output_per_mtok=output_per_mtok,
                    currency=currency,
                    source_url=source_url,
                    effective_date=effective_date,
                )
            )
            await s.commit()

    async def latest_price(self, model_id: str) -> Optional[kb.ModelPrice]:
        async with self._sf() as s:
            stmt = (
                select(kb.ModelPrice)
                .where(kb.ModelPrice.model_id == model_id)
                .order_by(kb.ModelPrice.captured_at.desc())
                .limit(1)
            )
            return (await s.execute(stmt)).scalars().first()

    # ----------------------------------------------------------------- benchmarks
    async def upsert_benchmark(
        self,
        *,
        id: str,
        name: str,
        use_case: Optional[str] = None,
        higher_is_better: bool = True,
        source_url: Optional[str] = None,
        description: Optional[str] = None,
    ) -> str:
        async with self._sf() as s:
            row = await s.get(kb.Benchmark, id)
            if row is None:
                row = kb.Benchmark(id=id, name=name)
                s.add(row)
            row.name = name
            row.higher_is_better = higher_is_better
            if use_case is not None:
                row.use_case = use_case
            if source_url is not None:
                row.source_url = source_url
            if description is not None:
                row.description = description
            await s.commit()
            return id

    async def list_benchmarks(self) -> List[kb.Benchmark]:
        async with self._sf() as s:
            return list((await s.execute(select(kb.Benchmark))).scalars().all())

    async def add_score(
        self,
        *,
        model_id: str,
        benchmark_id: str,
        score: float,
        rank: Optional[int] = None,
        source_url: Optional[str] = None,
    ) -> None:
        async with self._sf() as s:
            s.add(
                kb.BenchmarkScore(
                    model_id=model_id,
                    benchmark_id=benchmark_id,
                    score=score,
                    rank=rank,
                    source_url=source_url,
                )
            )
            await s.commit()

    async def latest_scores_for_benchmark(self, benchmark_id: str) -> Dict[str, kb.BenchmarkScore]:
        """Return the most recent score per model for a benchmark, keyed by model_id."""
        async with self._sf() as s:
            stmt = (
                select(kb.BenchmarkScore)
                .where(kb.BenchmarkScore.benchmark_id == benchmark_id)
                .order_by(kb.BenchmarkScore.captured_at.desc())
            )
            rows = (await s.execute(stmt)).scalars().all()
        latest: Dict[str, kb.BenchmarkScore] = {}
        for r in rows:  # already newest-first → first seen per model wins
            latest.setdefault(r.model_id, r)
        return latest

    # --------------------------------------------------------------- capabilities
    async def upsert_capability(
        self,
        *,
        model_id: str,
        use_case: str,
        qualitative_note: Optional[str] = None,
        evidence_item_ids: Optional[List[str]] = None,
    ) -> None:
        async with self._sf() as s:
            stmt = select(kb.Capability).where(
                kb.Capability.model_id == model_id,
                kb.Capability.use_case == use_case,
            )
            row = (await s.execute(stmt)).scalars().first()
            if row is None:
                row = kb.Capability(model_id=model_id, use_case=use_case)
                s.add(row)
            if qualitative_note is not None:
                row.qualitative_note = qualitative_note
            if evidence_item_ids is not None:
                row.evidence_item_ids = evidence_item_ids
            row.updated_at = _utcnow()
            await s.commit()

    # ---------------------------------------------------------------------- tools
    async def upsert_tool(
        self,
        *,
        id: str,
        name: str,
        company_id: Optional[str] = None,
        use_case: Optional[List[str]] = None,
        description: Optional[str] = None,
        url: Optional[str] = None,
    ) -> str:
        async with self._sf() as s:
            row = await s.get(kb.Tool, id)
            if row is None:
                row = kb.Tool(id=id, name=name)
                s.add(row)
            row.name = name
            if company_id is not None:
                row.company_id = company_id
            if use_case is not None:
                row.use_case = use_case
            if description is not None:
                row.description = description
            if url is not None:
                row.url = url
            row.last_updated = _utcnow()
            await s.commit()
            return id

    async def list_tools(self) -> List[kb.Tool]:
        async with self._sf() as s:
            return list((await s.execute(select(kb.Tool))).scalars().all())

    async def tools_for_use_case(self, use_case: str) -> List[kb.Tool]:
        uc = _norm(use_case)
        return [t for t in await self.list_tools() if uc in {_norm(u) for u in (t.use_case or [])}]

    # --------------------------------------------------------------------- events
    async def create_event(
        self,
        *,
        title: str,
        summary: Optional[str] = None,
        event_type: Optional[str] = None,
        primary_entity_id: Optional[str] = None,
        entity_ids: Optional[List[str]] = None,
        model_ids: Optional[List[str]] = None,
        item_ids: Optional[List[str]] = None,
        significance_score: int = 0,
        first_item_at: Optional[datetime] = None,
        last_item_at: Optional[datetime] = None,
    ) -> str:
        async with self._sf() as s:
            ev = kb.Event(
                title=title,
                summary=summary,
                event_type=event_type,
                primary_entity_id=primary_entity_id,
                entity_ids=entity_ids or [],
                model_ids=model_ids or [],
                item_ids=item_ids or [],
                significance_score=significance_score,
                first_item_at=first_item_at,
                last_item_at=last_item_at,
            )
            s.add(ev)
            await s.commit()
            return ev.id

    async def get_event(self, id: str) -> Optional[kb.Event]:
        async with self._sf() as s:
            return await s.get(kb.Event, id)

    async def recent_events(self, limit: int = 20, min_significance: int = 0) -> List[kb.Event]:
        async with self._sf() as s:
            stmt = (
                select(kb.Event)
                .where(kb.Event.significance_score >= min_significance)
                .order_by(kb.Event.created_at.desc())
                .limit(limit)
            )
            return list((await s.execute(stmt)).scalars().all())

    # --------------------------------------------------------------- leaderboards
    async def set_leaderboard(
        self,
        *,
        use_case: str,
        ranking: List[Dict[str, Any]],
        methodology_note: Optional[str] = None,
    ) -> None:
        async with self._sf() as s:
            row = await s.get(kb.Leaderboard, use_case)
            if row is None:
                row = kb.Leaderboard(use_case=use_case)
                s.add(row)
            row.ranking_json = ranking
            row.methodology_note = methodology_note
            row.computed_at = _utcnow()
            await s.commit()

    async def get_leaderboard(self, use_case: str) -> Optional[kb.Leaderboard]:
        async with self._sf() as s:
            return await s.get(kb.Leaderboard, use_case)

    async def list_leaderboards(self) -> List[kb.Leaderboard]:
        async with self._sf() as s:
            return list((await s.execute(select(kb.Leaderboard))).scalars().all())

    # ----------------------------------------------------------------------- seed
    async def seed_from_yaml(self, path: Optional[Path] = None) -> Dict[str, int]:
        """Idempotently load companies/models/tools/benchmarks from a YAML seed.

        Returns a count of rows processed per section. Safe to re-run — existing
        rows are updated in place rather than duplicated.
        """
        seed_path = path or SEED_FILE
        with open(seed_path, "r") as fh:
            data = yaml.safe_load(fh) or {}

        counts = {"companies": 0, "models": 0, "tools": 0, "benchmarks": 0}

        for c in data.get("companies", []):
            await self.upsert_company(**c)
            counts["companies"] += 1
        for m in data.get("models", []):
            await self.upsert_model(**m)
            counts["models"] += 1
        for t in data.get("tools", []):
            await self.upsert_tool(**t)
            counts["tools"] += 1
        for b in data.get("benchmarks", []):
            await self.upsert_benchmark(**b)
            counts["benchmarks"] += 1

        log.info("kb_seeded", **counts)
        return counts


# Module-level singleton, consistent with the rest of the codebase.
knowledge_base = KnowledgeBase()
