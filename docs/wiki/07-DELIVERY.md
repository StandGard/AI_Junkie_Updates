# 07 — Delivery

The delivery system formats analyzed updates as HTML messages and sends them to the appropriate Telegram channels. Components live in `ai_junkie_updates/delivery/`.

---

## Formatter (`formatter.py`)

**Purpose**: Convert UpdateItem objects into HTML-formatted messages for Telegram.

### Category Emojis

| Category | Emoji |
|----------|-------|
| PRODUCT_LAUNCH | 🚀 |
| MODEL_RELEASE | 🧠 |
| FUNDING | 💰 |
| ACQUISITION | 🤝 |
| OPEN_SOURCE_RELEASE | 📦 |
| RESEARCH_BREAKTHROUGH | 🔬 |
| INFRASTRUCTURE_CHANGE | ⚙️ |
| SECURITY_INCIDENT | 🔴 |
| REGULATORY_DEVELOPMENT | ⚖️ |
| PARTNERSHIP | 🔗 |
| LEADERSHIP_CHANGE | 👤 |
| MARKET_DATA | 📊 |
| OTHER | 📌 |

### Message Format

```html
🚀 <b>OpenAI Launches GPT-5</b>

Summary of the announcement in 2-3 sentences.

🏷 #product_launch #openai #gpt5
📡 Source: OpenAI Blog
🔗 <a href="https://...">Link</a>
📊 Score: 95 · Urgency: CRITICAL
```

All text is HTML-escaped to prevent injection in Telegram's HTML parser.

---

## Telegram Bot (`telegram_bot.py`)

**Purpose**: Rate-limited message delivery to Telegram channels.

**Singleton**: `telegram_bot = TelegramBot()`

### Lazy Initialization

The bot instance is created lazily via `_ensure_bot()` to avoid token validation at import time. This is critical because `settings.TELEGRAM_BOT_TOKEN` may be empty during testing or before `.env` is loaded.

### Channel Mapping

| DeliveryChannel | Settings Key |
|----------------|--------------|
| `CRITICAL_ALERTS` | `TELEGRAM_CHANNEL_CRITICAL` |
| `HIGH_PRIORITY` | `TELEGRAM_CHANNEL_HIGH` |
| `GENERAL` | `TELEGRAM_CHANNEL_GENERAL` |
| `WATCHLIST` | `TELEGRAM_CHANNEL_WATCHLIST` |

### Rate Limiting

- **Window**: 60 seconds
- **Max messages**: 20 per window
- **Behavior**: If limit is reached, `await asyncio.sleep()` until the oldest message in the window expires
- **Tracking**: `_send_times` list of `time.monotonic()` timestamps

### Retry Logic

Each `_send_message()` call retries up to 3 times with exponential backoff:
- Multiplier: 1
- Min wait: 2 seconds
- Max wait: 15 seconds

### Send Flow

```python
async def send(item: UpdateItem):
    1. Check channel — skip DROPPED or None
    2. Look up channel_id from _channel_map
    3. Format message via Formatter
    4. Wait for rate limit clearance
    5. Send HTML message to Telegram
    6. Record send timestamp
    7. Log success with item_id, channel, headline
```
