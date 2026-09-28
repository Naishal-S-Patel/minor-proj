"""
GroqClient — Groq API client using the official groq Python SDK.

Get a FREE API key at: https://console.groq.com/
Free tier: 30 requests/min, 14,400 requests/day.
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
    """Raised when a Groq API call exceeds the timeout."""


class LLMRequestError(Exception):
    """Raised when the Groq API call fails after all retries."""


class GroqClient:
    """
    Async wrapper around Groq API using the official groq SDK.
    Free tier: 30 RPM, fast inference with Llama models.
    """

    def __init__(self) -> None:
        try:
            from groq import Groq

            self._client = Groq(api_key=settings.groq_api_key)
            self._model = settings.groq_model
            logger.info("Initialized Groq client (model: %s)", self._model)
        except ImportError as exc:
            logger.error("groq not installed. Run: pip install groq")
            raise LLMRequestError("groq package required") from exc
        except Exception as exc:
            logger.error("Failed to initialize Groq client: %s", exc)
            raise LLMRequestError(f"Groq init failed: {exc}") from exc

    @retry(
        retry=retry_if_exception_type((LLMTimeoutError, LLMRequestError)),
        stop=stop_after_attempt(settings.llm_max_retries + 1),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        reraise=True,
    )
    async def generate_json(self, prompt: str) -> str:
        """Sends a prompt to Groq and returns raw JSON text."""
        try:
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: self._client.chat.completions.create(
                        model=self._model,
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "You are an AI assistant that responds with valid JSON only. "
                                    "No markdown, no explanations, just JSON."
                                ),
                            },
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.1,
                        max_tokens=settings.llm_max_output_tokens,
                        response_format={"type": "json_object"},
                    ),
                ),
                timeout=settings.llm_request_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            logger.warning("Groq request timed out after %ds", settings.llm_request_timeout_seconds)
            raise LLMTimeoutError(
                f"Groq request exceeded {settings.llm_request_timeout_seconds}s timeout"
            ) from exc
        except Exception as exc:
            logger.warning("Groq request failed: %s: %s", type(exc).__name__, exc)
            raise LLMRequestError(f"{type(exc).__name__}: {exc}") from exc

        if not response.choices or not response.choices[0].message.content:
            raise LLMRequestError("Groq returned an empty response")

        return response.choices[0].message.content.strip()
