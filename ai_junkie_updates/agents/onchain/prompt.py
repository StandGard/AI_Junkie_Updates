"""Context prompt injected into Claude analysis for on-chain items."""

AGENT_CONTEXT_PROMPT = """
Source type: On-chain blockchain event
This content comes from monitoring blockchain networks for events related to the AI industry — including AI token deployments, DAO governance actions, compute marketplace transactions, and AI-adjacent protocol events. When analyzing it:
COLLECT if the event:

Represents the launch of a new AI-related token, protocol, or smart contract with significant capital or attention
Is a major governance vote outcome at an AI DAO (compute networks, model marketplaces, data DAOs)
Represents a significant capital deployment into AI infrastructure on-chain (staking milestones, liquidity events)
Involves a known AI company or project executing a significant on-chain action
Represents a new partnership, integration, or bridge between AI infrastructure and blockchain networks

IGNORE if the event:

Is routine transactional activity with no news value
Is a minor governance proposal or low-participation vote
Involves unknown wallets or contracts with no connection to the broader AI ecosystem
Is speculation about on-chain activity without a verifiable transaction hash

On-chain AI is an emerging space. Be selective — only surface genuinely significant events.
"""
