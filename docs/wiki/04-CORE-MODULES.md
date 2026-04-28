# 04 — Core Modules

All core modules live in `ai_junkie_updates/core/`.

---

## models.py

**Purpose**: Defines the data structures that flow through the entire pipeline.

### RawItem (Pydantic BaseModel)

The input to the pipeline — raw content collected by an agent before any processing.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | UUID4 | Unique identifier |
| `source_type` | `SourceType` | required | Which agent collected it |
| `source_name` | `str` | required | Human-readable source name |
| `source_url` | `str \| None` | `None` | URL of the source item |
| `raw_content` | `str` | required | The raw text content |
| `collected_at` | `datetime` | UTC now | When it was collected |
| `metadata` | `dict` | `{}` | Agent-specific metadata |
| `fingerprint` | `str` | `""` | xxhash digest (set by deduplicator) |

### UpdateItem (Pydantic BaseModel)

The output of Claude analysis — a fully scored, categorized, and summarized item.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | required | Same ID as the source RawItem |
| `source_type` | `SourceType` | required | Source agent type |
| `source_name` | `str` | required | Human-readable source name |
| `source_url` | `str \| None` | `None` | URL of the original content |
| `is_relevant` | `bool` | required | Whether Claude deems it relevant |
| `category` | `UpdateCategory` | required | One of 13 categories |
| `urgency` | `UrgencyLevel` | required | CRITICAL / HIGH / MEDIUM / LOW |
| `score` | `int` | required | 0–100 relevance/importance score |
| `headline` | `str` | required | One-line headline |
| `summary` | `str` | required | 2–3 sentence summary |
| `reasoning` | `str` | required | Why Claude assigned this score |
| `tags` | `list[str]` | `[]` | Relevant tags for matching |
| `collected_at` | `datetime` | required | When originally collected |
| `analyzed_at` | `datetime` | required | When Claude analyzed it |
| `pipeline_status` | `PipelineStatus` | required | Current pipeline stage |
| `delivery_channel` | `DeliveryChannel \| None` | `None` | Which channel to deliver to |
| `delivered_at` | `datetime \| None` | `None` | When delivered to Telegram |
| `fingerprint` | `str` | `""` | Content fingerprint |

### UpdateRecord (SQLAlchemy ORM)

Maps UpdateItem to the `updates` SQLite table. Tags are stored as comma-separated strings.

**Conversion methods:**
- `to_update_item() -> UpdateItem` — ORM row → Pydantic model
- `from_update_item(item) -> UpdateRecord` — Pydantic model → ORM row (classmethod)

---

## database.py

**Purpose**: Async database manager using SQLAlchemy async engine with aiosqlite.

**Singleton**: `db = DatabaseManager()`

### Class: DatabaseManager

| Method | Description |
|--------|-------------|
| `__init__(url=None)` | Creates async engine and session factory. Defaults to `settings.DATABASE_URL` |
| `async init_db()` | Creates all tables if they don't exist |
| `async save_item(item)` | Insert or update an UpdateItem record (merge) |
| `async update_status(item_id, status, channel, delivered_at)` | Update pipeline status fields |
| `async get_item(item_id) -> UpdateItem \| None` | Fetch single item by ID |
| `async get_recent_items(hours=24, limit=100)` | Fetch items from the last N hours |
| `async fingerprint_exists(fingerprint) -> bool` | Check if a fingerprint already exists |
| `async close()` | Dispose engine connection pool |

---

## cache.py

**Purpose**: In-memory TTL cache for fast deduplication lookups before hitting the database.

**Singleton**: `cache = TTLCache()`

### Class: TTLCache

| Method | Description |
|--------|-------------|
| `__init__(default_ttl=None)` | Default TTL from `settings.CACHE_TTL_SECONDS` (86400 = 24h) |
| `set(key, value, ttl=None)` | Store with optional per-key TTL override |
| `get(key) -> Any \| None` | Return value or None if expired/missing |
| `exists(key) -> bool` | True if key present and not expired |
| `delete(key)` | Remove key |
| `cleanup()` | Remove all expired entries (called lazily on set/get) |

**Storage format**: `{key: (value, expiry_timestamp)}`

---

## claude_client.py

**Purpose**: Sends raw items to Claude for structured JSON analysis via the Anthropic API.

**Singleton**: `claude_client = ClaudeClient()`

### Class: ClaudeClient

| Method | Description |
|--------|-------------|
| `__init__()` | Sets model from `settings.CLAUDE_MODEL`. Client created lazily. |
| `_ensure_client()` | Creates `AsyncAnthropic` on first use (avoids token validation at import) |
| `_call_claude(user_message) -> str` | Send message, return text. Retries 3× with exponential backoff. |
| `analyze(raw_item) -> UpdateItem` | Full analysis: format message → call Claude → parse JSON → return UpdateItem |
| `_parse_response(data, raw_item) -> UpdateItem` | Map Claude's JSON response to an UpdateItem |
| `_fallback_item(raw_item) -> UpdateItem` | Return a not-relevant item when parsing fails |

**User message format sent to Claude:**
```
Source type: {source_type}
Source name: {source_name}
Source URL: {url}
Collected at: {timestamp}

--- RAW CONTENT ---

{raw_content}
```

**Retry config**: 3 attempts, exponential backoff (min 2s, max 30s)

---

## prompts/system_prompt.py

**Purpose**: The master system prompt sent with every Claude analysis request.

### SYSTEM_PROMPT Content

1. **Role**: AI Junkie Updates intelligence engine
2. **What to collect** (12 categories): product launches, model releases, funding, acquisitions, open-source releases, research breakthroughs, infrastructure changes, security incidents, regulatory developments, partnerships, leadership changes, market data
3. **What to filter out** (8 categories): opinion pieces, minor patches, marketing fluff, social media drama, unverified rumors, duplicate coverage, off-topic items, speculative analysis
4. **Scoring rubric**:
   - 90–100: Industry-changing, paradigm shifts, billion-dollar events
   - 70–89: Very important, significant releases, major funding
   - 50–69: Worth knowing, moderate significance
   - 40–49: Minor relevance, niche interest
   - 0–39: Noise, not relevant
5. **Output format**: Strict JSON schema with required fields
6. **Rules**: Valid JSON only, conservative scoring, specific headlines, English output
