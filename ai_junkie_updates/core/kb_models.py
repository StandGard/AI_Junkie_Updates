"""Knowledge-base ORM models for the intelligence layer.

These tables sit on top of the per-item `updates` table and hold the structured,
long-lived knowledge the advisor reasons over: companies, models, prices,
benchmarks, capabilities, story clusters (events), tools, and materialized
leaderboards. They share the same declarative ``Base`` as ``core.models`` so a
single ``Base.metadata.create_all`` (in ``database.init_db``) creates them all.

JSON columns store small lists/dicts (aliases, modality, id lists, ranking
snapshots). SQLAlchemy's ``JSON`` type serializes transparently on SQLite.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)

from ai_junkie_updates.core.models import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid4() -> str:
    return str(uuid.uuid4())


class Company(Base):
    """An AI company / lab / startup tracked by the system."""

    __tablename__ = "companies"

    id = Column(String, primary_key=True)  # slug, e.g. "anthropic"
    name = Column(String, nullable=False)
    aliases = Column(JSON, nullable=False, default=list)  # ["Anthropic", "Claude", ...]
    category = Column(String, nullable=True)  # frontier_lab/open_source/startup/infra/tooling
    homepage_url = Column(String, nullable=True)
    twitter_handle = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    first_seen = Column(DateTime, nullable=False, default=_utcnow)
    last_seen = Column(DateTime, nullable=False, default=_utcnow)


class Model(Base):
    """A specific AI model (a row per released model/version)."""

    __tablename__ = "models"

    id = Column(String, primary_key=True)  # slug, e.g. "claude-opus-4-5"
    company_id = Column(String, ForeignKey("companies.id"), nullable=True, index=True)
    family = Column(String, nullable=True)  # "claude", "gpt", "gemini", "llama"
    display_name = Column(String, nullable=False)
    version = Column(String, nullable=True)
    release_date = Column(DateTime, nullable=True)
    modality = Column(JSON, nullable=False, default=list)  # ["text","vision","audio","video"]
    context_window = Column(Integer, nullable=True)
    is_open_source = Column(Boolean, nullable=False, default=False)
    status = Column(String, nullable=False, default="current")  # current/preview/deprecated
    aliases = Column(JSON, nullable=False, default=list)
    last_updated = Column(DateTime, nullable=False, default=_utcnow)


class ModelPrice(Base):
    """A pricing observation for a model (history rows → pricing-change detection)."""

    __tablename__ = "model_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(String, ForeignKey("models.id"), nullable=False, index=True)
    input_per_mtok = Column(Float, nullable=True)   # USD per 1M input tokens
    output_per_mtok = Column(Float, nullable=True)  # USD per 1M output tokens
    currency = Column(String, nullable=False, default="USD")
    source_url = Column(String, nullable=True)
    effective_date = Column(DateTime, nullable=True)
    captured_at = Column(DateTime, nullable=False, default=_utcnow)


class Benchmark(Base):
    """A benchmark / leaderboard metric feeding the ranking engine."""

    __tablename__ = "benchmarks"

    id = Column(String, primary_key=True)  # slug, e.g. "swe-bench-verified", "lmarena-overall"
    name = Column(String, nullable=False)
    use_case = Column(String, nullable=True)  # maps to a leaderboard category
    higher_is_better = Column(Boolean, nullable=False, default=True)
    source_url = Column(String, nullable=True)
    description = Column(Text, nullable=True)


class BenchmarkScore(Base):
    """A model's score on a benchmark (history rows → improvement detection)."""

    __tablename__ = "benchmark_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(String, ForeignKey("models.id"), nullable=False, index=True)
    benchmark_id = Column(String, ForeignKey("benchmarks.id"), nullable=False, index=True)
    score = Column(Float, nullable=False)
    rank = Column(Integer, nullable=True)
    source_url = Column(String, nullable=True)
    captured_at = Column(DateTime, nullable=False, default=_utcnow)


class Capability(Base):
    """Qualitative, evidence-backed note on a model's fit for a use-case.

    Bridges fuzzy advice ("best for coding") to hard benchmarks: each row links a
    Claude-authored note to the source items (``updates.id``) that justify it.
    """

    __tablename__ = "capabilities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(String, ForeignKey("models.id"), nullable=False, index=True)
    use_case = Column(String, nullable=False)  # coding/agents/app_dev/automation/content/video/research/business
    qualitative_note = Column(Text, nullable=True)
    evidence_item_ids = Column(JSON, nullable=False, default=list)  # list of updates.id
    updated_at = Column(DateTime, nullable=False, default=_utcnow)


class Event(Base):
    """A story cluster: related items across sources collapsed into one event."""

    __tablename__ = "events"

    id = Column(String, primary_key=True, default=_uuid4)
    title = Column(String, nullable=False)
    summary = Column(Text, nullable=True)
    event_type = Column(String, nullable=True)  # reuses UpdateCategory values
    primary_entity_id = Column(String, nullable=True)
    entity_ids = Column(JSON, nullable=False, default=list)  # company/tool slugs
    model_ids = Column(JSON, nullable=False, default=list)
    item_ids = Column(JSON, nullable=False, default=list)    # contributing updates.id
    significance_score = Column(Integer, nullable=False, default=0)
    first_item_at = Column(DateTime, nullable=True)
    last_item_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    # Set once an advisor brief has been generated + delivered for this event,
    # so the synthesis job never re-briefs the same story.
    briefed = Column(Boolean, nullable=False, default=False)


class Tool(Base):
    """A non-model AI tool/platform (e.g. Claude Code, Cursor) to recommend."""

    __tablename__ = "tools"

    id = Column(String, primary_key=True)  # slug, e.g. "claude-code"
    company_id = Column(String, ForeignKey("companies.id"), nullable=True, index=True)
    name = Column(String, nullable=False)
    use_case = Column(JSON, nullable=False, default=list)
    description = Column(Text, nullable=True)
    url = Column(String, nullable=True)
    last_updated = Column(DateTime, nullable=False, default=_utcnow)


class Leaderboard(Base):
    """Materialized leaderboard snapshot — one row per use-case.

    Read directly by the Telegram commands (cheap, no LLM at query time).
    """

    __tablename__ = "leaderboards"

    use_case = Column(String, primary_key=True)  # coding/agents/.../overall/value
    ranking_json = Column(JSON, nullable=False, default=list)  # [{model_id, score, rank, rationale}]
    methodology_note = Column(Text, nullable=True)
    computed_at = Column(DateTime, nullable=False, default=_utcnow)
