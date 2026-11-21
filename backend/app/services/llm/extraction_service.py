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
from typing import Any
from pydantic import ValidationError

from app.core.config import settings
from app.services.llm.gemini_client import GeminiClient, LLMRequestError, LLMTimeoutError
from app.services.llm.groq_client import GroqClient, LLMRequestError as GroqRequestError, LLMTimeoutError as GroqTimeoutError
from app.services.llm.prompts import build_extraction_prompt
from app.services.llm.schemas import ExtractionResult
from app.services.llm.smart_engine import SmartLocalExtractor
from app.services.speaker_identity import detect_platform
from app.services.speaker_identity import is_meet as is_meet_platform
from app.services.speaker_identity import is_zoom as is_zoom_platform

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

    def __init__(self, client: Any = None, enable_fallback: bool | None = None) -> None:
        if client is not None:
            self._client = client
        else:
            self._client = self._init_client()
        if enable_fallback is None:
            self.enable_fallback = False if (client is not None) else True
        else:
            self.enable_fallback = enable_fallback

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

    async def extract(
        self,
        cleaned_transcript: str,
        meeting_title: str = "",
        platform: str = "",
    ) -> ExtractionResult:
        """
        Runs the extraction pipeline. If external LLM succeeds, uses it.
        If it fails (expired key, quota, timeout, network), falls back to SmartLocalExtractor.
        Ensures Zoom Tag IDs (USR-101, USR-102, ...) or Google Meet Tag IDs (P01, P02, ...)
        are appropriately extracted and assigned.
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

                    # Fill in detected language, calendar events, or dialogue turns if empty
                    if not result.calendar_events or not result.dialogue_turns:
                        local_fallback = SmartLocalExtractor.extract(
                            cleaned_transcript, meeting_title=meeting_title, platform=platform
                        )
                        if not result.calendar_events:
                            result.calendar_events = local_fallback.calendar_events
                        if not result.dialogue_turns:
                            result.dialogue_turns = local_fallback.dialogue_turns
                        if not result.speaker_map:
                            result.speaker_map = local_fallback.speaker_map

                    # Ensure platform-specific Tag IDs (Zoom USR-xxx or Meet P0x)
                    self._ensure_platform_tags(result, cleaned_transcript, meeting_title, platform)
                    return result

                logger.info("First extraction response failed schema parsing, attempting JSON-fix retry")
                retry_result = await self._retry_with_fix(raw_response)
                if retry_result is not None:
                    self._ensure_platform_tags(retry_result, cleaned_transcript, meeting_title, platform)
                    return retry_result
                if not self.enable_fallback:
                    raise ExtractionFailedError("Failed to parse LLM extraction response after retry")
            except Exception as exc:
                if not self.enable_fallback:
                    if isinstance(exc, (LLMRequestError, LLMTimeoutError)):
                        raise ExtractionFailedError(f"LLM request failed: {exc}") from exc
                    raise
                logger.warning(
                    "External LLM extraction call failed (%s: %s). Activating SmartLocalExtractor fallback.",
                    type(exc).__name__,
                    exc,
                )

        # Fallback to SmartLocalExtractor (always succeeds)
        logger.info("Executing SmartLocalExtractor for reliable meeting extraction.")
        return SmartLocalExtractor.extract(
            cleaned_transcript, meeting_title=meeting_title, platform=platform
        )

    def _ensure_platform_tags(
        self,
        result: ExtractionResult,
        cleaned_transcript: str,
        meeting_title: str = "",
        platform: str = "",
    ) -> None:
        """Assigns Zoom (USR-xxx) or Google Meet (P0x) tag IDs if meeting is on that platform."""
        detected = detect_platform(platform, None, meeting_title, cleaned_transcript)
        is_zoom = is_zoom_platform(detected)
        is_google_meet = is_meet_platform(detected) and not is_zoom

        if not (is_zoom or is_google_meet):
            return

        prefix = "USR-" if is_zoom else "P"
        start_num = 101 if is_zoom else 1
        allocated_tags = set(result.speaker_map.keys())
        tag_counter = start_num
        name_to_tag = {v: k for k, v in result.speaker_map.items() if k != v}

        for spk in result.speakers:
            if spk in result.speaker_map or spk in name_to_tag:
                continue
            while True:
                candidate = f"{prefix}{tag_counter}" if is_zoom else f"{prefix}{tag_counter:02d}"
                if candidate not in allocated_tags:
                    tag_id = candidate
                    allocated_tags.add(tag_id)
                    tag_counter += 1
                    break
                tag_counter += 1
            result.speaker_map[tag_id] = spk
            name_to_tag[spk] = tag_id

        for turn in result.dialogue_turns:
            if not turn.speaker_id:
                if turn.speaker in name_to_tag:
                    turn.speaker_id = name_to_tag[turn.speaker]
                elif turn.speaker in result.speaker_map:
                    turn.speaker_id = turn.speaker
            elif turn.speaker_id in result.speaker_map:
                turn.speaker = result.speaker_map[turn.speaker_id]

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
