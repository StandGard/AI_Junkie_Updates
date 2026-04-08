"""Normalizer — cleans and standardizes raw content before analysis."""

from __future__ import annotations

from ai_junkie_updates.core.models import RawItem
from ai_junkie_updates.utils.text_cleaner import (
    clean_html,
    collapse_whitespace,
    remove_control_characters,
    truncate,
)

MAX_CONTENT_LENGTH = 8000


class Normalizer:
    """Clean raw content so it is suitable for Claude analysis."""

    def normalize(self, raw_item: RawItem) -> RawItem:
        """Return a new RawItem with cleaned raw_content."""
        text = raw_item.raw_content
        text = clean_html(text)
        text = remove_control_characters(text)
        text = collapse_whitespace(text)
        text = truncate(text, MAX_CONTENT_LENGTH)
        return raw_item.model_copy(update={"raw_content": text})
