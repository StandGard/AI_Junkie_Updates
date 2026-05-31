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


# ---------------------------------------------------------------------------
# Intelligence-layer formatting (leaderboards, model cards, events, advice)
# ---------------------------------------------------------------------------

_MEDALS = {1: "\U0001f947", 2: "\U0001f948", 3: "\U0001f949"}  # \ud83e\udd47\ud83e\udd48\ud83e\udd49
_DOT = " \u00b7 "  # middle-dot separator (kept out of f-strings)

# Friendly labels for leaderboard use-cases.
USE_CASE_LABELS: Dict[str, str] = {
    "overall": "Overall",
    "coding": "Coding",
    "agents": "Agent development",
    "app_dev": "App development",
    "automation": "Automation",
    "content": "Content creation",
    "video": "Video production",
    "research": "Research & analysis",
    "business": "Business & productivity",
    "value": "Value for money",
}


def _esc(text: str) -> str:
    return html_lib.escape(str(text))


def use_case_label(use_case: str) -> str:
    return USE_CASE_LABELS.get(use_case, use_case.replace("_", " ").title())


def format_leaderboard(use_case: str, ranking: list, methodology: str = "",
                       top_n: int = 10) -> str:
    """Render a leaderboard as a ranked HTML list."""
    label = _esc(use_case_label(use_case))
    if not ranking:
        return f"\U0001f3c6 <b>{label}</b>\n\nNo ranking available yet."

    lines = [f"\U0001f3c6 <b>Best for {label}</b>", ""]
    for row in ranking[:top_n]:
        rank = row.get("rank", "?")
        marker = _MEDALS.get(rank, f"{rank}.")
        name = _esc(row.get("display_name", row.get("model_id", "?")))
        score = row.get("score")
        rationale = row.get("rationale", "")
        score_str = f" \u00b7 {round(float(score) * 100)}" if isinstance(score, (int, float)) else ""
        tail = f" \u2014 <i>{_esc(rationale)}</i>" if rationale else ""
        lines.append(f"{marker} <b>{name}</b>{score_str}{tail}")

    if methodology:
        lines.append("")
        lines.append(f"<i>{_esc(methodology)}</i>")
    return "\n".join(lines)


def format_leaderboard_index(use_cases: list) -> str:
    """List the available leaderboards and how to query them."""
    lines = ["\U0001f3c6 <b>Leaderboards</b>", "", "Ask for any with <code>/best &lt;area&gt;</code>:", ""]
    for uc in use_cases:
        lines.append(f"\u2022 <code>/best {_esc(uc)}</code> \u2014 {_esc(use_case_label(uc))}")
    return "\n".join(lines)


def format_model_card(model, company, price, scores: list) -> str:
    """Render a model knowledge card (model row, company, latest price, scores)."""
    name = _esc(model.display_name)
    lines = [f"\U0001f9e0 <b>{name}</b>"]

    meta = []
    if company is not None:
        meta.append(_esc(company.name))
    if model.status:
        meta.append(_esc(model.status))
    if model.is_open_source:
        meta.append("open source")
    if meta:
        lines.append(" \u00b7 ".join(meta))

    if model.modality:
        lines.append(f"\U0001f4e6 Modality: {_esc(', '.join(model.modality))}")
    if model.context_window:
        lines.append(f"\U0001f4cf Context: {model.context_window:,} tokens")
    if model.release_date:
        lines.append(f"\U0001f4c5 Released: {model.release_date.date().isoformat()}")

    if price is not None and (price.input_per_mtok is not None or price.output_per_mtok is not None):
        inp = price.input_per_mtok if price.input_per_mtok is not None else "?"
        out = price.output_per_mtok if price.output_per_mtok is not None else "?"
        lines.append(f"\U0001f4b0 Price: ${inp} in / ${out} out per 1M tokens")

    if scores:
        lines.append("")
        lines.append("\U0001f4ca <b>Benchmarks</b>")
        for bench_name, score in scores:
            lines.append(f"\u2022 {_esc(bench_name)}: <b>{_esc(score)}</b>")

    return "\n".join(lines)


def format_events(events: list, window_label: str = "recent") -> str:
    """Render a list of Event rows as a 'what's changed' digest."""
    if not events:
        return f"\U0001f5de No significant updates in the {_esc(window_label)} window."

    lines = [f"\U0001f5de <b>What's changed ({_esc(window_label)})</b>", ""]
    for e in events:
        sig = e.significance_score
        flame = "\U0001f525 " if sig >= 90 else ""
        title = _esc(e.title)
        lines.append(f"{flame}<b>{title}</b>")
        if e.summary:
            lines.append(_esc(e.summary))
        meta = []
        if e.model_ids:
            meta.append("models: " + _esc(", ".join(e.model_ids)))
        meta.append(f"significance {sig}")
        if e.item_ids:
            meta.append(f"{len(e.item_ids)} sources")
        lines.append(f"<i>{_DOT.join(meta)}</i>")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_switch_recommendations(recs: list) -> str:
    """Render deterministic switch advice."""
    if not recs:
        return "\u2705 <b>Your current stack is still optimal</b> for your priorities."

    lines = ["\U0001f504 <b>Switch recommendations</b>", ""]
    for r in recs:
        label = _esc(use_case_label(r["use_case"]))
        to_name = _esc(r.get("to_name", r["to"]))
        reason = _esc(r.get("reason", ""))
        if r.get("from"):
            lines.append(f"\u2022 <b>{label}</b>: {_esc(r['from'])} \u2192 <b>{to_name}</b>")
        else:
            lines.append(f"\u2022 <b>{label}</b>: adopt <b>{to_name}</b>")
        if reason:
            lines.append(f"   <i>{reason}</i>")
    return "\n".join(lines)
