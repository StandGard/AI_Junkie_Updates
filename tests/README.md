# Tests

## What runs here

| Test | What it proves | Network needed |
|------|----------------|----------------|
| `test_pipeline_offline.py` | The full in-process pipeline — Normalizer → Deduplicator (real SQLite + cache) → FilterEngine (all tier boundaries) → Formatter → Router (instant vs. batched delivery, DB persistence). Only the two external boundaries are mocked: Claude analysis and Telegram send. | **No** |

Run it directly (no pytest required):

```bash
python tests/test_pipeline_offline.py
```

Exits `0` on success, `1` if any check fails.

## What is NOT covered yet

- **Live data collection** — every agent's `collect()` hits the network. This
  sandbox uses an allowlist network policy (only the package registry is
  reachable), so live collection cannot be exercised here. Run in an
  environment with outbound egress to verify agents against real sources.
- **Live Claude analysis** — needs `AIJU_ANTHROPIC_API_KEY` and network access
  to `api.anthropic.com`.
- **Live Telegram delivery** — needs `AIJU_TELEGRAM_BOT_TOKEN`, channel IDs,
  and network access to the Telegram API.
- Per-agent unit tests with mocked HTTP (planned — see `TODO.md`).
