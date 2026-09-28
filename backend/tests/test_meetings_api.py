"""
Tests for the meetings router, using the fake repository from conftest.py.

These tests deliberately do NOT touch a real MongoDB — they verify route
behavior (status codes, response shape, 404 handling) in isolation, which is
what makes the test suite fast enough to run on every commit in CI.
"""

from datetime import datetime, timezone

from app.models.meeting import MeetingInDB, MeetingStatus


def _make_meeting(meeting_id: str, uploaded_by: str = "demo-user") -> MeetingInDB:
    """Test helper: builds a valid MeetingInDB with sensible defaults."""
    return MeetingInDB(
        id=meeting_id,
        title="Sprint Planning",
        uploaded_by=uploaded_by,
        status=MeetingStatus.PROCESSED,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        summary="Team discussed sprint goals.",
    )


def test_list_meetings_empty_returns_empty_list(client):
    response = client.get("/meetings")
    assert response.status_code == 200
    assert response.json() == []


def test_list_meetings_returns_seeded_data(client, fake_repo):
    fake_repo.seed(_make_meeting("meeting-1"))
    fake_repo.seed(_make_meeting("meeting-2"))

    response = client.get("/meetings")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert {m["id"] for m in body} == {"meeting-1", "meeting-2"}


def test_list_meetings_excludes_other_users(client, fake_repo):
    fake_repo.seed(_make_meeting("mine", uploaded_by="demo-user"))
    fake_repo.seed(_make_meeting("not-mine", uploaded_by="someone-else"))

    response = client.get("/meetings")

    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == "mine"


def test_get_meeting_by_id_returns_meeting(client, fake_repo):
    fake_repo.seed(_make_meeting("meeting-42"))

    response = client.get("/meetings/meeting-42")

    assert response.status_code == 200
    assert response.json()["id"] == "meeting-42"
    assert response.json()["summary"] == "Team discussed sprint goals."


def test_get_meeting_not_found_returns_404(client):
    response = client.get("/meetings/does-not-exist")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
