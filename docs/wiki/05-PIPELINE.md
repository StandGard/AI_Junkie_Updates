# 05 — Pipeline

The pipeline processes every raw item through a sequence of stages. Each stage is implemented as a separate module in `ai_junkie_updates/pipeline/`.

```
RawItem → Normalize → Deduplicate → Analyze → Filter → Route → Deliver
```

The pipeline is orchestrated by `BaseAgent._process_item()` in `agents/base_agent.py`.

---

## Stage 1: Normalizer (`normalizer.py`)

**Purpose**: Clean and standardize raw content before sending it to Claude.

**Constant**: `MAX_CONTENT_LENGTH = 8000`

### Processing Steps

1. **Strip HTML** → `clean_html()` uses BeautifulSoup to remove all tags and decode entities
2. **Remove control characters** → `remove_control_characters()` strips null bytes and non-printable chars
3. **Collapse whitespace** → `collapse_whitespace()` reduces multiple spaces/tabs/newlines to single spaces
4. **Truncate** → `truncate()` cuts to 8,000 characters with `…` suffix

### Input/Output

- **Input**: `RawItem` with raw `raw_content`
- **Output**: New `RawItem` with cleaned `raw_content` (original item is not mutated)

---

## Stage 2: Deduplicator (`deduplicator.py`)

**Purpose**: Prevent the same content from being processed (and billed for Claude analysis) twice.

**Constant**: `FINGERPRINT_TTL = 86400` (24 hours)

### How It Works

1. Generate xxhash (xxh64) fingerprint of the normalized content
2. Set `raw_item.fingerprint` as a side effect
3. **Fast path**: Check in-memory TTL cache → if found, it's a duplicate
4. **Slow path**: Check SQLite database → if found, it's a duplicate
5. **New content**: Store fingerprint in cache with 24h TTL, return `False`

### Why Two Layers?

- **Cache**: Sub-microsecond lookups, handles the common case (same item seen within hours)
- **Database**: Survives process restarts, catches items from previous runs

---

## Stage 3: Analyze (via `core/claude_client.py`)

**Purpose**: Send raw content to Claude AI and receive a structured analysis.

See [Core Modules — claude_client.py](04-CORE-MODULES.md#claude_clientpy) for full details.

The analysis returns an `UpdateItem` with:
- Relevance flag (`is_relevant`)
- Category (one of 13)
- Urgency level
- Score (0–100)
- Headline, summary, reasoning
- Tags for watchlist matching

---

## Stage 4: Filter Engine (`filter_engine.py`)

**Purpose**: Decide whether and where to deliver an analyzed update.

### Decision Logic

```python
def should_deliver(item, watchlist) -> (bool, DeliveryChannel):
    if not item.is_relevant:
        return (False, DROPPED)
    
    if item.score >= 90:
        return (True, CRITICAL_ALERTS)
    
    if item.score >= 70:
        return (True, HIGH_PRIORITY)
    
    if item.score >= 50:
        return (True, GENERAL)
    
    if item.score >= 40:
        # Only deliver if source_name or tags match watchlist
        if any_watchlist_match(item, watchlist):
            return (True, WATCHLIST)
    
    return (False, DROPPED)
```

### Watchlist Matching

For items scoring 40–49, the filter checks if any watchlist term (from `config/watchlist.yaml`) appears as a case-insensitive substring in:
- `item.source_name`
- Any of `item.tags`

---

## Stage 5: Router (`router.py`)

**Purpose**: Manage delivery timing — immediate for critical items, batched for lower priorities.

**Singleton**: `router = Router()`

### Queue Configuration

| Channel | Strategy | Flush Interval | Max Batch |
|---------|----------|---------------|-----------|
| CRITICAL_ALERTS | Immediate | — | 1 |
| HIGH_PRIORITY | Immediate | — | 1 |
| GENERAL | Batched | 5 minutes | 10 items |
| WATCHLIST | Batched | 15 minutes | — |

### Background Tasks

The router starts two `asyncio.Task` loops:
- `_flush_general_loop()` — flushes every 5 minutes or when 10 items accumulate
- `_flush_watchlist_loop()` — flushes every 15 minutes

### Shutdown

`router.stop()` flushes all remaining queued items and cancels background tasks.

---

## Pipeline Orchestration

The full pipeline runs in `BaseAgent._process_item()`:

```python
async def _process_item(self, raw_item: RawItem):
    # 1. Normalize
    raw_item = self._normalizer.normalize(raw_item)

    # 2. Deduplicate
    if await self._deduplicator.is_duplicate(raw_item):
        return  # silently drop

    # 3. Analyze via Claude (with the agent's source-specific context prompt)
    update_item = await claude_client.analyze(
        raw_item, context_prompt=self._context_prompt
    )

    # 4. Filter -> sets the delivery channel and pipeline status
    should_deliver, channel = self._filter_engine.should_deliver(
        update_item, self._watchlist
    )
    update_item.delivery_channel = channel
    update_item.pipeline_status = (
        PipelineStatus.FILTERED if should_deliver else PipelineStatus.DROPPED
    )

    # 5. Route for delivery
    await router.route(update_item)
```

> **Note on persistence:** `_process_item` does **not** write to the database
> itself. Persistence happens inside the **Router**: delivered items are saved
> by `Router._deliver()` (after a successful Telegram send), and dropped items
> are saved by `Router.route()`. A consequence is that items still sitting in
> the GENERAL/WATCHLIST batch queues at an ungraceful shutdown are not yet
> persisted — `router.stop()` flushes them on a graceful shutdown.
