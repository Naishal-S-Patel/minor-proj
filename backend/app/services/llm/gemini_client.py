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

    async def _generate_with_fallback(self, prompt: str, is_json: bool = False) -> str:
        """Calls Gemini API asynchronously with per-model timeout and resilient fallback."""
        config = {
            "max_output_tokens": settings.llm_max_output_tokens,
            "temperature": 0.1 if is_json else 0.3,
            "system_instruction": (
                "You are an AI assistant that responds with valid JSON only. "
                "No markdown, no explanations, just JSON."
                if is_json
                else (
                    "You are a concise, accurate AI meeting assistant. "
                    "Answer the user question directly using the meeting context."
                )
            ),
        }

        models_to_try = [self._model]
        for candidate in ("gemini-4-hydrogen", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"):
            if candidate not in models_to_try:
                models_to_try.append(candidate)

        loop = asyncio.get_event_loop()
        per_model_timeout = min(settings.llm_request_timeout_seconds, 10) if len(models_to_try) > 1 else settings.llm_request_timeout_seconds
        last_exc: Exception | None = None

        for model in models_to_try:
            try:
                response = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda m=model: self._client.models.generate_content(
                            model=m,
                            contents=prompt,
                            config=config,
                        ),
                    ),
                    timeout=per_model_timeout,
                )
                if response and response.text and response.text.strip():
                    return response.text.strip()
            except asyncio.TimeoutError as exc:
                logger.warning("Gemini model %s timed out after %ds", model, per_model_timeout)
                last_exc = LLMTimeoutError(f"Gemini model {model} exceeded {per_model_timeout}s timeout")
                continue
            except Exception as exc:
                err_str = str(exc)
                logger.warning("Gemini model %s call failed (%s): %s", model, type(exc).__name__, exc)
                last_exc = exc
                if any(code in err_str for code in ("503", "404", "429", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "NOT_FOUND")):
                    continue
                raise LLMRequestError(f"{type(exc).__name__}: {exc}") from exc

        if isinstance(last_exc, LLMTimeoutError):
            raise last_exc
        if last_exc:
            raise LLMRequestError(f"{type(last_exc).__name__}: {last_exc}") from last_exc
        raise LLMRequestError("Gemini returned an empty response")

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
        return await self._generate_with_fallback(prompt, is_json=True)

    @retry(
        retry=retry_if_exception_type((LLMTimeoutError, LLMRequestError)),
        stop=stop_after_attempt(settings.llm_max_retries + 1),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        reraise=True,
    )
    async def generate_text(self, prompt: str) -> str:
        """Sends a prompt to Gemini for natural language chat response (not JSON forced)."""
        return await self._generate_with_fallback(prompt, is_json=False)
