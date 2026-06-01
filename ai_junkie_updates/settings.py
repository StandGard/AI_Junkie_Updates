"""Application settings loaded from environment variables with AIJU_ prefix."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

# .env lives alongside this module (see .env.example), independent of CWD.
_ENV_FILE = Path(__file__).resolve().parent / ".env"


class Settings(BaseSettings):
    """All configuration for AI Junkie Updates, sourced from env vars."""

    model_config = SettingsConfigDict(
        env_prefix="AIJU_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required
    ANTHROPIC_API_KEY: str = ""
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHANNEL_CRITICAL: str = ""
    TELEGRAM_CHANNEL_HIGH: str = ""
    TELEGRAM_CHANNEL_GENERAL: str = ""
    TELEGRAM_CHANNEL_WATCHLIST: str = ""

    # Optional with defaults
    DATABASE_URL: str = "sqlite+aiosqlite:///storage/aiju.db"
    CACHE_TTL_SECONDS: int = 86400
    SCORE_THRESHOLD_DELIVER: int = 50
    SCORE_THRESHOLD_WATCHLIST: int = 40
    POLL_INTERVAL_SECONDS: int = 300
    MAX_CONCURRENT_AGENTS: int = 5
    CLAUDE_MODEL: str = "claude-opus-4-5"
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
