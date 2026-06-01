"""Tests for the FilterEngine score-threshold and watchlist logic."""

from __future__ import annotations

from ai_junkie_updates.constants import DeliveryChannel
from ai_junkie_updates.pipeline.filter_engine import FilterEngine
from tests.conftest import make_update_item

WATCHLIST = ["openai", "anthropic", "acquisition"]


class TestDefaultThresholds:
    def test_critical_tier(self):
        fe = FilterEngine()
        ok, channel = fe.should_deliver(make_update_item(score=95), WATCHLIST)
        assert ok is True
        assert channel == DeliveryChannel.CRITICAL_ALERTS

    def test_high_tier(self):
        fe = FilterEngine()
        ok, channel = fe.should_deliver(make_update_item(score=75), WATCHLIST)
        assert (ok, channel) == (True, DeliveryChannel.HIGH_PRIORITY)

    def test_general_tier_inclusive_boundary(self):
        fe = FilterEngine()
        # Default deliver threshold is 50 — boundary should deliver to GENERAL.
        ok, channel = fe.should_deliver(make_update_item(score=50), WATCHLIST)
        assert (ok, channel) == (True, DeliveryChannel.GENERAL)

    def test_watchlist_match_in_tags(self):
        fe = FilterEngine()
        item = make_update_item(score=45, tags=["openai", "gpt"], source_name="rss/x")
        ok, channel = fe.should_deliver(item, WATCHLIST)
        assert (ok, channel) == (True, DeliveryChannel.WATCHLIST)

    def test_watchlist_match_in_source_name(self):
        fe = FilterEngine()
        item = make_update_item(score=45, tags=["misc"], source_name="r/OpenAI")
        ok, channel = fe.should_deliver(item, WATCHLIST)
        assert (ok, channel) == (True, DeliveryChannel.WATCHLIST)

    def test_watchlist_no_match_dropped(self):
        fe = FilterEngine()
        item = make_update_item(score=45, tags=["meta"], source_name="rss/x")
        ok, channel = fe.should_deliver(item, WATCHLIST)
        assert (ok, channel) == (False, DeliveryChannel.DROPPED)

    def test_below_watchlist_dropped(self):
        fe = FilterEngine()
        ok, channel = fe.should_deliver(make_update_item(score=10), WATCHLIST)
        assert (ok, channel) == (False, DeliveryChannel.DROPPED)

    def test_not_relevant_always_dropped(self):
        fe = FilterEngine()
        # Even a 95 score is dropped if not relevant.
        item = make_update_item(score=95, is_relevant=False)
        ok, channel = fe.should_deliver(item, WATCHLIST)
        assert (ok, channel) == (False, DeliveryChannel.DROPPED)


class TestConfigurableThresholds:
    """Item 2 fix: the AIJU_SCORE_THRESHOLD_* settings must actually apply."""

    def test_custom_deliver_threshold_raises_general_bar(self):
        fe = FilterEngine(deliver_threshold=60, watchlist_threshold=55)
        # 58 would be GENERAL under the default 50, but must drop under 60.
        ok, channel = fe.should_deliver(make_update_item(score=58, tags=["x"]), WATCHLIST)
        assert (ok, channel) == (False, DeliveryChannel.DROPPED)

    def test_custom_deliver_threshold_general_at_boundary(self):
        fe = FilterEngine(deliver_threshold=60, watchlist_threshold=55)
        ok, channel = fe.should_deliver(make_update_item(score=60), WATCHLIST)
        assert (ok, channel) == (True, DeliveryChannel.GENERAL)

    def test_custom_watchlist_threshold(self):
        fe = FilterEngine(deliver_threshold=60, watchlist_threshold=55)
        # 56 is below deliver(60) but above watchlist(55) and matches a term.
        item = make_update_item(score=56, tags=["openai"])
        ok, channel = fe.should_deliver(item, WATCHLIST)
        assert (ok, channel) == (True, DeliveryChannel.WATCHLIST)

    def test_defaults_pulled_from_settings(self):
        # With no args, thresholds come from settings (50 / 40 by default).
        fe = FilterEngine()
        assert fe._deliver_threshold == 50
        assert fe._watchlist_threshold == 40
