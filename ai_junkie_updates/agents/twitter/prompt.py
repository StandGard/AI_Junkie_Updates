"""Context prompt injected into Claude analysis for Twitter items."""

from __future__ import annotations

AGENT_CONTEXT_PROMPT = """
Source type: Twitter/X social media post
This content was collected from Twitter/X. When analyzing it:
COLLECT if the tweet:

Announces a new AI product, tool, or model from an official company account or verified researcher
Contains a product launch thread with specific feature details
Reports a breaking news event in the AI industry (outage, incident, acquisition, funding)
Shares a GitHub link to a newly released open-source AI project with meaningful traction
Announces API changes, pricing updates, or deprecations from an AI provider
Is from a known AI lab or major company account and contains substantive news

IGNORE if the tweet:

Is an opinion, hot take, or commentary without factual news content
Is social media drama, arguments, or personal disputes
Is promotional or marketing copy without specific announcements
Contains vague hype ("something big is coming") without specifics
Is a retweet of content already in the system
Is engagement bait, polls, or community content with no news value
Is from an unverified or low-credibility account making unverifiable claims

Focus on signal, not noise. Twitter moves fast — only surface what matters.
"""
