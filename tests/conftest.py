"""Shared pytest fixtures.

Every test runs against a fresh, isolated in-memory-style SQLite database in a
temp file. Because the codebase uses module-level singletons (``db``,
``knowledge_base``, and the ``db`` references captured inside the intelligence
modules), the ``kb`` fixture rebinds them all to the test engine so the whole
stack operates on one throwaway database per test.
"""

from __future__ import annotations

import os
import tempfile

import pytest
import pytest_asyncio

# Dummy credentials so Settings() loads without a real environment.
os.environ.setdefault("AIJU_ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("AIJU_TELEGRAM_BOT_TOKEN", "test-token")


@pytest_asyncio.fixture
async def database():
    """A fresh DatabaseManager backed by a temp SQLite file, schema initialised."""
    from ai_junkie_updates.core.database import DatabaseManager

    path = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    db = DatabaseManager(url=f"sqlite+aiosqlite:///{path}")
    await db.init_db()
    await db.ensure_kb_schema()

    # Rebind the global ``db`` singleton and the references the intelligence
    # modules captured at import time, so everything shares this test engine.
    import ai_junkie_updates.core.database as dbmod
    import ai_junkie_updates.intelligence.entity_linker as elmod
    import ai_junkie_updates.intelligence.clustering as clmod

    dbmod.db._engine = db._engine
    dbmod.db._session_factory = db._session_factory
    elmod.db = db
    clmod.db = db

    try:
        yield db
    finally:
        await db.close()
        try:
            os.unlink(path)
        except OSError:
            pass


@pytest_asyncio.fixture
async def kb(database):
    """A KnowledgeBase on the test DB, with the global singleton rebound too."""
    from ai_junkie_updates.intelligence.knowledge_base import KnowledgeBase
    import ai_junkie_updates.intelligence.knowledge_base as kbmod

    knowledge = KnowledgeBase(session_factory=database.session_factory)
    kbmod.knowledge_base._sf = database.session_factory
    return knowledge


@pytest_asyncio.fixture
async def seeded_kb(kb):
    """A KnowledgeBase pre-loaded from the bundled seed_entities.yaml."""
    await kb.seed_from_yaml()
    return kb
