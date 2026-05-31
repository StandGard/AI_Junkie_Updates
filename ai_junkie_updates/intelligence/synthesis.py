"""Advisor synthesis — turns events + leaderboards into actionable briefs.

This is the only intelligence stage that uses the STRONG Claude model, and it
runs periodically (not per item), so its cost is bounded. Two products:

  * Event briefs  — for each significant new Event: what changed / why it matters
                    / who should care / action.
  * Digests       — periodic roll-up of top events + leaderboard state + switch
                    recommendations tailored to the user's profile.

"Should I switch?" advice is computed DETERMINISTICALLY here (compare the user's
current pick per use-case against the top of that leaderboard, honouring a margin
from the profile) and then handed to the model as facts to explain — so switch
advice is always grounded in the leaderboard, never hallucinated.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from ai_junkie_updates.core.claude_client import claude_client
from ai_junkie_updates.core.prompts.synthesis_prompt import (
    DIGEST_SYSTEM_PROMPT,
    EVENT_BRIEF_SYSTEM_PROMPT,
)
from ai_junkie_updates.intelligence.knowledge_base import knowledge_base
from ai_junkie_updates.utils.logger import get_logger

log = get_logger(__name__)

PROFILE_PATH = Path(__file__).resolve().parent.parent / "config" / "profile.yaml"


def load_profile(path: Optional[Path] = None) -> dict:
    """Load the user profile, returning an empty dict on any failure."""
    try:
        with open(path or PROFILE_PATH, "r") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


class Synthesizer:
    """Produce event briefs, switch recommendations, and digests."""

    def __init__(self, kb=None, client=None) -> None:
        self._kb = kb or knowledge_base
        self._client = client or claude_client

    # --------------------------------------------------- switch recommendations
    async def compute_switch_recommendations(self, profile: Optional[dict] = None) -> List[dict]:
        """Compare the user's current models against each leaderboard's leader.

        Deterministic. Returns a list of recommendation dicts; empty if the
        current stack already leads (within the margin).
        """
        profile = profile if profile is not None else load_profile()
        current = profile.get("current_models", {}) or {}
        margin = float(profile.get("switch_margin", 0.08))
        priorities = profile.get("priorities") or list(current.keys())

        recs: List[dict] = []
        for use_case in priorities:
            board = await self._kb.get_leaderboard(use_case)
            if not board or not board.ranking_json:
                continue
            ranking = board.ranking_json
            leader = ranking[0]
            current_model = current.get(use_case)

            if current_model is None:
                # No current pick → recommend the leader outright.
                recs.append(
                    {
                        "use_case": use_case,
                        "from": None,
                        "to": leader["model_id"],
                        "to_name": leader.get("display_name", leader["model_id"]),
                        "reason": leader.get("rationale", "tops the leaderboard"),
                        "delta": None,
                    }
                )
                continue

            if leader["model_id"] == current_model:
                continue  # already on the leader

            cur_row = next((r for r in ranking if r["model_id"] == current_model), None)
            cur_score = cur_row["score"] if cur_row else 0.0
            if leader["score"] - cur_score >= margin:
                recs.append(
                    {
                        "use_case": use_case,
                        "from": current_model,
                        "to": leader["model_id"],
                        "to_name": leader.get("display_name", leader["model_id"]),
                        "reason": leader.get("rationale", "higher leaderboard score"),
                        "delta": round(leader["score"] - cur_score, 3),
                    }
                )
        return recs

    # ------------------------------------------------------------- event briefs
    def _event_payload(self, event) -> dict:
        return {
            "title": event.title,
            "summary": event.summary,
            "event_type": event.event_type,
            "companies": event.entity_ids,
            "models": event.model_ids,
            "significance": event.significance_score,
            "source_count": len(event.item_ids or []),
        }

    async def brief_for_events(self, events, profile: Optional[dict] = None) -> Optional[str]:
        """Generate advisor briefs for a list of Event rows (one model call)."""
        if not events:
            return None
        profile = profile if profile is not None else load_profile()
        payload = {
            "profile": {
                "about": profile.get("about", ""),
                "priorities": profile.get("priorities", []),
            },
            "events": [self._event_payload(e) for e in events],
        }
        user_message = (
            "Produce a brief for each event below.\n\n"
            + json.dumps(payload, indent=2, default=str)
        )
        try:
            return await self._client.synthesize(
                EVENT_BRIEF_SYSTEM_PROMPT, user_message, max_tokens=1500
            )
        except Exception as exc:
            log.warning("event_brief_failed", error=str(exc))
            return self._fallback_brief(events)

    def _fallback_brief(self, events) -> str:
        """Deterministic brief if the model is unavailable (no API key, error)."""
        lines = []
        for e in events:
            lines.append(f"• {e.title}")
            if e.summary:
                lines.append(f"  {e.summary}")
            tag = f"  [{e.event_type or 'update'}] significance {e.significance_score}"
            if e.model_ids:
                tag += f" · models: {', '.join(e.model_ids)}"
            lines.append(tag)
        return "\n".join(lines)

    # ------------------------------------------------------------------ digests
    async def build_digest(self, hours: int = 24, max_events: int = 8,
                           profile: Optional[dict] = None) -> str:
        """Assemble and synthesize a periodic digest."""
        profile = profile if profile is not None else load_profile()
        events = await self._kb.recent_events(limit=max_events, min_significance=50)
        recs = await self.compute_switch_recommendations(profile)

        # Compact leaderboard snapshot for the user's priorities.
        boards: Dict[str, list] = {}
        for uc in (profile.get("priorities") or []):
            board = await self._kb.get_leaderboard(uc)
            if board and board.ranking_json:
                boards[uc] = [
                    {"model": r.get("display_name", r["model_id"]), "rank": r["rank"]}
                    for r in board.ranking_json[:3]
                ]

        payload = {
            "profile": {
                "about": profile.get("about", ""),
                "priorities": profile.get("priorities", []),
            },
            "top_events": [self._event_payload(e) for e in events],
            "leaderboards": boards,
            "switch_recommendations": recs,
        }
        user_message = (
            "Write the digest from the data below.\n\n"
            + json.dumps(payload, indent=2, default=str)
        )
        try:
            return await self._client.synthesize(
                DIGEST_SYSTEM_PROMPT, user_message, max_tokens=1800
            )
        except Exception as exc:
            log.warning("digest_failed", error=str(exc))
            return self._fallback_digest(events, recs, boards)

    def _fallback_digest(self, events, recs, boards) -> str:
        lines = ["AI Junkie Digest", ""]
        if events:
            lines.append("Top developments:")
            for e in events:
                lines.append(f"• {e.title}")
            lines.append("")
        if recs:
            lines.append("Switch recommendations:")
            for r in recs:
                frm = r["from"] or "(none)"
                lines.append(f"• {r['use_case']}: {frm} → {r['to_name']} ({r['reason']})")
        elif boards:
            lines.append("Your current stack is still optimal for your priorities.")
        return "\n".join(lines)


synthesizer = Synthesizer()
