"""
Tests for the Analytics feature (Feature 3).

Covers:
  - Route-level: auth required, correct structure, empty state
  - Repository-level: sentiment counts only processed meetings,
    pending tasks exclude done items
"""

import os

os.environ["TESTING"] = "true"

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.api.dependencies import get_meeting_repository
from app.main import app
from app.models.meeting import MeetingInDB, MeetingStatus, ActionItem
from tests.conftest import FakeMeetingRepository


def _make_meeting(
    id: str,
    title: str,
    status: MeetingStatus = MeetingStatus.PROCESSED,
    sentiment: str | None = "neutral",
    keywords: list[str] | None = None,
    action_items: list[ActionItem] | None = None,
    decisions: list[str] | None = None,
    created_at: datetime | None = None,
) -> MeetingInDB:
    return MeetingInDB(
        id=id,
        title=title,
        uploaded_by="demo-user",
        status=status,
        sentiment=sentiment,
        keywords=keywords or [],
        action_items=action_items or [],
        decisions=decisions or [],
        created_at=created_at or datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Route-level tests
# ---------------------------------------------------------------------------


@pytest.fixture
def analytics_client(fake_repo: FakeMeetingRepository) -> TestClient:
    """TestClient with analytics dependency overrides."""
    app.dependency_overrides[get_meeting_repository] = lambda: fake_repo

    from app.core.security import create_access_token
    token = create_access_token(
        user_id="demo-user",
        email="demo@test.com",
        display_name="Demo User",
        picture_url="",
        google_sub="demo-google-sub",
    )

    with TestClient(app, cookies={"access_token": token}) as tc:
        yield tc

    app.dependency_overrides.clear()


def test_analytics_overview_returns_correct_structure(analytics_client: TestClient):
    response = analytics_client.get("/analytics/overview")
    assert response.status_code == 200
    data = response.json()
    assert "total_meetings" in data
    assert "processed_meetings" in data
    assert "sentiment_breakdown" in data
    assert "top_keywords" in data
    assert "pending_tasks" in data
    assert "weekly_counts" in data


def test_analytics_requires_auth_returns_401():
    app.dependency_overrides.clear()
    with TestClient(app) as tc:
        response = tc.get("/analytics/overview")
        assert response.status_code in (401, 403)


def test_analytics_empty_for_new_user(fake_repo: FakeMeetingRepository):
    """New user with no meetings gets zeros, not errors."""
    app.dependency_overrides[get_meeting_repository] = lambda: fake_repo

    from app.core.security import create_access_token
    token = create_access_token(
        user_id="demo-user",
        email="demo@test.com",
        display_name="Demo User",
        picture_url="",
        google_sub="demo-google-sub",
    )

    try:
        with TestClient(app, cookies={"access_token": token}) as tc:
            response = tc.get("/analytics/overview")
            assert response.status_code == 200
            data = response.json()
            assert data["total_meetings"] == 0
            assert data["processed_meetings"] == 0
            assert data["sentiment_breakdown"] == {"positive": 0, "neutral": 0, "negative": 0}
            assert data["top_keywords"] == []
            assert data["pending_tasks"] == []
            assert all(w["count"] == 0 for w in data["weekly_counts"])
    finally:
        app.dependency_overrides.clear()


def test_analytics_sentiment_counts_only_processed_meetings(fake_repo: FakeMeetingRepository):
    """Unprocessed meetings should not appear in sentiment counts."""
    fake_repo.seed(_make_meeting(
        id="m1", title="Processed 1", status=MeetingStatus.PROCESSED, sentiment="positive",
    ))
    fake_repo.seed(_make_meeting(
        id="m2", title="Still processing", status=MeetingStatus.ANALYZING, sentiment="negative",
    ))
    fake_repo.seed(_make_meeting(
        id="m3", title="Processed 2", status=MeetingStatus.PROCESSED, sentiment="positive",
    ))

    app.dependency_overrides[get_meeting_repository] = lambda: fake_repo

    from app.core.security import create_access_token
    token = create_access_token(
        user_id="demo-user",
        email="demo@test.com",
        display_name="Demo User",
        picture_url="",
        google_sub="demo-google-sub",
    )

    try:
        with TestClient(app, cookies={"access_token": token}) as tc:
            response = tc.get("/analytics/overview")
            assert response.status_code == 200
            data = response.json()
            assert data["processed_meetings"] == 2
            assert data["sentiment_breakdown"]["positive"] == 2
            assert data["sentiment_breakdown"]["negative"] == 0
    finally:
        app.dependency_overrides.clear()


def test_analytics_pending_tasks_excludes_done_items(fake_repo: FakeMeetingRepository):
    """Only done=false action items should appear in pending_tasks."""
    fake_repo.seed(_make_meeting(
        id="m1",
        title="Planning",
        status=MeetingStatus.PROCESSED,
        action_items=[
            ActionItem(id="a1", person="Alice", task="Write spec", done=False),
            ActionItem(id="a2", person="Bob", task="Review PR", done=True),
            ActionItem(id="a3", person="Charlie", task="Deploy", done=False),
        ],
    ))

    app.dependency_overrides[get_meeting_repository] = lambda: fake_repo

    from app.core.security import create_access_token
    token = create_access_token(
        user_id="demo-user",
        email="demo@test.com",
        display_name="Demo User",
        picture_url="",
        google_sub="demo-google-sub",
    )

    try:
        with TestClient(app, cookies={"access_token": token}) as tc:
            response = tc.get("/analytics/overview")
            assert response.status_code == 200
            data = response.json()
            assert len(data["pending_tasks"]) == 2
            pending_ids = {t["item_id"] for t in data["pending_tasks"]}
            assert "a1" in pending_ids
            assert "a3" in pending_ids
            assert "a2" not in pending_ids
    finally:
        app.dependency_overrides.clear()
