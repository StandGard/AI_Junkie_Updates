#!/usr/bin/env python3
"""Discover Telegram chat IDs that have messaged the bot.

Why this exists
---------------
To deliver alerts, the bot needs a *destination* chat ID (your personal ID
for DMs, or a channel's -100... ID). The bot's own token does NOT contain
that — a destination is whoever the bot talks TO, not the bot itself.

How to use
----------
1. In Telegram, open your bot (@AIJunkieUpdatesBot) and press START, then
   send it any message (e.g. "hi"). For a channel, add the bot as admin and
   post a message in the channel.
2. Run this script in an environment with outbound network access:

       python scripts/get_chat_id.py

   It reads AIJU_TELEGRAM_BOT_TOKEN from the environment / .env, calls
   Telegram's getUpdates, and prints every chat that has interacted with the
   bot, with its numeric chat_id.

3. Copy the chat_id you want and paste it into ai_junkie_updates/.env as the
   four AIJU_TELEGRAM_CHANNEL_* values (or hand it to Claude to wire in).

Note: getUpdates only returns recent updates, and only those NOT already
consumed by a running poller. If you get nothing, send the bot a fresh
message and re-run. This will NOT work in the web/sandbox environment because
api.telegram.org is blocked by the network allowlist — run it where the bot
can actually reach Telegram.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# When run as `python scripts/get_chat_id.py`, sys.path[0] is the scripts/
# directory, so the package import below would fail. Put the repo root first.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _token_from_env_file() -> str:
    """Read AIJU_TELEGRAM_BOT_TOKEN straight from ai_junkie_updates/.env.

    Fallback for when the package can't be imported: settings normally loads
    the .env, but if that import fails we still want the token.
    """
    env_path = REPO_ROOT / "ai_junkie_updates" / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("AIJU_TELEGRAM_BOT_TOKEN=") and "=" in line:
            return line.split("=", 1)[1].strip()
    return ""


try:
    # Reuse the app's settings so token loading matches the real system.
    from ai_junkie_updates.settings import settings
    token = settings.TELEGRAM_BOT_TOKEN
except Exception:  # pragma: no cover - fallback if run outside the package
    token = os.environ.get("AIJU_TELEGRAM_BOT_TOKEN", "") or _token_from_env_file()

if not token:
    print("ERROR: AIJU_TELEGRAM_BOT_TOKEN is not set (checked settings + env).")
    print("Set it in ai_junkie_updates/.env, then re-run.")
    sys.exit(1)


def main() -> int:
    import json
    import urllib.request
    import urllib.error

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        print(f"HTTP {exc.code} from Telegram: {body}")
        if exc.code == 401:
            print("-> 401 means the bot token is invalid or revoked.")
        return 1
    except Exception as exc:  # network/allowlist/etc.
        print(f"Could not reach api.telegram.org: {exc}")
        print("-> If you're in the web/sandbox, this host is blocked by the "
              "network allowlist. Run this where the bot can reach Telegram.")
        return 1

    if not data.get("ok"):
        print(f"Telegram returned an error: {data}")
        return 1

    updates = data.get("result", [])
    if not updates:
        print("No updates yet. Open @AIJunkieUpdatesBot, press START, send it "
              "a message, then re-run. (For a channel, post a message there "
              "with the bot added as admin.)")
        return 0

    seen: dict[int, str] = {}
    for upd in updates:
        msg = (upd.get("message") or upd.get("channel_post")
               or upd.get("edited_message") or {})
        chat = msg.get("chat") or {}
        cid = chat.get("id")
        if cid is None:
            continue
        ctype = chat.get("type", "?")
        title = chat.get("title") or " ".join(
            x for x in (chat.get("first_name"), chat.get("last_name")) if x
        ) or chat.get("username") or ""
        seen[cid] = f"{ctype:8s} {title}".rstrip()

    if not seen:
        print("Got updates, but none contained a chat id.")
        return 0

    print("Chats that have interacted with the bot:")
    print("-" * 48)
    for cid, label in seen.items():
        print(f"  chat_id = {cid}    ({label})")
    print("-" * 48)
    print("Use the chat_id you want as AIJU_TELEGRAM_CHANNEL_* in .env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
