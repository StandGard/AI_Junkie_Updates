"""Enums and score-threshold constants used throughout the system."""

from __future__ import annotations

from enum import Enum


# ---------------------------------------------------------------------------
# Source types — one per agent
# ---------------------------------------------------------------------------

class SourceType(str, Enum):
    TWITTER = "twitter"
    RSS = "rss"
    WEB_SCRAPER = "web_scraper"
    CHANGELOG = "changelog"
    GITHUB = "github"
    REDDIT = "reddit"
    DISCORD = "discord"
    ONCHAIN = "onchain"
    TELEGRAM_CHANNEL = "telegram_channel"
    PRESS_RELEASE = "press_release"
    PODCAST = "podcast"
    REGULATORY = "regulatory"
    API_FEED = "api_feed"
    YOUTUBE = "youtube"
    BENCHMARK = "benchmark"


# ---------------------------------------------------------------------------
# Category assigned by Claude during analysis
# ---------------------------------------------------------------------------

class UpdateCategory(str, Enum):
    PRODUCT_LAUNCH = "PRODUCT_LAUNCH"
    MODEL_RELEASE = "MODEL_RELEASE"
    FUNDING = "FUNDING"
    ACQUISITION = "ACQUISITION"
    OPEN_SOURCE_RELEASE = "OPEN_SOURCE_RELEASE"
    RESEARCH_BREAKTHROUGH = "RESEARCH_BREAKTHROUGH"
    INFRASTRUCTURE_CHANGE = "INFRASTRUCTURE_CHANGE"
    SECURITY_INCIDENT = "SECURITY_INCIDENT"
    REGULATORY_DEVELOPMENT = "REGULATORY_DEVELOPMENT"
    PARTNERSHIP = "PARTNERSHIP"
    LEADERSHIP_CHANGE = "LEADERSHIP_CHANGE"
    MARKET_DATA = "MARKET_DATA"
    OTHER = "OTHER"


# ---------------------------------------------------------------------------
# Urgency level assigned by Claude
# ---------------------------------------------------------------------------

class UrgencyLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# ---------------------------------------------------------------------------
# Pipeline status tracking
# ---------------------------------------------------------------------------

class PipelineStatus(str, Enum):
    RAW = "RAW"
    NORMALIZED = "NORMALIZED"
    DEDUPLICATED = "DEDUPLICATED"
    ANALYZED = "ANALYZED"
    FILTERED = "FILTERED"
    DELIVERED = "DELIVERED"
    DROPPED = "DROPPED"


# ---------------------------------------------------------------------------
# Delivery channel (maps to Telegram channels)
# ---------------------------------------------------------------------------

class DeliveryChannel(str, Enum):
    CRITICAL_ALERTS = "CRITICAL_ALERTS"
    HIGH_PRIORITY = "HIGH_PRIORITY"
    GENERAL = "GENERAL"
    WATCHLIST = "WATCHLIST"
    DROPPED = "DROPPED"


# ---------------------------------------------------------------------------
# Score thresholds
# ---------------------------------------------------------------------------

SCORE_IMMEDIATE = 90
SCORE_IMPORTANT = 70
SCORE_WORTH_KNOWING = 50
SCORE_WATCHLIST = 40
SCORE_NOISE = 0


# ---------------------------------------------------------------------------
# Per-source poll intervals (seconds)
# ---------------------------------------------------------------------------
# Keyed by agent source_name. Agents fall back to settings.POLL_INTERVAL_SECONDS
# when their source_name is absent here. Slower polling on low-velocity sources
# also reduces the number of triage LLM calls.

POLL_INTERVALS = {
    "discord": 300,        # push receiver — collect() just drains the inbox
    "rss": 900,
    "youtube": 3600,       # channel RSS — videos drop infrequently
    "status": 600,         # status pages change fast during incidents
    "github": 900,
    "changelog": 900,
    "web_scraper": 1800,
    "twitter": 1800,
    "reddit": 1800,
    "onchain": 1800,
    "telegram_channels": 1800,
    "press_releases": 3600,
    "regulatory": 3600,
    "podcast": 3600,
    "api_feed": 3600,
}
