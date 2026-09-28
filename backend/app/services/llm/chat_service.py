"""
ChatService — Q&A engine for a specific meeting's content.

Given a meeting's summary, decisions, keywords, and transcript, answers
user questions using only that meeting's information. The LLM acts as a
focused retrieval-augmented Q&A engine, not a general chatbot.

Stateless: each request sends the full context. No conversation history
is maintained — chat is ephemeral per session.
"""

import logging

from app.services.llm.gemini_client import GeminiClient, LLMRequestError, LLMTimeoutError
from app.services.llm.prompts import build_chat_prompt

logger = logging.getLogger(__name__)


class ChatFailedError(Exception):
    """
    Raised when the LLM fails to produce an answer. Carries a
    human-readable reason for the 502 response the route will return.
    """


class ChatService:
    """
    High-level entry point: given a meeting's context fields and a user
    question, produces a plain-text answer via GeminiClient.
    """

    def __init__(self, client: GeminiClient | None = None) -> None:
        # Same DI seam as ExtractionService — injectable for tests
        self._client = client or GeminiClient()

    async def answer(
        self,
        question: str,
        summary: str | None,
        decisions: list[str],
        keywords: list[str],
        cleaned_transcript: str | None,
    ) -> str:
        """
        Builds a context-scoped Q&A prompt and returns the LLM's plain-text
        answer. Raises ChatFailedError on LLM failure.
        """
        prompt = build_chat_prompt(
            question=question,
            summary=summary,
            decisions=decisions,
            keywords=keywords,
            transcript=cleaned_transcript,
        )

        try:
            raw_response = await self._client.generate_json(prompt)
        except (LLMTimeoutError, LLMRequestError) as exc:
            logger.warning("Chat LLM request failed: %s", exc)
            raise ChatFailedError(f"LLM request failed: {exc}") from exc

        if not raw_response or not raw_response.strip():
            raise ChatFailedError("LLM returned an empty response")

        return raw_response.strip()
