"""
Export & Share API router.

Provides endpoints for:
  - Exporting meetings as PDF/CSV (authenticated, ownership-checked)
  - Generating, viewing, and revoking share links
  - Public share viewing (no auth required)
"""

import logging
import uuid
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_meeting_repository
from app.core.config import settings
from app.core.security import get_current_user
from app.models.meeting import MeetingInDB, MeetingPublic
from app.repositories.meeting_repository import MeetingRepository
from app.services.export_service import export_as_csv, export_as_pdf

logger = logging.getLogger(__name__)

router = APIRouter(tags=["export", "share"])


async def _get_owned_meeting(
    meeting_id: str,
    current_user: dict,
    repo: MeetingRepository,
) -> MeetingInDB:
    """Fetches a meeting and verifies ownership. Raises 404/403 on failure."""
    meeting = await repo.get_by_id(meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail=f"Meeting {meeting_id} not found")
    if meeting.uploaded_by != current_user["sub"]:
        raise HTTPException(status_code=403, detail="You do not have access to this meeting")
    return meeting


@router.get("/meetings/{meeting_id}/export")
async def export_meeting(
    meeting_id: str,
    format: str = Query(..., pattern="^(pdf|csv)$"),
    current_user: dict = Depends(get_current_user),
    repo: MeetingRepository = Depends(get_meeting_repository),
):
    """Exports a processed meeting as PDF or CSV. Ownership-checked."""
    meeting = await _get_owned_meeting(meeting_id, current_user, repo)

    if meeting.status != "processed":
        raise HTTPException(status_code=400, detail="Only processed meetings can be exported")

    safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in meeting.title).strip() or "meeting"

    if format == "csv":
        content = export_as_csv(meeting)
        return StreamingResponse(
            BytesIO(content),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.csv"'},
        )
    else:
        content = export_as_pdf(meeting)
        return StreamingResponse(
            BytesIO(content),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.pdf"'},
        )


@router.post("/meetings/{meeting_id}/share")
async def share_meeting(
    meeting_id: str,
    current_user: dict = Depends(get_current_user),
    repo: MeetingRepository = Depends(get_meeting_repository),
):
    """Generates a public share link for a processed meeting."""
    meeting = await _get_owned_meeting(meeting_id, current_user, repo)

    if meeting.status != "processed":
        raise HTTPException(status_code=400, detail="Only processed meetings can be shared")

    token = uuid.uuid4().hex
    await repo.update_fields(meeting_id, {"share_token": token, "is_public": True})

    frontend_url = settings.cors_origins_list[0] if settings.cors_origins_list else "http://localhost:5173"
    share_url = f"{frontend_url}/shared/{token}"
    return {"share_url": share_url}


@router.delete("/meetings/{meeting_id}/share")
async def unshare_meeting(
    meeting_id: str,
    current_user: dict = Depends(get_current_user),
    repo: MeetingRepository = Depends(get_meeting_repository),
):
    """Revokes a previously generated share link."""
    meeting = await _get_owned_meeting(meeting_id, current_user, repo)

    if not meeting.share_token:
        raise HTTPException(status_code=400, detail="Meeting is not currently shared")

    await repo.update_fields(meeting_id, {"share_token": None, "is_public": False})
    return {"detail": "Share link revoked"}


@router.get("/shared/{token}", response_model=MeetingPublic)
async def get_shared_meeting(
    token: str,
    repo: MeetingRepository = Depends(get_meeting_repository),
):
    """Public endpoint — returns a shared meeting by token. No auth required."""
    meeting = await repo.get_by_share_token(token)
    if meeting is None:
        raise HTTPException(status_code=404, detail="This link is no longer active")
    return MeetingPublic.from_db_model(meeting)
