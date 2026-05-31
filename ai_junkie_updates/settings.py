"""Application settings loaded from environment variables with AIJU_ prefix.

Loads ``ai_junkie_updates/.env`` (if present) at import time so credentials work
for BOTH run paths:
  * ``python -m ai_junkie_updates.main``  — .env -> os.environ via python-dotenv
  * ``docker compose up``                 — .env loaded by compose's env_file

load_dotenv populates os.environ, which matters for the non-AIJU_ secrets
(TWITTER_BEARER_TOKEN, GITHUB_TOKEN, CRUNCHBASE_API_KEY, ...) that
``load_sources()`` expands from ``${VAR}`` placeholders in sources.yaml.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent / ".env"

# Populate os.environ from .env if it exists (no-op when the file is absent, so
# real OS env vars / Docker env_file still work unchanged).
load_dotenv(_ENV_FILE)


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
    CLAUDE_MODEL: str = "claude-opus-4-7"
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
