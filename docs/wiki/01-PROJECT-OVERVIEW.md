# 01 — Project Overview

## What Is AI Junkie Updates?

AI Junkie Updates is a **real-time AI industry intelligence aggregator**. It continuously monitors 13 different source types across the AI landscape — Twitter, RSS feeds, GitHub releases, Reddit, regulatory bodies, podcasts, and more — and funnels every collected item through **Claude AI** for structured analysis. The result is a scored, categorized, and summarized stream of updates delivered to **Telegram channels** organized by urgency tier.

## Why Does It Exist?

The AI industry moves fast. Announcements, model releases, funding rounds, regulatory changes, and security incidents happen around the clock across dozens of platforms. No human can track all of it in real time.

AI Junkie Updates solves this by:

1. **Automating collection** — 13 async agents poll sources on configurable intervals
2. **Eliminating noise** — Claude AI scores every item 0–100, filtering out opinions, spam, and duplicates
3. **Prioritizing what matters** — critical alerts (score 90+) arrive instantly; low-priority items batch into periodic digests
4. **Delivering where you are** — four Telegram channels, tiered by urgency, so you only get interrupted for things that matter

## Part of the Antigravity Ecosystem

AI Junkie Updates is a component of the broader **Antigravity** ecosystem. It serves as the intelligence layer that keeps team members informed about the fast-moving AI landscape.

## How It Works (30-Second Version)

```
13 Source Agents → collect raw content
        ↓
   Normalize → strip HTML, clean text, truncate to 8k chars
        ↓
   Deduplicate → xxhash fingerprint, check cache + DB
        ↓
   Analyze → send to Claude AI, get JSON with score/category/summary
        ↓
   Filter → apply score thresholds + watchlist matching
        ↓
   Route → immediate delivery or batched queue
        ↓
   Deliver → formatted HTML message to Telegram channel
```

## Scoring Tiers

| Score | Tier | Channel | Delivery |
|-------|------|---------|----------|
| 90–100 | Critical | CRITICAL_ALERTS | Instant |
| 70–89 | Important | HIGH_PRIORITY | Instant |
| 50–69 | Worth knowing | GENERAL | Batched (5 min) |
| 40–49 | Watchlist | WATCHLIST | Batched (15 min), only if watchlist match |
| 0–39 | Noise | — | Dropped, saved to DB only |

## Key Numbers

- **13** source agents
- **72** source files
- **~3,600** lines of Python
- **13** update categories
- **4** Telegram delivery channels
- **5** concurrent agent limit (configurable)
- **8,000** character content limit per item
- **24-hour** deduplication window
- **20 messages/minute** Telegram rate limit
