"""Offline tests for the live-readiness preflight (no network).

Probes are mocked so the credential logic, source-grouping, and GO/NO-GO
verdict are verified deterministically.

    python tests/test_preflight_offline.py
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from ai_junkie_updates import preflight  # noqa: E402

_results: list[tuple[str, bool]] = []


def _check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok))
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{suffix}")


def test_credentials_all_present():
    env = {
        "AIJU_ANTHROPIC_API_KEY": "x",
        "AIJU_TELEGRAM_BOT_TOKEN": "x",
        "AIJU_TELEGRAM_CHANNEL_CRITICAL": "x",
        "AIJU_TELEGRAM_CHANNEL_HIGH": "x",
        "AIJU_TELEGRAM_CHANNEL_GENERAL": "x",
        "AIJU_TELEGRAM_CHANNEL_WATCHLIST": "x",
    }
    with patch.dict(os.environ, env, clear=False):
        from ai_junkie_updates.settings import Settings
        with patch.object(preflight, "settings", Settings()):
            rows, ok = preflight.check_credentials()
    _check("credentials: all present -> ok=True", ok is True)
    _check("credentials: never leaks values (only bools)",
           all(isinstance(present, bool) for _, present, _ in rows))


def test_credentials_missing():
    env = {k: "" for k in (
        "AIJU_ANTHROPIC_API_KEY", "AIJU_TELEGRAM_BOT_TOKEN",
        "AIJU_TELEGRAM_CHANNEL_CRITICAL", "AIJU_TELEGRAM_CHANNEL_HIGH",
        "AIJU_TELEGRAM_CHANNEL_GENERAL", "AIJU_TELEGRAM_CHANNEL_WATCHLIST",
    )}
    with patch.dict(os.environ, env, clear=False):
        from ai_junkie_updates.settings import Settings
        with patch.object(preflight, "settings", Settings()):
            _rows, ok = preflight.check_credentials()
    _check("credentials: missing -> ok=False", ok is False)


def _patch_probe(result):
    """Patch preflight._probe to always return a fixed (status, detail)."""
    async def fake_probe(session, url):
        return result
    return patch.object(preflight, "_probe", fake_probe)


async def test_sources_all_reachable():
    with _patch_probe((preflight.OK, "HTTP 200")):
        rows = await preflight.check_sources()
    by_agent = {r[0]: r for r in rows}
    # URL-based agents should report fully reachable.
    _check("sources: rss all reachable", by_agent["rss"][1] == preflight.OK)
    _check("sources: github all reachable", by_agent["github"][1] == preflight.OK)
    # Credential-gated agents with no token stay NO_TOKEN even if probes 'work'.
    _check("sources: twitter without token -> NO_TOKEN",
           by_agent["twitter"][1] == preflight.NO_TOKEN)
    _check("sources: api_feed without key -> NO_TOKEN",
           by_agent["api_feed"][1] == preflight.NO_TOKEN)
    # telegram_channels has an empty config list.
    _check("sources: telegram_channels -> NO_SOURCES",
           by_agent["telegram_channels"][1] == preflight.NO_SOURCES)


async def test_sources_all_blocked():
    with _patch_probe((preflight.BLOCKED, "host not in allowlist")):
        rows = await preflight.check_sources()
    reachable = preflight.print_sources(rows)
    _check("sources: all blocked -> 0 reachable agents", reachable == 0)


async def test_sources_rate_limited():
    # Hosts respond but are auth/rate-limited (e.g. GitHub 60/hr unauthenticated).
    with _patch_probe((preflight.RATE_LIMITED, "HTTP 403 rate limit")):
        rows = await preflight.check_sources()
    by_agent = {r[0]: r for r in rows}
    _check("sources: rate-limited host -> RATE_LIMITED (not OK)",
           by_agent["github"][1] == preflight.RATE_LIMITED)
    # Rate-limited does not count as 'fully reachable' for the GO verdict.
    reachable = preflight.print_sources(rows)
    _check("sources: rate-limited not counted as reachable", reachable == 0)


def test_probe_status_classification():
    # Unit-check the status mapping the live GitHub run surfaced.
    import aiohttp
    from unittest.mock import patch as _patch

    async def run(status, body):
        class _Resp:
            def __init__(self): self.status = status
            async def read(self): return body.encode()
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
        class _Sess:
            def get(self, *a, **k): return _Resp()
        return await preflight._probe(_Sess(), "https://api.github.com/x")

    st_429, _ = asyncio.run(run(429, "{}"))
    st_403rl, _ = asyncio.run(run(403, '{"message":"API rate limit exceeded"}'))
    st_200, _ = asyncio.run(run(200, "[]"))
    _check("probe: 429 -> RATE_LIMITED", st_429 == preflight.RATE_LIMITED)
    _check("probe: 403 rate-limit body -> RATE_LIMITED", st_403rl == preflight.RATE_LIMITED)
    _check("probe: 200 -> OK", st_200 == preflight.OK)


def test_verdict_go():
    rc = preflight.print_verdict(creds_ok=True, reachable_agents=3)
    _check("verdict: creds + reachable -> GO (exit 0)", rc == 0)


def test_verdict_no_go_creds():
    rc = preflight.print_verdict(creds_ok=False, reachable_agents=5)
    _check("verdict: missing creds -> NO-GO (exit 1)", rc == 1)


def test_verdict_no_go_network():
    rc = preflight.print_verdict(creds_ok=True, reachable_agents=0)
    _check("verdict: no reachable source -> NO-GO (exit 1)", rc == 1)


async def test_twitter_token_enables_probe():
    os.environ["TWITTER_BEARER_TOKEN"] = "tok"
    try:
        with _patch_probe((preflight.OK, "HTTP 200")):
            rows = await preflight.check_sources()
    finally:
        os.environ.pop("TWITTER_BEARER_TOKEN", None)
    by_agent = {r[0]: r for r in rows}
    _check("sources: twitter WITH token -> probed OK",
           by_agent["twitter"][1] == preflight.OK)


SYNC_TESTS = [
    test_credentials_all_present, test_credentials_missing,
    test_verdict_go, test_verdict_no_go_creds, test_verdict_no_go_network,
    test_probe_status_classification,
]
ASYNC_TESTS = [
    test_sources_all_reachable, test_sources_all_blocked,
    test_sources_rate_limited, test_twitter_token_enables_probe,
]


def main() -> int:
    for t in SYNC_TESTS:
        print(f"\n{t.__name__}:")
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            _check(f"{t.__name__} raised {type(exc).__name__}", False, str(exc))
    for t in ASYNC_TESTS:
        print(f"\n{t.__name__}:")
        try:
            asyncio.run(t())
        except Exception as exc:  # noqa: BLE001
            _check(f"{t.__name__} raised {type(exc).__name__}", False, str(exc))

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n=== PREFLIGHT TESTS: {passed}/{total} checks passed ===")
    if passed != total:
        for name, ok in _results:
            if not ok:
                print("  FAILED:", name)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
