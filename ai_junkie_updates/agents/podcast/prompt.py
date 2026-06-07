"""Context prompt injected into Claude analysis for podcast items."""

from __future__ import annotations

AGENT_CONTEXT_PROMPT = """
Source type: Podcast episode
This content comes from a podcast episode — either a title and description from an RSS feed, or a transcript excerpt. When analyzing it:
COLLECT if the episode:

Features an exclusive interview with an AI company CEO, founder, or lead researcher where new information is disclosed
Contains a first public announcement or preview of an upcoming product, model, or research
Includes a credible guest making news-worthy statements about the AI industry (acquisitions, fundraising, departures)
Covers a breaking development in the AI space with the host having primary knowledge
Features a technical deep-dive on a newly released model or architecture that constitutes a useful summary for developers

IGNORE if the episode:

Is a general discussion or debate without new factual information
Is an educational overview of existing concepts
Is a retrospective or "year in review" style episode
Covers AI tangentially without substantive industry news
Is a clip or teaser promoting a full episode already captured

Podcasts are low density for breaking news. Set a high bar — only surface episodes with genuine new information.
"""
