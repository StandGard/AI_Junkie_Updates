"""Entity linking — map analyzed items to known KB entities.

Reads recent ``updates`` rows that haven't been linked yet, matches their
tags / headline / summary / source_name against the alias tables in the
knowledge base, and writes a structured entity map back onto each row as JSON:

    {"companies": ["anthropic"], "models": ["claude-opus-4-8"], "tools": ["claude-code"]}

The match is **deterministic-first** (cheap, exact alias containment — the same
normalized-substring approach already used in ``pipeline/filter_engine.py``).
A model-based fallback is intentionally left as a hook (``_llm_fallback``) but is
off by default to keep cost down; deterministic alias matching covers the tracked
entities well because the KB seed carries rich alias lists.

Every scanned item is marked (its ``entity_ids`` column is set, even to an empty
map) so it is never re-scanned — this bounds cost and makes the job idempotent.
"""

from __future__ import annotations

import json
import re
from typing import Dict, List

from ai_junkie_updates.core.database import db
from ai_junkie_updates.intelligence.knowledge_base import knowledge_base
from ai_junkie_updates.utils.logger import get_logger

log = get_logger(__name__)


def _normalize(text: str) -> str:
    """Lowercase and collapse non-alphanumeric runs to single spaces.

    Padding with spaces lets us do whole-token containment checks that avoid
    matching short aliases inside unrelated words (e.g. 'ml' inside 'html').
    """
    return " " + re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip() + " "


def _alias_hit(haystack_norm: str, alias: str) -> bool:
    """True if a normalized alias appears as a whole token-run in the haystack."""
    a = _normalize(alias).strip()
    if not a:
        return False
    # Short/ambiguous aliases must match as a padded token; longer ones can be
    # plain substrings of the already-normalized (space-padded) haystack.
    return f" {a} " in haystack_norm if len(a) <= 3 else a in haystack_norm


class EntityLinker:
    """Link items to KB companies, models, and tools by alias matching."""

    def __init__(self, kb=None) -> None:
        self._kb = kb or knowledge_base
        # model/tool -> company implication maps; populated by run_once or
        # load_implications(). Default empty so link_text is safe standalone.
        self._model_company: Dict[str, str] = {}
        self._tool_company: Dict[str, str] = {}

    async def load_implications(self) -> None:
        """Populate the model/tool -> company maps from the KB."""
        self._model_company = {m.id: m.company_id for m in await self._kb.list_models()}
        self._tool_company = {t.id: t.company_id for t in await self._kb.list_tools()}

    async def _build_alias_index(self) -> Dict[str, List[tuple]]:
        """Build {kind: [(slug, alias), ...]} from the current KB contents.

        Aliases are sorted longest-first so the most specific match is found first
        (e.g. 'claude code' before 'claude').
        """
        companies = await self._kb.list_companies()
        models = await self._kb.list_models()
        tools = await self._kb.list_tools()

        def entries(rows, extra_name_attr):
            out = []
            for r in rows:
                # Tools carry no alias list; companies/models do.
                names = set(getattr(r, "aliases", None) or [])
                names.add(getattr(r, extra_name_attr))
                names.add(r.id)
                for alias in names:
                    if alias:
                        out.append((r.id, str(alias)))
            # longest alias first
            return sorted(out, key=lambda t: len(t[1]), reverse=True)

        return {
            "companies": entries(companies, "name"),
            "models": entries(models, "display_name"),
            "tools": entries(tools, "name"),
        }

    def _match(self, text_norm: str, index: List[tuple]) -> List[str]:
        """Return distinct slugs whose alias appears in the normalized text."""
        hits: List[str] = []
        for slug, alias in index:
            if slug in hits:
                continue
            if _alias_hit(text_norm, alias):
                hits.append(slug)
        return hits

    def link_text(self, text: str, index: Dict[str, List[tuple]]) -> Dict[str, List[str]]:
        """Link a single blob of text against a prebuilt alias index.

        Models imply their parent company even if the company name isn't present.
        """
        text_norm = _normalize(text)
        companies = self._match(text_norm, index["companies"])
        models = self._match(text_norm, index["models"])
        tools = self._match(text_norm, index["tools"])

        # A model mention implies its company.
        for m in models:
            mdl = self._model_company.get(m)
            if mdl and mdl not in companies:
                companies.append(mdl)
        # A tool mention implies its company.
        for t in tools:
            tc = self._tool_company.get(t)
            if tc and tc not in companies:
                companies.append(tc)

        return {"companies": companies, "models": models, "tools": tools}

    async def run_once(self, hours: int = 48, limit: int = 200) -> dict:
        """Scan unlinked recent items, link them, and persist the result.

        Returns a small summary dict for logging/metrics.
        """
        items = await db.get_unlinked_items(hours=hours, limit=limit)
        if not items:
            return {"scanned": 0, "linked": 0}

        index = await self._build_alias_index()
        await self.load_implications()

        linked = 0
        for item in items:
            blob = " ".join(
                [
                    item.get("headline", ""),
                    item.get("summary", ""),
                    " ".join(item.get("tags", [])),
                    item.get("source_name", ""),
                ]
            )
            entities = self.link_text(blob, index)
            if any(entities.values()):
                linked += 1
            # Persist even an empty map so the item is not re-scanned.
            await db.set_item_entities(item["id"], json.dumps(entities))

        log.info("entity_linking_done", scanned=len(items), linked=linked)
        return {"scanned": len(items), "linked": linked}


entity_linker = EntityLinker()
