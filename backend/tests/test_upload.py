"""
Tests for the upload endpoint.

Uses the fake repository from conftest.py to test file upload behavior
without needing a real MongoDB connection. Also relies on the `client`
fixture's fake_extraction_service swap (see conftest.py) so these tests
never make a real Gemini API call -- Starlette's TestClient runs
BackgroundTasks synchronously as part of handling the request, so by the
time client.post() returns, the full pipeline (including LLM extraction)
has already run against the fake.
"""

import io

from tests.conftest import SAMPLE_RAW_TRANSCRIPT


def test_upload_txt_success(client, fake_repo, fake_extraction_service):
    """
    Test successful upload of a .txt file, end to end through the full
    pipeline (cleaning -> extraction), since TestClient runs the
    BackgroundTask synchronously before returning a response.
    """
    response = client.post(
        "/meetings",
        data={"title": "Test Meeting"},
        files={"file": ("meeting.txt", io.BytesIO(SAMPLE_RAW_TRANSCRIPT.encode("utf-8")), "text/plain")},
    )

    # 202, not 201: the response is returned once the meeting record is
    # created, before extraction (a real network call in production) has
    # necessarily been kicked off from the CLIENT's perspective -- even
    # though TestClient happens to run it synchronously under the hood.
    assert response.status_code == 202
    body = response.json()
    assert body["title"] == "Test Meeting"

    # Verify meeting was stored in fake repo
    assert len(fake_repo._meetings) == 1
    meeting = list(fake_repo._meetings.values())[0]
    assert meeting.raw_transcript == SAMPLE_RAW_TRANSCRIPT

    # Because TestClient runs the BackgroundTask synchronously, by this
    # point the full pipeline has already completed -- fetch the meeting
    # again to see its final state.
    final_response = client.get(f"/meetings/{meeting.id}")
    final_body = final_response.json()
    assert final_body["status"] == "processed"
    assert final_body["cleaned_transcript"] is not None
    assert len(final_body["cleaned_transcript"]) > 0
    assert final_body["summary"] is not None
    assert len(final_body["action_items"]) > 0
    assert fake_extraction_service.call_count == 1


def test_upload_wrong_mime_type(client, fake_repo):
    """Test upload with wrong file type returns 415."""
    response = client.post(
        "/meetings",
        data={"title": "Test Meeting"},
        files={"file": ("meeting.pdf", io.BytesIO(b"PDF content"), "application/pdf")},
    )

    assert response.status_code == 415
    assert "Unsupported file type" in response.json()["detail"]
    assert len(fake_repo._meetings) == 0


def test_upload_wrong_extension(client, fake_repo):
    """Test upload with wrong file extension returns 415."""
    response = client.post(
        "/meetings",
        data={"title": "Test Meeting"},
        files={"file": ("meeting.csv", io.BytesIO(b"col1,col2"), "text/csv")},
    )

    assert response.status_code == 415
    assert "Unsupported file type" in response.json()["detail"]
    assert len(fake_repo._meetings) == 0


def test_upload_file_too_large(client, fake_repo):
    """Test upload with file exceeding 10MB limit returns 413."""
    # Create a file larger than 10MB
    large_content = b"x" * (10 * 1024 * 1024 + 1)
    response = client.post(
        "/meetings",
        data={"title": "Test Meeting"},
        files={"file": ("meeting.txt", io.BytesIO(large_content), "text/plain")},
    )

    assert response.status_code == 413
    assert "File too large" in response.json()["detail"]
    assert len(fake_repo._meetings) == 0


def test_upload_missing_title(client, fake_repo):
    """Test upload without title returns 422."""
    response = client.post(
        "/meetings",
        data={},
        files={"file": ("meeting.txt", io.BytesIO(b"content"), "text/plain")},
    )

    assert response.status_code == 422
    assert len(fake_repo._meetings) == 0


def test_upload_empty_file(client, fake_repo):
    """Test upload with empty file returns 422."""
    response = client.post(
        "/meetings",
        data={"title": "Test Meeting"},
        files={"file": ("meeting.txt", io.BytesIO(b""), "text/plain")},
    )

    assert response.status_code == 422
    assert "File is empty" in response.json()["detail"]
    assert len(fake_repo._meetings) == 0


def test_upload_transcript_cleaned(client, fake_repo):
    """Test that uploaded transcript is properly cleaned."""
    raw_with_timestamps = "[00:01:23] SPEAKER_00: Hello world"
    response = client.post(
        "/meetings",
        data={"title": "Cleaning Test"},
        files={"file": ("meeting.txt", io.BytesIO(raw_with_timestamps.encode("utf-8")), "text/plain")},
    )

    assert response.status_code == 202
    body = response.json()
    # cleaned_transcript is set synchronously in the route (before extraction
    # runs), so it's already correct in the immediate upload response --
    # unlike status/summary/etc., which only reach their final values after
    # the background pipeline completes.
    assert "[00:01:23]" not in body["cleaned_transcript"]
    assert "SPEAKER_00" not in body["cleaned_transcript"]
    assert "Hello world" in body["cleaned_transcript"]
