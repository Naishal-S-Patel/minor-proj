"""
Analytics API router.

Provides an aggregated overview of a user's meeting history:
sentiment breakdown, keyword frequency, pending tasks, and weekly volume.
"""

import logging

from fastapi import APIRouter, Depends

from app.api.dependencies import get_meeting_repository
from app.core.security import get_current_user
from app.models.meeting import AnalyticsOverview
from app.repositories.meeting_repository import MeetingRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=AnalyticsOverview)
async def get_analytics_overview(
    current_user: dict = Depends(get_current_user),
    repo: MeetingRepository = Depends(get_meeting_repository),
) -> AnalyticsOverview:
    """
    Returns aggregated analytics across all of the user's processed meetings.
    Returns sensible zeros/empty lists when the user has no processed meetings.
    """
    return await repo.get_analytics_overview(user_id=current_user["sub"])
