"""
Transcription background worker.

Drives the meeting through:
    UPLOADED → TRANSCRIBING → CLEANING → PROCESSED
                                   ↘ FAILED (on any error)

Supports real-time line-by-line streaming progress to DB and multi-language transcription.
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
    language: str | None = None,
) -> None:
    """Full transcription pipeline with progressive line-by-line updates."""
    try:
        # 1. Mark as transcribing (UI shows "Transcribing…")
        await repo.update_status(meeting_id, MeetingStatus.TRANSCRIBING)

        loop = asyncio.get_running_loop()

        def handle_segment(new_line: str, all_lines: list[str]) -> None:
            """Pushes each recognized dialogue line to the database in real-time."""
            try:
                asyncio.run_coroutine_threadsafe(
                    repo.update_fields(
                        meeting_id,
                        {
                            "live_transcript_lines": list(all_lines),
                        },
                    ),
                    loop,
                )
            except Exception as exc:
                logger.debug("Failed to dispatch live transcript update: %s", exc)

        # 2. Progressive transcription on worker thread
        result = await asyncio.to_thread(
            audio_service.transcribe,
            audio_bytes,
            filename,
            language,
            handle_segment,
        )

        if isinstance(result, tuple):
            raw_transcript, detected_lang = result
        else:
            raw_transcript, detected_lang = result, None

        # 3. Save raw transcript & language, advance to CLEANING
        update_dict: dict = {
            "raw_transcript": raw_transcript,
            "live_transcript_lines": [l for l in raw_transcript.split("\n") if l.strip()],
        }
        if detected_lang:
            update_dict["detected_language"] = detected_lang

        await repo.update_fields(meeting_id, update_dict)
        await repo.update_status(meeting_id, MeetingStatus.CLEANING)

        # 4. Clean transcript
        cleaned = transcript_service.clean(raw_transcript)

        # 5. Save cleaned transcript
        await repo.update_fields(meeting_id, {"cleaned_transcript": cleaned})
        logger.info("Transcription pipeline complete for meeting_id=%s", meeting_id)

    except Exception as exc:  # noqa: BLE001
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.error("Transcription pipeline failed for meeting_id=%s: %s", meeting_id, error_msg)
        await repo.update_status(meeting_id, MeetingStatus.FAILED, error_message=error_msg)
        raise
