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

from datetime import datetime, timedelta, timezone
import logging
import uuid

from app.models.meeting import ActionItem, CalendarEvent, DialogueTurn, MeetingStatus
from app.repositories.meeting_repository import MeetingRepository
from app.services.llm.extraction_service import ExtractionFailedError, ExtractionService
from app.services.speaker_identity import detect_platform

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

        # 2. Call the LLM extraction service with meeting platform & title context
        meeting = await repo.get_by_id(meeting_id)
        meeting_title = meeting.title if meeting else ""
        meeting_platform = detect_platform(
            meeting.platform if meeting else None,
            None,
            meeting_title,
            cleaned_transcript,
        ) or (meeting.platform if meeting else "") or ""

        result = await extraction_service.extract(
            cleaned_transcript,
            meeting_title=meeting_title,
            platform=meeting_platform,
        )

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

        now = datetime.now(timezone.utc)
        calendar_events = []
        for ev in result.calendar_events:
            target_dt = None
            if getattr(ev, "event_date", None):
                try:
                    target_dt = datetime.fromisoformat(ev.event_date)
                    if target_dt.tzinfo is None:
                        target_dt = target_dt.replace(tzinfo=timezone.utc)
                    days = max(0, (target_dt.date() - now.date()).days)
                except Exception:
                    target_dt = None

            if target_dt is None:
                # Try parsing explicit date from relative_time or title (e.g. "30th November", "30 नवंबर", "25 Nov")
                months_map = {
                    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
                    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
                    "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
                    "nov": 11, "november": 11, "dec": 12, "december": 12,
                    "जनवरी": 1, "फ़रवरी": 2, "फरवरी": 2, "मार्च": 3, "अप्रैल": 4, "मई": 5, "जून": 6,
                    "जुलाई": 7, "अगस्त": 8, "सितंबर": 9, "सितम्बर": 9, "अक्टूबर": 10, "अक्तूबर": 10,
                    "नवंबर": 11, "नवम्बर": 11, "दिसंबर": 12, "दिसम्बर": 12,
                }
                date_match = re.search(
                    r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([A-Za-z\u0900-\u097F]+)",
                    f"{ev.relative_time} {ev.title}",
                    re.IGNORECASE,
                ) or re.search(
                    r"([A-Za-z\u0900-\u097F]+)\s+(\d{1,2})(?:st|nd|rd|th)?",
                    f"{ev.relative_time} {ev.title}",
                    re.IGNORECASE,
                )
                if date_match:
                    g1, g2 = date_match.group(1), date_match.group(2)
                    day, mon_str = (int(g1), g2.lower()) if g1.isdigit() else (int(g2), g1.lower())
                    if mon_str in months_map and 1 <= day <= 31:
                        m_num = months_map[mon_str]
                        target_dt = datetime(now.year, m_num, day, tzinfo=timezone.utc)
                        if target_dt < now - timedelta(days=60):
                            target_dt = target_dt.replace(year=now.year + 1)
                        days = max(0, (target_dt.date() - now.date()).days)

            if target_dt is None:
                days = ev.days_from_now if ev.days_from_now is not None else 3
                target_dt = now + timedelta(days=days)

            title = ev.title
            if title.strip().lower() in ("l exam", "l test", "एल का एक्जाम", "एल एक्जाम"):
                title = "Machine Learning (ML) Exam"

            calendar_events.append(
                CalendarEvent(
                    id=uuid.uuid4().hex[:8],
                    title=title,
                    relative_time=ev.relative_time,
                    event_date=target_dt.strftime("%Y-%m-%d"),
                    formatted_date=target_dt.strftime("%A, %b %d, %Y"),
                    days_from_now=days,
                    speaker=ev.speaker,
                    context=ev.context,
                    category=ev.category,
                )
            )

        dialogue_turns = [
            DialogueTurn(
                speaker=turn.speaker,
                speaker_id=turn.speaker_id,
                time=turn.time,
                text=turn.text,
            )
            for turn in result.dialogue_turns
        ]

        await repo.update_fields(
            meeting_id,
            {
                "summary": result.summary,
                "action_items": [item.model_dump() for item in action_items],
                "decisions": result.decisions,
                "keywords": result.keywords,
                "sentiment": result.sentiment,
                "speakers": result.speakers,
                "speaker_map": result.speaker_map,
                "platform": meeting_platform,
                "calendar_events": [e.model_dump() for e in calendar_events],
                "dialogue_turns": [d.model_dump() for d in dialogue_turns],
                "detected_language": result.detected_language,
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
