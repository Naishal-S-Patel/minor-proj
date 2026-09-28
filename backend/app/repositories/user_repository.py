"""
UserRepository — the ONLY place in the codebase that issues MongoDB queries
for the `users` collection.

Follows exactly the same pattern as MeetingRepository:
  - All ObjectId↔string translation happens here, nowhere else.
  - Service/route code only ever sees plain Python objects (UserInDB).
  - One method per operation — no dynamic query building.

The key operation is `upsert_by_google_sub`: called once per login, it
creates the user on first login and updates mutable profile fields (display
name, picture URL) on subsequent logins. Using upsert instead of
insert+conditional keeps the login path idempotent and race-condition-free.
"""

import logging
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.user import UserInDB

logger = logging.getLogger(__name__)

COLLECTION_NAME = "users"


class UserRepository:
    """
    Encapsulates all CRUD operations for the `users` collection.

    Instantiated per-request via FastAPI's dependency injection
    (see api/dependencies.py).
    """

    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._collection = database[COLLECTION_NAME]

    @staticmethod
    def _doc_to_model(doc: dict) -> UserInDB:
        """
        Converts a raw MongoDB document into our typed UserInDB model.
        The only place that knows Mongo stores `_id` as ObjectId.
        """
        doc = dict(doc)
        doc["id"] = str(doc.pop("_id"))
        return UserInDB(**doc)

    async def upsert_by_google_sub(self, user: UserInDB) -> UserInDB:
        """
        Insert the user if they don't exist yet (first login), or update
        their mutable profile fields (display_name, picture_url) if they do.

        Uses MongoDB's `$setOnInsert` + `$set` pattern so `created_at` is
        only written on the very first insert, never overwritten on updates.

        Returns the full UserInDB (with Mongo-assigned `id`) after the
        upsert completes.
        """
        now = datetime.now(timezone.utc)
        result = await self._collection.find_one_and_update(
            {"google_sub": user.google_sub},
            {
                "$set": {
                    "display_name": user.display_name,
                    "picture_url": user.picture_url,
                    "email": user.email,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "google_sub": user.google_sub,
                    "created_at": now,
                },
            },
            upsert=True,
            return_document=True,  # return the document AFTER update
        )
        logger.info(
            "Upserted user google_sub=%s email=%s",
            user.google_sub,
            user.email,
        )
        return self._doc_to_model(result)

    async def get_by_google_sub(self, google_sub: str) -> UserInDB | None:
        """Fetches a user by their stable Google sub identifier, or None."""
        doc = await self._collection.find_one({"google_sub": google_sub})
        return self._doc_to_model(doc) if doc else None

    async def get_by_id(self, user_id: str) -> UserInDB | None:
        """Fetches a user by their MongoDB document id, or None."""
        try:
            object_id = ObjectId(user_id)
        except InvalidId:
            return None
        doc = await self._collection.find_one({"_id": object_id})
        return self._doc_to_model(doc) if doc else None
