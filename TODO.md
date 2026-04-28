# AI Junkie Updates — TODO

> Last updated: 2026-04-28

## Completed

- [x] Project scaffolding — 72 files, full directory structure
- [x] Core modules — models, database, cache, Claude client, prompts
- [x] Pipeline stages — normalizer, deduplicator, filter engine, router
- [x] All 13 source agents — Twitter, RSS, Web Scraper, Changelog, GitHub, Reddit, Discord, Onchain, Telegram Channels, Press Releases, Podcast, Regulatory, API Feed
- [x] Delivery system — Telegram bot with rate limiting, HTML formatter
- [x] Configuration — settings.py, sources.yaml, watchlist.yaml, .env.example
- [x] Bootstrap and main entrypoint with graceful shutdown
- [x] Utility modules — logger, fingerprint, text cleaner
- [x] All module imports verified passing
- [x] Initial commit and push to `claude/setup-ai-junkie-structure-dVcM7`
- [x] Wiki mesh documentation — 13 pages covering all components
- [x] CLAUDE.md memory file for session continuity
- [x] TODO.md task tracking

## In Progress

- [ ] PDF project overview document (fpdf2 installed, script not yet written)

## Backlog — Next Steps

### Testing
- [ ] Unit tests for pipeline stages (normalizer, deduplicator, filter engine)
- [ ] Unit tests for core modules (cache, database, models)
- [ ] Integration tests for agent collect() methods with mocked HTTP
- [ ] End-to-end pipeline test with mock Claude responses
- [ ] Test configuration for pytest + pytest-asyncio

### Infrastructure
- [ ] Dockerfile and docker-compose.yml for containerized deployment
- [ ] CI/CD pipeline (GitHub Actions) — lint, test, build
- [ ] Health check endpoint (lightweight HTTP server for monitoring)
- [ ] Metrics collection (Prometheus counters for items collected, analyzed, delivered)

### Features
- [ ] Web dashboard for viewing collected items and delivery status
- [ ] REST API for querying the database (FastAPI or similar)
- [ ] Email digest delivery option (daily/weekly summary)
- [ ] Slack delivery channel (in addition to Telegram)
- [ ] Agent-specific prompt injection (append AGENT_CONTEXT_PROMPT to system prompt)
- [ ] Configurable scoring weights per source type
- [ ] Historical trend analysis (score distribution over time)

### Data & Storage
- [ ] Database migration tooling (Alembic)
- [ ] Data retention policy (auto-delete items older than N days)
- [ ] Export to CSV/JSON for offline analysis
- [ ] PostgreSQL support for multi-instance deployment

### Quality
- [ ] Type checking with mypy (strict mode)
- [ ] Linting with ruff
- [ ] Pre-commit hooks configuration
- [ ] Code coverage reporting
- [ ] Security audit of credential handling

### Documentation
- [ ] API documentation (if REST API is added)
- [ ] Deployment guide (VPS, Docker, cloud)
- [ ] Troubleshooting guide
- [ ] Contributing guide
