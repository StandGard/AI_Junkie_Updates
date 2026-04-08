"""Filter engine — decides whether and where to deliver an update."""

from __future__ import annotations

from typing import List, Tuple

from ai_junkie_updates.constants import (
    SCORE_IMMEDIATE,
    SCORE_IMPORTANT,
    SCORE_WATCHLIST,
    SCORE_WORTH_KNOWING,
    DeliveryChannel,
)
from ai_junkie_updates.core.models import UpdateItem


class FilterEngine:
    """Apply score thresholds and watchlist matching to decide delivery."""

    def should_deliver(
        self, item: UpdateItem, watchlist: List[str]
    ) -> Tuple[bool, DeliveryChannel]:
        """Return (should_deliver, channel) for the given item."""
        if not item.is_relevant:
            return False, DeliveryChannel.DROPPED

        if item.score >= SCORE_IMMEDIATE:
            return True, DeliveryChannel.CRITICAL_ALERTS

        if item.score >= SCORE_IMPORTANT:
            return True, DeliveryChannel.HIGH_PRIORITY

        if item.score >= SCORE_WORTH_KNOWING:
            return True, DeliveryChannel.GENERAL

        if item.score >= SCORE_WATCHLIST:
            watchlist_lower = [w.lower() for w in watchlist]
            tags_lower = [t.lower() for t in item.tags]
            source_lower = item.source_name.lower()
            for term in watchlist_lower:
                if term in source_lower:
                    return True, DeliveryChannel.WATCHLIST
                for tag in tags_lower:
                    if term in tag:
                        return True, DeliveryChannel.WATCHLIST

        return False, DeliveryChannel.DROPPED
