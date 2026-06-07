"""Context prompt injected into Claude analysis for Reddit items."""

from __future__ import annotations

AGENT_CONTEXT_PROMPT = """
Source type: Reddit post
This content was collected from a monitored AI-focused subreddit. When analyzing it:
COLLECT if the post:

Contains a primary announcement of a new AI tool, model, or project (not a link to news already captured elsewhere)
Is an AMA or direct statement from an AI company employee or researcher containing new information
Reports a first-hand account of an AI system failure, security incident, or unexpected behaviour with verifiable details
Announces an open-source release with a GitHub link and meaningful community engagement
Contains a leak or credible early report of an upcoming product that is not yet public
Is a breaking news thread where the community is reporting a live event

IGNORE if the post:

Is a discussion thread, debate, or opinion piece
Is a question or request for help
Is a meme, image, or low-effort post
Is a link to an article already captured by RSS or web scraper agents
Is speculation or a rumour without a verifiable source
Is community drama or interpersonal conflict

Reddit can surface early signals. Apply strict criteria — most posts are noise.
"""
