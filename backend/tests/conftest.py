"""
Shared pytest fixtures.

The `client` fixture below overrides the real MongoDB-backed repository
dependency with an in-memory fake, so route tests run fast, deterministically,
and without needing a real database — this is exactly what the dependency
injection setup in api/dependencies.py was built to enable.
"""

import os

# Must be set BEFORE `from app.main import app` runs, because settings are
# read once at import time (see core/config.py's lru_cache). This tells the
# app's lifespan handler to skip connecting to a real MongoDB, since these
# route-level tests only exercise the faked repository below.
os.environ["TESTING"] = "true"

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_meeting_repository, get_user_repository
from app.main import app
from app.models.meeting import MeetingInDB, MeetingStatus
from app.models.user import UserInDB
from app.services.llm.schemas import ExtractionResult, LLMActionItem


# Sample raw transcript for testing
SAMPLE_RAW_TRANSCRIPT = """[00:01:23] SPEAKER_00: Hello everyone, welcome to the meeting.
SPEAKER_01: Thanks for joining. Let's get started.

[00:02:15] SPEAKER_00: First item on the agenda is the project update.
SPEAKER_01: I have the report ready.

[00:03:00] SPEAKER_00: Great, let's proceed.

[00:03:30] SPEAKER_01: Here are the action items from last time."""

# Minimal valid WAV header (44 bytes) for tests that need binary audio
SAMPLE_AUDIO_BYTES = (
    b"RIFF"              # ChunkID
    b"\x24\x00\x00\x00"  # ChunkSize (36 + data size)
    b"WAVE"              # Format
    b"fmt "              # Subchunk1ID
    b"\x10\x00\x00\x00"  # Subchunk1Size (16 for PCM)
    b"\x01\x00"          # AudioFormat (1 = PCM)
    b"\x01\x00"          # NumChannels (1 = mono)
    b"\x44\xac\x00\x00"  # SampleRate (44100)
    b"\x88\x58\x01\x00"  # ByteRate
    b"\x02\x00"          # BlockAlign
    b"\x10\x00"          # BitsPerSample (16)
    b"data"              # Subchunk2ID
    b"\x00\x00\x00\x00"  # Subchunk2Size (0 bytes of data)
)


class FakeMeetingRepository:
    """
    In-memory stand-in for MeetingRepository, used only in tests.

    Implements the same method signatures as the real repository so route
    code doesn't need to know or care that it's talking to a fake — this is
    the practical payoff of coding against a consistent interface.
    """

    def __init__(self) -> None:
        self._meetings: dict[str, MeetingInDB] = {}

    async def list_by_user(self, uploaded_by: str, limit: int = 50) -> list[MeetingInDB]:
        return [m for m in self._meetings.values() if m.uploaded_by == uploaded_by][:limit]

    async def get_by_id(self, meeting_id: str) -> MeetingInDB | None:
        return self._meetings.get(meeting_id)

    async def create(self, meeting: MeetingInDB) -> MeetingInDB:
        """Test helper: simulates MongoDB insert by assigning an ID."""
        if not meeting.id:
            meeting.id = f"fake-id-{len(self._meetings) + 1}"
        self._meetings[meeting.id] = meeting
        return meeting

    async def update_status(self, meeting_id: str, status: MeetingStatus, error_message: str | None = None) -> bool:
        """Simulates status update. Returns True if meeting exists."""
        if meeting_id not in self._meetings:
            return False
        update = {"status": status}
        if error_message is not None:
            update["error_message"] = error_message
        self._meetings[meeting_id] = self._meetings[meeting_id].model_copy(update=update)
        return True

    async def update_fields(self, meeting_id: str, fields: dict) -> bool:
        """Simulates field update. Returns True if meeting exists."""
        if meeting_id not in self._meetings:
            return False
        self._meetings[meeting_id] = self._meetings[meeting_id].model_copy(update=fields)
        return True

    async def get_by_share_token(self, token: str) -> MeetingInDB | None:
        for m in self._meetings.values():
            if m.share_token == token and m.is_public:
                return m
        return None

    async def set_action_item_done(self, meeting_id: str, item_id: str, done: bool) -> bool:
        """
        Test-fake mirror of the real repository's positional array update.
        Rebuilds the action_items list with the matching item's `done`
        field replaced -- simpler than MongoDB's arrayFilters since this is
        an in-memory dict, but must match the REAL repository's return-value
        contract exactly: True only if the meeting exists AND it has an
        action item with this id (see meeting_repository.py's docstring for
        why matched_count alone isn't sufficient there).
        """
        meeting = self._meetings.get(meeting_id)
        if meeting is None:
            return False

        found = False
        new_items = []
        for item in meeting.action_items:
            if item.id == item_id:
                found = True
                new_items.append(item.model_copy(update={"done": done}))
            else:
                new_items.append(item)

        if not found:
            return False

        self._meetings[meeting_id] = meeting.model_copy(update={"action_items": new_items})
        return True

    async def text_search(self, user_id: str, query: str, limit: int = 20) -> list:
        import re
        from app.models.meeting import MeetingSearchResult
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        results = []
        for m in self._meetings.values():
            if m.uploaded_by != user_id:
                continue
            searchable = f"{m.title} {m.summary or ''} {m.cleaned_transcript or ''} {' '.join(m.keywords)}"
            if pattern.search(searchable):
                results.append(MeetingSearchResult(
                    id=m.id, title=m.title, status=m.status,
                    created_at=m.created_at, summary=m.summary,
                    sentiment=m.sentiment, highlight=None, score=1.0,
                ))
                if len(results) >= limit:
                    break
        return results

    async def get_analytics_overview(self, user_id: str):
        """Fake implementation of get_analytics_overview for tests."""
        from datetime import datetime, timedelta, timezone
        from app.models.meeting import (
            AnalyticsOverview, KeywordFrequency, PendingTask, WeeklyCount,
        )

        user_meetings = [m for m in self._meetings.values() if m.uploaded_by == user_id]
        processed = [m for m in user_meetings if m.status.value == "processed"]

        total = len(user_meetings)
        processed_count = len(processed)

        # Sentiment breakdown
        sentiment_breakdown: dict[str, int] = {"positive": 0, "neutral": 0, "negative": 0}
        for m in processed:
            if m.sentiment and m.sentiment in sentiment_breakdown:
                sentiment_breakdown[m.sentiment] += 1

        # Top keywords
        keyword_counts: dict[str, int] = {}
        for m in processed:
            for kw in m.keywords:
                keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
        sorted_kw = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:15]
        top_keywords = [KeywordFrequency(keyword=kw, count=c) for kw, c in sorted_kw]

        # Pending tasks
        pending_tasks = []
        for m in processed:
            for item in m.action_items:
                if not item.done:
                    pending_tasks.append(PendingTask(
                        meeting_id=m.id,
                        meeting_title=m.title,
                        person=item.person,
                        task=item.task,
                        item_id=item.id,
                        deadline=item.deadline,
                    ))
        pending_tasks = pending_tasks[:20]

        # Weekly counts (last 8 weeks)
        now = datetime.now(timezone.utc)
        weekly_counts = []
        for i in range(7, -1, -1):
            week_start = now - timedelta(days=now.weekday() + i * 7)
            week_end = week_start + timedelta(days=7)
            label = week_start.strftime("%b %d")
            count = sum(1 for m in processed if week_start <= m.created_at.replace(tzinfo=timezone.utc) < week_end)
            weekly_counts.append(WeeklyCount(week=label, count=count))

        return AnalyticsOverview(
            total_meetings=total,
            processed_meetings=processed_count,
            sentiment_breakdown=sentiment_breakdown,
            top_keywords=top_keywords,
            pending_tasks=pending_tasks,
            weekly_counts=weekly_counts,
        )

    def seed(self, meeting: MeetingInDB) -> None:
        """Test helper to pre-populate data, not part of the real interface."""
        self._meetings[meeting.id] = meeting


# A realistic, fixed extraction result used by FakeExtractionService below.
# Defined once at module level (not rebuilt per-test) since it's immutable
# test data, same reasoning as SAMPLE_RAW_TRANSCRIPT above.
SAMPLE_EXTRACTION_RESULT = ExtractionResult(
    summary="The team discussed the project update and reviewed action items from the previous meeting.",
    action_items=[
        LLMActionItem(person="Speaker 1", task="Finish the report", deadline="Friday"),
    ],
    decisions=["Proceed with the current project plan."],
    keywords=["project update", "action items"],
    sentiment="neutral",
)


class FakeExtractionService:
    """
    In-memory stand-in for ExtractionService, used only in tests.

    Route/pipeline tests that exercise the upload endpoints trigger a
    BackgroundTask that calls ExtractionService.extract() -- see
    api/meetings.py and meeting_orchestrator.py. Without this fake, EVERY
    upload test would make a real network call to the Gemini API, which is
    slow, costs (a small amount of) money, requires a real API key to even
    run, and is non-deterministic (a flaky network call could make an
    otherwise-correct test fail). This fake makes extraction instant,
    free, and deterministic, matching the same fake-dependency philosophy
    already used for FakeMeetingRepository.

    Implements the same public method signature as the real
    ExtractionService (just `extract`), so route code doesn't need to know
    or care that it's talking to a fake.
    """

    def __init__(self, result: ExtractionResult = SAMPLE_EXTRACTION_RESULT) -> None:
        self._result = result
        self.call_count = 0  # lets tests assert extraction was actually invoked

    async def extract(self, cleaned_transcript: str) -> ExtractionResult:
        self.call_count += 1
        return self._result


class FakeUserRepository:
    """In-memory stand-in for UserRepository, provides a default test user."""

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


@pytest.fixture
def fake_repo() -> FakeMeetingRepository:
    return FakeMeetingRepository()


@pytest.fixture
def fake_extraction_service() -> FakeExtractionService:
    return FakeExtractionService()


@pytest.fixture
def fake_user_repo() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def client(fake_repo: FakeMeetingRepository, fake_extraction_service: FakeExtractionService, fake_user_repo: FakeUserRepository) -> TestClient:
    """
    A TestClient with the real MongoDB repository AND the real LLM
    extraction service swapped for fakes. Also overrides the user repository
    and provides a valid JWT cookie for the default test user.
    """
    import app.api.meetings as meetings_module

    app.dependency_overrides[get_meeting_repository] = lambda: fake_repo
    app.dependency_overrides[get_user_repository] = lambda: fake_user_repo
    original_extraction_svc = meetings_module._extraction_svc
    meetings_module._extraction_svc = fake_extraction_service

    from app.core.security import create_access_token
    _test_token = create_access_token(
        user_id="demo-user",
        email="demo@test.com",
        display_name="Demo User",
        picture_url="",
        google_sub="demo-google-sub",
    )

    with TestClient(app, cookies={"access_token": _test_token}) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    meetings_module._extraction_svc = original_extraction_svc
