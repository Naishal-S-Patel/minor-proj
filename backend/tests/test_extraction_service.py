"""
Tests for ExtractionService.

Uses a fake LLM client (not the real Gemini API call) -- no real inference
call required, no API key needed to run this file. Focuses on
parsing/validation/retry logic, which is ExtractionService's actual
responsibility; GeminiClient's own request/timeout handling is tested
separately in test_gemini_client.py.
"""

import pytest

from app.services.llm.extraction_service import ExtractionFailedError, ExtractionService
from app.services.llm.gemini_client import LLMRequestError, LLMTimeoutError


class FakeLLMClient:
    """
    In-memory stand-in for GeminiClient (or any LLM client implementing
    generate_json). Returns a scripted sequence of responses (or raises a
    scripted exception) on successive calls, which lets tests simulate
    "first response was malformed, second was fixed" without any real
    inference call.
    """

    def __init__(self, responses: list[str] | None = None, exception: Exception | None = None) -> None:
        self._responses = responses or []
        self._exception = exception
        self.call_count = 0
        self.prompts_received: list[str] = []

    async def generate_json(self, prompt: str) -> str:
        self.call_count += 1
        self.prompts_received.append(prompt)
        if self._exception is not None:
            raise self._exception
        return self._responses[min(self.call_count - 1, len(self._responses) - 1)]


VALID_EXTRACTION_JSON = """{
  "summary": "The team discussed the login module and agreed on a Friday deadline.",
  "action_items": [
    {"person": "Sarah", "task": "Complete the frontend", "deadline": "Friday"},
    {"person": "Mike", "task": "Complete the backend", "deadline": "Friday"}
  ],
  "decisions": ["Deployment scheduled for Monday."],
  "keywords": ["login module", "deployment", "frontend", "backend"],
  "sentiment": "positive"
}"""


@pytest.mark.asyncio
async def test_extract_success_on_first_attempt():
    """A well-formed response is parsed and validated without any retry."""
    fake_client = FakeLLMClient(responses=[VALID_EXTRACTION_JSON])
    service = ExtractionService(client=fake_client)

    result = await service.extract("John: We need to finish the login module by Friday.")

    assert result.summary.startswith("The team discussed")
    assert len(result.action_items) == 2
    assert result.action_items[0].person == "Sarah"
    assert result.decisions == ["Deployment scheduled for Monday."]
    assert result.sentiment == "positive"
    assert fake_client.call_count == 1


@pytest.mark.asyncio
async def test_extract_strips_markdown_fences():
    """
    A response wrapped in ```json ... ``` fences (despite prompt
    instructions not to) is still parsed correctly.
    """
    fenced = f"```json\n{VALID_EXTRACTION_JSON}\n```"
    fake_client = FakeLLMClient(responses=[fenced])
    service = ExtractionService(client=fake_client)

    result = await service.extract("Some transcript.")

    assert result.sentiment == "positive"
    assert fake_client.call_count == 1


@pytest.mark.asyncio
async def test_extract_retries_once_on_malformed_json():
    """
    A malformed first response triggers exactly one JSON-fix retry; if the
    retry succeeds, extraction succeeds overall.
    """
    malformed = "{summary: 'missing quotes, not valid json'"  # deliberately broken
    fake_client = FakeLLMClient(responses=[malformed, VALID_EXTRACTION_JSON])
    service = ExtractionService(client=fake_client)

    result = await service.extract("Some transcript.")

    assert result.sentiment == "positive"
    assert fake_client.call_count == 2  # original attempt + one fix retry


@pytest.mark.asyncio
async def test_extract_fails_after_retry_also_malformed():
    """If both the original AND the fix-retry response are malformed, extraction fails."""
    malformed = "not json at all"
    fake_client = FakeLLMClient(responses=[malformed, malformed])
    service = ExtractionService(client=fake_client)

    with pytest.raises(ExtractionFailedError):
        await service.extract("Some transcript.")

    assert fake_client.call_count == 2  # confirms the retry was actually attempted


@pytest.mark.asyncio
async def test_extract_fails_fast_on_schema_validation_error_then_retries():
    """
    Valid JSON syntax but missing a required field (e.g. no `summary`)
    fails Pydantic validation, which is treated the same as malformed JSON
    -- one retry attempt, same as a syntax error.
    """
    missing_summary = '{"action_items": [], "decisions": [], "keywords": [], "sentiment": "neutral"}'
    fake_client = FakeLLMClient(responses=[missing_summary, VALID_EXTRACTION_JSON])
    service = ExtractionService(client=fake_client)

    result = await service.extract("Some transcript.")

    assert result.sentiment == "positive"
    assert fake_client.call_count == 2


@pytest.mark.asyncio
async def test_extract_does_not_retry_on_llm_request_error():
    """
    If the underlying API call itself fails (not a parsing issue), no
    JSON-fix retry is attempted -- the LLM client already exhausted any
    internal retries for transient failures, so a follow-up prompt
    wouldn't help. Only one call should be made.
    """
    fake_client = FakeLLMClient(exception=LLMRequestError("rate limited"))
    service = ExtractionService(client=fake_client)

    with pytest.raises(ExtractionFailedError, match="LLM request failed"):
        await service.extract("Some transcript.")

    assert fake_client.call_count == 1


@pytest.mark.asyncio
async def test_extract_does_not_retry_on_timeout():
    """Same as above, for the timeout case specifically."""
    fake_client = FakeLLMClient(exception=LLMTimeoutError("timed out"))
    service = ExtractionService(client=fake_client)

    with pytest.raises(ExtractionFailedError, match="LLM request failed"):
        await service.extract("Some transcript.")

    assert fake_client.call_count == 1


@pytest.mark.asyncio
async def test_extract_empty_action_items_and_decisions_is_valid():
    """
    A transcript too short/unclear to extract meaningful action items or
    decisions should still succeed -- empty lists are valid, not errors
    (see prompts.py's explicit instruction on this).
    """
    minimal = """{
      "summary": "A brief exchange with no clear action items or decisions.",
      "action_items": [],
      "decisions": [],
      "keywords": [],
      "sentiment": "neutral"
    }"""
    fake_client = FakeLLMClient(responses=[minimal])
    service = ExtractionService(client=fake_client)

    result = await service.extract("Hey. Hi. See you later.")

    assert result.action_items == []
    assert result.decisions == []
    assert fake_client.call_count == 1
