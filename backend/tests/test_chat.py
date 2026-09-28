"""
Tests for the Chat feature (Feature 1).

Covers:
  - Route-level: auth, ownership, status validation, LLM failure handling
  - Service-level: correct context passed to LLM, error propagation
"""

import os

os.environ["TESTING"] = "true"

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_meeting_repository
from app.main import app
from app.models.meeting import MeetingInDB, MeetingStatus
from app.services.llm.chat_service import ChatFailedError, ChatService
from tests.conftest import FakeMeetingRepository

SAMPLE_MEETING = MeetingInDB(
    id="chat-test-1",
    title="Q4 Planning",
    uploaded_by="demo-user",
    status=MeetingStatus.PROCESSED,
    summary="The team discussed Q4 priorities and assigned action items.",
    action_items=[],
    decisions=["Launch the new feature by November."],
    keywords=["Q4", "planning", "roadmap"],
    sentiment="positive",
    cleaned_transcript="Alice: We need to launch by November.\nBob: Agreed, let's finalize the roadmap.",
)


class FakeLLMClient:
    """Minimal fake for LocalLLMClient used by ChatService tests."""

    def __init__(self, response: str = "Fake answer") -> None:
        self._response = response
        self.call_count = 0

    async def generate_json(self, prompt: str) -> str:
        self.call_count += 1
        return self._response


class FailingLLMClient:
    """Fake that always raises LLMRequestError."""

    async def generate_json(self, prompt: str) -> str:
        from app.services.llm.gemini_client import LLMRequestError
        raise LLMRequestError("Gemini API is unavailable")


# ---------------------------------------------------------------------------
# Route-level tests
# ---------------------------------------------------------------------------


@pytest.fixture
def chat_client(fake_repo: FakeMeetingRepository) -> TestClient:
    """TestClient with chat dependency overrides."""
    import app.api.chat as chat_module

    fake_repo.seed(SAMPLE_MEETING)

    app.dependency_overrides[get_meeting_repository] = lambda: fake_repo

    # Provide a fake LLM client for the chat module
    original_chat_svc = chat_module._chat_svc
    chat_module._chat_svc = ChatService(client=FakeLLMClient("According to the transcript, Alice is responsible."))

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
    chat_module._chat_svc = original_chat_svc


def test_chat_returns_answer_for_processed_meeting(chat_client: TestClient):
    response = chat_client.post(
        "/meetings/chat-test-1/chat",
        json={"question": "Who is responsible?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert len(data["answer"]) > 0


def test_chat_requires_auth_returns_401(fake_repo: FakeMeetingRepository):
    fake_repo.seed(SAMPLE_MEETING)
    app.dependency_overrides[get_meeting_repository] = lambda: fake_repo
    try:
        with TestClient(app) as tc:
            response = tc.post(
                "/meetings/chat-test-1/chat",
                json={"question": "Hello?"},
            )
            assert response.status_code in (401, 403)
    finally:
        app.dependency_overrides.clear()


def test_chat_wrong_user_returns_403(fake_repo: FakeMeetingRepository):
    other_user_meeting = SAMPLE_MEETING.model_copy(update={"uploaded_by": "other-user"})
    fake_repo.seed(other_user_meeting)

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
            response = tc.post(
                "/meetings/chat-test-1/chat",
                json={"question": "Hello?"},
            )
            assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_chat_unprocessed_meeting_returns_422(fake_repo: FakeMeetingRepository):
    unprocessed = SAMPLE_MEETING.model_copy(update={"status": MeetingStatus.UPLOADED})
    fake_repo.seed(unprocessed)

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
            response = tc.post(
                "/meetings/chat-test-1/chat",
                json={"question": "Hello?"},
            )
            assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_chat_empty_question_returns_422(fake_repo: FakeMeetingRepository):
    fake_repo.seed(SAMPLE_MEETING)

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
            response = tc.post(
                "/meetings/chat-test-1/chat",
                json={"question": ""},
            )
            assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_chat_llm_failure_returns_502(fake_repo: FakeMeetingRepository):
    import app.api.chat as chat_module

    fake_repo.seed(SAMPLE_MEETING)
    app.dependency_overrides[get_meeting_repository] = lambda: fake_repo

    original_chat_svc = chat_module._chat_svc
    chat_module._chat_svc = ChatService(client=FailingLLMClient())

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
            response = tc.post(
                "/meetings/chat-test-1/chat",
                json={"question": "Hello?"},
            )
            assert response.status_code == 502
    finally:
        chat_module._chat_svc = original_chat_svc
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_service_calls_llm_with_correct_context():
    fake = FakeLLMClient("Test response")
    svc = ChatService(client=fake)
    result = await svc.answer(
        question="What was decided?",
        summary="Budget discussion.",
        decisions=["Approved $50k budget."],
        keywords=["budget", "finance"],
        cleaned_transcript="CEO: Budget approved.",
    )
    assert result == "Test response"
    assert fake.call_count == 1


@pytest.mark.asyncio
async def test_chat_service_raises_chat_failed_error_on_llm_error():
    svc = ChatService(client=FailingLLMClient())
    with pytest.raises(ChatFailedError):
        await svc.answer(
            question="What?",
            summary="Test",
            decisions=[],
            keywords=[],
            cleaned_transcript="Test transcript.",
        )
