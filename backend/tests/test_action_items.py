"""
Tests for PATCH /meetings/{meeting_id}/action-items/{item_id}.

Follows the same fixture pattern as test_export.py/test_search.py/
test_share.py: its own client fixture (real JWT cookie via
create_access_token) rather than reusing the shared `client` fixture from
conftest.py, since this endpoint needs precise control over which user's
token is attached to test ownership (403) behavior.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_meeting_repository, get_user_repository
from app.core.security import create_access_token
from app.main import app
from app.models.meeting import ActionItem, MeetingInDB, MeetingStatus
from tests.conftest import FakeExtractionService, FakeMeetingRepository, FakeUserRepository


@pytest.fixture
def action_item_client():
    fake_repo = FakeMeetingRepository()
    fake_user_repo = FakeUserRepository()
    app.dependency_overrides[get_meeting_repository] = lambda: fake_repo
    app.dependency_overrides[get_user_repository] = lambda: fake_user_repo

    import app.api.meetings as meetings_module
    original = meetings_module._extraction_svc
    meetings_module._extraction_svc = FakeExtractionService()

    token = create_access_token("user-1", "t@t.com", "T", "", "g-sub")

    with TestClient(app, cookies={"access_token": token}) as c:
        yield c, fake_repo

    app.dependency_overrides.clear()
    meetings_module._extraction_svc = original


def _meeting_with_action_items(**overrides) -> MeetingInDB:
    defaults = dict(
        id="m1",
        title="Sprint Planning",
        uploaded_by="user-1",
        status=MeetingStatus.PROCESSED,
        action_items=[
            ActionItem(id="item-1", person="Alice", task="Write tests", deadline="Friday", done=False),
            ActionItem(id="item-2", person="Bob", task="Deploy", deadline=None, done=False),
        ],
    )
    defaults.update(overrides)
    return MeetingInDB(**defaults)


class TestUpdateActionItem:
    def test_marks_item_done(self, action_item_client):
        client, repo = action_item_client
        repo.seed(_meeting_with_action_items())

        resp = client.patch("/meetings/m1/action-items/item-1", json={"done": True})

        assert resp.status_code == 200
        body = resp.json()
        items_by_id = {i["id"]: i for i in body["action_items"]}
        assert items_by_id["item-1"]["done"] is True
        # Confirms the update is scoped to the ONE item addressed -- item-2
        # must be untouched, not accidentally flipped by a too-broad update.
        assert items_by_id["item-2"]["done"] is False

    def test_marks_item_not_done(self, action_item_client):
        """Toggling back to done=False (undo) works the same as marking done."""
        client, repo = action_item_client
        repo.seed(_meeting_with_action_items(
            action_items=[ActionItem(id="item-1", person="Alice", task="Write tests", done=True)]
        ))

        resp = client.patch("/meetings/m1/action-items/item-1", json={"done": False})

        assert resp.status_code == 200
        assert resp.json()["action_items"][0]["done"] is False

    def test_toggling_already_done_item_still_succeeds(self, action_item_client):
        """
        Regression guard for the matched_count-vs-modified_count edge case
        found while building this endpoint (see meeting_repository.py's
        set_action_item_done docstring): re-marking an already-done item as
        done again is a legitimate no-op, not a "not found" error.
        """
        client, repo = action_item_client
        repo.seed(_meeting_with_action_items(
            action_items=[ActionItem(id="item-1", person="Alice", task="Write tests", done=True)]
        ))

        resp = client.patch("/meetings/m1/action-items/item-1", json={"done": True})

        assert resp.status_code == 200
        assert resp.json()["action_items"][0]["done"] is True

    def test_returns_full_updated_meeting(self, action_item_client):
        """The response includes the whole meeting, not just the toggled item."""
        client, repo = action_item_client
        repo.seed(_meeting_with_action_items())

        resp = client.patch("/meetings/m1/action-items/item-1", json={"done": True})

        body = resp.json()
        assert body["id"] == "m1"
        assert body["title"] == "Sprint Planning"
        assert len(body["action_items"]) == 2

    def test_nonexistent_meeting_returns_404(self, action_item_client):
        client, _ = action_item_client
        resp = client.patch("/meetings/does-not-exist/action-items/item-1", json={"done": True})
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_nonexistent_item_on_real_meeting_returns_404(self, action_item_client):
        """
        The meeting exists but has no action item with this id -- must be
        404, not a silent no-op success. This is exactly the case the
        repository's combined top-level-filter fix (matched_count wouldn't
        be reliable with array_filters alone) was written to get right.
        """
        client, repo = action_item_client
        repo.seed(_meeting_with_action_items())

        resp = client.patch("/meetings/m1/action-items/does-not-exist", json={"done": True})

        assert resp.status_code == 404
        assert "action item" in resp.json()["detail"].lower()

    def test_wrong_user_returns_403(self, action_item_client):
        client, repo = action_item_client
        repo.seed(_meeting_with_action_items(uploaded_by="someone-else"))

        resp = client.patch("/meetings/m1/action-items/item-1", json={"done": True})

        assert resp.status_code == 403

    def test_requires_auth(self, action_item_client):
        _, repo = action_item_client
        repo.seed(_meeting_with_action_items())

        no_auth_client = TestClient(app)
        resp = no_auth_client.patch("/meetings/m1/action-items/item-1", json={"done": True})

        assert resp.status_code == 401

    def test_missing_done_field_returns_422(self, action_item_client):
        """Request body validation: `done` is required, not optional."""
        client, repo = action_item_client
        repo.seed(_meeting_with_action_items())

        resp = client.patch("/meetings/m1/action-items/item-1", json={})

        assert resp.status_code == 422
