"""
Chat API router.

Provides a per-meeting Q&A endpoint that answers user questions using
only that meeting's transcript, summary, decisions, and keywords.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_meeting_repository
from app.core.config import settings
from app.core.security import get_current_user
from app.repositories.meeting_repository import MeetingRepository
from app.services.llm.chat_service import ChatFailedError, ChatService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

_chat_svc = ChatService() if not settings.testing else None  # type: ignore[assignment]


class ChatRequest(BaseModel):
    """Request body for the chat endpoint."""

    question: str = Field(..., min_length=1, max_length=500)


class ChatResponse(BaseModel):
    """Response body for the chat endpoint."""

    answer: str


@router.post("/meetings/{meeting_id}/chat", response_model=ChatResponse)
async def chat_about_meeting(
    meeting_id: str,
    body: ChatRequest,
    current_user: dict = Depends(get_current_user),
    repo: MeetingRepository = Depends(get_meeting_repository),
) -> ChatResponse:
    """
    Answers a free-form question about a specific processed meeting.

    The LLM only sees the meeting's summary, decisions, keywords, and
    transcript — it cannot access outside knowledge or other meetings.
    """
    meeting = await repo.get_by_id(meeting_id)
    if meeting is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting {meeting_id} not found",
        )
    if meeting.uploaded_by != current_user["sub"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this meeting",
        )
    if meeting.status.value != "processed":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Meeting must be processed before you can chat about it",
        )

    try:
        answer = await _chat_svc.answer(
            question=body.question,
            summary=meeting.summary,
            decisions=meeting.decisions,
            keywords=meeting.keywords,
            cleaned_transcript=meeting.cleaned_transcript,
        )
    except ChatFailedError as exc:
        logger.warning("Chat failed for meeting %s: %s", meeting_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM failed to generate an answer: {exc}",
        )

    return ChatResponse(answer=answer)
