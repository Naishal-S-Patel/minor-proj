"""
DEPRECATED — LocalLLMClient (Ollama) has been replaced by GeminiClient.

This file is kept for reference only. The active LLM client is now:
    app/services/llm/gemini_client.py

If you need to use Ollama in the future, restore this file and update:
    - app/core/config.py (add ollama_* settings)
    - app/services/llm/extraction_service.py (import LocalLLMClient)
    - app/services/llm/chat_service.py (import LocalLLMClient)
"""

import asyncio
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMTimeoutError(Exception):
    """
    Raised when a local LLM inference call exceeds llm_request_timeout_seconds.
    """


class LLMRequestError(Exception):
    """
    Raised when the LLM inference fails (Ollama connection error, etc).
    """


class LocalLLMClient:
    """
    Client for Ollama local LLM server.

    Ollama must be running separately:
        1. Download Ollama from https://ollama.ai
        2. Run: ollama pull mistral (or any other model)
        3. Run: ollama serve (starts server on localhost:11434)

    This client connects to the running Ollama server and sends inference requests.
    """

    def __init__(self) -> None:
        """
        Initialize Ollama client. Does NOT start the Ollama server --
        that must be running separately on the configured URL.
        """
        try:
            # Lazy import to make it optional
            import httpx

            logger.info(
                "Initialized Ollama client (server: %s, model: %s)",
                settings.ollama_base_url,
                settings.ollama_model,
            )

            self._base_url = settings.ollama_base_url
            self._model = settings.ollama_model
            self._client = httpx.AsyncClient(timeout=settings.llm_request_timeout_seconds)

        except ImportError as exc:
            logger.error("httpx not installed. Install with: pip install httpx")
            raise LLMRequestError("httpx required for Ollama client") from exc
        except Exception as exc:
            logger.error("Failed to initialize Ollama client: %s", exc)
            raise LLMRequestError(f"Initialization failed: {exc}") from exc

    async def generate_json(self, prompt: str) -> str:
        """
        Sends a prompt to the Ollama server and returns the text response.
        """
        try:
            response_text = await asyncio.wait_for(
                self._generate_text(prompt),
                timeout=settings.llm_request_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            logger.warning(
                "Ollama inference timed out after %ds",
                settings.llm_request_timeout_seconds,
            )
            raise LLMTimeoutError(
                f"Ollama inference exceeded {settings.llm_request_timeout_seconds}s timeout"
            ) from exc
        except Exception as exc:
            logger.warning("Ollama inference failed: %s: %s", type(exc).__name__, exc)
            raise LLMRequestError(f"{type(exc).__name__}: {exc}") from exc

        if not response_text or not response_text.strip():
            raise LLMRequestError("Ollama returned an empty response")

        return response_text

    async def _generate_text(self, prompt: str) -> str:
        """
        Make an async request to Ollama's generate endpoint.
        """
        try:
            response = await self._client.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "stream": False,  # Get full response at once
                    "temperature": 0.1,  # Low temperature for focused outputs
                },
            )

            if response.status_code != 200:
                raise LLMRequestError(
                    f"Ollama returned status {response.status_code}: {response.text}"
                )

            data = response.json()
            generated_text = data.get("response", "").strip()

            return generated_text

        except Exception as exc:
            logger.error("Ollama request failed: %s", exc)
            raise LLMRequestError(f"Ollama request failed: {exc}") from exc

    async def __aenter__(self):
        """Context manager support."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close the client."""
        await self._client.aclose()
