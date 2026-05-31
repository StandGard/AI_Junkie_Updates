"""Filter engine — decides whether and where to deliver an update."""

from __future__ import annotations

from typing import List, Tuple

from ai_junkie_updates.constants import (
    SCORE_IMMEDIATE,
    SCORE_IMPORTANT,
    SCORE_WATCHLIST,
    SCORE_WORTH_KNOWING,
    DeliveryChannel,
)
from ai_junkie_updates.core.models import RawItem, UpdateItem

# Broad set of AI-related signals. The pre-LLM gate is deliberately lenient — it
# only drops content that contains NONE of these, so genuine news is never withheld
# from analysis. Most configured sources are AI-dedicated, so this mainly trims
# off-topic noise from high-volume mixed sources (e.g. broad subreddits, PR wires).
AI_KEYWORDS = frozenset(
    {
        "ai", "a.i", "artificial intelligence", "machine learning", " ml ", "llm",
        "large language model", "gpt", "chatgpt", "openai", "anthropic", "claude",
        "gemini", "deepmind", "google ai", "llama", "mistral", "meta ai",
        "perplexity", "deepseek", "hugging face", "huggingface", "transformer",
        "neural", "model", "agent", "inference", "fine-tune", "finetune", "rag",
        "embedding", "diffusion", "midjourney", "runway", "sora", "copilot",
        "cursor", "benchmark", "agi", "prompt", "multimodal", "reasoning",
        "nvidia", "gpu", "foundation model", "chatbot", "elevenlabs", "cohere",
        "grok", "xai", "qwen", "gemma", "open source model", "open-source model",
        "dataset", "training run", "quantization", "fine tuning",
    }
)


class FilterEngine:
    """Apply score thresholds and watchlist matching to decide delivery."""

    def passes_pre_llm_gate(self, raw_item: RawItem) -> bool:
        """Cheap keyword gate run before Claude analysis.

        Returns False for content that is too short or contains no AI-related
        signal at all, so the triage model is never spent on obvious noise.
        """
        text = (raw_item.raw_content or "").lower()
        if len(text.strip()) < 20:
            return False
        return any(kw in text for kw in AI_KEYWORDS)

    def should_deliver(
        self, item: UpdateItem, watchlist: List[str]
    ) -> Tuple[bool, DeliveryChannel]:
        """Return (should_deliver, channel) for the given item."""
        if not item.is_relevant:
            return False, DeliveryChannel.DROPPED

        if item.score >= SCORE_IMMEDIATE:
            return True, DeliveryChannel.CRITICAL_ALERTS

        if item.score >= SCORE_IMPORTANT:
            return True, DeliveryChannel.HIGH_PRIORITY

        if item.score >= SCORE_WORTH_KNOWING:
            return True, DeliveryChannel.GENERAL

        if item.score >= SCORE_WATCHLIST:
            watchlist_lower = [w.lower() for w in watchlist]
            tags_lower = [t.lower() for t in item.tags]
            source_lower = item.source_name.lower()
            for term in watchlist_lower:
                if term in source_lower:
                    return True, DeliveryChannel.WATCHLIST
                for tag in tags_lower:
                    if term in tag:
                        return True, DeliveryChannel.WATCHLIST

        return False, DeliveryChannel.DROPPED
