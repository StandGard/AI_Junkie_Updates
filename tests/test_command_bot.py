"""Interactive Telegram command handlers (pure KB reads)."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from ai_junkie_updates.delivery.command_bot import CommandBot
from ai_junkie_updates.intelligence.synthesis import Synthesizer


class _FakeSynthClient:
    async def synthesize(self, *a, **k):
        return "DIGEST: top stories ..."


@pytest.fixture
def bot(seeded_kb):
    return CommandBot(kb=seeded_kb, synth=Synthesizer(kb=seeded_kb, client=_FakeSynthClient()))


async def _setup_boards(kb):
    now = datetime.now(timezone.utc)
    await kb.upsert_model(id="claude-opus-4-8", display_name="Claude Opus 4.8",
                          release_date=now - timedelta(days=10))
    await kb.add_price(model_id="claude-opus-4-8", input_per_mtok=5.0, output_per_mtok=25.0)
    await kb.add_score(model_id="claude-opus-4-8", benchmark_id="swe-bench-verified", score=80.0)
    await kb.set_leaderboard(use_case="coding", ranking=[
        {"model_id": "claude-opus-4-8", "display_name": "Claude Opus 4.8", "score": 0.92, "rank": 1,
         "rationale": "top benchmarks, low cost"},
        {"model_id": "gpt-5", "display_name": "GPT-5", "score": 0.80, "rank": 2, "rationale": "strong benchmarks"}],
        methodology_note="benchmark+recency+price")
    await kb.create_event(title="GPT-5 launched", summary="OpenAI shipped GPT-5.",
                          event_type="MODEL_RELEASE", entity_ids=["openai"], model_ids=["gpt-5"],
                          item_ids=["u1", "u2"], significance_score=92,
                          first_item_at=now, last_item_at=now)


@pytest.mark.asyncio
async def test_help_and_leaderboard(bot, seeded_kb):
    await _setup_boards(seeded_kb)
    h = await bot.cmd_help()
    assert "/best" in h and "/leaderboard" in h
    lb = await bot.cmd_leaderboard()
    assert "coding" in lb


@pytest.mark.asyncio
async def test_best_with_synonyms(bot, seeded_kb):
    await _setup_boards(seeded_kb)
    best = await bot.cmd_best(["coding"])
    assert "Claude Opus 4.8" in best and "\U0001f947" in best  # gold medal
    assert "top benchmarks" in best
    assert "Claude Opus 4.8" in await bot.cmd_best(["code"])  # synonym
    assert "No leaderboard" in await bot.cmd_best(["nonsense"])
    assert "Usage" in await bot.cmd_best([])


@pytest.mark.asyncio
async def test_model_card_and_company_fallback(bot, seeded_kb):
    await _setup_boards(seeded_kb)
    mc = await bot.cmd_model(["claude", "opus"])
    assert "Claude Opus 4.8" in mc and "$5.0 in" in mc
    assert "SWE-bench Verified" in mc and "80.0" in mc
    assert "Claude Opus 4.8" in await bot.cmd_model(["anthropic"])  # company → lists models
    assert "No model matching" in await bot.cmd_model(["zzzznope"])


@pytest.mark.asyncio
async def test_compare(bot, seeded_kb):
    await _setup_boards(seeded_kb)
    cmp = await bot.cmd_compare(["gpt-5", "claude-opus-4-8"])
    assert "GPT-5" in cmp and "Claude Opus 4.8" in cmp
    assert "Usage" in await bot.cmd_compare(["gpt-5"])


@pytest.mark.asyncio
async def test_whatschanged(bot, seeded_kb):
    await _setup_boards(seeded_kb)
    wc = await bot.cmd_whatschanged(["week"])
    assert "GPT-5 launched" in wc
    assert "GPT-5 launched" in await bot.cmd_whatschanged([])  # default window


@pytest.mark.asyncio
async def test_switch_and_status_and_digest(bot, seeded_kb):
    await _setup_boards(seeded_kb)
    sw = await bot.cmd_switch()
    assert ("Switch recommendations" in sw) or ("still optimal" in sw)
    st = await bot.cmd_status()
    assert "Models tracked:" in st and "online" in st
    assert "DIGEST" in await bot.cmd_digest()


def test_authorization():
    import ai_junkie_updates.settings as stt
    bot = CommandBot()
    stt.settings.TELEGRAM_ADMIN_CHAT_ID = "999"
    assert bot._authorized(999) is True
    assert bot._authorized(123) is False
    stt.settings.TELEGRAM_ADMIN_CHAT_ID = ""
    assert bot._authorized(123) is True  # open when unset


def test_application_builds():
    """The telegram.ext Application builds with all handlers registered."""
    bot = CommandBot()
    app = bot._build_application()
    assert len(app.handlers[0]) >= 12
