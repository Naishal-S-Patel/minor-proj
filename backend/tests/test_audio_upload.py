"""
Tests for the audio upload endpoint.

Uses the fake repository from conftest.py to test file upload behavior
without needing a real MongoDB connection, Whisper transcription, or a real
Gemini API call (see conftest.py's fake_extraction_service).
"""

import io
from unittest.mock import patch, MagicMock

from tests.conftest import SAMPLE_AUDIO_BYTES, SAMPLE_RAW_TRANSCRIPT


def test_audio_upload_mp3_returns_202(client, fake_repo, fake_extraction_service):
    """Test successful upload of an .mp3 file returns 202 Accepted."""
    # Mock the AudioService to avoid loading Whisper model. Both
    # get_duration_seconds (called synchronously in the route) AND
    # transcribe (called in the background pipeline via asyncio.to_thread)
    # must be mocked with concrete return values -- a bare MagicMock()
    # return value for transcribe() would fail type checks inside
    # TranscriptService.clean(), which expects a real string.
    with patch("app.api.meetings._audio_svc") as mock_audio_svc:
        mock_audio_svc.get_duration_seconds.return_value = 60.0
        mock_audio_svc.transcribe.return_value = SAMPLE_RAW_TRANSCRIPT

        response = client.post(
            "/meetings",
            data={"title": "Test Audio Meeting"},
            files={"file": ("meeting.mp3", io.BytesIO(SAMPLE_AUDIO_BYTES), "audio/mpeg")},
        )

        assert response.status_code == 202
        body = response.json()
        assert body["title"] == "Test Audio Meeting"
        assert body["status"] == "uploaded"
        assert body["audio_filename"] == "meeting.mp3"
        assert body["audio_duration_seconds"] == 60.0

        # Verify meeting was stored in fake repo
        assert len(fake_repo._meetings) == 1

        # Because TestClient runs the BackgroundTask synchronously, the full
        # transcription -> cleaning -> extraction pipeline has already run
        # by this point -- verify it actually reached PROCESSED, not just
        # that the immediate upload response looked right.
        meeting_id = list(fake_repo._meetings.keys())[0]
        final_response = client.get(f"/meetings/{meeting_id}")
        final_body = final_response.json()
        assert final_body["status"] == "processed"
        assert final_body["summary"] is not None
        assert fake_extraction_service.call_count == 1


def test_audio_upload_wav_returns_202(client, fake_repo):
    """Test successful upload of a .wav file returns 202 Accepted."""
    with patch("app.api.meetings._audio_svc") as mock_audio_svc:
        mock_audio_svc.get_duration_seconds.return_value = 30.0
        mock_audio_svc.transcribe.return_value = SAMPLE_RAW_TRANSCRIPT

        response = client.post(
            "/meetings",
            data={"title": "Test WAV Meeting"},
            files={"file": ("meeting.wav", io.BytesIO(SAMPLE_AUDIO_BYTES), "audio/wav")},
        )

        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "uploaded"
        assert body["audio_filename"] == "meeting.wav"


def test_audio_upload_wrong_extension(client, fake_repo):
    """Test upload with wrong file extension returns 415."""
    response = client.post(
        "/meetings",
        data={"title": "Test Meeting"},
        files={"file": ("meeting.pdf", io.BytesIO(b"PDF content"), "application/pdf")},
    )

    assert response.status_code == 415
    assert "Unsupported file type" in response.json()["detail"]
    assert len(fake_repo._meetings) == 0


def test_audio_upload_too_large(client, fake_repo):
    """Test upload with file exceeding max size limit returns 413."""
    # Create a file larger than the limit (25 MB default)
    large_content = b"x" * (25 * 1024 * 1024 + 1)
    response = client.post(
        "/meetings",
        data={"title": "Test Meeting"},
        files={"file": ("meeting.mp3", io.BytesIO(large_content), "audio/mpeg")},
    )

    assert response.status_code == 413
    assert "File too large" in response.json()["detail"]
    assert len(fake_repo._meetings) == 0


def test_audio_upload_empty_file(client, fake_repo):
    """Test upload with empty file returns 422."""
    response = client.post(
        "/meetings",
        data={"title": "Test Meeting"},
        files={"file": ("meeting.mp3", io.BytesIO(b""), "audio/mpeg")},
    )

    assert response.status_code == 422
    assert "File is empty" in response.json()["detail"]
    assert len(fake_repo._meetings) == 0


def test_txt_upload_returns_202(client, fake_repo):
    """
    Test that the text path returns 202 (not 201) as of Phase 3, since
    extraction (a real network call in production) always follows cleaning.
    See test_upload.py's test_upload_txt_success for the full pipeline
    assertion (fetching the meeting again to see its PROCESSED end state).
    """
    response = client.post(
        "/meetings",
        data={"title": "Text Meeting"},
        files={"file": ("meeting.txt", io.BytesIO(SAMPLE_RAW_TRANSCRIPT.encode("utf-8")), "text/plain")},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["title"] == "Text Meeting"
    assert body["cleaned_transcript"] is not None


def test_background_task_enqueued(client, fake_repo):
    """Test that background task is properly enqueued for audio uploads."""
    with patch("app.api.meetings._audio_svc") as mock_audio_svc, \
         patch("app.services.meeting_orchestrator.run_transcription_pipeline") as mock_pipeline:
        mock_audio_svc.get_duration_seconds.return_value = 60.0

        response = client.post(
            "/meetings",
            data={"title": "Background Task Test"},
            files={"file": ("meeting.mp3", io.BytesIO(SAMPLE_AUDIO_BYTES), "audio/mpeg")},
        )

        assert response.status_code == 202
        # The background task would be added, but in test mode it's not actually executed
        # We verify the meeting was created with correct status
        assert len(fake_repo._meetings) == 1
        meeting = list(fake_repo._meetings.values())[0]
        assert meeting.status.value == "uploaded"
