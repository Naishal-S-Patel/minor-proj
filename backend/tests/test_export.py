"""Tests for export endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_meeting_repository, get_user_repository
from app.main import app
from app.models.meeting import MeetingInDB, MeetingStatus, ActionItem
from app.services.export_service import export_as_csv, export_as_pdf
from tests.conftest import FakeMeetingRepository, FakeUserRepository


@pytest.fixture
def export_client():
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


def _processed_meeting(**overrides) -> MeetingInDB:
    defaults = dict(
        id="m1", title="Test Meeting", uploaded_by="user-1",
        status=MeetingStatus.PROCESSED, summary="Test summary",
        action_items=[ActionItem(id="item-1", person="Alice", task="Do thing", deadline="Friday", done=False)],
        decisions=["Go with plan A"], keywords=["test", "meeting"],
        sentiment="positive",
    )
    defaults.update(overrides)
    return MeetingInDB(**defaults)


class TestExportService:
    def test_csv_has_headers(self):
        meeting = _processed_meeting()
        csv_bytes = export_as_csv(meeting)
        text = csv_bytes.decode("utf-8")
        assert "Title" in text
        assert "Summary" in text
        assert "Action Items" in text

    def test_pdf_not_empty(self):
        meeting = _processed_meeting()
        pdf_bytes = export_as_pdf(meeting)
        assert len(pdf_bytes) > 0
        assert pdf_bytes[:4] == b"%PDF"


class TestExportEndpoint:
    def test_export_csv(self, export_client):
        client, repo = export_client
        repo.seed(_processed_meeting())

        resp = client.get("/meetings/m1/export?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    def test_export_pdf(self, export_client):
        client, repo = export_client
        repo.seed(_processed_meeting())

        resp = client.get("/meetings/m1/export?format=pdf")
        assert resp.status_code == 200
        assert "application/pdf" in resp.headers["content-type"]

    def test_export_requires_auth(self, export_client):
        client, _ = export_client
        from fastapi.testclient import TestClient
        from app.main import app as _app
        no_auth_client = TestClient(_app)
        resp = no_auth_client.get("/meetings/m1/export?format=csv")
        assert resp.status_code == 401

    def test_export_wrong_user(self, export_client):
        client, repo = export_client
        repo.seed(_processed_meeting(id="m1", uploaded_by="other-user"))

        resp = client.get("/meetings/m1/export?format=csv")
        assert resp.status_code == 403
