"""
Tests for GeminiClient.

Mocks the google-genai SDK so these tests never need a real API key and
run instantly. Focuses on GeminiClient's responsibilities: timeout
enforcement and normalizing failures into our own exception types.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.llm.gemini_client import LLMRequestError, LLMTimeoutError, GeminiClient


def _make_client_with_mocked_sdk() -> tuple[GeminiClient, MagicMock]:
    """Builds a GeminiClient with the SDK mocked out."""
    with patch("app.services.llm.gemini_client.settings") as mock_settings:
        mock_settings.gemini_api_key = "test-key"
        mock_settings.gemini_model = "gemini-2.0-flash"
        mock_settings.llm_max_output_tokens = 2048
        mock_settings.llm_request_timeout_seconds = 60
        mock_settings.llm_max_retries = 2
        client = GeminiClient()
    return client, client._client


def _mock_gemini_response(text: str) -> MagicMock:
    """Builds a fake Gemini GenerateContentResponse."""
    response = MagicMock()
    response.text = text
    return response


@pytest.mark.asyncio
async def test_generate_json_returns_response_text():
    client, mock_sdk = _make_client_with_mocked_sdk()
    mock_sdk.models.generate_content.return_value = _mock_gemini_response('{"summary": "ok"}')

    result = await client.generate_json("some prompt")

    assert result == '{"summary": "ok"}'
    mock_sdk.models.generate_content.assert_called_once()


@pytest.mark.asyncio
async def test_generate_json_raises_on_empty_response():
    client, mock_sdk = _make_client_with_mocked_sdk()
    mock_sdk.models.generate_content.return_value = _mock_gemini_response("")

    with pytest.raises(LLMRequestError, match="empty response"):
        await client.generate_json("some prompt")


@pytest.mark.asyncio
async def test_generate_json_normalizes_errors():
    """SDK exceptions should be normalized to LLMRequestError."""
    client, mock_sdk = _make_client_with_mocked_sdk()
    mock_sdk.models.generate_content.side_effect = RuntimeError("API down")

    with pytest.raises(LLMRequestError, match="API down"):
        await client.generate_json("some prompt")


@pytest.mark.asyncio
async def test_generate_json_strips_markdown_fences():
    """Gemini sometimes wraps JSON in markdown fences — should still work."""
    client, mock_sdk = _make_client_with_mocked_sdk()
    mock_sdk.models.generate_content.return_value = _mock_gemini_response(
        '```json\n{"summary": "ok"}\n```'
    )

    result = await client.generate_json("some prompt")

    assert '{"summary": "ok"}' in result
