"""
Meeting pipeline orchestrator.

This is the one place that knows the full end-to-end sequence a meeting
goes through, and which stages apply to which upload type:

    Text upload:   CLEANING (sync, in the route) -> ANALYZING -> PROCESSED
    Audio upload:  TRANSCRIBING -> CLEANING -> ANALYZING -> PROCESSED
                                                       ↘ FAILED (any stage)

Why this file exists, rather than having each worker call the next one
directly:
    transcription_worker.py and extraction_worker.py are each written to
    know about exactly ONE stage -- this is deliberate (see both files'
    docstrings) so each is independently testable and reusable. If
    transcription_worker.py called run_extraction_pipeline directly at its
    end, the two stages would become coupled: you couldn't test
    transcription in isolation without also pulling in extraction's
    dependencies, and you couldn't reuse transcription for a hypothetical
    future flow that doesn't need extraction.

    This orchestrator is the seam where "what runs after what" is decided,
    kept separate from "how each stage works." It's the async equivalent of
    a simple pipeline/workflow definition.
"""

import logging

from app.repositories.meeting_repository import MeetingRepository
from app.services.audio_service import AudioService
from app.services.llm.extraction_service import ExtractionService
from app.services.transcript_service import TranscriptService
from app.workers.extraction_worker import run_extraction_pipeline
from app.workers.transcription_worker import run_transcription_pipeline

logger = logging.getLogger(__name__)


async def run_audio_pipeline(
    meeting_id: str,
    audio_bytes: bytes,
    filename: str,
    repo: MeetingRepository,
    audio_service: AudioService,
    transcript_service: TranscriptService,
    extraction_service: ExtractionService,
) -> None:
    """
    Full pipeline for an audio upload: transcription, then extraction.

    Scheduled as the single BackgroundTask for audio uploads (see
    api/meetings.py) -- rather than scheduling two separate background
    tasks, one function owns the sequencing so extraction only ever runs
    AFTER transcription has genuinely succeeded.
    """
    try:
        await run_transcription_pipeline(
            meeting_id=meeting_id,
            audio_bytes=audio_bytes,
            filename=filename,
            repo=repo,
            audio_service=audio_service,
            transcript_service=transcript_service,
        )
    except Exception:
        # run_transcription_pipeline already persisted status=FAILED and
        # an error_message before re-raising (see its own except block) --
        # we catch here ONLY to stop the pipeline from proceeding to
        # extraction, not to do any additional error handling. The
        # meeting's FAILED status is already correctly saved.
        logger.info(
            "Transcription failed for meeting_id=%s; skipping extraction stage", meeting_id
        )
        return

    # Re-fetch the meeting to get the cleaned_transcript that transcription
    # just saved. We can't reuse a local variable from
    # run_transcription_pipeline because that function doesn't return
    # anything (it communicates results only via the repository, per its
    # own design -- see its docstring on why every stage writes status/
    # fields directly to the DB rather than returning a result).
    meeting = await repo.get_by_id(meeting_id)
    if meeting is None or not meeting.cleaned_transcript:
        logger.error(
            "meeting_id=%s has no cleaned_transcript after transcription succeeded; "
            "this should not happen and indicates a bug in the transcription stage",
            meeting_id,
        )
        return

    await run_extraction_pipeline(
        meeting_id=meeting_id,
        cleaned_transcript=meeting.cleaned_transcript,
        repo=repo,
        extraction_service=extraction_service,
    )


async def run_text_pipeline(
    meeting_id: str,
    cleaned_transcript: str,
    repo: MeetingRepository,
    extraction_service: ExtractionService,
) -> None:
    """
    Pipeline for a text (.txt) upload: cleaning already happened
    synchronously in the route (it's fast, pure-regex work -- see
    api/meetings.py), so this only needs to run extraction.

    Kept as a thin named wrapper (rather than having the route call
    run_extraction_pipeline directly) so BOTH upload paths go through this
    orchestrator module -- if a future stage needs to be inserted before
    extraction for text uploads too, there's one obvious place to add it.
    """
    await run_extraction_pipeline(
        meeting_id=meeting_id,
        cleaned_transcript=cleaned_transcript,
        repo=repo,
        extraction_service=extraction_service,
    )
