# Tests

Both suites run with **no network** and **no API keys** — they mock the network
boundaries and exercise the real code. Run them directly (no pytest required):

```bash
python tests/test_pipeline_offline.py   # 17 checks
python tests/test_agents_offline.py     # 29 checks
```

Each exits `0` on success, `1` if any check fails.

## What runs here

| Test | What it proves | Network |
|------|----------------|---------|
| `test_pipeline_offline.py` | The full in-process pipeline — Normalizer → Deduplicator (real SQLite + cache) → FilterEngine (all tier boundaries) → Formatter → Router (instant vs. batched delivery + DB persistence). Mocks only Claude analysis and Telegram send. | none |
| `test_agents_offline.py` | Every one of the 13 agents' `collect()` parsing path, fed a realistic response body (real RSS XML through feedparser, real JSON for GitHub/Reddit/Twitter/on-chain/API feeds, real HTML through BeautifulSoup, Discord webhook POST). Asserts correctly-typed `RawItem`s and dedupe-on-re-poll. `aiohttp.ClientSession` is replaced with a fake. | none |

## What is NOT covered yet (needs a networked environment + credentials)

- **Live data collection** — every agent's `collect()` hits the real network.
  This sandbox uses an allowlist network policy (only the package registry is
  reachable: `pypi.org`→200, `reddit.com`→403 "Host not in allowlist"), so live
  collection cannot run here. Verify against real sources in an environment with
  outbound egress.
- **Live Claude analysis** — needs `AIJU_ANTHROPIC_API_KEY` and access to
  `api.anthropic.com`.
- **Live Telegram delivery** — needs `AIJU_TELEGRAM_BOT_TOKEN`, channel IDs, and
  access to the Telegram API.
