"""Tests for the Telegram HTML message formatter."""

from __future__ import annotations

from ai_junkie_updates.constants import UpdateCategory
from ai_junkie_updates.delivery.formatter import Formatter
from tests.conftest import make_update_item


def test_format_includes_headline_summary_and_score():
    item = make_update_item(headline="Big news", summary="It happened.", score=88)
    msg = Formatter().format_message(item)
    assert "Big news" in msg
    assert "It happened." in msg
    assert "88/100" in msg
    assert "<b>" in msg  # headline is bold


def test_html_special_chars_are_escaped():
    item = make_update_item(headline="A < B & C > D", summary="x & y")
    msg = Formatter().format_message(item)
    # Raw angle brackets from content must be escaped to avoid breaking HTML.
    assert "&lt;" in msg and "&gt;" in msg and "&amp;" in msg
    assert "A < B" not in msg


def test_source_url_renders_link():
    item = make_update_item()
    item.source_url = "https://example.com/x"
    msg = Formatter().format_message(item)
    assert 'href="https://example.com/x"' in msg
    assert "Read more" in msg


def test_no_url_omits_link():
    item = make_update_item()
    item.source_url = None
    msg = Formatter().format_message(item)
    assert "Read more" not in msg


def test_tags_rendered_when_present():
    item = make_update_item(tags=["openai", "gpt"])
    msg = Formatter().format_message(item)
    assert "openai" in msg and "gpt" in msg


def test_category_without_emoji_mapping_falls_back():
    item = make_update_item(category=UpdateCategory.OTHER)
    msg = Formatter().format_message(item)
    assert msg  # does not raise; produces a message
