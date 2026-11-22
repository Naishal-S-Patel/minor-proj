"""
BedrockClient — AWS Bedrock client using boto3 and the unified Bedrock Converse API.

Supports all Bedrock foundational models:
    - Anthropic Claude 3.5 Sonnet / Haiku
    - Amazon Nova Pro / Lite
    - Meta Llama 3.3 70B
    - Mistral Large
"""

import asyncio
import logging
import re
from typing import Any
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMTimeoutError(Exception):
    """Raised when an AWS Bedrock call exceeds timeout."""


class LLMAuthError(Exception):
    """Raised when AWS credentials or IAM permissions are invalid."""


class LLMRequestError(Exception):
    """Raised when the AWS Bedrock call fails."""


class BedrockClient:
    """Async wrapper around AWS Bedrock Runtime Converse API."""

    def __init__(self) -> None:
        try:
            import boto3
            from botocore.config import Config

            session_kwargs: dict[str, Any] = {}
            if settings.aws_access_key_id and settings.aws_secret_access_key:
                session_kwargs["aws_access_key_id"] = settings.aws_access_key_id
                session_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
                if settings.aws_session_token:
                    session_kwargs["aws_session_token"] = settings.aws_session_token

            client_config = Config(
                connect_timeout=settings.llm_request_timeout_seconds,
                read_timeout=settings.llm_request_timeout_seconds,
                retries={"max_attempts": settings.llm_max_retries, "mode": "standard"},
            )

            self._client = boto3.client(
                "bedrock-runtime",
                region_name=settings.aws_region or "us-east-1",
                config=client_config,
                **session_kwargs,
            )
            self._model_id = settings.bedrock_model_id or "anthropic.claude-3-5-sonnet-20241022-v2:0"
            logger.info("Initialized AWS Bedrock client (model: %s, region: %s)", self._model_id, settings.aws_region)
        except ImportError as exc:
            logger.error("boto3 is not installed. Install with: pip install boto3")
            raise LLMRequestError("boto3 required for Bedrock client") from exc
        except Exception as exc:
            logger.error("Failed to initialize AWS Bedrock client: %s", exc)
            raise LLMRequestError(f"Bedrock init failed: {exc}") from exc

    def _sync_converse(self, prompt: str, is_json: bool = False) -> str:
        """Synchronous Converse call executed in thread pool."""
        from botocore.exceptions import ClientError, ConnectTimeoutError, ReadTimeoutError

        system_text = (
            "You are an AI assistant that responds with valid JSON only. "
            "No markdown code fences, no explanations, just valid JSON matching the requested schema."
            if is_json
            else "You are a concise, accurate AI meeting assistant. Answer using only the provided meeting facts."
        )

        try:
            response = self._client.converse(
                modelId=self._model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": prompt}],
                    }
                ],
                system=[{"text": system_text}],
                inferenceConfig={
                    "maxTokens": settings.llm_max_output_tokens,
                    "temperature": 0.1 if is_json else 0.3,
                },
            )

            output_message = response.get("output", {}).get("message", {})
            content_list = output_message.get("content", [])
            if not content_list:
                raise LLMRequestError("Empty response content from AWS Bedrock")

            text = content_list[0].get("text", "").strip()

            if is_json:
                # Strip markdown fences if any LLM accidentally included them
                text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
                text = re.sub(r"\s*```$", "", text)
                text = text.strip()

            return text

        except (ConnectTimeoutError, ReadTimeoutError) as exc:
            logger.warning("AWS Bedrock request timed out: %s", exc)
            raise LLMTimeoutError(f"Bedrock timeout: {exc}") from exc
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            error_msg = exc.response.get("Error", {}).get("Message", str(exc))
            if error_code in ("UnrecognizedClientException", "AccessDeniedException", "InvalidSignatureException"):
                logger.error("AWS Bedrock Auth error: %s - %s", error_code, error_msg)
                raise LLMAuthError(f"AWS Auth failed: {error_msg}") from exc
            if error_code == "ThrottlingException":
                logger.warning("AWS Bedrock rate limit throttled: %s", error_msg)
                raise LLMRequestError("Bedrock throttling limit exceeded") from exc
            logger.error("AWS Bedrock ClientError: %s - %s", error_code, error_msg)
            raise LLMRequestError(f"Bedrock call failed ({error_code}): {error_msg}") from exc
        except Exception as exc:
            logger.error("Unexpected error calling AWS Bedrock: %s", exc)
            raise LLMRequestError(f"Bedrock invocation error: {exc}") from exc

    @retry(
        retry=retry_if_exception_type((LLMTimeoutError, LLMRequestError)),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    async def generate_json(self, prompt: str) -> str:
        """Asynchronously calls Bedrock Converse expecting JSON."""
        return await asyncio.to_thread(self._sync_converse, prompt, is_json=True)

    @retry(
        retry=retry_if_exception_type((LLMTimeoutError, LLMRequestError)),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    async def generate(self, prompt: str) -> str:
        """Asynchronously calls Bedrock Converse for natural text answers."""
        return await asyncio.to_thread(self._sync_converse, prompt, is_json=False)

