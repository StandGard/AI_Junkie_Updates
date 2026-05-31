"""Application settings loaded from environment variables with AIJU_ prefix."""

from __future__ import annotations

import sys
from typing import Optional

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """All configuration for AI Junkie Updates, sourced from env vars."""

    model_config = {"env_prefix": "AIJU_"}

    # Required
    ANTHROPIC_API_KEY: str = ""
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHANNEL_CRITICAL: str = ""
    TELEGRAM_CHANNEL_HIGH: str = ""
    TELEGRAM_CHANNEL_GENERAL: str = ""
    TELEGRAM_CHANNEL_WATCHLIST: str = ""

    # Personal chat ID — restricts interactive bot commands to the owner (Phase 2)
    TELEGRAM_ADMIN_CHAT_ID: str = ""

    # Optional with defaults
    DATABASE_URL: str = "sqlite+aiosqlite:///storage/aiju.db"
    CACHE_TTL_SECONDS: int = 86400
    SCORE_THRESHOLD_DELIVER: int = 50
    SCORE_THRESHOLD_WATCHLIST: int = 40
    POLL_INTERVAL_SECONDS: int = 300
    MAX_CONCURRENT_AGENTS: int = 5
    # Model tiering: a cheap model handles per-item triage (the bulk of calls);
    # a stronger model is reserved for periodic synthesis/digests (Phase 1).
    CLAUDE_TRIAGE_MODEL: str = "claude-haiku-4-5-20251001"
    CLAUDE_SYNTHESIS_MODEL: str = "claude-sonnet-4-6"
    LOG_LEVEL: str = "INFO"

    # Intelligence-layer scheduling (seconds). Entity-linking + clustering run
    # frequently and cheaply; ranking + synthesis run less often.
    LINK_CLUSTER_INTERVAL_SECONDS: int = 600       # 10 min
    RANKING_INTERVAL_SECONDS: int = 86400          # daily
    SYNTHESIS_INTERVAL_SECONDS: int = 3600         # hourly event briefs
    DIGEST_INTERVAL_SECONDS: int = 86400           # daily digest (fallback cadence)
    # Calendar-aligned digest delivery (local-time hour, 0-23). The daily digest
    # fires at DIGEST_HOUR; a weekly roll-up fires at DIGEST_HOUR on the weekday
    # given by WEEKLY_DIGEST_DOW (0=Monday). Set DIGEST_USE_CLOCK=false to fall
    # back to plain interval scheduling.
    DIGEST_USE_CLOCK: bool = True
    DIGEST_HOUR: int = 8
    WEEKLY_DIGEST_DOW: int = 0
    # Minimum event significance to trigger an advisor brief / digest delivery.
    BRIEF_MIN_SIGNIFICANCE: int = 70
    # Set false to run collection only, with no LLM synthesis (cost control).
    ENABLE_SYNTHESIS: bool = True

    # Data retention: prune raw `updates` older than this once they belong to an
    # event (set to 0 to disable). Keeps the SQLite DB bounded on a small VPS.
    RETENTION_DAYS: int = 60
    RETENTION_INTERVAL_SECONDS: int = 86400        # prune sweep cadence

    # Health-check HTTP server (for container/uptime monitoring).
    HEALTH_CHECK_ENABLED: bool = True
    HEALTH_CHECK_PORT: int = 8585

    def validate_required(self) -> None:
        """Hard-exit if required variables are missing."""
        missing: list[str] = []
        if not self.ANTHROPIC_API_KEY:
            missing.append("AIJU_ANTHROPIC_API_KEY")
        if not self.TELEGRAM_BOT_TOKEN:
            missing.append("AIJU_TELEGRAM_BOT_TOKEN")
        if missing:
            print(
                f"FATAL: Missing required environment variables: {', '.join(missing)}",
                file=sys.stderr,
            )
            sys.exit(1)


settings = Settings()
