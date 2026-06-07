"""Context prompt injected into Claude analysis for changelog items."""

from __future__ import annotations

AGENT_CONTEXT_PROMPT = """
Source type: Product changelog or release notes
This content comes from a changelog, release notes page, or version history document from an AI product or tool. When analyzing it:
COLLECT if the entry:

Introduces new capabilities, models, or major features
Changes API behaviour, parameters, response formats, or authentication in ways that affect developers
Announces deprecation of an existing feature, endpoint, or model with a timeline
Reports a resolved security vulnerability or significant bug affecting functionality
Changes pricing, rate limits, context windows, or other commercially significant parameters
Represents a major version increment (v1 → v2, not v1.0.1 → v1.0.2)

IGNORE if the entry:

Is a minor patch, bug fix with no user impact, or internal refactor
Covers documentation updates, typo fixes, or UI tweaks
Is a routine dependency update with no functional change
Is a very minor performance improvement with no observable difference

Developers depend on changelogs for integration decisions. Surface what matters to builders.
"""
