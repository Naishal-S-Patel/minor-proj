"""
LLM extraction background worker.

Drives a meeting that already has a cleaned_transcript through:
    (already at CLEANING status, from transcription/cleaning) -> ANALYZING -> PROCESSED
                                                                          -> FAILED (on error)

Design constraint, matching transcription_worker.py: MUST land on
PROCESSED or FAILED before returning. A meeting stuck at ANALYZING forever
is worse than FAILED.

Why this is a SEPARATE worker file from transcription_worker.py, not one
big combined pipeline:
    Transcription (Phase 2) and extraction (Phase 3) are independently
    useful, independently testable stages with different failure modes and
    different dependencies (local Whisper vs. a network call to Gemini).
    Keeping them as separate functions means:
      - test_transcription_worker.py and test_extraction_worker.py can each
        mock only what THAT stage needs, rather than one giant test file
        mocking both Whisper and Gemini together.
      - A future change to the LLM provider or retry strategy touches this
        file only, never transcription_worker.py.
      - The two stages can be triggered independently for text-only
        uploads (which skip transcription entirely) versus audio uploads
        (which need transcription first) -- see
        meeting_orchestrator.py for how each upload path chains the
        stages it actually needs.
"""

import logging
import uuid

from app.models.meeting import ActionItem, MeetingStatus
from app.repositories.meeting_repository import MeetingRepository
from app.services.llm.extraction_service import ExtractionFailedError, ExtractionService

logger = logging.getLogger(__name__)


async def run_extraction_pipeline(
    meeting_id: str,
    cleaned_transcript: str,
    repo: MeetingRepository,
    extraction_service: ExtractionService,
) -> None:
    """
    Full LLM extraction pipeline. Called as a FastAPI BackgroundTask, or
    chained directly after transcription/cleaning completes -- see
    meeting_orchestrator.py.
    """
    try:
        # 1. Mark as analyzing (UI shows "Analyzing…")
        await repo.update_status(meeting_id, MeetingStatus.ANALYZING)

        if not cleaned_transcript or not cleaned_transcript.strip():
            # Guards against a real edge case: a meeting could reach this
            # worker with an empty cleaned_transcript (e.g. an audio file
            # that was silence, or a .txt upload that was 100% filler
            # words stripped down to nothing by TranscriptService). Sending
            # empty text to the LLM would waste a call and produce a
            # meaningless "extraction" -- fail clearly here instead.
            raise ValueError("Cannot extract insights from an empty transcript")

        # 2. Call the LLM extraction service (owns its own retry logic
        # internally -- see GeminiClient's @retry decorator and
        # ExtractionService's JSON-fix retry).
        result = await extraction_service.extract(cleaned_transcript)

        # 3. Save extracted fields, advance to PROCESSED.
        #
        # Each LLMActionItem (person/task/deadline only -- what the LLM
        # actually produces, see schemas.py) is converted into a full
        # ActionItem here, generating a stable `id` and defaulting
        # `done=False`. This is the ONE place that conversion happens --
        # the LLM is never asked to invent an id or track completion state,
        # since both are application concerns, not extraction concerns.
        # uuid.uuid4().hex (not a MongoDB ObjectId) is enough: this id only
        # ever needs to be unique WITHIN one meeting's action_items list,
        # to address a specific item via PATCH /meetings/{id}/action-items/{item_id}.
        #
        # model_dump() on the resulting ActionItem list converts it to
        # plain dicts, which is what update_fields()/MongoDB expect --
        # Pydantic models aren't directly BSON-serializable, so this
        # conversion has to happen somewhere, and doing it here (at the
        # boundary between "typed extraction result" and "generic
        # repository update") keeps both ExtractionResult and
        # MeetingRepository ignorant of each other's types.
        action_items = [
            ActionItem(
                id=uuid.uuid4().hex,
                person=item.person,
                task=item.task,
                deadline=item.deadline,
                done=False,
            )
            for item in result.action_items
        ]

        await repo.update_fields(
            meeting_id,
            {
                "summary": result.summary,
                "action_items": [item.model_dump() for item in action_items],
                "decisions": result.decisions,
                "keywords": result.keywords,
                "sentiment": result.sentiment,
                "status": MeetingStatus.PROCESSED.value,
            },
        )
        logger.info("Extraction pipeline complete for meeting_id=%s", meeting_id)

    except ExtractionFailedError as exc:
        logger.error("Extraction failed for meeting_id=%s: %s", meeting_id, exc)
        await repo.update_status(meeting_id, MeetingStatus.FAILED, error_message=str(exc))

    except Exception as exc:  # noqa: BLE001
        # Safety net for anything unexpected (e.g. the empty-transcript
        # ValueError above, or a genuinely unforeseen bug) -- same
        # philosophy as transcription_worker.py's broad catch: never leave
        # a meeting stuck in ANALYZING with no explanation.
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.error("Extraction pipeline failed unexpectedly for meeting_id=%s: %s", meeting_id, error_msg)
        await repo.update_status(meeting_id, MeetingStatus.FAILED, error_message=error_msg)
