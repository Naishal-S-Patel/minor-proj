"""
Tests for meeting_orchestrator.py -- the sequencing logic that chains
transcription -> extraction (audio) and cleaning -> extraction (text).

Uses fake AudioService/TranscriptService/ExtractionService throughout, so
no real Whisper model load or Gemini API call happens.
"""

import pytest

from app.models.meeting import MeetingInDB, MeetingStatus
from app.services.llm.schemas import ExtractionResult, LLMActionItem
from app.services.meeting_orchestrator import run_audio_pipeline, run_text_pipeline
from tests.conftest import FakeMeetingRepository


SAMPLE_RESULT = ExtractionResult(
    summary="Summary.",
    action_items=[LLMActionItem(person="Sarah", task="Do the thing")],
    decisions=["Decided something."],
    keywords=["topic"],
    sentiment="neutral",
)


class FakeAudioService:
    def __init__(self, transcript: str = "raw transcript text", exception: Exception | None = None) -> None:
        self._transcript = transcript
        self._exception = exception

    def transcribe(self, audio_bytes: bytes, filename: str) -> str:
        if self._exception is not None:
            raise self._exception
        return self._transcript


class FakeTranscriptService:
    def clean(self, raw_text: str) -> str:
        return f"cleaned: {raw_text}"


class FakeExtractionService:
    def __init__(self, result: ExtractionResult | None = None) -> None:
        self._result = result or SAMPLE_RESULT
        self.call_count = 0
        self.received_transcripts: list[str] = []

    async def extract(self, cleaned_transcript: str) -> ExtractionResult:
        self.call_count += 1
        self.received_transcripts.append(cleaned_transcript)
        return self._result


@pytest.fixture
def fake_repo() -> FakeMeetingRepository:
    return FakeMeetingRepository()


@pytest.mark.asyncio
async def test_audio_pipeline_full_success_chain(fake_repo):
    """
    Confirms the whole chain runs: transcription saves a cleaned transcript,
    then extraction runs on THAT transcript and lands the meeting on
    PROCESSED with all extracted fields populated.
    """
    fake_repo.seed(
        MeetingInDB(
            id="meeting-1",
            title="Standup",
            uploaded_by="test-user",
            status=MeetingStatus.UPLOADED,
        )
    )
    extraction_service = FakeExtractionService()

    await run_audio_pipeline(
        meeting_id="meeting-1",
        audio_bytes=b"fake audio",
        filename="standup.mp3",
        repo=fake_repo,
        audio_service=FakeAudioService(transcript="John: hello"),
        transcript_service=FakeTranscriptService(),
        extraction_service=extraction_service,
    )

    updated = fake_repo._meetings["meeting-1"]
    assert updated.status == MeetingStatus.PROCESSED
    assert updated.raw_transcript == "John: hello"
    assert updated.cleaned_transcript == "cleaned: John: hello"
    assert updated.summary == "Summary."
    assert updated.decisions == ["Decided something."]

    # Confirms extraction received the CLEANED transcript, not the raw one
    # -- i.e. the orchestrator correctly passed transcription's output
    # forward as extraction's input.
    assert extraction_service.received_transcripts == ["cleaned: John: hello"]


@pytest.mark.asyncio
async def test_audio_pipeline_stops_after_transcription_failure(fake_repo):
    """
    If transcription fails, extraction must NEVER be called -- there's no
    transcript to extract from, and calling the LLM anyway would waste a
    request and produce a nonsensical result.
    """
    fake_repo.seed(
        MeetingInDB(
            id="meeting-2",
            title="Standup",
            uploaded_by="test-user",
            status=MeetingStatus.UPLOADED,
        )
    )
    extraction_service = FakeExtractionService()

    await run_audio_pipeline(
        meeting_id="meeting-2",
        audio_bytes=b"fake audio",
        filename="standup.mp3",
        repo=fake_repo,
        audio_service=FakeAudioService(exception=RuntimeError("Whisper crashed")),
        transcript_service=FakeTranscriptService(),
        extraction_service=extraction_service,
    )

    updated = fake_repo._meetings["meeting-2"]
    assert updated.status == MeetingStatus.FAILED
    assert "Whisper crashed" in updated.error_message
    assert extraction_service.call_count == 0  # the key assertion


@pytest.mark.asyncio
async def test_text_pipeline_calls_extraction_directly(fake_repo):
    """
    Text uploads skip transcription entirely (cleaning already happened
    synchronously in the route) -- run_text_pipeline should go straight to
    extraction.
    """
    fake_repo.seed(
        MeetingInDB(
            id="meeting-3",
            title="Notes",
            uploaded_by="test-user",
            status=MeetingStatus.CLEANING,
            cleaned_transcript="Already cleaned text.",
        )
    )
    extraction_service = FakeExtractionService()

    await run_text_pipeline(
        meeting_id="meeting-3",
        cleaned_transcript="Already cleaned text.",
        repo=fake_repo,
        extraction_service=extraction_service,
    )

    updated = fake_repo._meetings["meeting-3"]
    assert updated.status == MeetingStatus.PROCESSED
    assert extraction_service.received_transcripts == ["Already cleaned text."]
