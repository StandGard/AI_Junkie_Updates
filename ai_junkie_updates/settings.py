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
