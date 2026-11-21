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
import re

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
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
from app.services.speaker_identity import detect_platform, parse_participants, roster_header
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


class SpeakerMapUpdate(BaseModel):
    """Request body for mapping Person IDs / Speaker IDs to Speaker Names."""

    speaker_map: dict[str, str]


@router.patch("/{meeting_id}/speakers", response_model=MeetingPublic)
async def update_speaker_map(
    meeting_id: str,
    body: SpeakerMapUpdate,
    current_user: dict = Depends(get_current_user),
    repo: MeetingRepository = Depends(get_meeting_repository),
) -> MeetingPublic:
    """
    Maps Person IDs / Speaker IDs (e.g. 'P01', 'USR-101', 'Speaker 1') to
    real Speaker Names across dialogue turns, action items, calendar events, and speakers.
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

    cleaned_map = {
        k.strip(): v.strip()
        for k, v in body.speaker_map.items()
        if k.strip() and v.strip()
    }
    merged_map = {**meeting.speaker_map, **cleaned_map}

    # Remap dialogue turns
    updated_turns = []
    for turn in meeting.dialogue_turns:
        turn_dict = turn.model_dump()
        key = turn.speaker_id or turn.speaker
        if key in merged_map:
            if not turn_dict.get("speaker_id"):
                turn_dict["speaker_id"] = key
            turn_dict["speaker"] = merged_map[key]
        elif turn.speaker in merged_map:
            turn_dict["speaker"] = merged_map[turn.speaker]
        updated_turns.append(turn_dict)

    # Remap action items
    updated_actions = []
    for item in meeting.action_items:
        item_dict = item.model_dump()
        if item.person in merged_map:
            item_dict["person"] = merged_map[item.person]
        updated_actions.append(item_dict)

    # Remap calendar events
    updated_events = []
    for ev in meeting.calendar_events:
        ev_dict = ev.model_dump()
        if ev.speaker and ev.speaker in merged_map:
            ev_dict["speaker"] = merged_map[ev.speaker]
        updated_events.append(ev_dict)

    # Rebuild unique speakers list
    updated_speakers = list(dict.fromkeys(
        [t["speaker"] for t in updated_turns]
        + [merged_map.get(s, s) for s in meeting.speakers]
    ))

    await repo.update_fields(
        meeting_id,
        {
            "speaker_map": merged_map,
            "speakers": updated_speakers,
            "dialogue_turns": updated_turns,
            "action_items": updated_actions,
            "calendar_events": updated_events,
        },
    )

    refreshed = await repo.get_by_id(meeting_id)
    return MeetingPublic.from_db_model(refreshed)


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
    meeting_id_code: str | None = Form(None),
    platform: str | None = Form(None),
    language: str | None = Form("auto"),
    participants: str | None = Form(None, max_length=2000),
    background_tasks: BackgroundTasks = None,  # type: ignore[assignment]
    current_user: dict = Depends(get_current_user),
    repo: MeetingRepository = Depends(get_meeting_repository),
) -> JSONResponse:
    """
    Upload a .txt / .vtt transcript or audio file to create a new meeting.
    Supports meeting ID (e.g. Zoom / Meet ID), platform selection, English /
    Hindi / Hinglish transcription, and an optional participant roster
    ("USR-101: Ramesha", "P02 = Naishal", or "Ramesha, Naishal" in speaking
    order) used to put real names on Zoom / Google Meet speaker tags.
    """
    ext = os.path.splitext(file.filename or "")[1].lower()

    # Clean inputs
    cleaned_meeting_code = meeting_id_code.strip() if meeting_id_code and meeting_id_code.strip() else None
    detected_platform = platform.strip() if platform and platform.strip() else None
    chosen_lang = language.strip() if language and language.strip() else "auto"
    roster_text = participants.strip() if participants and participants.strip() else None

    if ext in (".txt", ".vtt"):
        raw_text = await _file_validation_svc.validate_and_read_text(file)
        cleaned_text = _transcript_svc.clean(raw_text)

        # Auto-detect Zoom Meeting ID if not entered
        if not cleaned_meeting_code:
            zoom_match = re.search(r"(?:Meeting ID|Zoom ID|Session ID)[:\s]+([\d\s\-]{8,15})", raw_text, re.IGNORECASE)
            if zoom_match:
                cleaned_meeting_code = zoom_match.group(1).strip()
                if not detected_platform:
                    detected_platform = "Zoom"

        if not detected_platform:
            detected_platform = detect_platform(None, file.filename, title, raw_text)

        # A roster typed at upload is prepended as "Participants:" header lines,
        # which both the local extractor and the LLM prompt already map onto
        # the transcript's speaker tags.
        roster = parse_participants(roster_text)
        if roster:
            header = roster_header(roster, detected_platform, cleaned_text)
            cleaned_text = f"{header}\n\n{cleaned_text}"

        meeting = MeetingInDB(
            id="",
            title=title,
            uploaded_by=current_user["sub"],
            status=MeetingStatus.CLEANING,
            meeting_id_code=cleaned_meeting_code,
            platform=detected_platform or "Meeting",
            language=chosen_lang,
            raw_transcript=raw_text,
            cleaned_transcript=cleaned_text,
        )
        created = await repo.create(meeting)

        extraction_service = _extraction_svc or ExtractionService()
        background_tasks.add_task(
            run_text_pipeline,
            meeting_id=created.id,
            cleaned_transcript=cleaned_text,
            repo=repo,
            extraction_service=extraction_service,
        )

        return JSONResponse(
            content=MeetingPublic.from_db_model(created).model_dump(mode="json"),
            status_code=status.HTTP_202_ACCEPTED,
        )

    elif ext in AUDIO_EXTENSIONS:
        audio_bytes = await _file_validation_svc.validate_audio(
            file, max_size_mb=settings.audio_max_size_mb
        )

        try:
            duration = _audio_svc.get_duration_seconds(audio_bytes, file.filename)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        if duration > settings.audio_max_duration_seconds:
            raise HTTPException(
                status_code=413,
                detail=f"Audio too long. Maximum: {settings.audio_max_duration_seconds // 3600} hours",
            )

        if not detected_platform:
            detected_platform = detect_platform(None, file.filename, title)

        meeting = MeetingInDB(
            id="",
            title=title,
            uploaded_by=current_user["sub"],
            status=MeetingStatus.UPLOADED,
            meeting_id_code=cleaned_meeting_code,
            platform=detected_platform or "Audio Recording",
            language=chosen_lang,
            audio_filename=file.filename,
            audio_duration_seconds=duration,
        )
        created = await repo.create(meeting)

        extraction_service = _extraction_svc or ExtractionService()
        background_tasks.add_task(
            run_audio_pipeline,
            meeting_id=created.id,
            audio_bytes=audio_bytes,
            filename=file.filename,
            repo=repo,
            audio_service=_audio_svc,
            transcript_service=_transcript_svc,
            extraction_service=extraction_service,
            language=chosen_lang,
            participants=roster_text,
        )

        return JSONResponse(
            content=MeetingPublic.from_db_model(created).model_dump(mode="json"),
            status_code=status.HTTP_202_ACCEPTED,
        )
    else:
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Upload a .txt, .vtt, or .mp3/.mp4/.wav/.m4a file.",
        )


@router.get("/{meeting_id}/calendar/ics")
async def download_calendar_ics(
    meeting_id: str,
    current_user: dict = Depends(get_current_user),
    repo: MeetingRepository = Depends(get_meeting_repository),
) -> Response:
    """Exports all calendar events from this meeting as an iCal (.ics) file."""
    meeting = await repo.get_by_id(meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if meeting.uploaded_by != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    events = meeting.calendar_events
    if not events:
        raise HTTPException(status_code=400, detail="No calendar events found for this meeting")

    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//AI Meeting Intelligence//Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for ev in events:
        dt_clean = ev.event_date.replace("-", "")
        ics_lines.extend([
            "BEGIN:VEVENT",
            f"UID:{ev.id}@{meeting_id}.meetingai",
            f"DTSTAMP:{dt_clean}T090000Z",
            f"DTSTART;VALUE=DATE:{dt_clean}",
            f"DTEND;VALUE=DATE:{dt_clean}",
            f"SUMMARY:{ev.title} ({meeting.title})",
            f"DESCRIPTION:Context: {ev.context}\\nAnnounced by: {ev.speaker or 'Meeting Participant'}",
            "STATUS:CONFIRMED",
            "END:VEVENT",
        ])

    ics_lines.append("END:VCALENDAR")
    ics_content = "\r\n".join(ics_lines)

    filename = f"{re.sub(r'[^a-zA-Z0-9_-]', '_', meeting.title)}_schedule.ics"
    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
