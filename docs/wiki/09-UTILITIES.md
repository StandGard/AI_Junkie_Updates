# 09 — Utilities

Shared utility modules in `ai_junkie_updates/utils/`.

---

## fingerprint.py

**Purpose**: Content fingerprinting for deduplication using xxhash.

### Function

```python
def generate_fingerprint(content: str) -> str
```

Returns the xxh64 hex digest of the input string. xxhash is chosen over SHA-256 for its speed — deduplication runs on every collected item, so sub-microsecond hashing matters.

**Library**: `xxhash` (xxh64)

---

## text_cleaner.py

**Purpose**: Text cleaning utilities used by the Normalizer pipeline stage.

### Functions

| Function | Description |
|----------|-------------|
| `clean_html(text) -> str` | Strip all HTML tags and decode entities using BeautifulSoup |
| `collapse_whitespace(text) -> str` | Collapse multiple spaces, tabs, and newlines into single spaces via regex |
| `remove_control_characters(text) -> str` | Strip null bytes and non-printable control characters using `unicodedata` |
| `truncate(text, max_chars) -> str` | Truncate to `max_chars`, appending `…` if truncated |

### Dependencies

- `beautifulsoup4` — for HTML cleaning
- `re` — for whitespace regex
- `unicodedata` — for control character detection

---

## logger.py

**Purpose**: Structured logging configuration using structlog.

### Setup

`_configure_once()` is called automatically on first `get_logger()` call. It:

1. Configures structlog processors: context vars, log level filtering, timestamps, exception formatting
2. Bridges structlog with Python's stdlib `logging` module
3. Selects `ConsoleRenderer` for human-readable output
4. Uses a global `_configured` flag to ensure setup runs exactly once

### Usage

```python
from ai_junkie_updates.utils.logger import get_logger

log = get_logger(__name__)
log.info("event_name", key1="value1", key2="value2")
```

### Output Format

Structured key-value pairs, e.g.:
```
2026-04-28 12:34:56 [info] telegram_sent  item_id=abc123  channel=critical_alerts  headline=OpenAI launches...
```

**Library**: `structlog`
