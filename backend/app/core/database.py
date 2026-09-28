"""
MongoDB connection lifecycle management.

Why a dedicated module for this:
    We want exactly ONE MongoDB client per running application process.
    Creating a new client per-request is a classic performance bug — each
    client manages its own connection pool, and spinning up a fresh pool per
    request defeats the purpose of pooling entirely and can exhaust the
    database's max-connections limit under load.

    Motor's AsyncIOMotorClient is itself connection-pooled and safe to share
    across concurrent requests, so we create it once at app startup and reuse
    it everywhere via `get_database()`.
"""

import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

logger = logging.getLogger(__name__)

# Module-level references, populated by connect_to_mongo() at startup and
# torn down by close_mongo_connection() at shutdown. Deliberately private
# (leading underscore) — external code should go through the functions
# below, not touch these globals directly.
_client: AsyncIOMotorClient | None = None
_database: AsyncIOMotorDatabase | None = None


async def connect_to_mongo() -> None:
    """
    Establishes the MongoDB connection. Called once during FastAPI startup
    (see main.py's lifespan handler).
    """
    global _client, _database

    logger.info("Connecting to MongoDB at %s", settings.mongodb_uri.split("@")[-1])
    # .split("@")[-1] above strips any embedded credentials (user:pass@host)
    # before logging, so we never accidentally leak a connection string with
    # a password in it into log output.

    _client = AsyncIOMotorClient(settings.mongodb_uri)
    _database = _client[settings.mongodb_db_name]

    # ping is a cheap way to fail fast at startup if Mongo is unreachable,
    # rather than discovering it on the first real request from a user.
    await _client.admin.command("ping")
    logger.info("MongoDB connection established (db=%s)", settings.mongodb_db_name)


async def close_mongo_connection() -> None:
    """Cleanly closes the MongoDB connection. Called on FastAPI shutdown."""
    global _client
    if _client is not None:
        _client.close()
        logger.info("MongoDB connection closed")


def get_database() -> AsyncIOMotorDatabase:
    """
    Returns the shared database instance.

    Raises a clear error if called before connect_to_mongo() has run, instead
    of a confusing AttributeError on None deep inside a repository call.
    """
    if _database is None:
        raise RuntimeError(
            "Database not initialized. connect_to_mongo() must be called "
            "at application startup before any DB access."
        )
    return _database
