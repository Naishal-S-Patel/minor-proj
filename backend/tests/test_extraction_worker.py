"""
Tests for the extraction worker pipeline.

Mirrors test_transcription_worker.py's structure: fake repository, fake
ExtractionService, no real DB or Gemini API calls.
"""

import pytest

from app.models.meeting import MeetingInDB, MeetingStatus
from app.services.llm.extraction_service import ExtractionFailedError
from app.services.llm.schemas import ExtractionResult, LLMActionItem
from app.workers.extraction_worker import run_extraction_pipeline
from tests.conftest import FakeMeetingRepository


SAMPLE_RESULT = ExtractionResult(
    summary="A productive discussion about the login module.",
    action_items=[LLMActionItem(person="Sarah", task="Finish frontend", deadline="Friday")],
    decisions=["Ship on Monday."],
    keywords=["login", "frontend"],
    sentiment="positive",
)


class FakeExtractionService:
    """Scriptable fake matching ExtractionService's public interface."""

    def __init__(self, result: ExtractionResult | None = None, exception: Exception | None = None) -> None:
        self._result = result
        self._exception = exception
        self.call_count = 0
        self.received_transcripts: list[str] = []

    async def extract(self, cleaned_transcript: str) -> ExtractionResult:
        self.call_count += 1
        self.received_transcripts.append(cleaned_transcript)
        if self._exception is not None:
            raise self._exception
        return self._result


@pytest.fixture
def fake_repo() -> FakeMeetingRepository:
    return FakeMeetingRepository()


def _seed_cleaning_stage_meeting(repo: FakeMeetingRepository, meeting_id: str) -> None:
    """
    Seeds a meeting in the state extraction_worker expects to receive it:
    already cleaned (status=CLEANING is the last status transcription_worker
    or the text upload route leaves it in -- see both files' docstrings on
    why extraction is responsible for advancing past that point).
    """
    repo.seed(
        MeetingInDB(
            id=meeting_id,
            title="Test Meeting",
            uploaded_by="test-user",
            status=MeetingStatus.CLEANING,
            cleaned_transcript="John: We need to finish the login module by Friday.",
        )
    )


@pytest.mark.asyncio
async def test_pipeline_happy_path(fake_repo):
    _seed_cleaning_stage_meeting(fake_repo, "meeting-1")
    extraction_service = FakeExtractionService(result=SAMPLE_RESULT)

    await run_extraction_pipeline(
        meeting_id="meeting-1",
        cleaned_transcript="John: We need to finish the login module by Friday.",
        repo=fake_repo,
        extraction_service=extraction_service,
    )

    updated = fake_repo._meetings["meeting-1"]
    assert updated.status == MeetingStatus.PROCESSED
    assert updated.summary == "A productive discussion about the login module."
    assert len(updated.action_items) == 1
    assert updated.action_items[0]["person"] == "Sarah"  # stored as dict, not ActionItem
    # extraction_worker.py assigns id/done at persist time (the LLM never
    # produces these -- see LLMActionItem vs ActionItem in schemas.py /
    # models/meeting.py) -- confirm that conversion actually happened.
    assert updated.action_items[0]["id"]  # non-empty string, a real uuid4 hex
    assert updated.action_items[0]["done"] is False
    assert updated.decisions == ["Ship on Monday."]
    assert updated.keywords == ["login", "frontend"]
    assert updated.sentiment == "positive"
    assert updated.error_message is None
    assert extraction_service.call_count == 1


@pytest.mark.asyncio
async def test_pipeline_extraction_failure(fake_repo):
    _seed_cleaning_stage_meeting(fake_repo, "meeting-2")
    extraction_service = FakeExtractionService(
        exception=ExtractionFailedError("LLM response could not be parsed after retry")
    )

    await run_extraction_pipeline(
        meeting_id="meeting-2",
        cleaned_transcript="John: We need to finish the login module by Friday.",
        repo=fake_repo,
        extraction_service=extraction_service,
    )

    updated = fake_repo._meetings["meeting-2"]
    assert updated.status == MeetingStatus.FAILED
    assert "could not be parsed" in updated.error_message


@pytest.mark.asyncio
async def test_pipeline_rejects_empty_transcript(fake_repo):
    """
    A meeting reaching this worker with an empty/whitespace-only
    cleaned_transcript (e.g. an audio file that was silence) should fail
    clearly rather than wasting an LLM call on nothing.
    """
    _seed_cleaning_stage_meeting(fake_repo, "meeting-3")
    extraction_service = FakeExtractionService(result=SAMPLE_RESULT)

    await run_extraction_pipeline(
        meeting_id="meeting-3",
        cleaned_transcript="   ",  # whitespace only
        repo=fake_repo,
        extraction_service=extraction_service,
    )

    updated = fake_repo._meetings["meeting-3"]
    assert updated.status == MeetingStatus.FAILED
    assert "empty" in updated.error_message.lower()
    # The LLM should never have been called for empty input -- confirms the
    # guard runs BEFORE extraction_service.extract(), not after a wasted call.
    assert extraction_service.call_count == 0


@pytest.mark.asyncio
async def test_pipeline_status_sequence(fake_repo):
    _seed_cleaning_stage_meeting(fake_repo, "meeting-4")
    extraction_service = FakeExtractionService(result=SAMPLE_RESULT)

    status_updates = []
    original_update_status = fake_repo.update_status
    original_update_fields = fake_repo.update_fields

    async def tracking_update_status(meeting_id, status, error_message=None):
        status_updates.append(("status", status))
        return await original_update_status(meeting_id, status, error_message)

    async def tracking_update_fields(meeting_id, fields):
        if "status" in fields:
            status_updates.append(("fields", MeetingStatus(fields["status"])))
        return await original_update_fields(meeting_id, fields)

    fake_repo.update_status = tracking_update_status
    fake_repo.update_fields = tracking_update_fields

    await run_extraction_pipeline(
        meeting_id="meeting-4",
        cleaned_transcript="John: We need to finish the login module by Friday.",
        repo=fake_repo,
        extraction_service=extraction_service,
    )

    assert status_updates == [
        ("status", MeetingStatus.ANALYZING),
        ("fields", MeetingStatus.PROCESSED),
    ]
