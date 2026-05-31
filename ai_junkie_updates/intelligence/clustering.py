"""Story clustering — collapse same-story items into a single Event.

A single development (e.g. "OpenAI ships GPT-5.1") is typically reported by many
sources within a short window: an RSS article, a Reddit thread, a YouTube video,
a press release. Each arrives as its own ``updates`` row. Clustering groups those
near-duplicate-but-not-identical items into one canonical ``events`` row so the
advisor reasons about *one* story, not twelve copies of it.

This runs AFTER entity linking and is **deterministic-first** — no LLM cost. Two
items are judged "same story" when they:

  * share at least one strong entity (a model or a company), AND
  * fall within a time window of each other, AND
  * have enough lexical overlap in their headlines/tags (Jaccard over tokens).

Items already assigned to an event (``event_id`` set) are skipped, so the job is
idempotent and incremental. Each new cluster becomes an Event whose
``significance_score`` is the max item score, whose ``event_type`` is the most
common category, and whose title is the highest-scoring item's headline.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import timedelta
from typing import Dict, List

from ai_junkie_updates.core.database import db
from ai_junkie_updates.utils.logger import get_logger

log = get_logger(__name__)

# Tuning knobs (deliberately conservative — prefer a few extra events over
# wrongly merging unrelated stories).
TIME_WINDOW_HOURS = 36
MIN_TOKEN_JACCARD = 0.18
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
        "is", "are", "be", "by", "at", "as", "new", "now", "ai", "its", "it",
        "this", "that", "from", "has", "have", "will", "what", "how", "why",
        "you", "your", "we", "they", "their", "more", "into", "out", "up",
    }
)


def _tokens(text: str) -> set:
    """Lowercase alphanumeric tokens (len>2), minus stopwords."""
    raw = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {t for t in raw if len(t) > 2 and t not in _STOPWORDS}


def _item_tokens(item: dict) -> set:
    toks = _tokens(item.get("headline", ""))
    for tag in item.get("tags", []):
        toks |= _tokens(tag)
    return toks


def _strong_entities(item: dict) -> set:
    """Models + companies — the identity signal for a story."""
    ents = item.get("entities") or {}
    return {f"m:{m}" for m in ents.get("models", [])} | {
        f"c:{c}" for c in ents.get("companies", [])
    }


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class Clusterer:
    """Group entity-linked items into Event clusters."""

    def _same_story(self, a: dict, b: dict) -> bool:
        # 1) shared strong entity
        if not (_strong_entities(a) & _strong_entities(b)):
            return False
        # 2) time proximity
        ta, tb = a.get("analyzed_at"), b.get("analyzed_at")
        if ta and tb and abs((ta - tb)) > timedelta(hours=TIME_WINDOW_HOURS):
            return False
        # 3) lexical overlap
        return _jaccard(a["_tokens"], b["_tokens"]) >= MIN_TOKEN_JACCARD

    def cluster_items(self, items: List[dict]) -> List[List[dict]]:
        """Greedy single-link clustering. Returns a list of item-groups.

        Items are processed newest-first; each item joins the first existing
        cluster it matches (by matching any member), else starts a new cluster.
        """
        for it in items:
            it["_tokens"] = _item_tokens(it)

        clusters: List[List[dict]] = []
        for it in items:
            placed = False
            for cluster in clusters:
                if any(self._same_story(it, member) for member in cluster):
                    cluster.append(it)
                    placed = True
                    break
            if not placed:
                clusters.append([it])
        return clusters

    def _summarize_cluster(self, cluster: List[dict]) -> dict:
        """Derive Event fields from a group of items (deterministic, no LLM)."""
        lead = max(cluster, key=lambda x: x.get("score", 0))
        categories = [c["category"] for c in cluster if c.get("category")]
        event_type = Counter(categories).most_common(1)[0][0] if categories else None

        companies, models, tools, item_ids = [], [], [], []
        for c in cluster:
            ents = c.get("entities") or {}
            for x in ents.get("companies", []):
                if x not in companies:
                    companies.append(x)
            for x in ents.get("models", []):
                if x not in models:
                    models.append(x)
            for x in ents.get("tools", []):
                if x not in tools:
                    tools.append(x)
            item_ids.append(c["id"])

        times = [c["analyzed_at"] for c in cluster if c.get("analyzed_at")]
        entity_ids = companies + [f"tool:{t}" for t in tools]
        return {
            "title": lead.get("headline", "Untitled event"),
            "summary": lead.get("summary", ""),
            "event_type": event_type,
            "primary_entity_id": companies[0] if companies else None,
            "entity_ids": entity_ids,
            "model_ids": models,
            "item_ids": item_ids,
            "significance_score": max((c.get("score", 0) for c in cluster), default=0),
            "first_item_at": min(times) if times else None,
            "last_item_at": max(times) if times else None,
        }

    async def run_once(self, hours: int = 48, limit: int = 500, kb=None) -> dict:
        """Cluster recent event-less linked items and persist new Events.

        Only items that linked to at least one strong entity are clustered;
        entity-less items are left for a future run (they may link later or are
        simply ungrouped noise). Returns a summary dict.
        """
        from ai_junkie_updates.intelligence.knowledge_base import knowledge_base

        K = kb or knowledge_base
        items = await db.get_linked_items(hours=hours, limit=limit, eventless_only=True)
        # Keep only items with a strong entity to anchor the story.
        items = [it for it in items if _strong_entities(it)]
        if not items:
            return {"items": 0, "events": 0}

        clusters = self.cluster_items(items)
        events_created = 0
        for cluster in clusters:
            fields = self._summarize_cluster(cluster)
            event_id = await K.create_event(**fields)
            for member in cluster:
                await db.set_item_event(member["id"], event_id)
            events_created += 1

        log.info(
            "clustering_done",
            items=len(items),
            events=events_created,
        )
        return {"items": len(items), "events": events_created}


clusterer = Clusterer()
