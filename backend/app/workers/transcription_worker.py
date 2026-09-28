"""
Transcription background worker.

Drives the meeting through:
    UPLOADED → TRANSCRIBING → CLEANING → PROCESSED
                                   ↘ FAILED (on any error)

Design constraint: MUST update status to PROCESSED or FAILED before
returning. A meeting stuck at TRANSCRIBING forever is worse than FAILED.
"""

import asyncio
import logging

from app.models.meeting import MeetingStatus
from app.repositories.meeting_repository import MeetingRepository
from app.services.audio_service import AudioService
from app.services.transcript_service import TranscriptService

logger = logging.getLogger(__name__)


async def run_transcription_pipeline(
    meeting_id: str,
    audio_bytes: bytes,
    filename: str,
    repo: MeetingRepository,
    audio_service: AudioService,
    transcript_service: TranscriptService,
) -> None:
    """Full transcription pipeline. Called as a FastAPI BackgroundTask."""
    try:
        # 1. Mark as transcribing (UI shows "Transcribing…")
        await repo.update_status(meeting_id, MeetingStatus.TRANSCRIBING)

        # 2. Transcribe using local Whisper.
        #
        # audio_service.transcribe() is a SYNCHRONOUS, CPU-bound call --
        # Whisper model inference runs on the CPU (or GPU) for the entire
        # duration of the audio, which can be many seconds to minutes.
        # Calling it directly here (`audio_service.transcribe(...)`) would
        # block the single asyncio event loop thread for that whole time --
        # even though this function is a BackgroundTask (so it doesn't hold
        # up the original HTTP response), it still runs on FastAPI's one
        # event loop, so EVERY other concurrent request (health checks,
        # other users' GET /meetings, anything) would freeze until
        # transcription finishes.
        #
        # asyncio.to_thread() runs the call in a separate worker thread
        # (backed by a thread pool) and awaits its result without blocking
        # the event loop -- this is the standard fix for wrapping
        # synchronous, CPU-bound or blocking code inside async code.
        raw_transcript = await asyncio.to_thread(
            audio_service.transcribe, audio_bytes, filename
        )

        # 3. Save raw transcript, advance to CLEANING
        await repo.update_fields(meeting_id, {"raw_transcript": raw_transcript})
        await repo.update_status(meeting_id, MeetingStatus.CLEANING)

        # 4. Clean transcript (synchronous, battle-tested from Phase 1)
        cleaned = transcript_service.clean(raw_transcript)

        # 5. Save cleaned transcript.
        #
        # Deliberately does NOT set status=PROCESSED here -- as of Phase 3,
        # a meeting isn't fully done until LLM extraction has also run.
        # This worker's job ends at "transcription + cleaning complete";
        # app/services/meeting_orchestrator.py is responsible for calling
        # run_extraction_pipeline next. Leaving status alone here (rather
        # than setting an intermediate value) is intentional: the
        # orchestrator immediately calls extraction_worker, which sets
        # status=ANALYZING as its own first step -- so there's no window
        # where an inaccurate status is visible to a polling client.
        await repo.update_fields(meeting_id, {"cleaned_transcript": cleaned})
        logger.info("Transcription pipeline complete for meeting_id=%s", meeting_id)

    except Exception as exc:  # noqa: BLE001
        # Always land in FAILED — never leave status=TRANSCRIBING indefinitely
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.error("Transcription pipeline failed for meeting_id=%s: %s", meeting_id, error_msg)
        await repo.update_status(meeting_id, MeetingStatus.FAILED, error_message=error_msg)
        # Re-raise so the orchestrator knows transcription failed and does
        # NOT proceed to call extraction on a meeting with no transcript.
        # BackgroundTasks doesn't surface this to any HTTP response (the
        # request already returned), so re-raising here is safe -- it only
        # affects the orchestrator's own control flow, not any client.
        raise
