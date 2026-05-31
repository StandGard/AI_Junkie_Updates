#!/usr/bin/env python3
"""Send ONE real test message through the production Telegram path.

Purpose
-------
Confirms end-to-end delivery: real bot token -> real api.telegram.org ->
a real chat. It builds a sample UpdateItem and pushes it through the exact
same TelegramBot.send() used in production (formatter + rate limiter +
send_message), so a success here means the live pipeline can deliver.

Usage
-----
    python scripts/send_test_message.py <chat_id>

  <chat_id>  Destination. Your personal id (DM), or a channel's -100... id.
             If omitted, falls back to AIJU_TELEGRAM_CHANNEL_CRITICAL from .env.

Prerequisites
-------------
  * AIJU_TELEGRAM_BOT_TOKEN set in ai_junkie_updates/.env  (already done)
  * For a DM: you must have pressed START on @AIJunkieUpdatesBot first,
    otherwise Telegram returns 403 "bot can't initiate conversation".
  * For a channel: the bot must be an admin of it.
  * Outbound network to api.telegram.org (BLOCKED in the web sandbox; run this
    where the bot can actually reach Telegram, e.g. the Docker deployment).
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# The telegram library logs full tracebacks on each retry when the response
# isn't valid JSON (e.g. a sandbox proxy returning a bare error string). Quiet
# it so this CLI's own messages aren't buried.
logging.getLogger("telegram").setLevel(logging.CRITICAL)
logging.getLogger("httpx").setLevel(logging.CRITICAL)

# Run-as-a-script path fix: ensure the repo root (not scripts/) is importable.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_junkie_updates.settings import settings  # noqa: E402
from ai_junkie_updates.constants import (  # noqa: E402
    DeliveryChannel,
    UpdateCategory,
    UrgencyLevel,
    SourceType,
)
from ai_junkie_updates.core.models import UpdateItem  # noqa: E402
from ai_junkie_updates.delivery.telegram_bot import TelegramBot  # noqa: E402


def _resolve_chat_id() -> str:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip()
    fallback = settings.TELEGRAM_CHANNEL_CRITICAL
    if fallback:
        print(f"No chat_id argument given; using AIJU_TELEGRAM_CHANNEL_CRITICAL ({fallback}).")
        return fallback
    print("ERROR: no chat_id given and AIJU_TELEGRAM_CHANNEL_CRITICAL is empty.")
    print("Usage: python scripts/send_test_message.py <chat_id>")
    sys.exit(2)


def _sample_item() -> UpdateItem:
    return UpdateItem(
        id="aiju-test-message",
        source_type=SourceType.GITHUB,
        source_name="AI Junkie Updates",
        source_url="https://github.com/standgard/ai_junkie_updates",
        is_relevant=True,
        category=UpdateCategory.OPEN_SOURCE_RELEASE,
        urgency=UrgencyLevel.CRITICAL,
        score=99,
        headline="✅ AI Junkie Updates — live delivery test",
        summary="If you can read this in Telegram, end-to-end delivery works: "
                "token, network, and chat_id are all good.",
        reasoning="Sent by scripts/send_test_message.py to verify the live path.",
        tags=["test", "telegram", "setup"],
        collected_at=datetime.now(timezone.utc),
        delivery_channel=DeliveryChannel.CRITICAL_ALERTS,
    )


async def _run(chat_id: str) -> int:
    if not settings.TELEGRAM_BOT_TOKEN:
        print("ERROR: AIJU_TELEGRAM_BOT_TOKEN is not set in .env.")
        return 1

    bot = TelegramBot()
    # Create the real Bot, then point the CRITICAL tier at the chosen chat_id
    # (override AFTER _ensure_bot so it isn't clobbered by settings).
    bot._ensure_bot()
    bot._channel_map[DeliveryChannel.CRITICAL_ALERTS] = chat_id

    print(f"Sending test message to chat_id={chat_id} via the production send path...")
    try:
        await bot.send(_sample_item())
    except Exception as exc:  # noqa: BLE001 - surface the real Telegram error
        # Telegram wraps the underlying cause, so walk the whole chain.
        parts, cur = [], exc
        while cur is not None:
            parts.append(f"{type(cur).__name__}: {cur}")
            cur = cur.__cause__ or cur.__context__
        chain = "  <-  ".join(parts)
        low = chain.lower()
        print(f"FAILED: {chain}")
        if "allowlist" in low or "invalid server response" in low:
            print("-> Looks like this environment can't reach api.telegram.org "
                  "(network allowlist returns a non-JSON error). Run where the "
                  "bot has real internet access.")
        elif "chat not found" in low:
            print("-> The chat_id is wrong, or (for a DM) you haven't pressed "
                  "START on @AIJunkieUpdatesBot yet.")
        elif "can't initiate" in low:
            print("-> Press START on @AIJunkieUpdatesBot first, then re-run.")
        elif "unauthorized" in low or "401" in low:
            print("-> The bot token is invalid or revoked.")
        elif "not enough rights" in low or "forbidden" in low:
            print("-> The bot must be an ADMIN of that channel to post.")
        return 1

    print("SUCCESS: message sent. Check Telegram — it should be there.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run(_resolve_chat_id())))
