# CLAUDE.md — Session Memory for AI Junkie Updates

> This file allows any new Claude session to pick up where the last one left off.
> Read this file first when starting a new chat about this project.

## Project Identity

- **Name**: AI Junkie Updates
- **Repo**: `standgard/ai_junkie_updates` (GitHub)
- **Branch**: `claude/jolly-mendel-P6fsR`
- **Ecosystem**: Part of the broader **Antigravity** project
- **Language**: Python 3.11+ (full async/await)
- **Purpose**: A personal **AI performance advisor** on Telegram. Monitors 15+ source types, triages each item through a cheap Claude model, builds a knowledge base of models/prices/benchmarks, and delivers advisor briefs + leaderboards ("what changed, why it matters, should you switch?") via push alerts, scheduled digests, and on-demand bot commands.

## Project Status

**Phase**: All 4 build phases complete. ~6,000 lines of Python, 42 passing tests, Dockerised, CI on every push. Not yet run live (needs real API keys).

### What's Done
- **Collection** — 13 source agents + config-driven YouTube (RSS), X-via-RSS-bridge, and provider status pages (15+ source types total)
- **Triage pipeline** — collect → normalize → pre-LLM gate → dedup (restart-safe) → analyze (cheap Claude model, prompt-cached, per-agent context) → filter → route → tiered Telegram alerts
- **Intelligence layer** (`intelligence/`) — entity linking → story clustering (events) → pricing/benchmark ingestion → ranking engine (10 leaderboards) → advisor synthesis (strong Claude model) → orchestrated on asyncio timers in `jobs.py`
- **Knowledge base** — `core/kb_models.py`: companies, models, model_prices, benchmarks, benchmark_scores, capabilities, events, tools, leaderboards (+ `event_id`/`entity_ids` on `updates`)
- **Interactive Telegram** — `delivery/command_bot.py`: `/best`, `/model`, `/compare`, `/whatschanged`, `/switch`, `/leaderboard`, `/digest`, `/status` (owner-gated, pure KB reads); calendar-aligned daily + weekly digests
- **Cost control** — model tiering, prompt caching, pre-LLM gate, structured data bypasses the LLM, per-source poll intervals
- **Reliability** — 42 pytest tests (`tests/`), `Dockerfile` + `docker-compose.yml` (`restart: unless-stopped`), health server (`health.py`, `/health` + `/ready`), retention/prune job, GitHub Actions CI (`.github/workflows/ci.yml`)

### What's NOT Done
- Never run live end-to-end (needs Anthropic + Telegram keys; benchmark-leaderboard URLs are fail-soft best-guesses needing validation vs live HF Spaces)
- No Alembic (idempotent `ensure_kb_schema()` ALTERs are used instead)
- No web dashboard / REST API (intentional — Telegram-only product)
- YouTube RSS carries title/description only (no transcripts)

## Architecture Quick Reference

```
15+ sources → [triage pipeline: normalize → gate → dedup → cheap-Claude analyze
              → filter → route → tiered Telegram alerts] → SQLite `updates`
                         ↓ (periodic jobs.py timers)
   entity-link → cluster(events) → ingest prices/benchmarks → rank(leaderboards)
              → synthesize briefs/digests (strong Claude) → Telegram
                         ↑ command_bot answers /best /model /switch from the KB
```

**Alert scoring**: 90+ = Critical (instant), 70-89 = High (instant), 50-69 = General (5-min batch), 40-49 = Watchlist (15-min batch, only if watchlist match), <40 = Dropped
**Ranking** (per use-case, deterministic): weighted blend of normalized benchmark score + recency decay + inverted price, weights in `config/ranking.yaml`.

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
| Agent prompts | `ai_junkie_updates/agents/{name}/prompt.py` (wired into triage via base_agent) |
| **KB ORM models** | `ai_junkie_updates/core/kb_models.py` |
| **Intelligence layer** | `ai_junkie_updates/intelligence/` (knowledge_base, entity_linker, clustering, ingest, ranking_engine, synthesis, jobs) |
| **Synthesis prompts** | `ai_junkie_updates/core/prompts/synthesis_prompt.py` |
| Telegram outbound bot | `ai_junkie_updates/delivery/telegram_bot.py` (send + send_text) |
| **Telegram command bot** | `ai_junkie_updates/delivery/command_bot.py` |
| Message formatter | `ai_junkie_updates/delivery/formatter.py` (+ leaderboard/model/event/switch) |
| **Health server** | `ai_junkie_updates/health.py` (`/health`, `/ready`) |
| Source config | `ai_junkie_updates/config/sources.yaml` (rss, youtube, rss_bridge, api_feed incl. status…) |
| Watchlist config | `ai_junkie_updates/config/watchlist.yaml` |
| **Seed entities** | `ai_junkie_updates/config/seed_entities.yaml` |
| **Ranking weights** | `ai_junkie_updates/config/ranking.yaml` |
| **User profile** | `ai_junkie_updates/config/profile.yaml` (drives switch advice) |
| Env template | `ai_junkie_updates/.env.example` |
| Dependencies | `ai_junkie_updates/requirements.txt` |
| **Tests** | `tests/` (42 tests, `pytest -q`); CI: `.github/workflows/ci.yml` |
| **Container** | `Dockerfile`, `docker-compose.yml` |
| Wiki docs | `docs/wiki/` (13 pages); full map: `docs/MINDMAP.md` |

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
# Run the full test suite (42 tests). Set dummy keys so Settings() loads.
AIJU_ANTHROPIC_API_KEY=x AIJU_TELEGRAM_BOT_TOKEN=y pytest -q

# Run the system (needs real keys in .env)
python -m ai_junkie_updates.main

# Run as an always-on container
docker compose up -d --build

# Health / readiness
curl localhost:8585/health
curl localhost:8585/ready

# Query the database
sqlite3 storage/aiju.db "SELECT headline, score FROM updates ORDER BY analyzed_at DESC LIMIT 10"
sqlite3 storage/aiju.db "SELECT use_case, computed_at FROM leaderboards"
```

> Note: `feedparser` needs `pip install --no-deps feedparser` on Python 3.11
> (its `sgmllib3k` dep fails to build); tests that touch RSS agents read the
> source as text to avoid importing it.

## Conventions

- **Env vars**: Always `AIJU_` prefix
- **Logging**: structlog with `get_logger(__name__)`, event-based (`log.info("event_name", key=value)`)
- **Error handling**: Try/except in agents and pipeline; log warnings/errors; never crash the loop
- **Cache keys**: Agent-prefixed (e.g., `rss:{id}`, `github:{repo}:{id}`, `onchain:{name}:{id}`)
- **Async**: Everything is async. No threads, no blocking calls.
- **Models**: Pydantic for validation, SQLAlchemy ORM for persistence, conversion methods on UpdateRecord
- **Retry**: tenacity with 3 attempts, exponential backoff for Claude and Telegram APIs

## Git Workflow

- **Branch**: `claude/jolly-mendel-P6fsR`
- **Remote**: `origin` → `standgard/ai_junkie_updates`
- **Commit style**: `feat:`, `fix:`, `docs:`, `test:`, `chore:` prefixes
- Always push to the feature branch, never to main directly
