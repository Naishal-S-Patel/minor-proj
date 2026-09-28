"""
FastAPI dependency providers.

Why this pattern:
    FastAPI's `Depends()` system lets route handlers declare what they need
    (e.g. "a MeetingRepository") without knowing how it's constructed. This
    is dependency injection — it means:
      1. Routes stay thin and only import what they use.
      2. In tests, you can override `get_meeting_repository` to return a
         fake/mock repository, letting you test route logic without a real
         MongoDB connection at all.
"""

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database
from app.repositories.meeting_repository import MeetingRepository
from app.repositories.user_repository import UserRepository


def get_meeting_repository() -> MeetingRepository:
    """
    Provides a MeetingRepository instance bound to the shared database.

    Declared as a plain function (not async) because constructing the
    repository object itself does no I/O — it just wraps a reference to the
    already-connected database. FastAPI supports sync dependency functions
    for exactly this kind of cheap, non-blocking setup.
    """
    database: AsyncIOMotorDatabase = get_database()
    return MeetingRepository(database)


def get_user_repository() -> UserRepository:
    """Provides a UserRepository instance bound to the shared database."""
    database: AsyncIOMotorDatabase = get_database()
    return UserRepository(database)
