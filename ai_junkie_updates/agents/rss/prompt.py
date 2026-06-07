"""Context prompt injected into Claude analysis for RSS items."""

from __future__ import annotations

AGENT_CONTEXT_PROMPT = """
Source type: RSS feed article
This content was collected from an RSS feed from an AI news source, company blog, or research publication. When analyzing it:
COLLECT if the article:

Announces a new AI model, product, or significant feature update
Reports a funding round, acquisition, or major business event
Covers a research paper that represents a meaningful capability advance
Reports regulatory action, government policy, or legal developments affecting AI
Covers a security incident, breach, or safety failure
Is a primary source announcement from an AI company blog (not a summary of a summary)
Covers infrastructure events: outages, new APIs, pricing changes, deprecations

IGNORE if the article:

Is an opinion column or editorial
Is a listicle, roundup, or "top 10 AI tools" style content
Is a tutorial, how-to guide, or educational content
Summarises news already covered elsewhere without adding new information
Is sponsored content or advertorial
Covers AI topics in a highly speculative or sensationalist way

RSS feeds are high volume — be strict about relevance.
"""
