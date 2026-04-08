"""Context prompt injected into Claude analysis for API feed items."""

AGENT_CONTEXT_PROMPT = """
Source type: Structured API feed
This content comes from a structured data API — such as a news aggregation API, data provider feed, financial data source, or third-party monitoring service. When analyzing it:
COLLECT if the item:

Reports a funding event (Series A or above, or any round over $10M) in the AI sector
Reports an acquisition, merger, or significant investment in an AI company
Reports a company valuation event, IPO filing, or secondary market transaction for an AI firm
Is a structured data point confirming an event (e.g. SEC filing confirming a deal already rumoured)
Provides verified pricing, usage, or capability data about an AI model or service
Reports a data breach, security incident, or CVE affecting an AI system or platform

IGNORE if the item:

Is a duplicate of a press release or news article already captured
Is a financial data point with no direct AI industry relevance
Is a generic market data point (stock prices, indices) without specific AI company context
Is a low-confidence signal from an unverified data source

API feeds are structured and reliable. Cross-reference with other agents when possible.
"""
