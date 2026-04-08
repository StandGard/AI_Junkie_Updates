"""Text cleaning utilities for normalizing raw content."""

from __future__ import annotations

import html
import re
import unicodedata

from bs4 import BeautifulSoup


def clean_html(text: str) -> str:
    """Strip HTML tags and decode HTML entities."""
    soup = BeautifulSoup(text, "html.parser")
    cleaned = soup.get_text(separator=" ")
    return html.unescape(cleaned)


def collapse_whitespace(text: str) -> str:
    """Collapse multiple spaces, tabs, and newlines into a single space."""
    return re.sub(r"\s+", " ", text).strip()


def remove_control_characters(text: str) -> str:
    """Strip null bytes and non-printable control characters."""
    return "".join(
        ch for ch in text
        if ch == "\n" or ch == "\t" or not unicodedata.category(ch).startswith("C")
    )


def truncate(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, appending '…' if truncated."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"
