"""
LLM extraction result schema.

Why this is a separate model from ActionItem/Sentiment in models/meeting.py:
    ExtractionResult represents "what the LLM is asked to return" -- it's
    the contract between our prompt and the LLM's JSON response. It's used
    ONLY inside the llm/ package, to validate and parse the raw response
    before anything else touches it.

    MeetingInDB/MeetingPublic (in models/meeting.py) represent "what's
    stored/returned" -- they happen to reuse ActionItem and Sentiment for
    convenience (no reason to duplicate those two types), but keeping
    ExtractionResult itself separate means the LLM package's internal
    contract can evolve (e.g. add a `confidence` field per extraction)
    without every unrelated part of the app needing to know about it.
"""

from pydantic import BaseModel, Field

from app.models.meeting import Sentiment


class LLMActionItem(BaseModel):
    """
    The shape of an action item as the LLM actually produces it --
    person/task/deadline only. Deliberately narrower than
    app.models.meeting.ActionItem, which additionally has `id` and `done`
    fields that are application concerns (assigned/toggled by our own code,
    not something to ask an LLM to invent or track). See ActionItem's
    docstring for the full reasoning.

    extraction_worker.py converts each LLMActionItem into a full ActionItem
    (generating an id, defaulting done=False) at persist time -- see its
    own comments for exactly where that happens.
    """

    person: str = Field(..., min_length=1, max_length=100)
    task: str = Field(..., min_length=1, max_length=500)
    deadline: str | None = None


class ExtractionResult(BaseModel):
    """
    The structured output we ask the LLM to produce for a cleaned meeting
    transcript. Field names and types here match prompts.py's instructions
    exactly -- if you change one, change the other, or extraction parsing
    will start failing validation.
    """

    summary: str = Field(
        ...,
        min_length=1,
        description="A concise 2-4 sentence summary of what was discussed and decided.",
    )
    action_items: list[LLMActionItem] = Field(
        default_factory=list,
        description="Concrete tasks assigned to specific people, with deadlines if stated.",
    )
    decisions: list[str] = Field(
        default_factory=list,
        description="Concrete decisions that were made during the meeting.",
    )
    keywords: list[str] = Field(
        default_factory=list,
        max_length=15,
        description="Short topic/technology keywords mentioned in the meeting.",
    )
    sentiment: Sentiment = Field(
        ...,
        description="Overall tone of the meeting: positive, neutral, or negative.",
    )
