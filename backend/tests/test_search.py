"""Tests for search endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_meeting_repository, get_user_repository
from app.main import app
from app.models.meeting import MeetingInDB, MeetingStatus
from tests.conftest import FakeMeetingRepository, FakeUserRepository


@pytest.fixture
def search_client():
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


class TestSearch:
    def test_search_returns_matching(self, search_client):
        client, repo = search_client
        repo.seed(MeetingInDB(id="m1", title="Sprint Planning", uploaded_by="user-1",
                              status=MeetingStatus.PROCESSED, summary="Discussed sprint goals"))
        repo.seed(MeetingInDB(id="m2", title="Design Review", uploaded_by="user-1",
                              status=MeetingStatus.PROCESSED, summary="Reviewed UI mockups"))

        resp = client.get("/meetings/search?q=sprint")
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) >= 1
        assert results[0]["title"] == "Sprint Planning"

    def test_search_empty_when_no_match(self, search_client):
        client, repo = search_client
        repo.seed(MeetingInDB(id="m1", title="Sprint", uploaded_by="user-1", status=MeetingStatus.PROCESSED))

        resp = client.get("/meetings/search?q=xyznotfound")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_search_requires_auth(self, search_client):
        from fastapi.testclient import TestClient
        from app.main import app as _app
        no_auth_client = TestClient(_app)
        resp = no_auth_client.get("/meetings/search?q=test")
        assert resp.status_code == 401

    def test_search_isolation(self, search_client):
        client, repo = search_client
        repo.seed(MeetingInDB(id="m1", title="My Meeting", uploaded_by="user-1", status=MeetingStatus.PROCESSED))
        repo.seed(MeetingInDB(id="m2", title="Other Meeting", uploaded_by="other-user", status=MeetingStatus.PROCESSED))

        resp = client.get("/meetings/search?q=Meeting")
        assert resp.status_code == 200
        ids = [r["id"] for r in resp.json()]
        assert "m2" not in ids
