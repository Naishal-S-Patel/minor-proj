"""
ExtractionService — orchestrates turning a cleaned transcript into a
validated ExtractionResult.

Resilient multi-tier strategy:
    1. Attempts LLM extraction using configured provider (Groq or Gemini).
    2. Validates JSON schema against ExtractionResult.
    3. If LLM call or parsing fails (e.g. expired API key, quota limit, network timeout),
       seamlessly falls back to SmartLocalExtractor to ensure meeting insights,
       calendar events, and keywords are ALWAYS successfully generated.
"""

import json
import logging
from pydantic import ValidationError

from app.core.config import settings
from app.services.llm.gemini_client import GeminiClient, LLMRequestError as GeminiRequestError, LLMTimeoutError as GeminiTimeoutError
from app.services.llm.groq_client import GroqClient, LLMRequestError as GroqRequestError, LLMTimeoutError as GroqTimeoutError
from app.services.llm.prompts import build_extraction_prompt
from app.services.llm.schemas import ExtractionResult
from app.services.llm.smart_engine import SmartLocalExtractor

logger = logging.getLogger(__name__)

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
    """Raised only if both LLM and local fallback fail completely."""


class ExtractionService:
    """High-level entry point: given a cleaned transcript, returns a validated ExtractionResult."""

    def __init__(self, client: GeminiClient | GroqClient | None = None) -> None:
        if client is not None:
            self._client = client
        else:
            self._client = self._init_client()

    def _init_client(self):
        """Attempts to initialize the configured LLM client."""
        try:
            if settings.llm_provider == "gemini" and settings.gemini_api_key:
                return GeminiClient()
            elif settings.llm_provider == "groq" and settings.groq_api_key:
                return GroqClient()
            elif settings.gemini_api_key:
                return GeminiClient()
            elif settings.groq_api_key:
                return GroqClient()
        except Exception as exc:
            logger.warning("Could not initialize external LLM client: %s. Will use SmartLocalExtractor.", exc)
        return None

    async def extract(self, cleaned_transcript: str) -> ExtractionResult:
        """
        Runs the extraction pipeline. If external LLM succeeds, uses it.
        If it fails (expired key, quota, timeout, network), falls back to SmartLocalExtractor.
        """
        if self._client is not None:
            try:
                prompt = build_extraction_prompt(cleaned_transcript)
                raw_response = await self._client.generate_json(prompt)
                result = self._try_parse(raw_response)
                if result is not None:
                    # Merge explicit ID -> Speaker roster mappings and normalize labels
                    explicit_map = SmartLocalExtractor.extract_speaker_map(cleaned_transcript)
                    merged_map = {**result.speaker_map, **explicit_map}
                    result.speaker_map = merged_map
                    if merged_map:
                        for turn in result.dialogue_turns:
                            if not turn.speaker_id and turn.speaker in merged_map:
                                turn.speaker_id = turn.speaker
                            if turn.speaker_id and turn.speaker_id in merged_map:
                                turn.speaker = merged_map[turn.speaker_id]
                            elif turn.speaker in merged_map:
                                turn.speaker = merged_map[turn.speaker]
                        for item in result.action_items:
                            if item.person in merged_map:
                                item.person = merged_map[item.person]
                        for ev in result.calendar_events:
                            if ev.speaker and ev.speaker in merged_map:
                                ev.speaker = merged_map[ev.speaker]
                        result.speakers = list(dict.fromkeys(
                            merged_map.get(s, s) for s in result.speakers
                        )) or list(dict.fromkeys(t.speaker for t in result.dialogue_turns))

                    # Fill in detected language or calendar events if LLM left them empty
                    if not result.calendar_events:
                        local_fallback = SmartLocalExtractor.extract(cleaned_transcript)
                        result.calendar_events = local_fallback.calendar_events
                    if not result.dialogue_turns:
                        local_fallback = SmartLocalExtractor.extract(cleaned_transcript)
                        result.dialogue_turns = local_fallback.dialogue_turns
                    return result

                logger.info("First extraction response failed schema parsing, attempting JSON-fix retry")
                retry_result = await self._retry_with_fix(raw_response)
                if retry_result is not None:
                    return retry_result
            except Exception as exc:
                logger.warning(
                    "External LLM extraction call failed (%s: %s). Activating SmartLocalExtractor fallback.",
                    type(exc).__name__,
                    exc,
                )

        # Fallback to SmartLocalExtractor (always succeeds)
        logger.info("Executing SmartLocalExtractor for reliable meeting extraction.")
        return SmartLocalExtractor.extract(cleaned_transcript)

    def _try_parse(self, raw_response: str) -> ExtractionResult | None:
        try:
            cleaned_json = _strip_markdown_fences(raw_response)
            data = json.loads(cleaned_json)
        except json.JSONDecodeError as exc:
            logger.warning("Extraction response was not valid JSON: %s", exc)
            return None

        try:
            return ExtractionResult(**data)
        except ValidationError as exc:
            logger.warning("Extraction response failed schema validation: %s", exc)
            return None

    async def _retry_with_fix(self, prompt_context: str) -> ExtractionResult | None:
        fix_prompt = _JSON_FIX_PROMPT_TEMPLATE.format(
            error="Response was not valid JSON matching the required schema.",
            previous_response=prompt_context,
        )
        try:
            raw_response = await self._client.generate_json(fix_prompt)
            return self._try_parse(raw_response)
        except Exception as exc:
            logger.warning("JSON-fix retry request also failed: %s", exc)
            return None


def _strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        stripped = "\n".join(lines)
    return stripped.strip()
