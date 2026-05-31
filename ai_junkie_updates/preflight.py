"""Live-readiness preflight.

Run before a live deployment to see, at a glance, whether the system can
actually collect and deliver:

    python -m ai_junkie_updates.preflight

It performs three checks and prints a colour-coded report:

  1. Credentials   — are the required API keys / channel IDs present?
                     (only presence is reported, never the secret values)
  2. Source reach  — can each configured source URL be reached from here?
                     (a quick HTTP probe per source, grouped by agent)
  3. Verdict       — GO / NO-GO for a live run, with the reason.

Exit code is 0 when the system is live-ready (credentials present and at
least one source reachable), 1 otherwise — so it can gate a deploy script.

No secrets are printed. No data is collected or delivered; this only probes.
"""

from __future__ import annotations

import asyncio
import sys
from typing import List, Optional, Tuple

import aiohttp

from ai_junkie_updates.agents.base_agent import load_sources
from ai_junkie_updates.settings import settings

# ---------------------------------------------------------------------------
# Terminal colours (degrade to plain text when not a TTY)
# ---------------------------------------------------------------------------

_TTY = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


def _green(t: str) -> str:
    return _c("32", t)


def _red(t: str) -> str:
    return _c("31", t)


def _yellow(t: str) -> str:
    return _c("33", t)


def _bold(t: str) -> str:
    return _c("1", t)


OK = "OK"
MISSING = "MISSING"
BLOCKED = "BLOCKED"
NO_TOKEN = "NO TOKEN"
NO_SOURCES = "NO SOURCES"
LOCAL = "LOCAL"

_MARK = {
    OK: _green("●"),
    MISSING: _red("●"),
    BLOCKED: _red("●"),
    NO_TOKEN: _yellow("●"),
    NO_SOURCES: _yellow("○"),
    LOCAL: _yellow("○"),
}


# ---------------------------------------------------------------------------
# 1. Credentials
# ---------------------------------------------------------------------------

def check_credentials() -> Tuple[List[Tuple[str, bool, bool]], bool]:
    """Return [(label, present, required)] and whether all required are present."""
    rows = [
        ("AIJU_ANTHROPIC_API_KEY", bool(settings.ANTHROPIC_API_KEY), True),
        ("AIJU_TELEGRAM_BOT_TOKEN", bool(settings.TELEGRAM_BOT_TOKEN), True),
        ("AIJU_TELEGRAM_CHANNEL_CRITICAL", bool(settings.TELEGRAM_CHANNEL_CRITICAL), True),
        ("AIJU_TELEGRAM_CHANNEL_HIGH", bool(settings.TELEGRAM_CHANNEL_HIGH), True),
        ("AIJU_TELEGRAM_CHANNEL_GENERAL", bool(settings.TELEGRAM_CHANNEL_GENERAL), True),
        ("AIJU_TELEGRAM_CHANNEL_WATCHLIST", bool(settings.TELEGRAM_CHANNEL_WATCHLIST), True),
    ]
    all_required = all(present for _, present, required in rows if required)
    return rows, all_required


def print_credentials(rows: List[Tuple[str, bool, bool]]) -> None:
    print(_bold("\n1. Credentials"))
    for label, present, required in rows:
        status = OK if present else MISSING
        tag = "" if required else _yellow(" (optional)")
        print(f"   {_MARK[status]} {label:<34} {status}{tag}")


# ---------------------------------------------------------------------------
# 2. Source reachability
# ---------------------------------------------------------------------------

# How to find each agent's probe URL(s) and whether a credential gates them.
# (agent_key, url_field, needs_token_field)
_URL_AGENTS = [
    ("rss", "url", None),
    ("web_scraper", "url", None),
    ("changelog", "url", None),
    ("github", "repo", None),          # special-cased below (repo -> api url)
    ("reddit", "subreddit", None),     # special-cased below
    ("onchain", "api_url", None),
    ("press_releases", "url", None),
    ("podcast", "url", None),
    ("regulatory", "url", None),
    ("telegram_channels", "rss_url", None),
    ("api_feed", "url", "api_key"),
    ("twitter", None, "bearer_token"),
]

_PROBE_HEADERS = {"User-Agent": "AIJunkieUpdates-Preflight/1.0"}


def _source_url(agent_key: str, src: dict) -> Optional[str]:
    """Resolve a probe URL for one configured source entry."""
    if agent_key == "github":
        repo = src.get("repo")
        return f"https://api.github.com/repos/{repo}/releases" if repo else None
    if agent_key == "reddit":
        sub = src.get("subreddit")
        return f"https://www.reddit.com/r/{sub}/new.json" if sub else None
    if agent_key == "twitter":
        return "https://api.twitter.com/2/openapi.json"
    field = next((f for k, f, _ in _URL_AGENTS if k == agent_key), None)
    return src.get(field) if field else None


async def _probe(session: aiohttp.ClientSession, url: str) -> Tuple[str, str]:
    """Probe one URL. Return (status_const, detail)."""
    try:
        async with session.get(
            url, headers=_PROBE_HEADERS, allow_redirects=True,
            timeout=aiohttp.ClientTimeout(total=12),
        ) as resp:
            body = (await resp.read())[:200].decode("utf-8", "replace").lower()
            if "not in allowlist" in body:
                return BLOCKED, "host not in network allowlist"
            # Any HTTP response (even 401/403/404) means the host is reachable.
            return OK, f"HTTP {resp.status}"
    except asyncio.TimeoutError:
        return BLOCKED, "timeout"
    except aiohttp.ClientError as exc:
        return BLOCKED, type(exc).__name__
    except Exception as exc:  # noqa: BLE001 - preflight must never raise
        return BLOCKED, type(exc).__name__


async def check_sources() -> List[Tuple[str, str, int, int, str]]:
    """Probe every configured source. Return per-agent summary rows.

    Each row: (agent, status, reachable, total, detail).
    """
    rows: List[Tuple[str, str, int, int, str]] = []
    async with aiohttp.ClientSession() as session:
        for agent_key, _url_field, token_field in _URL_AGENTS:
            sources = load_sources(agent_key)

            # discord is a passive local webhook receiver — nothing to probe.
            if agent_key == "discord":
                rows.append((agent_key, LOCAL, 0, 0, "passive webhook receiver"))
                continue

            # Credential-gated agents with no key set: skip probing, flag clearly.
            if token_field is not None:
                has_token = any(s.get(token_field) for s in sources) or (
                    agent_key == "twitter" and bool(
                        next((s.get("bearer_token") for s in sources if s.get("bearer_token")), "")
                    )
                )
                if not has_token:
                    rows.append((agent_key, NO_TOKEN, 0, len(sources),
                                 f"set {token_field.upper()} to enable"))
                    continue

            urls = [u for u in (_source_url(agent_key, s) for s in sources) if u]
            if not urls:
                rows.append((agent_key, NO_SOURCES, 0, 0, "none configured"))
                continue

            results = await asyncio.gather(*(_probe(session, u) for u in urls))
            reachable = sum(1 for st, _ in results if st == OK)
            total = len(urls)
            if reachable == total:
                status, detail = OK, "all reachable"
            elif reachable == 0:
                status = BLOCKED
                detail = results[0][1] if results else "unreachable"
            else:
                status, detail = BLOCKED, f"{total - reachable} unreachable"
            rows.append((agent_key, status, reachable, total, detail))
    return rows


def print_sources(rows: List[Tuple[str, str, int, int, str]]) -> int:
    """Print the source table; return the number of agents fully reachable."""
    print(_bold("\n2. Source reachability"))
    print(f"   {'':1} {'agent':<18} {'reach':<8} {'status':<11} detail")
    fully_ok = 0
    for agent, status, reachable, total, detail in rows:
        if status == OK:
            fully_ok += 1
        # Only show a reach fraction when an actual probe ran.
        probed = status in (OK, BLOCKED)
        reach = f"{reachable}/{total}" if (probed and total) else "-"
        mark = _MARK.get(status, "●")
        colour = _green if status == OK else (_yellow if status in (NO_TOKEN, NO_SOURCES, LOCAL) else _red)
        print(f"   {mark} {agent:<18} {reach:<8} {colour(status):<20} {detail}")
    return fully_ok


# ---------------------------------------------------------------------------
# 3. Verdict
# ---------------------------------------------------------------------------

def print_verdict(creds_ok: bool, reachable_agents: int) -> int:
    print(_bold("\n3. Verdict"))
    problems = []
    if not creds_ok:
        problems.append("required credentials are missing")
    if reachable_agents == 0:
        problems.append("no source is reachable from this environment")

    if not problems:
        print("   " + _green(_bold("GO")) +
              f" — credentials present and {reachable_agents} source group(s) reachable.")
        print("   Start the system with:  python -m ai_junkie_updates.main")
        return 0

    print("   " + _red(_bold("NO-GO")) + " — " + "; ".join(problems) + ".")
    if not creds_ok:
        print("   • Set the missing AIJU_* variables (see ai_junkie_updates/.env.example).")
    if reachable_agents == 0:
        print("   • This environment's network policy is blocking outbound HTTP.")
        print("     Run where outbound egress is allowed. See:")
        print("     https://code.claude.com/docs/en/claude-code-on-the-web")
    return 1


async def _main() -> int:
    print(_bold("AI Junkie Updates — live-readiness preflight"))
    cred_rows, creds_ok = check_credentials()
    print_credentials(cred_rows)
    source_rows = await check_sources()
    reachable_agents = print_sources(source_rows)
    return print_verdict(creds_ok, reachable_agents)


def main() -> int:
    try:
        return asyncio.run(_main())
    except KeyboardInterrupt:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
