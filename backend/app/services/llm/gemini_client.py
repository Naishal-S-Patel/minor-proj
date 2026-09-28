"""
GeminiClient — the ONLY file in the codebase that imports the Google
Generative AI (Gemini) SDK directly.

Mirrors the isolation pattern of ClaudeClient/MongoDB: provider-specific
code lives here and nowhere else. Swapping to another LLM provider means
rewriting this one file.

Responsibilities:
    - Own the Gemini API client and API key
    - Send a prompt, return the raw response text
    - Retry on transient failures with exponential backoff
    - Enforce a hard timeout so a hung call can't block a pipeline forever

Does NOT:
    - Know about MeetingStatus, MongoDB, or the extraction pipeline
    - Parse/validate the response into ExtractionResult (extraction_service's job)
    - Decide what prompt to send (prompts.py's job)
"""

import asyncio
import logging

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMTimeoutError(Exception):
    """Raised when a Gemini API call exceeds the timeout."""


class LLMRequestError(Exception):
    """Raised when the Gemini API call fails after all retries."""


class GeminiClient:
    """
    Async wrapper around Google Gemini API for structured text generation.

    Uses google-genai SDK (the modern Google Gen AI SDK).
    Get a free API key at: https://aistudio.google.com/apikey
    Free tier: 15 RPM, 1M tokens/day.
    """

    def __init__(self) -> None:
        try:
            from google import genai

            self._client = genai.Client(api_key=settings.gemini_api_key)
            self._model = settings.gemini_model
            logger.info(
                "Initialized Gemini client (model: %s)",
                settings.gemini_model,
            )
        except ImportError as exc:
            logger.error("google-genai not installed. Install with: pip install google-genai")
            raise LLMRequestError("google-genai required for Gemini client") from exc
        except Exception as exc:
            logger.error("Failed to initialize Gemini client: %s", exc)
            raise LLMRequestError(f"Gemini init failed: {exc}") from exc

    @retry(
        retry=retry_if_exception_type((LLMTimeoutError, LLMRequestError)),
        stop=stop_after_attempt(settings.llm_max_retries + 1),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        reraise=True,
    )
    async def generate_json(self, prompt: str) -> str:
        """
        Sends a prompt to Gemini and returns the raw text response.
        Instructs Gemini to output JSON only.
        """
        try:
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: self._client.models.generate_content(
                        model=self._model,
                        contents=prompt,
                        config={
                            "max_output_tokens": settings.llm_max_output_tokens,
                            "temperature": 0.1,
                            "system_instruction": (
                                "You are an AI assistant that responds with valid JSON only. "
                                "No markdown, no explanations, just JSON."
                            ),
                        },
                    )
                ),
                timeout=settings.llm_request_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            logger.warning(
                "Gemini request timed out after %ds",
                settings.llm_request_timeout_seconds,
            )
            raise LLMTimeoutError(
                f"Gemini request exceeded {settings.llm_request_timeout_seconds}s timeout"
            ) from exc
        except Exception as exc:
            logger.warning(
                "Gemini request failed: %s: %s", type(exc).__name__, exc
            )
            raise LLMRequestError(f"{type(exc).__name__}: {exc}") from exc

        if not response.text:
            raise LLMRequestError("Gemini returned an empty response")

        return response.text.strip()
