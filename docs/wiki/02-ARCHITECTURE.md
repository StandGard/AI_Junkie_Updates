# 02 — Architecture

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        main.py                                  │
│  bootstrap() → build agents → asyncio.gather() with semaphore  │
│  Graceful shutdown via SIGINT / SIGTERM handlers                │
└──────────────────────────┬──────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐       ┌────▼────┐       ┌────▼────┐
   │ Agent 1 │       │ Agent 2 │  ...  │ Agent 13│   (semaphore-limited)
   │ Twitter │       │   RSS   │       │ API Feed│
   └────┬────┘       └────┬────┘       └────┬────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                    ┌──────▼──────┐
                    │  Pipeline   │
                    │             │
                    │ normalize() │
                    │ deduplicate │
                    │ analyze()   │  ← Claude AI
                    │ filter()    │
                    │ route()     │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
         ┌────▼───┐  ┌────▼───┐  ┌────▼────┐
         │Immediate│  │ 5-min  │  │ 15-min  │
         │ Queue   │  │ Queue  │  │ Queue   │
         │CRIT/HIGH│  │GENERAL │  │WATCHLIST│
         └────┬───┘  └────┬───┘  └────┬────┘
              │            │            │
              └────────────┼────────────┘
                           │
                    ┌──────▼──────┐
                    │ Telegram Bot│
                    │ (rate-      │
                    │  limited)   │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
         ┌────▼────┐ ┌────▼────┐ ┌────▼────┐
         │Critical │ │  High   │ │ General │  + Watchlist
         │Alerts   │ │Priority │ │ Updates │
         └─────────┘ └─────────┘ └─────────┘
```

## Data Flow

### 1. Collection Phase
Each agent independently polls its sources on a configurable interval (default 300s). Agents run concurrently but are limited by `MAX_CONCURRENT_AGENTS` (default 5) via an asyncio Semaphore.

### 2. Normalization
Raw content is cleaned: HTML stripped, control characters removed, whitespace collapsed, truncated to 8,000 characters.

### 3. Deduplication
An xxhash fingerprint is computed from the normalized content. The system checks:
- **Fast path**: in-memory TTL cache (24h)
- **Slow path**: SQLite database

If the fingerprint exists in either, the item is silently dropped.

### 4. Analysis
The raw content is sent to Claude AI with a structured system prompt. Claude returns a JSON object containing:
- `is_relevant` (bool)
- `category` (one of 13 categories)
- `urgency` (CRITICAL / HIGH / MEDIUM / LOW)
- `score` (0–100)
- `headline`, `summary`, `reasoning`
- `tags` (list of strings)

### 5. Filtering
The filter engine applies score thresholds:
- Score ≥ 90 → CRITICAL_ALERTS
- Score ≥ 70 → HIGH_PRIORITY
- Score ≥ 50 → GENERAL
- Score ≥ 40 → WATCHLIST (only if tags/source match watchlist)
- Score < 40 → DROPPED

### 6. Routing & Delivery
The router manages three delivery strategies:
- **Immediate**: CRITICAL and HIGH items are sent instantly
- **5-minute batch**: GENERAL items are queued and flushed every 5 minutes (or when 10 accumulate)
- **15-minute batch**: WATCHLIST items are queued and flushed every 15 minutes

## Data Models

```
RawItem (Pydantic)              UpdateItem (Pydantic)
├── id: str (UUID4)             ├── id: str
├── source_type: SourceType     ├── source_type: SourceType
├── source_name: str            ├── source_name: str
├── source_url: str | None      ├── source_url: str | None
├── raw_content: str            ├── is_relevant: bool
├── collected_at: datetime      ├── category: UpdateCategory
├── metadata: dict              ├── urgency: UrgencyLevel
└── fingerprint: str            ├── score: int (0-100)
                                ├── headline: str
                                ├── summary: str
                                ├── reasoning: str
                                ├── tags: list[str]
                                ├── collected_at: datetime
                                ├── analyzed_at: datetime
                                ├── pipeline_status: PipelineStatus
                                ├── delivery_channel: DeliveryChannel
                                ├── delivered_at: datetime | None
                                └── fingerprint: str
```

## Persistence

- **SQLite** (via aiosqlite + SQLAlchemy async) — stores all analyzed items
- **In-memory TTL cache** — fast deduplication layer, 24-hour expiry
- **UpdateRecord** ORM model maps UpdateItem to/from the `updates` table

## Concurrency Model

- Full `async/await` throughout (no threads)
- `asyncio.gather()` runs all agents concurrently
- `asyncio.Semaphore` caps concurrent agent runs
- Background `asyncio.Task` instances for router flush loops
- `aiohttp.ClientSession` for all HTTP operations
- Graceful shutdown via SIGINT/SIGTERM signal handlers that stop agents and flush queues
