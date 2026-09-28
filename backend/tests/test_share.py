"""Tests for share endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_meeting_repository, get_user_repository
from app.main import app
from app.models.meeting import MeetingInDB, MeetingStatus
from tests.conftest import FakeMeetingRepository, FakeUserRepository


@pytest.fixture
def share_client():
    fake_repo = FakeMeetingRepository()
    fake_user_repo = FakeUserRepository()
    app.dependency_overrides[get_meeting_repository] = lambda: fake_repo
    app.dependency_overrides[get_user_repository] = lambda: fake_user_repo

    import app.api.meetings as meetings_module
    from tests.conftest import FakeExtractionService
    original = meetings_module._extraction_svc
    meetings_module._extraction_svc = FakeExtractionService()

    from app.core.security import create_access_token
    token = create_access_token("user-1", "t@t.com", "T", "", "g-sub")

    with TestClient(app, cookies={"access_token": token}) as c:
        yield c, fake_repo

    app.dependency_overrides.clear()
    meetings_module._extraction_svc = original


class TestShare:
    def test_share_creates_token(self, share_client):
        client, repo = share_client
        repo.seed(MeetingInDB(id="m1", title="T", uploaded_by="user-1", status=MeetingStatus.PROCESSED))

        resp = client.post("/meetings/m1/share")
        assert resp.status_code == 200
        assert "share_url" in resp.json()

    def test_share_revoke(self, share_client):
        client, repo = share_client
        repo.seed(MeetingInDB(id="m1", title="T", uploaded_by="user-1", status=MeetingStatus.PROCESSED,
                              share_token="abc123", is_public=True))

        resp = client.delete("/meetings/m1/share")
        assert resp.status_code == 200

    def test_get_shared_meeting(self, share_client):
        client, repo = share_client
        repo.seed(MeetingInDB(id="m1", title="Shared", uploaded_by="user-1",
                              status=MeetingStatus.PROCESSED, share_token="tok1", is_public=True))

        resp = client.get("/shared/tok1")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Shared"

    def test_shared_invalid_token(self, share_client):
        client, _ = share_client
        resp = client.get("/shared/nonexistent")
        assert resp.status_code == 404

    def test_shared_revoked_token(self, share_client):
        client, repo = share_client
        repo.seed(MeetingInDB(id="m1", title="T", uploaded_by="user-1",
                              status=MeetingStatus.PROCESSED, share_token="tok1", is_public=False))

        resp = client.get("/shared/tok1")
        assert resp.status_code == 404
