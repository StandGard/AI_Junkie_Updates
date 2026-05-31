# AI Junkie Updates

A personal **AI performance advisor** delivered through Telegram. It continuously
monitors the AI industry across 15+ source types, analyses every item through
Claude, and — beyond just relaying news — maintains a **knowledge base** of
models, prices, and benchmarks to tell you *what changed, why it matters, who
should care, and whether you should switch tools or models*.

## What it answers

Ask it on demand from Telegram, or receive it in daily/weekly digests:

- **Best models per use-case** — coding, agents, app-dev, automation, content,
  video, research, business, value-for-money, overall.
- **Should I switch?** — compares your current stack against the live leaderboards.
- **What changed** — clustered, significance-ranked events (one story, many sources).
- **Model facts** — pricing, context window, benchmarks, side-by-side comparisons.

## Architecture

```
                 15+ source types (RSS, GitHub, Reddit, YouTube, X, status pages,
                 regulators, podcasts, on-chain, press, changelogs, API feeds…)
                         │
        ┌────────────────▼─────────────────┐
        │  Ingestion + triage pipeline      │   collect → normalize → dedup →
        │  (cheap Claude model, per item)   │   pre-LLM gate → analyze → filter →
        └────────────────┬─────────────────┘   route → Telegram alerts
                         │  persisted to SQLite (updates)
        ┌────────────────▼─────────────────┐
        │  Intelligence layer (periodic)    │   entity-link → cluster (events) →
        │  jobs.py on asyncio timers        │   ingest pricing/benchmarks → rank →
        │                                   │   synthesize (strong Claude model)
        └────────────────┬─────────────────┘
                         │  knowledge base: companies, models, prices,
                         │  benchmarks, capabilities, events, tools, leaderboards
        ┌────────────────▼─────────────────┐
        │  Telegram                         │   • alerts & advisor briefs (push)
        │  outbound bot + command bot       │   • /best /model /compare /switch
        │                                   │   • daily + weekly digests
        └───────────────────────────────────┘
```

**Two delivery surfaces, one bot token:**
- **Outbound** — tiered alerts (Critical/High/General/Watchlist), advisor briefs,
  and scheduled digests, rate-limited.
- **Inbound command bot** — owner-gated slash commands answered as pure
  knowledge-base reads (no LLM at query time, so they're instant and free).

## Telegram commands

| Command | Returns |
|---|---|
| `/leaderboard` | All available leaderboards |
| `/best <area>` | Ranked models for coding/agents/video/value/… (synonyms accepted) |
| `/model <name>` | Model card: price, context, modality, benchmarks |
| `/compare <a> <b>` | Two models side-by-side |
| `/whatschanged [24h\|week]` | Recent significant events |
| `/switch` | "Should I switch?" advice vs your `profile.yaml` |
| `/digest` | On-demand synthesized digest |
| `/status` · `/help` | System state / command list |

## Cost control

- **Model tiering** — a cheap model triages every item; the strong model is
  reserved for periodic synthesis/digests only (`AIJU_CLAUDE_TRIAGE_MODEL` /
  `AIJU_CLAUDE_SYNTHESIS_MODEL`).
- **Prompt caching** on the stable system prompt; **pre-LLM keyword gate** drops
  obvious noise before any Claude call.
- **Structured data bypasses the LLM** — pricing/benchmarks go straight to the KB.
- **Restart-safe dedup** + per-source poll intervals keep call volume down.
- `AIJU_ENABLE_SYNTHESIS=false` runs collection-only for the lowest spend.

## Setup

```bash
cp ai_junkie_updates/.env.example .env   # fill in keys (see below)
docker compose up -d --build             # single always-on service
```

Or run locally:

```bash
pip install --no-deps feedparser          # works around sgmllib3k on 3.11
pip install -r ai_junkie_updates/requirements.txt
python -m ai_junkie_updates.main
```

### Required environment variables

| Variable | Description |
|---|---|
| `AIJU_ANTHROPIC_API_KEY` | Anthropic API key |
| `AIJU_TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather |
| `AIJU_TELEGRAM_CHANNEL_CRITICAL/HIGH/GENERAL/WATCHLIST` | Channel IDs per alert tier |
| `AIJU_TELEGRAM_ADMIN_CHAT_ID` | Your chat ID — restricts commands to you |

Optional source keys (Twitter/GitHub/Crunchbase/NewsAPI) and tuning
(`AIJU_DIGEST_HOUR`, `AIJU_RETENTION_DAYS`, …) are documented in `.env.example`.
Sources without a key are skipped gracefully. X/Twitter also works key-free via
the `rss_bridge` block (RSSHub/Nitter, best-effort).

## Health & operations

- Health server: `GET /health` (liveness) and `GET /ready` (200 once the KB is
  seeded, else 503) on `AIJU_HEALTH_CHECK_PORT` (default 8585). The container
  `HEALTHCHECK` and `restart: unless-stopped` keep it always-on.
- Data retention: event-linked raw items older than `AIJU_RETENTION_DAYS` are
  pruned daily (the clustered event rows keep the knowledge).

## Configuration

- `config/sources.yaml` — all sources per agent (rss, youtube, rss_bridge,
  github, reddit, api_feed incl. status pages, …).
- `config/seed_entities.yaml` — tracked companies, models, tools, benchmarks.
- `config/ranking.yaml` — per-use-case leaderboard weights (benchmark/recency/price).
- `config/profile.yaml` — your current stack + priorities, for switch advice.

## Tests

```bash
pytest -q        # 42 tests; CI runs them on every push (.github/workflows/ci.yml)
```

## Tech stack

Python 3.11+ async · Anthropic SDK (prompt caching + model tiering) · Pydantic v2 ·
SQLAlchemy async + aiosqlite · aiohttp · python-telegram-bot · feedparser ·
BeautifulSoup/lxml · structlog · xxhash · tenacity · pytest/pytest-asyncio · Docker.

See `docs/MINDMAP.md` for a full component map and `docs/wiki/` for deep-dives.
