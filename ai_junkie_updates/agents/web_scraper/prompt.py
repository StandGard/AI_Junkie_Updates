"""Context prompt injected into Claude analysis for web scraper items."""

AGENT_CONTEXT_PROMPT = """
Source type: Web page scrape
This content was scraped from a monitored web page — typically a company website, product page, documentation site, or news publication. When analyzing it:
COLLECT if the page:

Shows new content that was not present in a prior scrape (product launches, announcements, new documentation sections)
Announces availability of a new product, model, API endpoint, or pricing tier
Contains a press release or official statement from an AI company
Shows a material change to a company's product page (new capabilities listed, old ones removed)
Contains a news article about a funding event, acquisition, or leadership change

IGNORE if the page:

Is a static marketing page with no substantive new content
Is boilerplate legal or compliance text
Is a generic company overview with no newsworthy updates
Has changed only in trivial ways (date stamps, navigation elements, footers)

Web scraping is noisy. Apply a high standard before flagging anything as relevant.
"""
