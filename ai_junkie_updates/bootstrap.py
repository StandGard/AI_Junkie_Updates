"""Bootstrap — validate settings, initialise database, warm up singletons."""

from __future__ import annotations

from ai_junkie_updates.core.cache import cache
from ai_junkie_updates.core.claude_client import claude_client
from ai_junkie_updates.core.database import db
from ai_junkie_updates.delivery.telegram_bot import telegram_bot
from ai_junkie_updates.settings import settings
from ai_junkie_updates.utils.logger import get_logger

log = get_logger(__name__)


async def bootstrap() -> dict:
    """Validate configuration, create tables, and return initialised singletons."""
    # Hard-exit if required vars are missing
    settings.validate_required()

    # Initialise database (create tables)
    await db.init_db()

    # Warm up the cache singleton (triggers lazy init)
    cache.cleanup()

    log.info(
        "bootstrap_complete",
        project="AI Junkie Updates",
        database=settings.DATABASE_URL,
        claude_model=settings.CLAUDE_MODEL,
        log_level=settings.LOG_LEVEL,
        max_agents=settings.MAX_CONCURRENT_AGENTS,
        poll_interval=settings.POLL_INTERVAL_SECONDS,
    )

    return {
        "db": db,
        "cache": cache,
        "claude_client": claude_client,
        "telegram_bot": telegram_bot,
    }
