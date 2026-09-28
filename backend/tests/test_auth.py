"""
Tests for the authentication API routes.

Uses dependency overrides (same pattern as existing tests) — no real Google
OAuth or network calls. JWT tokens are created directly via the security
module so we can test protected route behavior.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_meeting_repository, get_user_repository
from app.core.security import create_access_token
from app.main import app
from app.models.meeting import ActionItem, MeetingInDB, MeetingStatus
from app.models.user import UserInDB


# ---------- Fakes ----------


class FakeUserRepository:
    """In-memory stand-in for UserRepository."""

    def __init__(self) -> None:
        self._users: dict[str, UserInDB] = {}

    async def upsert_by_google_sub(self, user: UserInDB) -> UserInDB:
        existing = self._users.get(user.google_sub)
        if existing:
            updated = existing.model_copy(update={
                "display_name": user.display_name,
                "picture_url": user.picture_url,
                "email": user.email,
            })
            self._users[user.google_sub] = updated
            return updated
        user.id = f"user-{len(self._users) + 1}"
        self._users[user.google_sub] = user
        return user

    async def get_by_google_sub(self, google_sub: str) -> UserInDB | None:
        return self._users.get(google_sub)

    async def get_by_id(self, user_id: str) -> UserInDB | None:
        for user in self._users.values():
            if user.id == user_id:
                return user
        return None


class FakeMeetingRepository:
    """In-memory stand-in for MeetingRepository."""

    def __init__(self) -> None:
        self._meetings: dict[str, MeetingInDB] = {}

    async def list_by_user(self, uploaded_by: str, limit: int = 50) -> list[MeetingInDB]:
        return [m for m in self._meetings.values() if m.uploaded_by == uploaded_by][:limit]

    async def get_by_id(self, meeting_id: str) -> MeetingInDB | None:
        return self._meetings.get(meeting_id)

    async def create(self, meeting: MeetingInDB) -> MeetingInDB:
        if not meeting.id:
            meeting.id = f"fake-id-{len(self._meetings) + 1}"
        self._meetings[meeting.id] = meeting
        return meeting

    async def update_status(self, meeting_id: str, status: MeetingStatus, error_message: str | None = None) -> bool:
        if meeting_id not in self._meetings:
            return False
        update = {"status": status}
        if error_message is not None:
            update["error_message"] = error_message
        self._meetings[meeting_id] = self._meetings[meeting_id].model_copy(update=update)
        return True

    async def update_fields(self, meeting_id: str, fields: dict) -> bool:
        if meeting_id not in self._meetings:
            return False
        self._meetings[meeting_id] = self._meetings[meeting_id].model_copy(update=fields)
        return True

    def seed(self, meeting: MeetingInDB) -> None:
        self._meetings[meeting.id] = meeting


# ---------- Fixtures ----------


@pytest.fixture
def fake_user_repo() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def fake_meeting_repo() -> FakeMeetingRepository:
    return FakeMeetingRepository()


@pytest.fixture
def auth_client(fake_user_repo: FakeUserRepository, fake_meeting_repo: FakeMeetingRepository) -> TestClient:
    """TestClient with auth + meeting repositories faked."""
    app.dependency_overrides[get_user_repository] = lambda: fake_user_repo
    app.dependency_overrides[get_meeting_repository] = lambda: fake_meeting_repo

    import app.api.meetings as meetings_module
    original_extraction_svc = meetings_module._extraction_svc
    from tests.conftest import FakeExtractionService
    meetings_module._extraction_svc = FakeExtractionService()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    meetings_module._extraction_svc = original_extraction_svc


# ---------- Helper ----------


def _make_token(user_id: str = "user-1", google_sub: str = "google-sub-123") -> str:
    return create_access_token(
        user_id=user_id,
        email="test@example.com",
        display_name="Test User",
        picture_url="https://example.com/photo.jpg",
        google_sub=google_sub,
    )


# ---------- Tests ----------


class TestGetMe:
    def test_returns_user_info_with_valid_token(self, auth_client: TestClient):
        token = _make_token()
        response = auth_client.get("/auth/me", cookies={"access_token": token})
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"
        assert data["display_name"] == "Test User"
        assert data["sub"] == "user-1"

    def test_returns_401_without_cookie(self, auth_client: TestClient):
        response = auth_client.get("/auth/me")
        assert response.status_code == 401

    def test_returns_401_with_invalid_token(self, auth_client: TestClient):
        response = auth_client.get("/auth/me", cookies={"access_token": "garbage-token"})
        assert response.status_code == 401


class TestLogout:
    def test_logout_clears_cookie(self, auth_client: TestClient):
        token = _make_token()
        response = auth_client.post("/auth/logout", cookies={"access_token": token})
        assert response.status_code == 200
        assert "access_token" in response.headers.get("set-cookie", "")


class TestProtectedMeetings:
    def test_list_meetings_without_auth_returns_401(self, auth_client: TestClient):
        response = auth_client.get("/meetings")
        assert response.status_code == 401

    def test_list_meetings_with_valid_token_returns_empty(self, auth_client: TestClient):
        token = _make_token(user_id="user-1")
        response = auth_client.get("/meetings", cookies={"access_token": token})
        assert response.status_code == 200
        assert response.json() == []

    def test_get_meeting_wrong_user_returns_403(self, auth_client: TestClient, fake_meeting_repo: FakeMeetingRepository):
        meeting = MeetingInDB(
            id="meeting-1",
            title="Secret Meeting",
            uploaded_by="other-user",
            status=MeetingStatus.PROCESSED,
        )
        fake_meeting_repo.seed(meeting)

        token = _make_token(user_id="user-1")
        response = auth_client.get("/meetings/meeting-1", cookies={"access_token": token})
        assert response.status_code == 403

    def test_get_meeting_correct_user_returns_200(self, auth_client: TestClient, fake_meeting_repo: FakeMeetingRepository):
        meeting = MeetingInDB(
            id="meeting-1",
            title="My Meeting",
            uploaded_by="user-1",
            status=MeetingStatus.PROCESSED,
        )
        fake_meeting_repo.seed(meeting)

        token = _make_token(user_id="user-1")
        response = auth_client.get("/meetings/meeting-1", cookies={"access_token": token})
        assert response.status_code == 200
        assert response.json()["title"] == "My Meeting"
