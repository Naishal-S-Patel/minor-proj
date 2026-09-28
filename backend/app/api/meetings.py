"""
Meetings API router.

Phase 3 scope: list/get endpoints plus upload endpoint for .txt and audio
files. Both upload paths now return 202 (not 201) because BOTH end with an
LLM extraction call (a network request to Gemini, taking real wall-clock
time) -- there is no longer a fully-synchronous path that can return a
finished, PROCESSED meeting immediately. See meeting_orchestrator.py for
how each upload type's pipeline is sequenced.
"""

import logging
import os

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.dependencies import get_meeting_repository
from app.core.config import settings
from app.core.security import get_current_user
from app.models.meeting import MeetingInDB, MeetingPublic, MeetingSearchResult, MeetingStatus
from app.repositories.meeting_repository import MeetingRepository
from app.services.audio_service import AudioService
from app.services.file_validation_service import FileValidationService
from app.services.llm.extraction_service import ExtractionService
from app.services.meeting_orchestrator import run_audio_pipeline, run_text_pipeline
from app.services.transcript_service import TranscriptService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/meetings", tags=["meetings"])

# Service instances (stateless, no I/O -- or in ExtractionService's case,
# I/O happens per-call, not at construction time, same as AudioService's
# lazy-loaded Whisper model).
_file_validation_svc = FileValidationService()
_transcript_svc = TranscriptService()
_audio_svc = AudioService()
_extraction_svc = ExtractionService() if not settings.testing else None  # type: ignore[assignment]

# Allowed audio extensions for quick lookup
AUDIO_EXTENSIONS = {".mp3", ".mp4", ".wav", ".m4a", ".m4v"}


@router.get("", response_model=list[MeetingPublic])
async def list_meetings(
    current_user: dict = Depends(get_current_user),
    repo: MeetingRepository = Depends(get_meeting_repository),
) -> list[MeetingPublic]:
    """Returns the current user's meetings, most recent first."""
    meetings = await repo.list_by_user(uploaded_by=current_user["sub"])
    return [MeetingPublic.from_db_model(m) for m in meetings]


@router.get("/search", response_model=list[MeetingSearchResult])
async def search_meetings(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(20, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
    repo: MeetingRepository = Depends(get_meeting_repository),
) -> list[MeetingSearchResult]:
    """Searches the current user's meetings by text content."""
    results = await repo.text_search(user_id=current_user["sub"], query=q, limit=limit)
    return results


@router.get("/{meeting_id}", response_model=MeetingPublic)
async def get_meeting(
    meeting_id: str,
    current_user: dict = Depends(get_current_user),
    repo: MeetingRepository = Depends(get_meeting_repository),
) -> MeetingPublic:
    """Returns a single meeting by id, or 404 if it doesn't exist."""
    meeting = await repo.get_by_id(meeting_id)
    if meeting is None:
        logger.info("Meeting not found: id=%s", meeting_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting {meeting_id} not found",
        )
    if meeting.uploaded_by != current_user["sub"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this meeting",
        )
    return MeetingPublic.from_db_model(meeting)


class ActionItemUpdate(BaseModel):
    """Request body for toggling an action item's completion state."""

    done: bool


@router.patch("/{meeting_id}/action-items/{item_id}", response_model=MeetingPublic)
async def update_action_item(
    meeting_id: str,
    item_id: str,
    body: ActionItemUpdate,
    current_user: dict = Depends(get_current_user),
    repo: MeetingRepository = Depends(get_meeting_repository),
) -> MeetingPublic:
    """
    Toggles a single action item's completion state (done/not done).

    Ownership is checked BEFORE the toggle, via the same fetch-then-compare
    pattern as get_meeting above -- deliberately not folded into the
    repository's set_action_item_done query (e.g. filtering by uploaded_by
    there too) so that "meeting exists but isn't yours" (403) stays
    distinguishable from "meeting/item genuinely doesn't exist" (404)
    at the HTTP layer, matching how every other route in this file
    reports ownership failures.

    Returns the FULL updated meeting (not just the toggled item) so the
    frontend can replace its entire cached copy in one response, rather
    than needing a separate re-fetch after every toggle.
    """
    meeting = await repo.get_by_id(meeting_id)
    if meeting is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting {meeting_id} not found",
        )
    if meeting.uploaded_by != current_user["sub"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this meeting",
        )

    updated = await repo.set_action_item_done(meeting_id, item_id, body.done)
    if not updated:
        # The meeting itself exists (checked above) but no action item on
        # it has this item_id -- a 404 here specifically means "that item
        # id", not "that meeting", which is why this check happens after
        # the meeting-level 404/403 checks, not folded into one generic
        # "not found" branch.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action item {item_id} not found on this meeting",
        )

    # Re-fetch to return the full, current state of the meeting rather than
    # reconstructing it in Python from the pre-update `meeting` + the known
    # change -- re-fetching is the source of truth and avoids any risk of
    # the returned object silently drifting from what's actually in the DB.
    refreshed = await repo.get_by_id(meeting_id)
    return MeetingPublic.from_db_model(refreshed)


@router.post("")
async def create_meeting(
    title: str = Form(..., min_length=1, max_length=200),
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,  # type: ignore[assignment]  # FastAPI injects the real instance
    current_user: dict = Depends(get_current_user),
    repo: MeetingRepository = Depends(get_meeting_repository),
) -> JSONResponse:
    """
    Upload a .txt transcript or audio file to create a new meeting.
    - .txt  -> cleaning runs synchronously, returns 202 with status=cleaning;
              LLM extraction then runs in the background
    - audio -> saves file, returns 202 with status=uploaded; transcription
              then LLM extraction both run in the background

    Both paths converge on the same eventual outcome: poll GET
    /meetings/{id} until status is "processed" (fully done) or "failed".
    """
    ext = os.path.splitext(file.filename or "")[1].lower()

    if ext == ".txt":
        # Text path: cleaning is synchronous (fast, pure-regex work -- see
        # TranscriptService), but as of Phase 3 the pipeline isn't done
        # until LLM extraction also runs, and that's a real network call
        # to Gemini that can take several seconds. So the meeting is
        # created with status=CLEANING already satisfied (cleaned_transcript
        # is set immediately) but extraction is scheduled as a background
        # task -- same non-blocking-response principle Phase 2 already
        # established for audio, now applied here too.
        raw_text = await _file_validation_svc.validate_and_read_text(file)
        cleaned_text = _transcript_svc.clean(raw_text)

        meeting = MeetingInDB(
            id="",  # assigned by MongoDB on insert
            title=title,
            uploaded_by=current_user["sub"],
            status=MeetingStatus.CLEANING,
            raw_transcript=raw_text,
            cleaned_transcript=cleaned_text,
        )
        created = await repo.create(meeting)

        background_tasks.add_task(
            run_text_pipeline,
            meeting_id=created.id,
            cleaned_transcript=cleaned_text,
            repo=repo,
            extraction_service=_extraction_svc,
        )

        return JSONResponse(
            content=MeetingPublic.from_db_model(created).model_dump(mode="json"),
            status_code=status.HTTP_202_ACCEPTED,
        )

    elif ext in AUDIO_EXTENSIONS:
        # Audio path — asynchronous processing throughout: transcription
        # (Phase 2) followed by LLM extraction (Phase 3), both chained via
        # run_audio_pipeline in meeting_orchestrator.py.
        audio_bytes = await _file_validation_svc.validate_audio(
            file, max_size_mb=settings.audio_max_size_mb
        )

        # Check audio duration
        try:
            duration = _audio_svc.get_duration_seconds(audio_bytes, file.filename)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        if duration > settings.audio_max_duration_seconds:
            raise HTTPException(
                status_code=413,
                detail=f"Audio too long. Maximum: {settings.audio_max_duration_seconds // 3600} hours",
            )

        # Create meeting with uploaded status
        meeting = MeetingInDB(
            id="",  # assigned by MongoDB on insert
            title=title,
            uploaded_by=current_user["sub"],
            status=MeetingStatus.UPLOADED,
            audio_filename=file.filename,
            audio_duration_seconds=duration,
        )
        created = await repo.create(meeting)

        # Add background pipeline task: transcription, then (on success)
        # extraction -- see meeting_orchestrator.run_audio_pipeline for the
        # sequencing logic.
        background_tasks.add_task(
            run_audio_pipeline,
            meeting_id=created.id,
            audio_bytes=audio_bytes,
            filename=file.filename,
            repo=repo,
            audio_service=_audio_svc,
            transcript_service=_transcript_svc,
            extraction_service=_extraction_svc,
        )

        return JSONResponse(
            content=MeetingPublic.from_db_model(created).model_dump(mode="json"),
            status_code=status.HTTP_202_ACCEPTED,
        )
    else:
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Upload a .txt or .mp3/.mp4/.wav/.m4a file.",
        )
