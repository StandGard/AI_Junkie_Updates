# AI Junkie Updates

Real-time AI industry intelligence aggregator. Monitors 13 source types, analyses every item through Claude AI, and delivers actionable alerts to Telegram channels.

## Architecture

```
Sources (13 agents)
    │
    ▼
┌───────────────────────────────────────────────┐
│  Pipeline                                     │
│  collect → normalize → deduplicate → analyze  │
│          → filter → route → deliver           │
└───────────────────────────────────────────────┘
    │                       │
    ▼                       ▼
  SQLite DB            Telegram Channels
                    (Critical / High / General / Watchlist)
```

**Core components:**
- **Agents** — 13 async collectors, one per source type
- **Normalizer** — strips HTML, collapses whitespace, truncates to 8k chars
- **Deduplicator** — xxhash fingerprinting with in-memory cache + DB fallback
- **Claude Client** — sends raw content to Claude for structured JSON analysis
- **Filter Engine** — score thresholds + watchlist matching
- **Router** — batched delivery with immediate, 5-min, and 15-min queues
- **Telegram Bot** — rate-limited HTML message delivery

## Setup

```bash
# Clone the repository
git clone https://github.com/your-org/ai_junkie_updates.git
cd ai_junkie_updates

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r ai_junkie_updates/requirements.txt

# Configure environment
cp ai_junkie_updates/.env.example ai_junkie_updates/.env
# Edit .env and fill in your API keys and Telegram channel IDs
```

### Required environment variables

| Variable | Description |
|---|---|
| `AIJU_ANTHROPIC_API_KEY` | Anthropic API key |
| `AIJU_TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather |
| `AIJU_TELEGRAM_CHANNEL_CRITICAL` | Channel ID for critical alerts (score 90+) |
| `AIJU_TELEGRAM_CHANNEL_HIGH` | Channel ID for high-priority updates (score 70–89) |
| `AIJU_TELEGRAM_CHANNEL_GENERAL` | Channel ID for general updates (score 50–69) |
| `AIJU_TELEGRAM_CHANNEL_WATCHLIST` | Channel ID for watchlist matches (score 40–49) |

## Running

```bash
cd ai_junkie_updates
python -m ai_junkie_updates.main
```

The system starts all 13 agents concurrently (limited by `AIJU_MAX_CONCURRENT_AGENTS`, default 5) and runs continuously until interrupted with Ctrl+C or SIGTERM.

### Dry run (collect only, no Claude/Telegram)

To confirm that real sources parse correctly without spending Claude tokens or
sending Telegram messages:

```bash
python -m scripts.dry_run                 # every agent, once
python -m scripts.dry_run rss github      # specific agents
python -m scripts.dry_run --preview 200 rss
```

## Testing

```bash
pip install -r requirements-dev.txt
pytest
```

The suite (77 tests) covers the pipeline stages, core modules, the async
database manager (in-memory SQLite), agent `collect()` parsing (HTTP mocked via
aioresponses), and a full end-to-end pipeline run with Claude and Telegram
mocked.

## Agents

| Agent | Source Type | Description |
|---|---|---|
| Twitter | `twitter` | Twitter/X API v2 search for accounts and terms |
| RSS | `rss` | RSS feed polling (news sites, blogs, arXiv) |
| Web Scraper | `web_scraper` | HTML page scraping for company news pages |
| Changelog | `changelog` | Product changelog and release notes parsing |
| GitHub | `github` | GitHub Releases API for open-source repos |
| Reddit | `reddit` | Reddit JSON API for AI-focused subreddits |
| Discord | `discord` | Webhook receiver for Discord bot forwards |
| On-chain | `onchain` | Blockchain API polling for AI-related events |
| Telegram Channels | `telegram_channels` | RSS bridge or Bot API for Telegram channels |
| Press Releases | `press_releases` | PR newswire and company press page scraping |
| Podcast | `podcast` | Podcast RSS feed polling for new episodes |
| Regulatory | `regulatory` | Government and regulatory body website scraping |
| API Feed | `api_feed` | Structured JSON API consumption with pagination |

## Scoring System

Every collected item is analysed by Claude and assigned a score from 0 to 100:

| Score | Level | Delivery |
|---|---|---|
| 90–100 | Immediate | CRITICAL_ALERTS channel, delivered instantly |
| 70–89 | Important | HIGH_PRIORITY channel, delivered instantly |
| 50–69 | Worth knowing | GENERAL channel, batched every 5 min |
| 40–49 | Watchlist | WATCHLIST channel, only if tag/source matches watchlist |
| 0–39 | Noise | Dropped, saved to DB only |

## Telegram Channel Structure

Set up four Telegram channels and add your bot as an admin:

1. **Critical Alerts** — industry-changing events (score 90+)
2. **High Priority** — important updates (score 70–89)
3. **General** — worth-knowing updates (score 50–69)
4. **Watchlist** — minor items matching your watchlist (score 40–49)

## Configuration

- **`config/sources.yaml`** — all source URLs, API endpoints, and credentials per agent
- **`config/watchlist.yaml`** — companies, models, and topics to watch

## Adding a New Agent

1. Create a new directory under `agents/` with `__init__.py`, `agent.py`, and `prompt.py`
2. In `agent.py`, extend `BaseAgent` and implement `collect() -> List[RawItem]`
3. In `prompt.py`, define `AGENT_CONTEXT_PROMPT` with source-specific analysis guidance
4. Add the new source type to `SourceType` enum in `constants.py`
5. Add source configuration to `config/sources.yaml`
6. Import and instantiate the agent in `main.py`

## Tech Stack

- **Python 3.11+** with full async/await throughout
- **Anthropic SDK** — Claude API for content analysis
- **Pydantic v2** — data validation and settings management
- **SQLAlchemy (async)** — database ORM with aiosqlite
- **aiohttp** — async HTTP client for source fetching
- **python-telegram-bot** — Telegram delivery
- **structlog** — structured logging
- **xxhash** — fast content fingerprinting
- **BeautifulSoup + lxml** — HTML parsing
- **feedparser** — RSS/Atom feed parsing
- **tenacity** — retry logic with exponential backoff
