"""
JWT authentication utilities.

Why this exists:
    Centralizes token creation, verification, and the FastAPI dependency
    that extracts the current user from the request cookie. Keeps auth
    logic out of route handlers and the OAuth flow.
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, HTTPException, Request, status
from jose import JWTError, jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

ACCESS_TOKEN_COOKIE = "access_token"


def create_access_token(
    user_id: str,
    email: str,
    display_name: str,
    picture_url: str,
    google_sub: str,
) -> str:
    """Signs a JWT containing the user's identity claims."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.jwt_expiry_minutes)
    payload = {
        "sub": user_id,
        "google_sub": google_sub,
        "email": email,
        "display_name": display_name,
        "picture_url": picture_url,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """
    Verifies a JWT's signature and expiry, returning the decoded payload.

    Raises HTTPException(401) on any failure — expired, tampered, or
    malformed token.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("sub") is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject",
            )
        return payload
    except JWTError as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


async def get_current_user(request: Request) -> dict:
    """
    FastAPI dependency — reads the JWT from the httpOnly cookie and
    returns the decoded payload dict.

    Used as: `current_user: dict = Depends(get_current_user)` in route
    handlers that require authentication.
    """
    token: str | None = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return decode_access_token(token)
