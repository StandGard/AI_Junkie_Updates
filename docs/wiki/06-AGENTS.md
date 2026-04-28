# 06 — Agents

All 13 source agents live in `ai_junkie_updates/agents/`. Each agent is a directory with three files:

- `agent.py` — the collector implementation
- `prompt.py` — source-specific analysis guidance (`AGENT_CONTEXT_PROMPT`)
- `__init__.py` — re-exports the agent class

Every agent extends `BaseAgent` and implements the abstract `collect() -> List[RawItem]` method.

---

## BaseAgent (`base_agent.py`)

The abstract base class that all agents inherit from.

### Constructor

```python
BaseAgent(
    source_type: SourceType,     # e.g. SourceType.TWITTER
    source_name: str,            # e.g. "Twitter Monitor"
    poll_interval_seconds: int   # override per agent or use settings default
)
```

### Key Methods

| Method | Description |
|--------|-------------|
| `collect() -> List[RawItem]` | **Abstract** — subclasses implement source-specific collection |
| `run()` | Infinite loop: call `collect()`, process each item, sleep for poll interval |
| `_process_item(raw_item)` | Run single item through full pipeline (normalize → dedup → analyze → filter → route) |
| `stop()` | Signal the agent to stop after the current cycle |

### Helper Functions

| Function | Description |
|----------|-------------|
| `load_sources(agent_key)` | Load source config list from `config/sources.yaml` |
| `load_watchlist()` | Load combined watchlist (companies + models + topics) from `config/watchlist.yaml` |

---

## Agent Summary Table

| # | Agent | Source Type | Data Source | Key Library |
|---|-------|-------------|-------------|-------------|
| 1 | TwitterAgent | `twitter` | Twitter API v2 | aiohttp |
| 2 | RSSAgent | `rss` | RSS/Atom feeds | feedparser |
| 3 | WebScraperAgent | `web_scraper` | HTML pages | BeautifulSoup |
| 4 | ChangelogAgent | `changelog` | Changelog pages | regex + BS4 |
| 5 | GitHubAgent | `github` | GitHub REST API | aiohttp |
| 6 | RedditAgent | `reddit` | Reddit JSON API | aiohttp |
| 7 | DiscordAgent | `discord` | Webhook receiver | aiohttp.web |
| 8 | OnchainAgent | `onchain` | Blockchain APIs | aiohttp |
| 9 | TelegramChannelsAgent | `telegram_channels` | RSS bridge / Bot API | feedparser + aiohttp |
| 10 | PressReleasesAgent | `press_releases` | PR newswire pages | BeautifulSoup |
| 11 | PodcastAgent | `podcast` | Podcast RSS feeds | feedparser |
| 12 | RegulatoryAgent | `regulatory` | Government websites | BeautifulSoup |
| 13 | APIFeedAgent | `api_feed` | JSON API endpoints | aiohttp |

---

## Agent Details

### 1. TwitterAgent (`agents/twitter/`)

Fetches recent tweets from monitored accounts and search terms via the Twitter API v2.

- **Endpoint**: `https://api.twitter.com/2/tweets/search/recent`
- **Auth**: Bearer token from `sources.yaml`
- **Query construction**: `from:account` for each monitored account, plus custom search terms
- **Parameters**: `max_results=10`, includes `tweet.fields`, `expansions`, `user.fields`
- **Cache key**: per-tweet ID

### 2. RSSAgent (`agents/rss/`)

Polls configured RSS/Atom feeds and returns new entries.

- **Library**: feedparser
- **Dedup**: Cache key `rss:{entry_id}` with 24h TTL
- **Sources**: TechCrunch, VentureBeat, The Batch, Import AI, Stratechery, W&B, OpenAI blog, Anthropic blog, DeepMind blog, HuggingFace blog, Mistral blog, arXiv cs.AI, arXiv cs.LG

### 3. WebScraperAgent (`agents/web_scraper/`)

Scrapes monitored web pages and extracts text content.

- **Library**: BeautifulSoup + lxml
- **Cleanup**: Removes `script`, `style`, `nav`, `footer`, `header` tags
- **Crawl delay**: Configurable per source (default 2s between requests)
- **Sources**: OpenAI, Anthropic, DeepMind, Meta AI, Microsoft AI, NVIDIA, HuggingFace news pages

### 4. ChangelogAgent (`agents/changelog/`)

Parses product changelog pages and splits them into individual version entries.

- **Regex**: `VERSION_PATTERN` matches version numbers and date headers
- **Limit**: First 5 entries per page to avoid flooding
- **Cache key**: includes hash of first 200 chars of entry
- **Sources**: OpenAI, Anthropic, HuggingFace, LangChain, LlamaIndex, Ollama, vLLM

### 5. GitHubAgent (`agents/github/`)

Fetches latest releases from monitored GitHub repositories.

- **Endpoint**: `https://api.github.com/repos/{repo}/releases`
- **Auth**: Optional GitHub token
- **Limit**: `per_page=5` releases per repo
- **Cache key**: `github:{repo}:{release_id}`
- **Sources**: transformers, openai-python, anthropic-sdk-python, langchain, llama_index, ollama, vllm, autogen, litellm, llama.cpp

### 6. RedditAgent (`agents/reddit/`)

Fetches new posts from monitored subreddits via the public JSON API.

- **Endpoint**: `https://www.reddit.com/r/{subreddit}/new.json`
- **Auth**: None (public API)
- **Limit**: 25 posts per subreddit
- **Metadata**: score, author, post_id, subreddit
- **Sources**: r/MachineLearning, r/LocalLLaMA, r/artificial, r/OpenAI, r/ClaudeAI, r/StableDiffusion, r/singularity

### 7. DiscordAgent (`agents/discord/`)

Runs an HTTP webhook receiver that accepts Discord bot forwards.

- **Model**: Push-based (not polling) — runs an aiohttp web server
- **Endpoint**: `POST /discord/webhook` on port 8484
- **Pattern**: Messages accumulate in an inbox buffer; `collect()` drains the buffer
- **Sources**: Configurable Discord servers forwarding via bot

### 8. OnchainAgent (`agents/onchain/`)

Polls blockchain explorer APIs for AI-related on-chain events.

- **Flexible parsing**: Handles multiple JSON response structures (`data`, `events`)
- **ID resolution**: Tries `id`, `hash`, `tx_hash` fields
- **Cache key**: `onchain:{name}:{event_id}`
- **Sources**: Bittensor, Fetch.ai, Ocean Protocol, Render Network

### 9. TelegramChannelsAgent (`agents/telegram_channels/`)

Monitors Telegram channels via two configurable methods.

- **RSS method**: Parses RSS export feeds (e.g., via rsshub.app)
- **Bot API method**: Uses `getUpdates` endpoint with bot token
- **Cache key**: `tg:{name}:{entry_id}` (RSS) or `tg_bot:{channel_id}:{msg_id}` (Bot API)

### 10. PressReleasesAgent (`agents/press_releases/`)

Scrapes PR newswire and company press release pages.

- **CSS selectors**: Configurable `article_selector`, `title_selector`, `link_selector`
- **URL handling**: Converts relative URLs to absolute
- **Limit**: First 10 articles per page
- **Delay**: 1 second between sources
- **Sources**: PR Newswire, BusinessWire, GlobeNewswire, SEC EDGAR

### 11. PodcastAgent (`agents/podcast/`)

Polls podcast RSS feeds for new episodes.

- **Library**: feedparser
- **Limit**: Latest 5 episodes per feed
- **Metadata**: show name, episode title, published date, feed URL
- **Sources**: Lex Fridman, TWIML AI, Gradient Dissent, Practical AI, Alignment Forum, 80,000 Hours, No Priors

### 12. RegulatoryAgent (`agents/regulatory/`)

Scrapes government and regulatory body websites for AI policy developments.

- **CSS selectors**: Configurable with sensible defaults (`article, .press-release, .news-item, li`)
- **Validation**: Minimum 20-char body text to skip empty/nav elements
- **Delay**: 2 seconds between sources (respectful crawl rate for government sites)
- **Sources**: FTC, EU AI Office, NIST, US Congressional, UK DSIT, European Parliament

### 13. APIFeedAgent (`agents/api_feed/`)

Consumes structured JSON API endpoints with pagination support.

- **JSON path**: Dot-notation `content_path` to navigate nested responses
- **Pagination**: Max 3 pages, configurable `page_param` (default `"page"`)
- **Fallback keys**: Tries `data`, `results`, `items`, `articles`, `entries` for entry extraction
- **Auth**: API key header per source
- **Sources**: Crunchbase, PitchBook, NewsAPI
