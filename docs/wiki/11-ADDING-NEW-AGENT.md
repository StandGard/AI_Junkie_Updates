# 11 — Adding a New Agent

Step-by-step guide to adding a 14th (or Nth) source agent.

---

## Step 1: Add the Source Type

Edit `ai_junkie_updates/constants.py` and add a new value to `SourceType`:

```python
class SourceType(str, Enum):
    # ... existing types ...
    MY_NEW_SOURCE = "my_new_source"
```

## Step 2: Create the Agent Directory

```bash
mkdir ai_junkie_updates/agents/my_new_source
```

Create three files:

### `__init__.py`

```python
from ai_junkie_updates.agents.my_new_source.agent import MyNewSourceAgent

__all__ = ["MyNewSourceAgent"]
```

### `prompt.py`

```python
AGENT_CONTEXT_PROMPT = """
Source type: My New Source

COLLECT:
- List specific signals this source should capture
- Be precise about what constitutes a relevant item

IGNORE:
- List what to filter out from this source
- Be specific about noise patterns
"""
```

### `agent.py`

```python
from __future__ import annotations

from typing import List

import aiohttp

from ai_junkie_updates.agents.base_agent import BaseAgent, load_sources
from ai_junkie_updates.constants import SourceType
from ai_junkie_updates.core.cache import cache
from ai_junkie_updates.core.models import RawItem


class MyNewSourceAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            source_type=SourceType.MY_NEW_SOURCE,
            source_name="My New Source",
            poll_interval_seconds=300,
        )
        self._sources = load_sources("my_new_source")

    async def collect(self) -> List[RawItem]:
        items: List[RawItem] = []
        async with aiohttp.ClientSession() as session:
            for src in self._sources:
                try:
                    # Fetch data from source
                    async with session.get(src["url"]) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()

                    # Process and deduplicate
                    for entry in data:
                        entry_id = entry.get("id")
                        cache_key = f"my_source:{entry_id}"
                        if cache.exists(cache_key):
                            continue
                        cache.set(cache_key, True, ttl=86400)

                        items.append(RawItem(
                            source_type=SourceType.MY_NEW_SOURCE,
                            source_name=src["name"],
                            source_url=entry.get("url"),
                            raw_content=str(entry),
                        ))
                except Exception as exc:
                    self.log.warning("collect_error", source=src["name"], error=str(exc))
        return items
```

## Step 3: Add Source Configuration

Edit `ai_junkie_updates/config/sources.yaml`:

```yaml
my_new_source:
  - name: "Source One"
    url: "https://api.example.com/feed"
  - name: "Source Two"
    url: "https://other.example.com/data"
```

## Step 4: Register the Agent

Edit `ai_junkie_updates/main.py`:

1. Add the import:
```python
from ai_junkie_updates.agents.my_new_source import MyNewSourceAgent
```

2. Add to `_build_agents()`:
```python
def _build_agents() -> list:
    return [
        # ... existing agents ...
        MyNewSourceAgent(),
    ]
```

## Step 5: Test

```bash
# Verify import works
python -c "from ai_junkie_updates.agents.my_new_source import MyNewSourceAgent; print('OK')"

# Run the full system
python -m ai_junkie_updates.main
```

---

## Checklist

- [ ] New `SourceType` enum value in `constants.py`
- [ ] Agent directory with `__init__.py`, `agent.py`, `prompt.py`
- [ ] Agent class extends `BaseAgent`, implements `collect()`
- [ ] Source config in `config/sources.yaml`
- [ ] Agent imported and instantiated in `main.py`
- [ ] Cache keys use unique prefix (e.g., `my_source:{id}`)
- [ ] Error handling with structured logging
- [ ] Import test passes
