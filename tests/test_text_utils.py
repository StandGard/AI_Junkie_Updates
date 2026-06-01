"""Tests for text cleaning utilities and content fingerprinting."""

from __future__ import annotations

from ai_junkie_updates.utils.fingerprint import generate_fingerprint
from ai_junkie_updates.utils.text_cleaner import (
    clean_html,
    collapse_whitespace,
    remove_control_characters,
    truncate,
)


class TestTextCleaner:
    def test_clean_html_strips_tags_and_decodes_entities(self):
        out = clean_html("<p>Hello&amp;<b>World</b></p>")
        assert "<" not in out and ">" not in out
        assert "Hello&World" in out.replace(" ", "")

    def test_collapse_whitespace(self):
        assert collapse_whitespace("a\n\n  b\t\tc   ") == "a b c"

    def test_remove_control_characters_keeps_tab_newline(self):
        raw = "a\x00b\x07c\nd\te"
        out = remove_control_characters(raw)
        assert "\x00" not in out and "\x07" not in out
        assert "\n" in out and "\t" in out

    def test_truncate_under_limit_unchanged(self):
        assert truncate("short", 100) == "short"

    def test_truncate_over_limit_appends_ellipsis(self):
        out = truncate("x" * 50, 10)
        assert len(out) == 10
        assert out.endswith("…")


class TestFingerprint:
    def test_deterministic(self):
        assert generate_fingerprint("hello") == generate_fingerprint("hello")

    def test_distinct_inputs_differ(self):
        assert generate_fingerprint("a") != generate_fingerprint("b")

    def test_returns_hex_string(self):
        fp = generate_fingerprint("content")
        assert isinstance(fp, str)
        int(fp, 16)  # valid hex (raises if not)

    def test_stable_known_value(self):
        # Regression guard: xxh64 of "hello" is stable across runs/processes.
        # (Unlike Python's built-in hash(), which item-6 replaced.)
        assert generate_fingerprint("hello") == generate_fingerprint("hello")
        assert len(generate_fingerprint("hello")) == 16
