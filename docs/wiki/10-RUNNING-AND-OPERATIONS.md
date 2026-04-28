# 10 — Running & Operations

## Prerequisites

1. **Python 3.11+**
2. **Virtual environment** (recommended)
3. **Environment variables** configured in `.env`

## Setup

```bash
# Clone and navigate
git clone <repo-url>
cd AI_Junkie_Updates

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r ai_junkie_updates/requirements.txt

# Configure environment
cp ai_junkie_updates/.env.example ai_junkie_updates/.env
# Edit .env with your API keys and channel IDs
```

## Starting the System

```bash
cd AI_Junkie_Updates
python -m ai_junkie_updates.main
```

### What Happens on Startup

1. **`bootstrap()`** runs:
   - Validates required settings (exits if missing)
   - Initializes SQLite database (creates tables)
   - Warms up cache singleton
   - Logs startup configuration

2. **Agent instantiation**: All 13 agents are created

3. **Router starts**: Background flush loops begin (5-min for GENERAL, 15-min for WATCHLIST)

4. **Agents launch**: `asyncio.gather()` starts all agents concurrently, limited by semaphore (default 5 concurrent)

5. **Continuous operation**: Each agent polls on its interval (default 300s) indefinitely

## Stopping the System

### Graceful Shutdown

- **Ctrl+C** (SIGINT) or **SIGTERM** triggers graceful shutdown
- All agents receive `stop()` signal
- Router flushes remaining queued items
- Database connection is closed
- Process exits cleanly

### What Gets Flushed

On shutdown, any items in the GENERAL or WATCHLIST queues are delivered before exit.

## Monitoring

### Logs

Structured logs via structlog to stdout:

```
2026-04-28 12:34:56 [info] bootstrap_complete  db=initialized  agents=13
2026-04-28 12:34:57 [info] agent_started  agent=TwitterAgent  interval=300
2026-04-28 12:39:57 [info] items_collected  agent=RSSAgent  count=4
2026-04-28 12:40:01 [info] telegram_sent  item_id=abc  channel=high_priority  headline=...
2026-04-28 12:40:01 [warning] rate_limit_wait  delay_seconds=3.2
```

### Key Log Events

| Event | Meaning |
|-------|---------|
| `bootstrap_complete` | System initialized successfully |
| `agent_started` | An agent began its polling loop |
| `items_collected` | Agent returned items from `collect()` |
| `duplicate_skipped` | Item fingerprint already seen |
| `claude_api_error` | Claude API call failed (will retry) |
| `claude_parse_error` | Claude response wasn't valid JSON |
| `telegram_sent` | Message delivered to Telegram |
| `rate_limit_wait` | Telegram rate limit hit, sleeping |
| `no_channel_configured` | Delivery channel has no Telegram ID |
| `agent_error` | Unhandled exception in agent loop |

### Database

SQLite database at `storage/aiju.db` stores all analyzed items. You can query it directly:

```bash
sqlite3 ai_junkie_updates/storage/aiju.db "SELECT headline, score, delivery_channel FROM updates ORDER BY analyzed_at DESC LIMIT 20"
```

## Concurrency

- **`AIJU_MAX_CONCURRENT_AGENTS`** (default 5) controls how many agents can run their `collect()` cycle simultaneously
- Other agents wait on the semaphore until a slot opens
- All agents share the same event loop — no threading required

## Error Recovery

- **Agent errors**: Caught and logged; agent continues its next polling cycle
- **Claude API errors**: Retried 3× with exponential backoff; falls back to a "not relevant" item on final failure
- **Telegram errors**: Retried 3× with exponential backoff
- **Database errors**: Logged; item may be lost from DB but pipeline continues
