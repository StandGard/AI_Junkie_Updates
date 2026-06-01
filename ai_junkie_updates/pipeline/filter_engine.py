"""Filter engine — decides whether and where to deliver an update."""

from __future__ import annotations

from typing import List, Optional, Tuple

from ai_junkie_updates.constants import (
    SCORE_IMMEDIATE,
    SCORE_IMPORTANT,
    DeliveryChannel,
)
from ai_junkie_updates.core.models import UpdateItem
from ai_junkie_updates.settings import settings


class FilterEngine:
    """Apply score thresholds and watchlist matching to decide delivery.

    The CRITICAL (>=90) and HIGH (>=70) tiers use fixed constants. The GENERAL
    and WATCHLIST thresholds are configurable via the AIJU_SCORE_THRESHOLD_DELIVER
    and AIJU_SCORE_THRESHOLD_WATCHLIST settings.
    """

    def __init__(
        self,
        deliver_threshold: Optional[int] = None,
        watchlist_threshold: Optional[int] = None,
    ) -> None:
        self._deliver_threshold = (
            deliver_threshold
            if deliver_threshold is not None
            else settings.SCORE_THRESHOLD_DELIVER
        )
        self._watchlist_threshold = (
            watchlist_threshold
            if watchlist_threshold is not None
            else settings.SCORE_THRESHOLD_WATCHLIST
        )

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

        if item.score >= self._deliver_threshold:
            return True, DeliveryChannel.GENERAL

        if item.score >= self._watchlist_threshold:
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
