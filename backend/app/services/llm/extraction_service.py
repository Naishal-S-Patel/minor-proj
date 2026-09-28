"""
ExtractionService — orchestrates turning a cleaned transcript into a
validated ExtractionResult.

Sits between the worker (which drives DB status transitions) and
GeminiClient (which only knows how to make an inference call). This is
the layer that:
    1. Builds the prompt (via prompts.py)
    2. Calls the LLM client
    3. Parses the response as JSON
    4. Validates it against ExtractionResult
    5. On a parse/validation failure, retries ONCE with a "fix your JSON"
       follow-up prompt before giving up

This mirrors the retry-with-correction pattern from the original project
plan: LLMs occasionally return near-valid JSON (a trailing comma, a
missing quote) that's worth one correction attempt before treating the
whole extraction as failed.
"""

import json
import logging

from pydantic import ValidationError

from app.services.llm.gemini_client import GeminiClient, LLMRequestError, LLMTimeoutError
from app.services.llm.groq_client import GroqClient
from app.services.llm.prompts import build_extraction_prompt
from app.services.llm.schemas import ExtractionResult
from app.core.config import settings

logger = logging.getLogger(__name__)

# Sent as a follow-up prompt when the first response fails to parse/validate.
# Deliberately short and specific -- the goal is a narrow correction, not a
# fresh attempt at the whole extraction task (which the model already has
# the transcript and instructions for, from the first prompt in the same
# conceptual turn).
_JSON_FIX_PROMPT_TEMPLATE = """Your previous response was not valid JSON matching the required schema. \
The error was: {error}

Here was your previous response:
---
{previous_response}
---

Respond again with ONLY a single valid JSON object matching the schema \
described in the original instructions. No markdown code fences, no \
explanation -- just the corrected JSON object."""


class ExtractionFailedError(Exception):
    """
    Raised when extraction fails after the initial attempt and one JSON-fix
    retry. Carries a human-readable reason for the FAILED status message
    the worker will persist.
    """


class ExtractionService:
    """
    High-level entry point: given a cleaned transcript, returns a validated
    ExtractionResult or raises ExtractionFailedError.
    """

    def __init__(self, client: GeminiClient | GroqClient | None = None) -> None:
        # Accepts an optional client so tests can inject a fake/mock
        # client without needing API keys.
        if client is None:
            if settings.llm_provider == "groq":
                self._client = GroqClient()
            else:
                self._client = GeminiClient()
        else:
            self._client = client

    async def extract(self, cleaned_transcript: str) -> ExtractionResult:
        """
        Runs the full extract -> parse -> validate flow, with one retry on
        malformed output. Raises ExtractionFailedError if both attempts fail.
        """
        prompt = build_extraction_prompt(cleaned_transcript)

        try:
            raw_response = await self._client.generate_json(prompt)
        except (LLMTimeoutError, LLMRequestError) as exc:
            # No point attempting the JSON-fix retry here -- if the API
            # call itself failed (timeout, rate limit, connection refused),
            # a follow-up prompt won't help; the failure is at the
            # transport/service level, not something rephrasing the prompt
            # can fix.
            raise ExtractionFailedError(f"LLM request failed: {exc}") from exc

        result = self._try_parse(raw_response)
        if result is not None:
            return result

        logger.info("First extraction response failed validation, attempting one JSON-fix retry")
        result = await self._retry_with_fix(prompt_context=raw_response)
        if result is not None:
            return result

        raise ExtractionFailedError(
            "LLM response could not be parsed as valid extraction JSON after retry"
        )

    def _try_parse(self, raw_response: str) -> ExtractionResult | None:
        """
        Attempts to parse and validate a raw LLM response. Returns None
        (not an exception) on failure -- this method's job is "did it
        work," leaving the caller to decide what to do next (retry, give
        up), consistent with how MeetingRepository.get_by_id returns None
        rather than raising for its own "not found" case.
        """
        try:
            data = json.loads(_strip_markdown_fences(raw_response))
        except json.JSONDecodeError as exc:
            logger.warning("Extraction response was not valid JSON: %s", exc)
            return None

        try:
            return ExtractionResult(**data)
        except ValidationError as exc:
            logger.warning("Extraction response failed schema validation: %s", exc)
            return None

    async def _retry_with_fix(self, prompt_context: str) -> ExtractionResult | None:
        """
        Sends one corrective follow-up prompt and attempts to parse that
        response. Returns None if the retry also fails -- caller raises
        ExtractionFailedError in that case.
        """
        fix_prompt = _JSON_FIX_PROMPT_TEMPLATE.format(
            error="Response was not valid JSON matching the required schema.",
            previous_response=prompt_context,
        )
        try:
            raw_response = await self._client.generate_json(fix_prompt)
        except (LLMTimeoutError, LLMRequestError) as exc:
            logger.warning("JSON-fix retry request also failed: %s", exc)
            return None

        return self._try_parse(raw_response)


def _strip_markdown_fences(text: str) -> str:
    """
    Strips ```json ... ``` or ``` ... ``` code fences if the model wrapped
    its JSON response in them despite instructions not to.

    This is a defensive normalization step, not a workaround for one
    specific provider's quirk -- LLMs across providers commonly wrap JSON
    in markdown fences by habit even when explicitly told not to, so
    handling it here is cheap insurance rather than a fragile
    provider-specific hack.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        # Drop the opening fence line (```json or ```) and the closing ``` line.
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        stripped = "\n".join(lines)
    return stripped.strip()
