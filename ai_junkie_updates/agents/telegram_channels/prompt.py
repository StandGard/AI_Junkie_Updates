"""Context prompt injected into Claude analysis for Telegram channel items."""

AGENT_CONTEXT_PROMPT = """
Source type: Telegram channel post
This content was collected from a monitored Telegram channel — typically an AI company's official channel, a researcher's channel, or a well-regarded AI news channel. When analyzing it:
COLLECT if the post:

Is an official announcement from an AI company or lab's verified Telegram channel
Reports breaking news about a model release, product launch, or incident
Contains technical details, API announcements, or developer-facing information
Is from a credible researcher announcing new work or findings
Reports a funding event, acquisition, or major business development

IGNORE if the post:

Is a forward of content already captured by another agent
Is promotional or advertising content
Is a community discussion or opinion post
Is from an unverified or low-credibility channel
Is vague or speculative without factual content

Telegram channels can be primary sources for AI companies. Focus on first-mover announcements.
"""
