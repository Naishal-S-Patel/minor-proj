"""
ClaudeClient — the ONLY file in the codebase that imports the Anthropic
(Claude) SDK directly.

Why isolate this, mirroring MeetingRepository's isolation of MongoDB:
    Just like MeetingRepository is the sole place that knows about
    ObjectId/bson so the rest of the app can swap MongoDB later without a
    rewrite, ClaudeClient is the sole place that knows about the Claude
    SDK's specific call shape, error types, and response format. If a
    different LLM provider is ever needed (Gemini, OpenAI, a self-hosted
    model), only this file changes -- extraction_service.py and everything
    above it depends only on this class's plain async method signature,
    not on any Claude-specific types.

Responsibilities:
    - Own the Anthropic SDK client and API key
    - Send a prompt, request JSON output, return the raw response text
    - Retry on transient failures (rate limits, timeouts) with backoff
    - Enforce a hard timeout so a hung call can't block a pipeline forever

Does NOT:
    - Know about MeetingStatus, MongoDB, or the extraction pipeline
    - Parse/validate the response into ExtractionResult (extraction_service's job)
    - Decide what prompt to send (prompts.py's job)
"""

import asyncio
import json
import logging

from anthropic import AsyncAnthropic, RateLimitError, APITimeoutError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMTimeoutError(Exception):
    """
    Raised when a Claude API call exceeds llm_request_timeout_seconds.

    A dedicated exception type (not letting asyncio.TimeoutError propagate
    directly) so callers catch a clearly-named, LLM-specific error rather
    than a generic timeout that could mean anything.
    """


class LLMRequestError(Exception):
    """
    Raised when the Claude API call fails after all retries are exhausted
    (e.g. persistent rate limiting, invalid API key, service outage).
    """


class ClaudeClient:
    """
    Thin async wrapper around the Claude API for structured text generation.

    Instantiated once (see extraction_service.py) and reused across
    requests -- the underlying AsyncAnthropic client is safe to share,
    same reasoning as MeetingRepository holding one shared database
    connection rather than reconnecting per call.
    """

    def __init__(self) -> None:
        # An empty api_key here means every call will fail at request time
        # with a clear authentication error from the SDK -- we don't
        # validate the key's presence at construction time, because
        # ClaudeClient is instantiated at module import time (see
        # extraction_service.py), before Settings necessarily has a real
        # key loaded in every environment (e.g. CI running tests that never
        # actually call the API). Fail at call time, not import time.
        self._client = AsyncAnthropic(api_key=settings.claude_api_key)
        self._model = settings.claude_model

    @retry(
        # Only retry on our own LLMTimeoutError/LLMRequestError wrapper --
        # NOT on every possible exception. Retrying a genuinely broken
        # request (e.g. malformed prompt causing a 400) would just fail the
        # same way `llm_max_retries` times in a row, wasting time and
        # obscuring the real error with retry noise.
        retry=retry_if_exception_type((LLMTimeoutError, LLMRequestError)),
        stop=stop_after_attempt(settings.llm_max_retries + 1),  # +1: first attempt isn't a "retry"
        wait=wait_exponential(multiplier=1, min=2, max=15),
        reraise=True,  # after exhausting retries, raise the real exception, not a RetryError wrapper
    )
    async def generate_json(self, prompt: str) -> str:
        """
        Sends a prompt to Claude and returns the raw text response.

        Claude is instructed to output JSON, which constrains its output
        to valid JSON syntax at the API level (an extra layer of reliability
        on top of the prompt's own instructions in prompts.py -- belt and
        suspenders, since LLMs occasionally ignore prompt-only formatting
        instructions but are more reliable when explicitly configured for
        structured output).
        """
        try:
            response = await asyncio.wait_for(
                self._client.messages.create(
                    model=self._model,
                    max_tokens=settings.llm_max_output_tokens,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                    system="You are an AI assistant that responds with valid JSON only. No markdown, no explanations, just JSON.",
                ),
                timeout=settings.llm_request_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            logger.warning(
                "Claude request timed out after %ds", settings.llm_request_timeout_seconds
            )
            raise LLMTimeoutError(
                f"Claude request exceeded {settings.llm_request_timeout_seconds}s timeout"
            ) from exc
        except RateLimitError as exc:
            # Claude's specific rate limit error
            logger.warning("Claude rate limited: %s", exc)
            raise LLMRequestError(f"Claude rate limited: {exc}") from exc
        except APITimeoutError as exc:
            # Claude's timeout error type
            logger.warning("Claude API timeout: %s", exc)
            raise LLMTimeoutError(f"Claude API timeout: {exc}") from exc
        except Exception as exc:
            # The Claude SDK can raise several different exception types
            # (auth errors, rate limits, network errors, etc.) -- we
            # deliberately normalize all of them into one LLMRequestError
            # here so callers (and the @retry decorator above) only need
            # to handle one exception type, not enumerate every possible
            # SDK-specific exception class.
            logger.warning("Claude request failed: %s: %s", type(exc).__name__, exc)
            raise LLMRequestError(f"{type(exc).__name__}: {exc}") from exc

        # Extract text content from the response
        if not response.content or not response.content[0].text:
            # An empty response (e.g. blocked by safety filters, or the
            # model returned nothing) is a real failure case worth
            # surfacing distinctly -- silently returning "" would let an
            # empty string flow into JSON parsing and fail there with a
            # much less clear error message.
            raise LLMRequestError("Claude returned an empty response")

        return response.content[0].text
