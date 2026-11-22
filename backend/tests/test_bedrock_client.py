"""
Tests for BedrockClient.

Mocks boto3 so these tests run deterministically without AWS credentials or cloud calls.
"""

from unittest.mock import MagicMock, patch
import pytest

from app.services.llm.bedrock_client import BedrockClient, LLMAuthError, LLMRequestError, LLMTimeoutError


def _make_mocked_bedrock_client():
    with patch("app.services.llm.bedrock_client.settings") as mock_settings:
        mock_settings.aws_access_key_id = "test-access-key"
        mock_settings.aws_secret_access_key = "test-secret-key"
        mock_settings.aws_session_token = ""
        mock_settings.aws_region = "us-east-1"
        mock_settings.bedrock_model_id = "anthropic.claude-3-5-sonnet-20241022-v2:0"
        mock_settings.llm_max_output_tokens = 2048
        mock_settings.llm_request_timeout_seconds = 10
        mock_settings.llm_max_retries = 1

        with patch("boto3.client") as mock_boto:
            mock_runtime = MagicMock()
            mock_boto.return_value = mock_runtime
            client = BedrockClient()
            client._client = mock_runtime
            return client, mock_runtime


@pytest.mark.asyncio
async def test_bedrock_generate_json_success():
    client, mock_runtime = _make_mocked_bedrock_client()
    mock_runtime.converse.return_value = {
        "output": {
            "message": {
                "content": [{"text": '{"summary": "AWS Bedrock processed successfully"}'}]
            }
        }
    }

    result = await client.generate_json("test prompt")
    assert result == '{"summary": "AWS Bedrock processed successfully"}'
    mock_runtime.converse.assert_called_once()


@pytest.mark.asyncio
async def test_bedrock_strips_markdown_fences():
    client, mock_runtime = _make_mocked_bedrock_client()
    mock_runtime.converse.return_value = {
        "output": {
            "message": {
                "content": [{"text": '```json\n{"summary": "clean json"}\n```'}]
            }
        }
    }

    result = await client.generate_json("test prompt")
    assert result == '{"summary": "clean json"}'


@pytest.mark.asyncio
async def test_bedrock_generate_text_success():
    client, mock_runtime = _make_mocked_bedrock_client()
    mock_runtime.converse.return_value = {
        "output": {
            "message": {
                "content": [{"text": "Meeting discussion covered Q4 deliverables."}]
            }
        }
    }

    result = await client.generate("test prompt")
    assert result == "Meeting discussion covered Q4 deliverables."


@pytest.mark.asyncio
async def test_bedrock_empty_response_raises():
    client, mock_runtime = _make_mocked_bedrock_client()
    mock_runtime.converse.return_value = {"output": {"message": {"content": []}}}

    with pytest.raises(LLMRequestError, match="Empty response"):
        await client.generate_json("test prompt")

