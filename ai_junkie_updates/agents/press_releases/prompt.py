"""Context prompt injected into Claude analysis for press release items."""

AGENT_CONTEXT_PROMPT = """
Source type: Press release or official company statement
This content comes from a press release, PR newswire feed, or official company statement page. When analyzing it:
COLLECT if the release:

Announces a new product, model, or significant service update
Announces a funding round, acquisition, merger, or major investment
Reports a leadership change at a significant AI company (C-suite or equivalent)
Announces a significant enterprise partnership or customer win that indicates market traction
Contains a regulatory filing, compliance announcement, or legal development
Announces an office opening, expansion, or major operational milestone that signals company trajectory

IGNORE if the release:

Is a routine award, ranking, or "best place to work" type announcement
Is a speaking engagement or conference appearance notice
Contains only vague forward-looking statements with no specific news
Is a human interest or culture story with no business news value
Repackages already-announced news without adding new information

Press releases are official but often over-packaged. Extract the actual news.
"""
