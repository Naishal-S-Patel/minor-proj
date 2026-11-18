"""
GroqClient — Groq API client using httpx async client.

Uses the OpenAI-compatible REST endpoint https://api.groq.com/openai/v1/chat/completions.
Works reliably with httpx without requiring third-party SDK installation.
Get a FREE API key at: https://console.groq.com/
"""

import asyncio
import logging
import httpx
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


class LLMAuthError(Exception):
    """Raised when Groq returns 401 or 403 (invalid or expired API key). Never retry."""


class LLMRequestError(Exception):
    """Raised when the Groq API call fails after all retries."""


class GroqClient:
    """Async Groq client using httpx for fast inference."""

    def __init__(self) -> None:
        self._api_key = settings.groq_api_key
        model = settings.groq_model
        if "gpt-oss" in model or not model:
            model = "llama-3.3-70b-versatile"
        self._model = model
        self._endpoint = "https://api.groq.com/openai/v1/chat/completions"
        logger.info("Initialized Groq HTTP client (model: %s)", self._model)

    @retry(
        retry=retry_if_exception_type((LLMTimeoutError, LLMRequestError)),
        stop=stop_after_attempt(1),
        reraise=True,
    )
    async def generate_json(self, prompt: str) -> str:
        """Sends a prompt to Groq expecting JSON."""
        if not self._api_key or self._api_key.startswith("your-") or len(self._api_key) < 10:
            raise LLMAuthError("Invalid or missing Groq API key")

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an AI assistant that responds with valid JSON only. "
                        "No markdown, no explanations, just JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": settings.llm_max_output_tokens,
            "response_format": {"type": "json_object"},
        }

        try:
            timeout_cfg = httpx.Timeout(10.0, connect=3.0)
            async with httpx.AsyncClient(timeout=timeout_cfg) as client:
                res = await client.post(self._endpoint, json=payload, headers=headers)
                if res.status_code in (401, 403):
                    raise LLMAuthError(f"Groq API Key invalid or expired (HTTP {res.status_code})")
                if res.status_code == 429:
                    raise LLMRequestError("Groq API rate limit reached")
                res.raise_for_status()
                data = res.json()
                content = data["choices"][0]["message"]["content"]
                return content.strip()
        except LLMAuthError:
            raise
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"Groq request timed out: {exc}") from exc
        except (httpx.HTTPError, KeyError, IndexError) as exc:
            raise LLMRequestError(f"Groq request error: {exc}") from exc

    @retry(
        retry=retry_if_exception_type((LLMTimeoutError, LLMRequestError)),
        stop=stop_after_attempt(1),
        reraise=True,
    )
    async def generate_text(self, prompt: str) -> str:
        """Sends a prompt to Groq for natural language chat response."""
        if not self._api_key or self._api_key.startswith("your-") or len(self._api_key) < 10:
            raise LLMAuthError("Invalid or missing Groq API key")

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a concise, accurate AI assistant for this meeting. Answer clearly.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": settings.llm_max_output_tokens,
        }

        try:
            timeout_cfg = httpx.Timeout(10.0, connect=3.0)
            async with httpx.AsyncClient(timeout=timeout_cfg) as client:
                res = await client.post(self._endpoint, json=payload, headers=headers)
                if res.status_code in (401, 403):
                    raise LLMAuthError(f"Groq API Key invalid or expired (HTTP {res.status_code})")
                res.raise_for_status()
                data = res.json()
                content = data["choices"][0]["message"]["content"]
                return content.strip()
        except LLMAuthError:
            raise
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"Groq chat timed out: {exc}") from exc
        except (httpx.HTTPError, KeyError, IndexError) as exc:
            raise LLMRequestError(f"Groq chat error: {exc}") from exc
