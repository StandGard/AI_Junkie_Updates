"""Tests for the Normalizer pipeline stage."""

from __future__ import annotations

from ai_junkie_updates.pipeline.normalizer import MAX_CONTENT_LENGTH, Normalizer

from tests.conftest import make_raw_item


def test_normalize_strips_html_and_collapses_whitespace():
    item = make_raw_item(raw_content="<p>Hello   <b>World</b></p>\n\n\nfoo")
    out = Normalizer().normalize(item)
    assert "<" not in out.raw_content
    assert "  " not in out.raw_content  # whitespace collapsed
    assert "Hello World foo" in out.raw_content


def test_normalize_truncates_long_content():
    item = make_raw_item(raw_content="a" * (MAX_CONTENT_LENGTH + 500))
    out = Normalizer().normalize(item)
    assert len(out.raw_content) <= MAX_CONTENT_LENGTH


def test_normalize_returns_new_item_without_mutating_original():
    original = make_raw_item(raw_content="<p>x</p>")
    out = Normalizer().normalize(original)
    assert out is not original
    assert original.raw_content == "<p>x</p>"  # original untouched


def test_normalize_preserves_metadata_and_identity():
    item = make_raw_item(raw_content="<p>hi</p>", metadata={"k": "v"})
    out = Normalizer().normalize(item)
    assert out.metadata == {"k": "v"}
    assert out.id == item.id
    assert out.source_url == item.source_url
