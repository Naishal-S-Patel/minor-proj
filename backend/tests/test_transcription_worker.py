"""
Tests for the transcription worker pipeline.

Tests the background worker with fake AudioService and fake repository.
No real Whisper calls are made.

As of Phase 3, this worker no longer sets status=PROCESSED itself -- it
hands off to the extraction stage (see meeting_orchestrator.py), so its own
responsibility ends once cleaned_transcript is saved. These tests were
updated accordingly; test_meeting_orchestrator.py covers the full chained
sequence (transcription -> extraction) that ends in PROCESSED.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models.meeting import MeetingInDB, MeetingStatus
from app.workers.transcription_worker import run_transcription_pipeline


@pytest.fixture
def fake_repo():
    """Create a fake repository for worker tests."""
    from tests.conftest import FakeMeetingRepository
    return FakeMeetingRepository()


@pytest.fixture
def mock_audio_service():
    """Create a mock AudioService."""
    mock = MagicMock()
    mock.transcribe.return_value = "Hello, this is the transcribed text."
    return mock


@pytest.fixture
def mock_transcript_service():
    """Create a mock TranscriptService."""
    mock = MagicMock()
    mock.clean.return_value = "Hello, this is the transcribed text."
    return mock


@pytest.mark.asyncio
async def test_pipeline_happy_path(fake_repo, mock_audio_service, mock_transcript_service):
    """Test the full pipeline completes successfully."""
    # Seed a meeting with uploaded status
    meeting = MeetingInDB(
        id="test-meeting-1",
        title="Test Meeting",
        uploaded_by="test-user",
        status=MeetingStatus.UPLOADED,
    )
    fake_repo.seed(meeting)

    # Run the pipeline
    await run_transcription_pipeline(
        meeting_id="test-meeting-1",
        audio_bytes=b"fake audio data",
        filename="test.mp3",
        repo=fake_repo,
        audio_service=mock_audio_service,
        transcript_service=mock_transcript_service,
    )

    # Verify final state. Status stays at CLEANING (its last explicit
    # update) -- this worker's job ends once cleaned_transcript is saved;
    # advancing to ANALYZING/PROCESSED is the extraction stage's
    # responsibility (see meeting_orchestrator.py).
    updated_meeting = fake_repo._meetings["test-meeting-1"]
    assert updated_meeting.status == MeetingStatus.CLEANING
    assert updated_meeting.raw_transcript == "Hello, this is the transcribed text."
    assert updated_meeting.cleaned_transcript == "Hello, this is the transcribed text."
    assert updated_meeting.error_message is None


@pytest.mark.asyncio
async def test_pipeline_whisper_failure(fake_repo, mock_transcript_service):
    """Test pipeline handles Whisper transcription failure."""
    from unittest.mock import MagicMock

    # Create audio service that raises an exception
    failing_audio_service = MagicMock()
    failing_audio_service.transcribe.side_effect = RuntimeError("Whisper model not found")

    # Seed a meeting
    meeting = MeetingInDB(
        id="test-meeting-2",
        title="Test Meeting",
        uploaded_by="test-user",
        status=MeetingStatus.UPLOADED,
    )
    fake_repo.seed(meeting)

    # Run the pipeline. As of Phase 3, the worker re-raises the original
    # exception after persisting FAILED status (see its own docstring on
    # why: this lets meeting_orchestrator.py know transcription failed, so
    # it doesn't proceed to call extraction on a meeting with no
    # transcript). pytest.raises confirms that re-raise happens; the DB
    # assertions afterward confirm FAILED was persisted BEFORE the raise.
    with pytest.raises(RuntimeError, match="Whisper model not found"):
        await run_transcription_pipeline(
            meeting_id="test-meeting-2",
            audio_bytes=b"fake audio data",
            filename="test.mp3",
            repo=fake_repo,
            audio_service=failing_audio_service,
            transcript_service=mock_transcript_service,
        )

    # Verify failure state
    updated_meeting = fake_repo._meetings["test-meeting-2"]
    assert updated_meeting.status == MeetingStatus.FAILED
    assert "RuntimeError" in updated_meeting.error_message
    assert "Whisper model not found" in updated_meeting.error_message


@pytest.mark.asyncio
async def test_pipeline_cleaning_failure(fake_repo, mock_audio_service):
    """Test pipeline handles transcript cleaning failure."""
    from unittest.mock import MagicMock

    # Create transcript service that raises an exception
    failing_transcript_service = MagicMock()
    failing_transcript_service.clean.side_effect = ValueError("Cleaning failed")

    # Seed a meeting
    meeting = MeetingInDB(
        id="test-meeting-3",
        title="Test Meeting",
        uploaded_by="test-user",
        status=MeetingStatus.UPLOADED,
    )
    fake_repo.seed(meeting)

    # Run the pipeline (see test_pipeline_whisper_failure above for why
    # pytest.raises is needed here as of Phase 3).
    with pytest.raises(ValueError, match="Cleaning failed"):
        await run_transcription_pipeline(
            meeting_id="test-meeting-3",
            audio_bytes=b"fake audio data",
            filename="test.mp3",
            repo=fake_repo,
            audio_service=mock_audio_service,
            transcript_service=failing_transcript_service,
        )

    # Verify failure state
    updated_meeting = fake_repo._meetings["test-meeting-3"]
    assert updated_meeting.status == MeetingStatus.FAILED
    assert "ValueError" in updated_meeting.error_message
    assert "Cleaning failed" in updated_meeting.error_message


@pytest.mark.asyncio
async def test_pipeline_status_sequence(fake_repo, mock_audio_service, mock_transcript_service):
    """Test that status updates happen in the correct order."""
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

    # Seed a meeting
    meeting = MeetingInDB(
        id="test-meeting-4",
        title="Test Meeting",
        uploaded_by="test-user",
        status=MeetingStatus.UPLOADED,
    )
    fake_repo.seed(meeting)

    # Run the pipeline
    await run_transcription_pipeline(
        meeting_id="test-meeting-4",
        audio_bytes=b"fake audio data",
        filename="test.mp3",
        repo=fake_repo,
        audio_service=mock_audio_service,
        transcript_service=mock_transcript_service,
    )

    # Verify status sequence. No third entry: this worker no longer sets
    # status=PROCESSED itself as of Phase 3 (see module docstring above).
    assert status_updates == [
        ("status", MeetingStatus.TRANSCRIBING),
        ("status", MeetingStatus.CLEANING),
    ]
