"""
Health check endpoint.

Why this matters in production (not just a nice-to-have):
    Deployment platforms (Render, Vercel, k8s, AWS ELB, etc.) poll a health
    endpoint to decide whether an instance is ready to receive traffic, and
    to detect and restart instances that have crashed or hung. Without one,
    a platform has no reliable way to know your app is actually alive versus
    just "the process exists but is deadlocked."

    We check the database connection here too — a common production bug is
    a "healthy" app server that's actually lost its DB connection and is
    silently failing every real request. A true health check should catch that.
"""

import logging

from fastapi import APIRouter

from app.core.database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    """
    Returns 200 with status details if the app and its database connection
    are both healthy. Returns a degraded status (still 200, but flagged) if
    the DB ping fails, so monitoring can alert without the whole endpoint
    looking like a hard outage.
    """
    db_status = "ok"
    try:
        database = get_database()
        await database.command("ping")
    except Exception as exc:  # noqa: BLE001 - intentionally broad: this
        # covers both "database.command() failed" (real connectivity issue,
        # e.g. Mongo down or unreachable) and "get_database() raised
        # RuntimeError because connect_to_mongo() never ran" (e.g. app is
        # running with TESTING=true). Both cases mean the same thing from a
        # health check's perspective: the database isn't currently usable.
        # We deliberately don't crash the health check itself over this.
        logger.warning("Health check DB status check failed: %s", exc)
        db_status = "unreachable"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "database": db_status,
    }
