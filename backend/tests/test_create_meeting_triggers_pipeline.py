"""
Integration test: uploading a .txt file via the POST /meetings route
returns 202 with status "cleaning" and an "id" field, and the meeting
is retrievable via GET.
"""

import io

from fastapi.testclient import TestClient


def test_upload_txt_returns_202_with_cleaning_status(client: TestClient) -> None:
    """POST /meetings with a .txt file returns 202 with status=cleaning and id."""
    response = client.post(
        "/meetings",
        data={"title": "Integration Test Meeting"},
        files={"file": ("transcript.txt", io.BytesIO(b"Hello world, this is a test transcript."), "text/plain")},
    )

    assert response.status_code == 202
    body = response.json()
    assert "id" in body
    assert body["status"] == "cleaning"
    assert body["title"] == "Integration Test Meeting"


def test_upload_txt_meeting_is_retrievable(client: TestClient) -> None:
    """After uploading a .txt file, the meeting can be fetched by id."""
    upload_response = client.post(
        "/meetings",
        data={"title": "Fetchable Meeting"},
        files={"file": ("notes.txt", io.BytesIO(b"Some meeting notes here."), "text/plain")},
    )
    assert upload_response.status_code == 202
    meeting_id = upload_response.json()["id"]

    get_response = client.get(f"/meetings/{meeting_id}")
    assert get_response.status_code == 200
    fetched = get_response.json()
    assert fetched["id"] == meeting_id
    assert fetched["title"] == "Fetchable Meeting"
    assert fetched["cleaned_transcript"] is not None


def test_upload_txt_cleaned_transcript_stripped(client: TestClient) -> None:
    """Timestamps and speaker labels are stripped from the transcript."""
    raw = "[00:01:23] SPEAKER_00: Hello everyone.\nSPEAKER_01: Thanks for joining."
    response = client.post(
        "/meetings",
        data={"title": "Clean Test"},
        files={"file": ("t.txt", io.BytesIO(raw.encode()), "text/plain")},
    )
    assert response.status_code == 202
    meeting_id = response.json()["id"]

    get_response = client.get(f"/meetings/{meeting_id}")
    transcript = get_response.json()["cleaned_transcript"]
    assert "[00:01:23]" not in transcript
    assert "SPEAKER_00:" not in transcript
    assert "Hello everyone." in transcript
