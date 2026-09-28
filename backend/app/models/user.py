"""
User domain models.

Why this exists:
    Separates the user data shape from the repository and API layers.
    UserInDB is the canonical representation stored in MongoDB — other
    layers translate to/from it.
"""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class UserInDB(BaseModel):
    """
    Full user document as stored in MongoDB.

    `google_sub` is Google's stable, unique identifier for the user — it
    never changes, unlike email or display name. Used as the natural key
    for upserts on login.
    """
    id: str = ""
    google_sub: str
    email: str
    display_name: str = ""
    picture_url: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
