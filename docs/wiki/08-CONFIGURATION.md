# 08 — Configuration

Configuration is managed through three mechanisms:
1. **Environment variables** (via `.env` file) — secrets and runtime settings
2. **`config/sources.yaml`** — data source URLs and API endpoints
3. **`config/watchlist.yaml`** — companies, models, and topics to track

---

## Environment Variables (`.env`)

All environment variables use the `AIJU_` prefix. Copy `.env.example` to `.env` and fill in your values.

### Required Variables

| Variable | Description |
|----------|-------------|
| `AIJU_ANTHROPIC_API_KEY` | Anthropic API key for Claude analysis |
| `AIJU_TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather |
| `AIJU_TELEGRAM_CHANNEL_CRITICAL` | Channel ID for critical alerts (score 90+) |
| `AIJU_TELEGRAM_CHANNEL_HIGH` | Channel ID for high-priority updates (70–89) |
| `AIJU_TELEGRAM_CHANNEL_GENERAL` | Channel ID for general updates (50–69) |
| `AIJU_TELEGRAM_CHANNEL_WATCHLIST` | Channel ID for watchlist matches (40–49) |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AIJU_DATABASE_URL` | `sqlite+aiosqlite:///storage/aiju.db` | SQLite database path |
| `AIJU_CACHE_TTL_SECONDS` | `86400` | In-memory cache TTL (24 hours) |
| `AIJU_SCORE_THRESHOLD_DELIVER` | `50` | Minimum score for auto-delivery |
| `AIJU_SCORE_THRESHOLD_WATCHLIST` | `40` | Minimum score for watchlist delivery |
| `AIJU_POLL_INTERVAL_SECONDS` | `300` | Agent polling interval (5 minutes) |
| `AIJU_MAX_CONCURRENT_AGENTS` | `5` | Max agents running simultaneously |
| `AIJU_CLAUDE_MODEL` | `claude-opus-4-8` | Claude model for analysis |
| `AIJU_LOG_LEVEL` | `INFO` | Logging level |

### Settings Validation

`settings.validate_required()` (called during bootstrap) hard-exits the process if any required variable is empty.

---

## sources.yaml

Located at `ai_junkie_updates/config/sources.yaml`. Defines all data sources for each agent type.

### Structure

```yaml
agent_key:
  - name: "Source Name"
    url: "https://..."
    # Agent-specific fields:
    api_key: "${ENV_VAR}"
    selector: "css-selector"
    crawl_delay: 2
    # etc.
```

### Configured Sources

| Agent Key | # Sources | Examples |
|-----------|-----------|---------|
| `twitter` | 14 accounts + search terms | @OpenAI, @AnthropicAI, @GoogleDeepMind |
| `rss` | 13 feeds | TechCrunch AI, VentureBeat, arXiv cs.AI |
| `web_scraper` | 7 pages | OpenAI blog, Anthropic news, DeepMind blog |
| `changelog` | 7 changelogs | OpenAI, Anthropic, HuggingFace, LangChain |
| `github` | 10 repos | transformers, openai-python, langchain |
| `reddit` | 7 subreddits | r/MachineLearning, r/LocalLLaMA |
| `discord` | 3 servers | Configurable via webhook |
| `onchain` | 4 protocols | Bittensor, Fetch.ai, Ocean, Render |
| `telegram_channels` | — | Placeholder (user-configurable) |
| `press_releases` | 4 sources | PR Newswire, BusinessWire, SEC EDGAR |
| `podcast` | 7 feeds | Lex Fridman, TWIML AI, Practical AI |
| `regulatory` | 6 bodies | FTC, EU AI Office, NIST, Congress |
| `api_feed` | 3 APIs | Crunchbase, PitchBook, NewsAPI |

---

## watchlist.yaml

Located at `ai_junkie_updates/config/watchlist.yaml`. Items scoring 40–49 are only delivered if they match a term from this file.

### Categories

**Companies** (20):
OpenAI, Anthropic, Google DeepMind, Meta AI, Mistral AI, xAI, Cohere, HuggingFace, Stability AI, Runway, ElevenLabs, Perplexity, Inflection, Character.AI, Adept, Cognition, Together AI, Groq, Cerebras, SambaNova

**Models** (8):
GPT-5, GPT-4o, Claude 4, Gemini 2, Llama 4, Mistral Large, Grok 3, Command R+

**Topics** (7):
AGI, model collapse, safety incident, regulatory ban, billion dollar, acquisition, raises

### How Matching Works

The filter engine combines all three lists into a flat list of strings. For each watchlist term, it performs a **case-insensitive substring search** against:
- `item.source_name`
- Each string in `item.tags`
