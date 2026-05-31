"""Interactive Telegram command bot.

Phase 2 makes the advisor queryable on demand. Where ``telegram_bot.py`` is the
OUTBOUND deliverer (alerts, briefs, digests), this is the INBOUND command layer:
it runs a ``telegram.ext.Application`` that answers slash commands from the owner.

Commands are pure knowledge-base reads (no LLM at query time), so they are fast
and free:

  /leaderboard            list available leaderboards
  /best <use_case>        the leaderboard for an area (coding, video, value, ...)
  /model <name>           knowledge card for a model (price, context, benchmarks)
  /compare <a> <b>        side-by-side of two models
  /whatschanged [24h|week] recent significant events
  /switch                 deterministic "should I switch?" advice vs your profile
  /digest                 on-demand digest (uses synthesis; may call the model)
  /status, /help          operational

Both this Application and the outbound ``telegram_bot`` share the same bot token —
one bot can push to channels and answer commands. Commands are restricted to
``settings.TELEGRAM_ADMIN_CHAT_ID`` when set (single-user product).

The Application is driven via the manual lifecycle (initialize / start /
updater.start_polling) so it co-exists inside the existing asyncio app rather
than taking over the event loop with run_polling().
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from ai_junkie_updates.delivery import formatter as fmt
from ai_junkie_updates.intelligence.knowledge_base import knowledge_base
from ai_junkie_updates.intelligence.synthesis import load_profile, synthesizer
from ai_junkie_updates.settings import settings
from ai_junkie_updates.utils.logger import get_logger

log = get_logger(__name__)

# Window aliases for /whatschanged.
_WINDOWS = {"24h": 24, "day": 24, "today": 24, "48h": 48, "week": 168, "7d": 168}


class CommandBot:
    """Inbound Telegram command handler bot."""

    def __init__(self, kb=None, synth=None) -> None:
        self._kb = kb or knowledge_base
        self._synth = synth or synthesizer
        self._app = None  # telegram.ext.Application, built lazily

    # ------------------------------------------------------------- authorization
    def _authorized(self, chat_id) -> bool:
        admin = (settings.TELEGRAM_ADMIN_CHAT_ID or "").strip()
        if not admin:
            return True  # no admin configured → open (single-user dev mode)
        return str(chat_id) == admin

    # ------------------------------------------------------- command implementations
    # Each returns an HTML string; the handlers wrap these and send the reply.
    async def cmd_help(self, args=None) -> str:
        return (
            "\U0001f916 <b>AI Junkie Advisor</b>\n\n"
            "<code>/leaderboard</code> — list all leaderboards\n"
            "<code>/best &lt;area&gt;</code> — best models (coding, agents, video, research, value…)\n"
            "<code>/model &lt;name&gt;</code> — model card (price, context, benchmarks)\n"
            "<code>/compare &lt;a&gt; &lt;b&gt;</code> — compare two models\n"
            "<code>/whatschanged [24h|week]</code> — recent significant updates\n"
            "<code>/switch</code> — should I switch tools/models?\n"
            "<code>/digest</code> — on-demand digest\n"
            "<code>/status</code> — system status"
        )

    async def cmd_leaderboard(self, args=None) -> str:
        boards = await self._kb.list_leaderboards()
        if not boards:
            return "No leaderboards computed yet. They populate once benchmark data is ingested."
        use_cases = sorted(b.use_case for b in boards)
        return fmt.format_leaderboard_index(use_cases)

    async def cmd_best(self, args) -> str:
        if not args:
            boards = await self._kb.list_leaderboards()
            ucs = sorted(b.use_case for b in boards) or list(fmt.USE_CASE_LABELS)
            return "Usage: <code>/best &lt;area&gt;</code>\n\n" + fmt.format_leaderboard_index(ucs)
        use_case = self._resolve_use_case(" ".join(args))
        board = await self._kb.get_leaderboard(use_case)
        if not board:
            return (
                f"No leaderboard for <b>{fmt._esc(use_case)}</b> yet.\n"
                "Try <code>/leaderboard</code> to see available areas."
            )
        return fmt.format_leaderboard(use_case, board.ranking_json, board.methodology_note or "")

    def _resolve_use_case(self, term: str) -> str:
        """Map a free-text area to a leaderboard key."""
        t = term.strip().lower().replace(" ", "_")
        if t in fmt.USE_CASE_LABELS:
            return t
        # synonyms
        synonyms = {
            "code": "coding", "coder": "coding", "programming": "coding",
            "agent": "agents", "agentic": "agents",
            "app": "app_dev", "apps": "app_dev", "app_development": "app_dev",
            "auto": "automation",
            "writing": "content", "content_creation": "content",
            "video_editing": "video", "editing": "video",
            "analysis": "research", "researching": "research",
            "productivity": "business", "ops": "business",
            "value_for_money": "value", "cheap": "value", "price": "value",
            "overall_best": "overall", "best": "overall",
        }
        return synonyms.get(t, t)

    async def cmd_model(self, args) -> str:
        if not args:
            return "Usage: <code>/model &lt;name&gt;</code> e.g. <code>/model claude opus</code>"
        query = " ".join(args)
        model = await self._kb.find_model_by_alias(query)
        if model is None:
            # maybe they named a company — show its models
            company = await self._kb.find_company_by_alias(query)
            if company is not None:
                models = await self._kb.models_by_company(company.id)
                if models:
                    names = "\n".join(f"• {fmt._esc(m.display_name)}" for m in models)
                    return f"<b>{fmt._esc(company.name)}</b> models:\n{names}\n\nTry <code>/model &lt;name&gt;</code>."
            return f"No model matching <b>{fmt._esc(query)}</b>. Try <code>/model claude opus</code>."

        company = await self._kb.get_company(model.company_id) if model.company_id else None
        price = await self._kb.latest_price(model.id)
        scores = await self._scores_for_model(model.id)
        return fmt.format_model_card(model, company, price, scores)

    async def _scores_for_model(self, model_id: str) -> list:
        """Collect (benchmark_name, score) pairs for a model, latest per benchmark."""
        out = []
        for bench in await self._kb.list_benchmarks():
            latest = await self._kb.latest_scores_for_benchmark(bench.id)
            row = latest.get(model_id)
            if row is not None:
                out.append((bench.name, row.score))
        return out

    async def cmd_compare(self, args) -> str:
        if len(args) < 2:
            return "Usage: <code>/compare &lt;model a&gt; &lt;model b&gt;</code>"
        # Split args into two model names on a midpoint heuristic, else try alias on each.
        a = await self._kb.find_model_by_alias(args[0])
        b = await self._kb.find_model_by_alias(args[-1])
        if a is None or b is None or a.id == b.id:
            # fall back: try joining halves
            mid = len(args) // 2
            a = a or await self._kb.find_model_by_alias(" ".join(args[:mid]))
            b = b or await self._kb.find_model_by_alias(" ".join(args[mid:]))
        if a is None or b is None:
            return "Could not resolve both models. Try <code>/compare gpt-5 claude opus</code>."
        card_a = fmt.format_model_card(a, await self._kb.get_company(a.company_id) if a.company_id else None,
                                       await self._kb.latest_price(a.id), await self._scores_for_model(a.id))
        card_b = fmt.format_model_card(b, await self._kb.get_company(b.company_id) if b.company_id else None,
                                       await self._kb.latest_price(b.id), await self._scores_for_model(b.id))
        return card_a + "\n\n———\n\n" + card_b

    async def cmd_whatschanged(self, args) -> str:
        window_label = (args[0].lower() if args else "48h")
        hours = _WINDOWS.get(window_label, 48)
        if window_label not in _WINDOWS:
            window_label = "48h"
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        events = await self._kb.recent_events(limit=15, min_significance=50)
        events = [e for e in events if (e.created_at or cutoff) >= cutoff]
        return fmt.format_events(events, window_label)

    async def cmd_switch(self, args=None) -> str:
        profile = load_profile()
        recs = await self._synth.compute_switch_recommendations(profile)
        return fmt.format_switch_recommendations(recs)

    async def cmd_digest(self, args=None) -> str:
        if not settings.ENABLE_SYNTHESIS:
            return "Synthesis is disabled (collection-only mode). Use <code>/whatschanged</code>."
        return await self._synth.build_digest()

    async def cmd_status(self, args=None) -> str:
        models = await self._kb.list_models()
        companies = await self._kb.list_companies()
        boards = await self._kb.list_leaderboards()
        events = await self._kb.recent_events(limit=1)
        last_event = events[0].created_at.isoformat() if events else "none yet"
        return (
            "✅ <b>AI Junkie Advisor — online</b>\n\n"
            f"Companies tracked: {len(companies)}\n"
            f"Models tracked: {len(models)}\n"
            f"Leaderboards: {len(boards)}\n"
            f"Latest event: {fmt._esc(last_event)}\n"
            f"Triage model: <code>{fmt._esc(settings.CLAUDE_TRIAGE_MODEL)}</code>\n"
            f"Synthesis model: <code>{fmt._esc(settings.CLAUDE_SYNTHESIS_MODEL)}</code>"
        )

    # ------------------------------------------------------------ telegram glue
    def _build_application(self):
        from telegram.ext import Application, CommandHandler

        app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

        # (command, handler-coroutine, takes-args)
        mapping = [
            ("help", self.cmd_help), ("start", self.cmd_help),
            ("leaderboard", self.cmd_leaderboard), ("leaderboards", self.cmd_leaderboard),
            ("best", self.cmd_best),
            ("model", self.cmd_model),
            ("compare", self.cmd_compare),
            ("whatschanged", self.cmd_whatschanged), ("whats_changed", self.cmd_whatschanged),
            ("switch", self.cmd_switch),
            ("digest", self.cmd_digest),
            ("status", self.cmd_status),
        ]
        for name, impl in mapping:
            app.add_handler(CommandHandler(name, self._make_handler(impl)))
        return app

    def _make_handler(self, impl):
        """Wrap a cmd_* coroutine into a telegram handler with auth + error guard."""
        async def handler(update, context):
            chat_id = update.effective_chat.id if update.effective_chat else None
            if not self._authorized(chat_id):
                await update.message.reply_text("Not authorized.")
                return
            try:
                text = await impl(getattr(context, "args", []) or [])
            except TypeError:
                # impls that take no args
                text = await impl()
            except Exception as exc:
                log.error("command_error", command=impl.__name__, error=str(exc))
                text = "⚠️ Something went wrong handling that command."
            await update.message.reply_text(
                text, parse_mode="HTML", disable_web_page_preview=True
            )
        return handler

    # --------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        """Initialise and start polling for commands (non-blocking)."""
        if not settings.TELEGRAM_BOT_TOKEN:
            log.warning("command_bot_disabled", reason="no bot token")
            return
        self._app = self._build_application()
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        log.info("command_bot_started",
                 admin_restricted=bool(settings.TELEGRAM_ADMIN_CHAT_ID))

    async def stop(self) -> None:
        """Stop polling and shut down the Application."""
        if self._app is None:
            return
        try:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        except Exception as exc:
            log.warning("command_bot_stop_error", error=str(exc))


command_bot = CommandBot()
