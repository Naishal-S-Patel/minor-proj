"""
Application entrypoint.

Wires together: logging, DB lifecycle, CORS, and route registration.
Run locally with:  uvicorn app.main:app --reload
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api import analytics, auth, chat, export, health, meetings
from app.core.config import settings
from app.core.database import close_mongo_connection, connect_to_mongo
from app.core.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages startup/shutdown using FastAPI's recommended lifespan pattern
    (replaces the older, now-deprecated @app.on_event("startup") decorators).

    Code before `yield` runs once at startup (before the app accepts any
    requests). Code after `yield` runs once at shutdown (e.g. when you
    Ctrl+C the dev server, or when the platform gracefully stops the
    container). This is where connection pools should be opened and closed
    — exactly once, not per-request.
    """
    logger.info("Starting %s (environment=%s)", settings.app_name, settings.environment)
    if not settings.testing:
        await connect_to_mongo()
    yield
    if not settings.testing:
        await close_mongo_connection()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.app_name,
    description="Automated meeting transcription, summarization, and insight extraction.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS: without this, a browser-based frontend running on a different origin
# (e.g. localhost:5173 talking to localhost:8000, or later your Vercel
# domain talking to your Render domain) will have every request blocked by
# the browser's same-origin policy. allow_origins is deliberately read from
# settings (not hardcoded "*") so production can lock this to only the real
# frontend domain — allowing "*" in production would let any website make
# authenticated requests to your API on a logged-in user's behalf.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SessionMiddleware is required for the OAuth CSRF state cookie.
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret_key)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(meetings.router)
app.include_router(chat.router)
app.include_router(analytics.router)
app.include_router(export.router)
