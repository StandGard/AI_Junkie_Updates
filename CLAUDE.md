# CLAUDE.md — Session Memory for AI Junkie Updates

> This file allows any new Claude session to pick up where the last one left off.
> Read this file first when starting a new chat about this project.

## Project Identity

- **Name**: AI Junkie Updates
- **Repo**: `standgard/ai_junkie_updates` (GitHub)
- **Branch**: `claude/setup-ai-junkie-structure-dVcM7`
- **Ecosystem**: Part of the broader **Antigravity** project
- **Language**: Python 3.11+ (full async/await)
- **Purpose**: Real-time AI industry intelligence aggregator — monitors 13 source types, analyzes every item through Claude AI, delivers tiered alerts to Telegram channels

## Project Status

**Phase**: Initial build complete. All code written and imports verified. No tests yet.

### What's Done
- 72 source files (~3,600 lines of Python) — fully implemented, no stubs
- 13 async source agents (Twitter, RSS, Web Scraper, Changelog, GitHub, Reddit, Discord, Onchain, Telegram Channels, Press Releases, Podcast, Regulatory, API Feed)
- Full pipeline: collect → normalize → deduplicate → analyze (Claude AI) → filter → route → deliver
- Telegram delivery with 4 channels (Critical/High/General/Watchlist), rate limiting, HTML formatting
- SQLite persistence via async SQLAlchemy, in-memory TTL cache for deduplication
- YAML configuration for sources and watchlist
- Pydantic v2 models and settings with AIJU_ env prefix
- Wiki documentation: 13 pages in `docs/wiki/`
- TODO.md with completed items and backlog

### What's NOT Done
- No tests (unit, integration, or e2e)
- No Docker/CI/CD
- No web dashboard or REST API
- No database migrations (Alembic)
- PDF project overview document (fpdf2 installed but script not written)

## Architecture Quick Reference

```
13 Agents → Normalize → Deduplicate → Claude Analysis → Filter → Route → Telegram
                                                                    ↓
                                                              SQLite DB
```

**Scoring**: 90+ = Critical (instant), 70-89 = High (instant), 50-69 = General (5-min batch), 40-49 = Watchlist (15-min batch, only if watchlist match), <40 = Dropped

## Key File Locations

| What | Where |
|------|-------|
| Entrypoint | `ai_junkie_updates/main.py` |
| Settings | `ai_junkie_updates/settings.py` (AIJU_ prefix) |
| Enums & constants | `ai_junkie_updates/constants.py` |
| Data models | `ai_junkie_updates/core/models.py` |
| Database | `ai_junkie_updates/core/database.py` |
| Cache | `ai_junkie_updates/core/cache.py` |
| Claude client | `ai_junkie_updates/core/claude_client.py` |
| System prompt | `ai_junkie_updates/core/prompts/system_prompt.py` |
| Pipeline stages | `ai_junkie_updates/pipeline/` (normalizer, deduplicator, filter_engine, router) |
| Base agent | `ai_junkie_updates/agents/base_agent.py` |
| Agent implementations | `ai_junkie_updates/agents/{name}/agent.py` |
| Agent prompts | `ai_junkie_updates/agents/{name}/prompt.py` |
| Telegram bot | `ai_junkie_updates/delivery/telegram_bot.py` |
| Message formatter | `ai_junkie_updates/delivery/formatter.py` |
| Source config | `ai_junkie_updates/config/sources.yaml` |
| Watchlist config | `ai_junkie_updates/config/watchlist.yaml` |
| Env template | `ai_junkie_updates/.env.example` |
| Dependencies | `ai_junkie_updates/requirements.txt` |
| Wiki docs | `docs/wiki/` (13 pages, start at 00-INDEX.md) |

## Singletons

These are module-level instances created at import time (with lazy initialization where noted):

| Singleton | Module | Notes |
|-----------|--------|-------|
| `settings` | `settings.py` | Pydantic-settings, loaded from env |
| `db` | `core/database.py` | Async SQLAlchemy engine |
| `cache` | `core/cache.py` | In-memory TTL cache |
| `claude_client` | `core/claude_client.py` | **Lazy** — client created on first `analyze()` call |
| `telegram_bot` | `delivery/telegram_bot.py` | **Lazy** — Bot created on first `send()` call |
| `router` | `pipeline/router.py` | Manages delivery queues |

## Known Issues & Workarounds

1. **sgmllib3k build failure**: feedparser's dependency sgmllib3k fails to build on Python 3.11. Workaround: install feedparser with `--no-deps`, then manually extract `sgmllib.py` from the source tarball into site-packages.

2. **cffi/_cffi_backend missing**: python-telegram-bot needs cryptography which needs cffi. Fix: `pip install cffi cryptography`.

3. **Token validation at import**: Both `telegram.Bot()` and `anthropic.AsyncAnthropic()` validate tokens on construction. Since module-level singletons are created at import time, empty tokens cause crashes. Fix: lazy initialization via `_ensure_bot()` and `_ensure_client()` methods.

## Development Commands

```bash
# Verify all imports
python -c "import ai_junkie_updates.main"

# Run the system
python -m ai_junkie_updates.main

# Check individual modules
python -c "from ai_junkie_updates.core.models import RawItem, UpdateItem"
python -c "from ai_junkie_updates.pipeline.normalizer import Normalizer"
python -c "from ai_junkie_updates.agents.twitter import TwitterAgent"

# Query the database
sqlite3 ai_junkie_updates/storage/aiju.db "SELECT headline, score FROM updates ORDER BY analyzed_at DESC LIMIT 10"
```

## Conventions

- **Env vars**: Always `AIJU_` prefix
- **Logging**: structlog with `get_logger(__name__)`, event-based (`log.info("event_name", key=value)`)
- **Error handling**: Try/except in agents and pipeline; log warnings/errors; never crash the loop
- **Cache keys**: Agent-prefixed (e.g., `rss:{id}`, `github:{repo}:{id}`, `onchain:{name}:{id}`)
- **Async**: Everything is async. No threads, no blocking calls.
- **Models**: Pydantic for validation, SQLAlchemy ORM for persistence, conversion methods on UpdateRecord
- **Retry**: tenacity with 3 attempts, exponential backoff for Claude and Telegram APIs

## Git Workflow

- **Branch**: `claude/setup-ai-junkie-structure-dVcM7`
- **Remote**: `origin` → `standgard/ai_junkie_updates`
- **Commit style**: `feat:`, `fix:`, `docs:`, `test:`, `chore:` prefixes
- Always push to the feature branch, never to main directly
