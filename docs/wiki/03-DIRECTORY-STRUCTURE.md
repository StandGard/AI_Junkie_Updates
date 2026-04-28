# 03 — Directory Structure

```
AI_Junkie_Updates/
├── docs/
│   └── wiki/                          # This documentation
│       ├── 00-INDEX.md
│       ├── 01-PROJECT-OVERVIEW.md
│       ├── 02-ARCHITECTURE.md
│       ├── 03-DIRECTORY-STRUCTURE.md
│       ├── 04-CORE-MODULES.md
│       ├── 05-PIPELINE.md
│       ├── 06-AGENTS.md
│       ├── 07-DELIVERY.md
│       ├── 08-CONFIGURATION.md
│       ├── 09-UTILITIES.md
│       ├── 10-RUNNING-AND-OPERATIONS.md
│       ├── 11-ADDING-NEW-AGENT.md
│       └── 12-TECH-STACK.md
│
├── CLAUDE.md                          # Session memory for AI continuity
├── TODO.md                            # Task tracking and roadmap
│
└── ai_junkie_updates/                 # Main package
    ├── __init__.py                    # Package docstring
    ├── main.py                        # Async entrypoint — boots system, runs agents
    ├── bootstrap.py                   # Validates settings, inits DB, warms singletons
    ├── settings.py                    # Pydantic-settings with AIJU_ env prefix
    ├── constants.py                   # Enums (SourceType, UpdateCategory, etc.) + thresholds
    ├── requirements.txt               # Python dependencies
    ├── .env.example                   # Template for environment variables
    ├── README.md                      # Quick-start guide
    │
    ├── config/                        # YAML configuration files
    │   ├── sources.yaml               # All source URLs/APIs for 13 agents
    │   └── watchlist.yaml             # Companies, models, topics to track
    │
    ├── core/                          # Core system components
    │   ├── __init__.py
    │   ├── models.py                  # RawItem, UpdateItem (Pydantic) + UpdateRecord (ORM)
    │   ├── database.py                # Async SQLAlchemy database manager
    │   ├── cache.py                   # In-memory TTL cache for deduplication
    │   ├── claude_client.py           # Async Anthropic API client
    │   └── prompts/
    │       ├── __init__.py
    │       └── system_prompt.py       # Master system prompt for Claude analysis
    │
    ├── pipeline/                      # Processing pipeline stages
    │   ├── __init__.py
    │   ├── normalizer.py              # HTML strip, whitespace collapse, truncate
    │   ├── deduplicator.py            # xxhash fingerprint, cache + DB check
    │   ├── filter_engine.py           # Score thresholds + watchlist matching
    │   └── router.py                  # Batched delivery queues + flush loops
    │
    ├── agents/                        # Source collection agents
    │   ├── __init__.py
    │   ├── base_agent.py              # Abstract base class with full pipeline
    │   ├── twitter/
    │   │   ├── __init__.py
    │   │   ├── agent.py               # Twitter API v2 search
    │   │   └── prompt.py              # Source-specific analysis guidance
    │   ├── rss/                       # RSS feed polling (feedparser)
    │   ├── web_scraper/               # HTML page scraping (BeautifulSoup)
    │   ├── changelog/                 # Product changelog parsing
    │   ├── github/                    # GitHub Releases API
    │   ├── reddit/                    # Reddit JSON API
    │   ├── discord/                   # Webhook receiver (HTTP server)
    │   ├── onchain/                   # Blockchain API polling
    │   ├── telegram_channels/         # Telegram channel monitoring
    │   ├── press_releases/            # PR newswire scraping
    │   ├── podcast/                   # Podcast RSS feed polling
    │   ├── regulatory/                # Government website scraping
    │   └── api_feed/                  # Structured JSON API consumption
    │
    ├── delivery/                      # Output delivery
    │   ├── __init__.py
    │   ├── formatter.py               # HTML message formatting for Telegram
    │   └── telegram_bot.py            # Rate-limited Telegram message delivery
    │
    ├── storage/                       # SQLite database location (created at runtime)
    │
    └── utils/                         # Shared utilities
        ├── __init__.py
        ├── fingerprint.py             # xxhash content fingerprinting
        ├── text_cleaner.py            # HTML cleaning, whitespace, truncation
        └── logger.py                  # structlog configuration
```

## File Count Summary

| Directory | Files | Description |
|-----------|-------|-------------|
| `ai_junkie_updates/` (root) | 7 | Settings, constants, bootstrap, main, init, requirements, env |
| `config/` | 2 | YAML source and watchlist configuration |
| `core/` | 6 | Models, database, cache, Claude client, prompts |
| `pipeline/` | 5 | Normalizer, deduplicator, filter, router, init |
| `agents/` | 42 | Base agent + 13 agents × 3 files each (agent, prompt, init) + init |
| `delivery/` | 3 | Formatter, Telegram bot, init |
| `utils/` | 4 | Fingerprint, text cleaner, logger, init |
| `docs/wiki/` | 13 | This documentation |
| **Total** | **~85** | |
