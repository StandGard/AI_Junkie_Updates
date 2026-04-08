"""Format UpdateItems as HTML messages for Telegram delivery."""

from __future__ import annotations

import html as html_lib
from typing import Dict

from ai_junkie_updates.constants import UpdateCategory
from ai_junkie_updates.core.models import UpdateItem

CATEGORY_EMOJI: Dict[UpdateCategory, str] = {
    UpdateCategory.PRODUCT_LAUNCH: "\U0001f680",       # 🚀
    UpdateCategory.MODEL_RELEASE: "\U0001f9e0",        # 🧠
    UpdateCategory.FUNDING: "\U0001f4b0",              # 💰
    UpdateCategory.ACQUISITION: "\U0001f91d",          # 🤝
    UpdateCategory.OPEN_SOURCE_RELEASE: "\U0001f4e6",  # 📦
    UpdateCategory.RESEARCH_BREAKTHROUGH: "\U0001f52c", # 🔬
    UpdateCategory.INFRASTRUCTURE_CHANGE: "\u2699\ufe0f",  # ⚙️
    UpdateCategory.SECURITY_INCIDENT: "\U0001f534",    # 🔴
    UpdateCategory.REGULATORY_DEVELOPMENT: "\u2696\ufe0f", # ⚖️
    UpdateCategory.PARTNERSHIP: "\U0001f517",           # 🔗
    UpdateCategory.LEADERSHIP_CHANGE: "\U0001f464",    # 👤
    UpdateCategory.MARKET_DATA: "\U0001f4ca",          # 📊
    UpdateCategory.OTHER: "\U0001f4cc",                # 📌
}


class Formatter:
    """Build HTML-formatted Telegram messages from UpdateItems."""

    def format_message(self, item: UpdateItem) -> str:
        """Return an HTML string ready for Telegram parse_mode=HTML."""
        emoji = CATEGORY_EMOJI.get(item.category, "\U0001f4cc")
        headline = html_lib.escape(item.headline)
        summary = html_lib.escape(item.summary)
        tags_str = " \u00b7 ".join(html_lib.escape(t) for t in item.tags) if item.tags else ""
        source = html_lib.escape(item.source_name)
        urgency = html_lib.escape(item.urgency.value)

        lines = [
            f"{emoji} <b>{headline}</b>",
            f"{summary}",
        ]

        if tags_str:
            lines.append(f"\U0001f3f7 {tags_str}")

        lines.append(f"\U0001f4e1 {source}")

        if item.source_url:
            lines.append(f'\U0001f517 <a href="{html_lib.escape(item.source_url)}">Read more</a>')

        lines.append(f"\u23f1 Score: {item.score}/100 \u00b7 {urgency}")

        return "\n".join(lines)
