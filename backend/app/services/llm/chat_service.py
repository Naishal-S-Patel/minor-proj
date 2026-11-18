"""
ChatService — Q&A engine for a specific meeting's content.

Given a meeting's summary, decisions, keywords, calendar events, action items,
and transcript, answers user questions using only that meeting's information.

Resilient multi-tier strategy:
  1. Tries configured LLM provider (Groq / Gemini) using natural chat generation.
  2. If the API key is expired, rate-limited, or fails, seamlessly falls back
     to SmartLocalQABot to answer questions directly from meeting facts,
     calendar events, action items, and transcript search.
"""

import logging
from typing import Any

from app.core.config import settings
from app.services.llm.gemini_client import GeminiClient
from app.services.llm.groq_client import GroqClient
from app.services.llm.prompts import build_chat_prompt
from app.services.llm.smart_engine import SmartLocalQABot

logger = logging.getLogger(__name__)


class ChatFailedError(Exception):
    """Raised only if both LLM and local fallback fail."""


class ChatService:
    """High-level entry point: answers questions using meeting context."""

    def __init__(self, client: Any = None) -> None:
        if client is not None:
            self._client = client
        else:
            self._client = self._init_client()

    def _init_client(self):
        try:
            if settings.llm_provider == "gemini" and settings.gemini_api_key:
                return GeminiClient()
            elif settings.llm_provider == "groq" and settings.groq_api_key:
                return GroqClient()
            elif settings.gemini_api_key:
                return GeminiClient()
            elif settings.groq_api_key:
                return GroqClient()
        except Exception as exc:
            logger.warning("Could not initialize external LLM client for chat: %s", exc)
        return None

    async def answer(
        self,
        question: str,
        summary: str | None,
        decisions: list[str],
        keywords: list[str],
        cleaned_transcript: str | None,
        action_items: list[Any] | None = None,
        calendar_events: list[Any] | None = None,
        speakers: list[str] | None = None,
    ) -> str:
        """
        Produces an answer using LLM if available, or SmartLocalQABot fallback.
        Never leaves the user with a broken 502.
        """
        if self._client is not None:
            try:
                prompt = build_chat_prompt(
                    question=question,
                    summary=summary,
                    decisions=decisions,
                    keywords=keywords,
                    transcript=cleaned_transcript,
                    action_items=action_items,
                    calendar_events=calendar_events,
                )
                if hasattr(self._client, "generate_text"):
                    raw_response = await self._client.generate_text(prompt)
                else:
                    raw_response = await self._client.generate_json(prompt)

                if raw_response and raw_response.strip():
                    return raw_response.strip()
            except Exception as exc:
                logger.warning(
                    "External LLM chat failed (%s: %s). Activating SmartLocalQABot fallback.",
                    type(exc).__name__,
                    exc,
                )

        # Smart local Q&A fallback
        logger.info("Using SmartLocalQABot to answer question: %r", question)
        return SmartLocalQABot.answer(
            question=question,
            summary=summary,
            decisions=decisions,
            keywords=keywords,
            transcript=cleaned_transcript,
            action_items=action_items,
            calendar_events=calendar_events,
            speakers=speakers,
        )
