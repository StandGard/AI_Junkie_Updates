# AI Junkie Updates — TODO

> Last updated: 2026-05-31

The project evolved from a news aggregator into a full **AI performance advisor**.
All four build phases of the approved plan are complete (see `docs/MINDMAP.md`
and `README.md`).

## Completed — original build

- [x] Project scaffolding, core modules, 4-stage pipeline
- [x] 13 source agents + Telegram delivery (4 tiers) + SQLite persistence
- [x] YAML config, Pydantic settings, wiki docs, mind map

## Completed — advisor platform (this build)

### Phase 0 — cost guardrails & correctness
- [x] Model tiering (cheap triage model + strong synthesis model)
- [x] Prompt caching on the stable system prompt
- [x] Wire per-agent `AGENT_CONTEXT_PROMPT` into triage
- [x] Restart-safe dedup (`seen_fingerprints` table)
- [x] Pre-LLM relevance gate; per-source poll intervals
- [x] Fix corrupted Twitter handles

### Phase 1 — the advisor brain
- [x] Knowledge base (`core/kb_models.py`): companies, models, prices, benchmarks,
      benchmark_scores, capabilities, events, tools, leaderboards
- [x] `intelligence/`: knowledge_base, entity_linker, clustering, ranking_engine, synthesis, jobs
- [x] `config/ranking.yaml` + `config/profile.yaml`; seed_entities.yaml
- [x] Idempotent schema upgrade (`ensure_kb_schema`) + KB auto-seed on bootstrap

### Phase 2 — interactive Telegram
- [x] `delivery/command_bot.py`: /best, /model, /compare, /whatschanged, /switch,
      /leaderboard, /digest, /status (owner-gated, pure KB reads)
- [x] Leaderboard/model-card/event/switch formatters
- [x] Calendar-aligned daily + weekly digests

### Phase 3 — source breadth
- [x] OpenRouter pricing/context ingestion (key-free) → value leaderboard
- [x] Benchmark leaderboard ingestion (LMArena/SWE-bench, fail-soft, provenance)
- [x] YouTube via channel RSS; X founders/researchers via RSS-bridge
- [x] Provider status pages (OpenAI/Anthropic) via api_feed
- [x] `YOUTUBE` + `BENCHMARK` SourceType enums

### Phase 4 — reliability
- [x] pytest suite (42 tests, `tests/`) + GitHub Actions CI
- [x] Dockerfile + docker-compose (`restart: unless-stopped`)
- [x] Health server (`/health`, `/ready`)
- [x] Data retention / prune job

## Remaining — deploy-time (not code work)

- [ ] **Live run with real credentials** — Anthropic + Telegram keys; confirm
      actual delivery, OpenRouter/benchmark fetches, and container reboot survival
- [ ] **Validate benchmark-leaderboard URLs** against the live HF Spaces (the
      current URLs are fail-soft best-guesses)
- [ ] Add real YouTube channel IDs / curate the X RSS-bridge handle list

## Backlog — optional future enhancements

- [ ] YouTube transcript fetch (richer than title/description)
- [ ] Self-hosted RSSHub for reliable X coverage
- [ ] Alembic migrations (currently idempotent ALTERs) + PostgreSQL for multi-instance
- [ ] More benchmark sources (Aider, tau-bench, GPQA live feeds)
- [ ] Prometheus metrics / token-cost counter
- [ ] `/ask` open-ended command (on-demand strong-model Q&A)
