# 12 — Tech Stack & Dependencies

## Runtime Requirements

- **Python 3.11+** — required for `asyncio.TaskGroup`, modern type hints, and `tomllib`

## Core Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `anthropic` | ≥0.39, <1.0 | Anthropic SDK — async Claude API client |
| `pydantic` | ≥2.9, <3.0 | Data validation for RawItem, UpdateItem models |
| `pydantic-settings` | ≥2.6, <3.0 | Settings management with `AIJU_` env prefix |
| `sqlalchemy[asyncio]` | ≥2.0.36, <3.0 | Async ORM for SQLite persistence |
| `aiosqlite` | ≥0.20, <1.0 | Async SQLite driver for SQLAlchemy |
| `aiohttp` | ≥3.11, <4.0 | Async HTTP client for all source fetching |
| `aiofiles` | ≥24.1, <25.0 | Async file I/O operations |
| `python-telegram-bot` | ≥21.7, <22.0 | Telegram Bot API for message delivery |
| `structlog` | ≥24.4, <25.0 | Structured logging with key-value pairs |
| `tenacity` | ≥9.0, <10.0 | Retry logic with exponential backoff |

## Parsing & Processing

| Package | Version | Purpose |
|---------|---------|---------|
| `feedparser` | ≥6.0.11, <7.0 | RSS/Atom feed parsing (used by RSS, Podcast, Telegram agents) |
| `beautifulsoup4` | ≥4.12.3, <5.0 | HTML parsing and text extraction |
| `lxml` | ≥5.3, <6.0 | Fast HTML/XML parser backend for BeautifulSoup |
| `xxhash` | ≥3.5, <4.0 | Fast content fingerprinting (xxh64) for deduplication |

## Configuration & Utilities

| Package | Version | Purpose |
|---------|---------|---------|
| `python-dotenv` | ≥1.0.1, <2.0 | Load `.env` files into environment |
| `pyyaml` | ≥6.0.2, <7.0 | Parse `sources.yaml` and `watchlist.yaml` |
| `httpx` | ≥0.28, <1.0 | Modern HTTP client (used alongside aiohttp) |

## Why These Choices

### Anthropic SDK over raw HTTP
The official SDK handles auth, retries, streaming, and type safety. Using it directly avoids reimplementing API quirks.

### Pydantic v2 over dataclasses
Pydantic provides runtime validation, JSON serialization, and type coercion. The v2 rewrite (Rust core) is significantly faster than v1.

### SQLAlchemy async over raw SQL
The ORM provides migration-ready schema definitions, type-safe queries, and the `merge()` pattern for upserts. The async engine avoids blocking the event loop.

### aiosqlite over PostgreSQL
SQLite is zero-config, file-based, and sufficient for single-instance operation. If scaling to multiple workers, swap the `DATABASE_URL` to PostgreSQL.

### xxhash over SHA-256
xxhash (xxh64) is ~10× faster than SHA-256 for non-cryptographic hashing. Deduplication doesn't need collision resistance — it needs speed.

### structlog over stdlib logging
Structured key-value logs are grep-friendly, JSON-serializable, and easier to parse in log aggregators than formatted strings.

### feedparser over raw XML
feedparser handles RSS 0.9x, 1.0, 2.0, Atom 0.3, Atom 1.0, CDF, and various edge cases. Reimplementing this would be fragile.

### BeautifulSoup + lxml over regex
HTML is not a regular language. BS4 + lxml handles malformed HTML, character encoding, and entity decoding correctly.

## Architecture Patterns

| Pattern | Where Used |
|---------|-----------|
| Lazy singleton | ClaudeClient, TelegramBot (avoid validation at import) |
| Module-level singleton | `db`, `cache`, `router`, `claude_client`, `telegram_bot` |
| Abstract base class | BaseAgent with abstract `collect()` |
| TTL cache | In-memory deduplication with automatic expiry |
| Two-level lookup | Cache (fast) → Database (persistent) for fingerprints |
| Exponential backoff | Claude API, Telegram API via tenacity |
| Batched delivery | Router queues for GENERAL (5-min) and WATCHLIST (15-min) |
| Graceful shutdown | SIGINT/SIGTERM handlers stop agents and flush queues |
| Pipeline pattern | normalize → deduplicate → analyze → filter → route → deliver |
