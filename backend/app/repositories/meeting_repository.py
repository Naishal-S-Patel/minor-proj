"""
MeetingRepository — the ONLY place in the codebase that issues MongoDB
queries for meetings.

Why isolate DB access like this:
    Without this layer, it's tempting to sprinkle `db.meetings.find_one(...)`
    calls directly inside API route handlers. That works for a demo, but it
    means:
      1. Swapping databases later (e.g. Mongo -> Postgres) requires hunting
         through every route file.
      2. Business logic (services/) becomes tightly coupled to MongoDB's
         query syntax and ObjectId quirks, making it hard to unit test
         without a real database running.
      3. There's no single place to add cross-cutting concerns like query
         logging, caching, or retry logic.

    By funneling every query through this class, `services/` and `api/` only
    ever talk to plain Python objects (MeetingInDB), never to bson/ObjectId
    or raw Mongo query dicts.
"""

import logging
from datetime import datetime, timezone, timedelta

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.meeting import (
    MeetingInDB,
    MeetingSearchResult,
    MeetingStatus,
    AnalyticsOverview,
    KeywordFrequency,
    PendingTask,
    WeeklyCount,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "meetings"


class MeetingRepository:
    """
    Encapsulates all CRUD operations for the `meetings` collection.

    Instantiated per-request via FastAPI's dependency injection (see
    api/dependencies.py), holding a reference to the shared database object.
    """

    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._collection = database[COLLECTION_NAME]

    @staticmethod
    def _doc_to_model(doc: dict) -> MeetingInDB:
        """
        Converts a raw MongoDB document into our typed MeetingInDB model.

        This is the ONE place that knows Mongo stores the id as `_id`
        (an ObjectId) while the rest of the app just wants a plain string
        `id`. Keeping that translation here means no other file needs to
        import bson.ObjectId at all.
        """
        doc = dict(doc)  # avoid mutating the caller's dict
        doc["id"] = str(doc.pop("_id"))

        # Backfill missing `id` on legacy action items that were stored
        # before the id field was added to the ActionItem model. Uses
        # deterministic ids (position-based) so the frontend can toggle
        # them via set_action_item_done.
        if "action_items" in doc and doc["action_items"]:
            for i, item in enumerate(doc["action_items"]):
                if isinstance(item, dict) and "id" not in item:
                    item["id"] = f"_legacy_{i}"

        return MeetingInDB(**doc)

    async def create(self, meeting: MeetingInDB) -> MeetingInDB:
        """Inserts a new meeting document and returns it with its assigned id."""
        payload = meeting.model_dump(exclude={"id"})
        result = await self._collection.insert_one(payload)
        logger.info("Created meeting id=%s title=%r", result.inserted_id, meeting.title)
        return meeting.model_copy(update={"id": str(result.inserted_id)})

    async def get_by_id(self, meeting_id: str) -> MeetingInDB | None:
        """
        Fetches a single meeting by id.

        Returns None (not an exception) if not found or if the id string
        isn't even a valid ObjectId — callers decide what "not found" means
        for their context (404 in an API route, a log warning in a
        background job, etc.) rather than this layer making that decision.
        """
        try:
            object_id = ObjectId(meeting_id)
        except InvalidId:
            logger.warning("get_by_id called with malformed id=%r", meeting_id)
            return None

        doc = await self._collection.find_one({"_id": object_id})
        return self._doc_to_model(doc) if doc else None

    async def list_by_user(self, uploaded_by: str, limit: int = 50) -> list[MeetingInDB]:
        """Returns the most recent meetings for a given user, newest first."""
        cursor = (
            self._collection.find({"uploaded_by": uploaded_by})
            .sort("created_at", -1)
            .limit(limit)
        )
        return [self._doc_to_model(doc) async for doc in cursor]

    async def update_status(
        self,
        meeting_id: str,
        status: MeetingStatus,
        error_message: str | None = None,
    ) -> bool:
        """
        Updates a meeting's processing status (and optionally an error
        message if the pipeline failed).

        Returns True if a document was actually modified, False otherwise —
        callers use this to detect "meeting_id didn't exist" without a
        separate lookup.
        """
        update_fields: dict = {
            "status": status.value,
            "updated_at": datetime.now(timezone.utc),
        }
        if error_message is not None:
            update_fields["error_message"] = error_message

        try:
            object_id = ObjectId(meeting_id)
        except InvalidId:
            return False

        result = await self._collection.update_one(
            {"_id": object_id}, {"$set": update_fields}
        )
        return result.modified_count > 0

    async def update_fields(self, meeting_id: str, fields: dict) -> bool:
        """
        Generic partial update, used by the processing pipeline to write
        transcript/summary/action_items etc. as each stage completes.

        Kept generic (vs. one method per field) because the pipeline writes
        several optional fields at different stages — one method per field
        would mean constant repository changes every time Phase 3 adds a
        new extracted field.
        """
        fields = {**fields, "updated_at": datetime.now(timezone.utc)}
        try:
            object_id = ObjectId(meeting_id)
        except InvalidId:
            return False

        result = await self._collection.update_one({"_id": object_id}, {"$set": fields})
        return result.modified_count > 0

    async def get_by_share_token(self, token: str) -> MeetingInDB | None:
        """Fetches a meeting by its share token. Used by the public share endpoint."""
        doc = await self._collection.find_one({"share_token": token, "is_public": True})
        return self._doc_to_model(doc) if doc else None

    async def set_action_item_done(
        self, meeting_id: str, item_id: str, done: bool
    ) -> bool:
        """
        Toggles a single action item's completion state, addressed by its
        stable `id` (assigned at extraction time -- see extraction_worker.py).

        For legacy action items stored without `id` fields, the frontend
        receives deterministic ids like `_legacy_0`, `_legacy_1` from
        _doc_to_model. This method detects those and performs the toggle
        by array index position, backfilling the real id into MongoDB at
        the same time so future lookups work.

        Returns True if the toggle took effect; False otherwise.
        """
        try:
            object_id = ObjectId(meeting_id)
        except InvalidId:
            return False

        # Standard path: item has a real id field
        result = await self._collection.update_one(
            {"_id": object_id, "action_items.id": item_id},
            {
                "$set": {
                    "action_items.$[elem].done": done,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            array_filters=[{"elem.id": item_id}],
        )
        if result.matched_count > 0:
            return True

        # Legacy path: item_id is like "_legacy_N" — toggle by position
        if item_id.startswith("_legacy_"):
            try:
                index = int(item_id.split("_", 2)[2])
            except (IndexError, ValueError):
                return False

            # Use positional index to update, and backfill the id at the same time
            result = await self._collection.update_one(
                {"_id": object_id},
                {
                    "$set": {
                        f"action_items.{index}.done": done,
                        f"action_items.{index}.id": f"_backfilled_{index}",
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
            return result.modified_count > 0

        return False

    async def text_search(self, user_id: str, query: str, limit: int = 20) -> list[MeetingSearchResult]:
        """
        Searches meetings by text content. Uses Atlas $search when enabled,
        falls back to regex for local dev.
        """
        if settings.use_atlas_search:
            return await self._atlas_search(user_id, query, limit)
        return await self._regex_search(user_id, query, limit)

    async def _atlas_search(self, user_id: str, query: str, limit: int) -> list[MeetingSearchResult]:
        """MongoDB Atlas $search aggregation pipeline."""
        pipeline = [
            {
                "$search": {
                    "index": settings.atlas_search_index,
                    "compound": {
                        "must": [
                            {
                                "text": {
                                    "query": query,
                                    "path": ["title", "summary", "cleaned_transcript", "keywords"],
                                }
                            }
                        ],
                        "filter": [
                            {"equals": {"path": "uploaded_by", "value": user_id}}
                        ],
                    },
                    "highlight": {"path": ["title", "summary", "cleaned_transcript"]},
                }
            },
            {"$limit": limit},
            {
                "$project": {
                    "_id": 1,
                    "title": 1,
                    "status": 1,
                    "created_at": 1,
                    "summary": 1,
                    "sentiment": 1,
                    "score": {"$meta": "searchScore"},
                    "highlight": {"$meta": "searchHighlights"},
                }
            },
        ]
        cursor = self._collection.aggregate(pipeline)
        results = []
        async for doc in cursor:
            highlight_text = None
            if doc.get("highlight") and doc["highlight"].get("highlights"):
                for h in doc["highlight"]["highlights"]:
                    if h.get("texts"):
                        highlight_text = "".join(
                            t["value"] if not t.get("highlight") else t["value"]
                            for t in h["texts"]
                        )
                        break
            results.append(MeetingSearchResult(
                id=str(doc["_id"]),
                title=doc["title"],
                status=doc["status"],
                created_at=doc["created_at"],
                summary=doc.get("summary"),
                sentiment=doc.get("sentiment"),
                highlight=highlight_text,
                score=doc.get("score", 0.0),
            ))
        return results

    async def _regex_search(self, user_id: str, query: str, limit: int) -> list[MeetingSearchResult]:
        """Regex fallback for local dev (no Atlas required)."""
        import re
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        cursor = (
            self._collection.find({"uploaded_by": user_id})
            .sort("created_at", -1)
            .limit(200)
        )
        results = []
        async for doc in cursor:
            searchable = " ".join([
                doc.get("title", ""),
                doc.get("summary", "") or "",
                doc.get("cleaned_transcript", "") or "",
                " ".join(doc.get("keywords", [])),
            ])
            if pattern.search(searchable):
                highlight = None
                for field in ["summary", "cleaned_transcript"]:
                    text = doc.get(field, "")
                    if text and pattern.search(text):
                        match = pattern.search(text)
                        start = max(0, match.start() - 40)
                        end = min(len(text), match.end() + 40)
                        snippet = text[start:end]
                        highlight = pattern.sub(lambda m: f"<em>{m.group()}</em>", snippet)
                        break
                results.append(MeetingSearchResult(
                    id=str(doc["_id"]),
                    title=doc["title"],
                    status=doc["status"],
                    created_at=doc["created_at"],
                    summary=doc.get("summary"),
                    sentiment=doc.get("sentiment"),
                    highlight=highlight,
                    score=1.0,
                ))
                if len(results) >= limit:
                    break
        return results

    async def get_analytics_overview(self, user_id: str) -> AnalyticsOverview:
        """
        Computes aggregated analytics for a user in a single MongoDB
        aggregation pipeline. Returns sensible defaults when the user
        has no processed meetings.
        """
        pipeline = [
            {"$match": {"uploaded_by": user_id}},
            {
                "$facet": {
                    "totals": [
                        {
                            "$group": {
                                "_id": None,
                                "total": {"$sum": 1},
                                "processed": {
                                    "$sum": {"$cond": [{"$eq": ["$status", "processed"]}, 1, 0]}
                                },
                            }
                        }
                    ],
                    "sentiment": [
                        {"$match": {"status": "processed", "sentiment": {"$ne": None}}},
                        {
                            "$group": {
                                "_id": "$sentiment",
                                "count": {"$sum": 1},
                            }
                        },
                    ],
                    "keywords": [
                        {"$match": {"status": "processed"}},
                        {"$unwind": "$keywords"},
                        {"$group": {"_id": "$keywords", "count": {"$sum": 1}}},
                        {"$sort": {"count": -1}},
                        {"$limit": 15},
                    ],
                    "pending_tasks": [
                        {"$match": {"status": "processed"}},
                        {"$unwind": "$action_items"},
                        {"$match": {"action_items.done": False}},
                        {
                            "$project": {
                                "_id": 0,
                                "meeting_id": {"$toString": "$_id"},
                                "meeting_title": "$title",
                                "person": "$action_items.person",
                                "task": "$action_items.task",
                                "item_id": "$action_items.id",
                                "deadline": "$action_items.deadline",
                            }
                        },
                        {"$limit": 20},
                    ],
                    "weekly": [
                        {"$match": {"status": "processed"}},
                        {
                            "$group": {
                                "_id": {
                                    "$dateToString": {
                                        "format": "%Y-%m-%d",
                                        "date": {
                                            "$subtract": [
                                                "$created_at",
                                                {
                                                    "$multiply": [
                                                        {"$dayOfWeek": "$created_at"},
                                                        86400000,
                                                    ]
                                                },
                                            ]
                                        },
                                    }
                                },
                                "count": {"$sum": 1},
                            }
                        },
                        {"$sort": {"_id": -1}},
                        {"$limit": 8},
                    ],
                }
            },
        ]

        cursor = self._collection.aggregate(pipeline)
        result = await cursor.next()

        # Parse totals
        totals = result["totals"][0] if result["totals"] else {"total": 0, "processed": 0}

        # Parse sentiment
        sentiment_breakdown: dict[str, int] = {"positive": 0, "neutral": 0, "negative": 0}
        for doc in result["sentiment"]:
            sentiment_breakdown[doc["_id"]] = doc["count"]

        # Parse keywords
        top_keywords = [KeywordFrequency(keyword=doc["_id"], count=doc["count"]) for doc in result["keywords"]]

        # Parse pending tasks
        pending_tasks = [
            PendingTask(
                meeting_id=doc["meeting_id"],
                meeting_title=doc["meeting_title"],
                person=doc["person"],
                task=doc["task"],
                item_id=doc["item_id"],
                deadline=doc.get("deadline"),
            )
            for doc in result["pending_tasks"]
        ]

        # Parse weekly counts - reverse to chronological order
        weekly_raw = result["weekly"]
        weekly_raw.reverse()
        weekly_counts = [
            WeeklyCount(week=doc["_id"][5:10] if len(doc["_id"]) >= 10 else doc["_id"], count=doc["count"])
            for doc in weekly_raw
        ]

        return AnalyticsOverview(
            total_meetings=totals["total"],
            processed_meetings=totals["processed"],
            sentiment_breakdown=sentiment_breakdown,
            top_keywords=top_keywords,
            pending_tasks=pending_tasks,
            weekly_counts=weekly_counts,
        )
