"""
Meeting domain models.

Design note:
    We define separate models for different purposes rather than one giant
    "do everything" class:

    - MeetingStatus:     enum of valid processing states (prevents invalid
                          strings like "procesing" typos from ever reaching
                          the database)
    - MeetingCreate:     what the API accepts on upload (minimal — just what
                          the client actually sends)
    - MeetingInDB:       the full document shape as stored in MongoDB
                          (includes fields the client never sets directly,
                          like `status` or `created_at`)
    - MeetingPublic:     what the API returns to clients (may hide/reshape
                          internal fields as the app grows)

    This separation is a standard production pattern: it stops internal
    implementation details from leaking into your API contract, and stops
    clients from being able to set fields they shouldn't control (e.g. a
    client should never be able to set `status="processed"` directly on
    upload — only the pipeline should do that).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class MeetingStatus(str, Enum):
    """
    All valid states a Meeting can be in. Using an Enum (not a bare string)
    means invalid states are caught at the type-checking / validation layer,
    not discovered as a bug in production when someone typos "procesing".
    """

    UPLOADED = "uploaded"
    TRANSCRIBING = "transcribing"       # audio -> text in progress (Phase 2)
    CLEANING = "cleaning"               # transcript normalization in progress
    ANALYZING = "analyzing"             # LLM extraction in progress (Phase 3)
    PROCESSED = "processed"             # pipeline completed successfully
    FAILED = "failed"                   # pipeline failed at some stage


class MeetingCreate(BaseModel):
    """Fields the client provides when uploading a meeting."""

    title: str = Field(..., min_length=1, max_length=200)
    # Note: the actual file bytes come via UploadFile in the route layer,
    # not through this model. MeetingCreate is what we pass BETWEEN layers
    # after the route has validated/read the file.
    filename: str | None = None   # original filename, stored for audit


class ActionItem(BaseModel):
    """
    A single action item extracted from a meeting transcript by the LLM
    (Phase 3). Defined as a real Pydantic model -- not a bare dict -- so
    the LLM's JSON response is validated at the boundary: a malformed or
    incomplete extraction (e.g. missing `task`) fails loudly right where
    the LLM response is parsed, instead of silently reaching the frontend
    as a dict with unpredictable keys.

    `id` and `done` are deliberately NOT populated by the LLM -- see
    ExtractionResult in services/llm/schemas.py, which defines a narrower
    LLMActionItem (person/task/deadline only) for what the model actually
    produces. `id`/`done` are assigned by extraction_worker.py when the
    LLM's raw result is persisted, since a stable identifier and a
    completion flag are application concerns, not something an LLM should
    be asked to invent.
    """

    id: str = Field(
        ...,
        description="Stable identifier for this item within its meeting, "
        "assigned at persist time (see extraction_worker.py). Used by the "
        "action-item completion toggle endpoint to address a specific item.",
    )
    person: str = Field(..., min_length=1, max_length=100)
    task: str = Field(..., min_length=1, max_length=500)
    # Deadlines in transcripts are almost always relative/fuzzy ("by Friday",
    # "end of sprint") rather than absolute dates a meeting transcript would
    # rarely state unambiguously. Storing this as free text (not `date`)
    # avoids forcing the LLM to guess a specific calendar date it can't
    # actually know, which would silently fabricate precision that isn't
    # in the source material.
    deadline: str | None = None
    # Completion state, toggled by the user from the UI (not extracted).
    # Defaults to False: a freshly-extracted action item is, by definition,
    # not yet done.
    done: bool = False


Sentiment = Literal["positive", "neutral", "negative"]


class MeetingInDB(BaseModel):
    """
    The full shape of a Meeting document as stored in MongoDB.

    `id` is a string representation of Mongo's ObjectId — we convert at the
    repository boundary so the rest of the app never has to import bson
    types directly (keeps Mongo-specific details contained to one layer).
    """

    id: str
    title: str
    uploaded_by: str
    status: MeetingStatus = MeetingStatus.UPLOADED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    raw_transcript: str | None = None
    cleaned_transcript: str | None = None
    error_message: str | None = None

    # Audio metadata (Phase 2)
    audio_filename: str | None = None           # original uploaded filename
    audio_duration_seconds: float | None = None # probed before Whisper call

    # Populated in Phase 3 by the LLM pipeline. Left as None/empty until
    # then. Typed as ActionItem (not a bare dict) now that Phase 3 actually
    # writes to this field -- see ActionItem's docstring above for why.
    summary: str | None = None
    action_items: list[ActionItem] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    sentiment: Sentiment | None = None

    # Phase 5 — sharing
    share_token: str | None = None       # UUID4 string; None = not shared
    is_public: bool = False              # True once share link is generated


class MeetingPublic(BaseModel):
    """
    What gets returned to API clients. Currently mirrors MeetingInDB minus
    nothing, but exists as a separate model so we have a seam to hide
    internal-only fields (e.g. internal processing metadata) without
    touching the storage model, if that need arises later.
    """

    id: str
    title: str
    status: MeetingStatus
    created_at: datetime
    updated_at: datetime
    cleaned_transcript: str | None = None
    error_message: str | None = None
    audio_filename: str | None = None
    audio_duration_seconds: float | None = None
    summary: str | None = None
    action_items: list[ActionItem] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    sentiment: Sentiment | None = None

    # Phase 5 — sharing
    share_token: str | None = None
    is_public: bool = False

    @classmethod
    def from_db_model(cls, meeting: MeetingInDB) -> "MeetingPublic":
        """Explicit, readable conversion from the storage model to the API model."""
        return cls(
            id=meeting.id,
            title=meeting.title,
            status=meeting.status,
            created_at=meeting.created_at,
            updated_at=meeting.updated_at,
            cleaned_transcript=meeting.cleaned_transcript,
            error_message=meeting.error_message,
            audio_filename=meeting.audio_filename,
            audio_duration_seconds=meeting.audio_duration_seconds,
            summary=meeting.summary,
            action_items=meeting.action_items,
            decisions=meeting.decisions,
            keywords=meeting.keywords,
            sentiment=meeting.sentiment,
            share_token=meeting.share_token,
            is_public=meeting.is_public,
        )


class MeetingSearchResult(BaseModel):
    """Search result with relevance score and optional highlight snippet."""

    id: str
    title: str
    status: MeetingStatus
    created_at: datetime
    summary: str | None = None
    sentiment: Sentiment | None = None
    highlight: str | None = None
    score: float = 0.0


# --- Analytics models (Feature 3) ---


class KeywordFrequency(BaseModel):
    """A keyword with its frequency count across all processed meetings."""

    keyword: str
    count: int


class PendingTask(BaseModel):
    """An incomplete action item from a processed meeting."""

    meeting_id: str
    meeting_title: str
    person: str
    task: str
    item_id: str
    deadline: str | None = None


class WeeklyCount(BaseModel):
    """Meeting count for a calendar week."""

    week: str  # ISO week label e.g. "Jul 14"
    count: int


class AnalyticsOverview(BaseModel):
    """
    Aggregated analytics across all of a user's processed meetings.
    Returned by GET /analytics/overview.
    """

    total_meetings: int
    processed_meetings: int
    sentiment_breakdown: dict[str, int]  # {"positive": N, "neutral": N, "negative": N}
    top_keywords: list[KeywordFrequency]  # sorted by count desc, max 15
    pending_tasks: list[PendingTask]  # across all processed meetings, max 20
    weekly_counts: list[WeeklyCount]  # last 8 weeks
