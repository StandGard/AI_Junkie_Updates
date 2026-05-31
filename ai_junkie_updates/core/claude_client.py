"""Async Claude client for analyzing raw items via the Anthropic API."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from ai_junkie_updates.constants import (
    DeliveryChannel,
    PipelineStatus,
    UpdateCategory,
    UrgencyLevel,
)
from ai_junkie_updates.core.models import RawItem, UpdateItem
from ai_junkie_updates.core.prompts.system_prompt import SYSTEM_PROMPT
from ai_junkie_updates.settings import settings
from ai_junkie_updates.utils.logger import get_logger

log = get_logger(__name__)


class ClaudeClient:
    """Sends raw items to Claude for structured analysis."""

    def __init__(self) -> None:
        self._client: anthropic.AsyncAnthropic | None = None
        self._model = settings.CLAUDE_TRIAGE_MODEL

    def _ensure_client(self) -> anthropic.AsyncAnthropic:
        """Lazily create the Anthropic client on first use."""
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _call_claude(
        self, user_message: str, context_prompt: str | None = None
    ) -> str:
        """Send a message to Claude and return the text response.

        The stable SYSTEM_PROMPT is sent as a cached block to cut token cost across
        the high volume of triage calls; the optional per-source context_prompt is
        appended as a second system block.
        """
        client = self._ensure_client()
        system_blocks: list = [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        if context_prompt:
            system_blocks.append({"type": "text", "text": context_prompt})
        response = await client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system_blocks,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text

    async def analyze(
        self, raw_item: RawItem, context_prompt: str | None = None
    ) -> UpdateItem:
        """Analyze a RawItem via Claude and return a structured UpdateItem."""
        user_message = (
            f"Source type: {raw_item.source_type.value}\n"
            f"Source name: {raw_item.source_name}\n"
            f"Source URL: {raw_item.source_url or 'N/A'}\n"
            f"Collected at: {raw_item.collected_at.isoformat()}\n"
            f"\n--- RAW CONTENT ---\n\n"
            f"{raw_item.raw_content}"
        )

        try:
            response_text = await self._call_claude(user_message, context_prompt)
            data = json.loads(response_text)
            return self._parse_response(data, raw_item)
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            log.error(
                "claude_parse_error",
                item_id=raw_item.id,
                error=str(exc),
            )
            return self._fallback_item(raw_item)
        except Exception as exc:
            log.error(
                "claude_api_error",
                item_id=raw_item.id,
                error=str(exc),
            )
            return self._fallback_item(raw_item)

    def _parse_response(self, data: dict, raw_item: RawItem) -> UpdateItem:
        """Map Claude's JSON response to an UpdateItem."""
        return UpdateItem(
            id=raw_item.id,
            source_type=raw_item.source_type,
            source_name=raw_item.source_name,
            source_url=raw_item.source_url,
            is_relevant=bool(data["is_relevant"]),
            category=UpdateCategory(data["category"]),
            urgency=UrgencyLevel(data["urgency"]),
            score=max(0, min(100, int(data["score"]))),
            headline=str(data["headline"]),
            summary=str(data["summary"]),
            reasoning=str(data["reasoning"]),
            tags=list(data.get("tags", [])),
            collected_at=raw_item.collected_at,
            analyzed_at=datetime.now(timezone.utc),
            pipeline_status=PipelineStatus.ANALYZED,
            fingerprint=raw_item.fingerprint,
        )

    def _fallback_item(self, raw_item: RawItem) -> UpdateItem:
        """Return a not-relevant item when Claude's response is unparseable."""
        return UpdateItem(
            id=raw_item.id,
            source_type=raw_item.source_type,
            source_name=raw_item.source_name,
            source_url=raw_item.source_url,
            is_relevant=False,
            category=UpdateCategory.OTHER,
            urgency=UrgencyLevel.LOW,
            score=0,
            headline="Analysis failed",
            summary="Could not parse Claude response for this item.",
            reasoning="JSON parse error or API failure.",
            tags=[],
            collected_at=raw_item.collected_at,
            analyzed_at=datetime.now(timezone.utc),
            pipeline_status=PipelineStatus.ANALYZED,
            delivery_channel=DeliveryChannel.DROPPED,
            fingerprint=raw_item.fingerprint,
        )


claude_client = ClaudeClient()
