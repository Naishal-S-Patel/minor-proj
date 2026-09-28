"""
Authentication API router.

Handles the Google OAuth 2.0 flow:
  1. GET /auth/google         — redirect to Google consent screen
  2. GET /auth/google/callback — exchange code for tokens, upsert user, set JWT cookie
  3. POST /auth/logout        — clear the JWT cookie
  4. GET /auth/me             — return current user info from JWT
"""

import logging
import secrets
import urllib.parse

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from starlette.responses import RedirectResponse

from app.api.dependencies import get_user_repository
from app.core.config import settings
from app.core.security import ACCESS_TOKEN_COOKIE, create_access_token, get_current_user
from app.models.user import UserInDB
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# ---------- OAuth client setup ----------

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


# ---------- Routes ----------


@router.get("/dev-login")
@router.post("/dev-login")
async def dev_login(
    repo: UserRepository = Depends(get_user_repository),
):
    """
    Bypass login for development / testing without requiring Google OAuth setup.
    Upserts a mock/guest user in MongoDB and sets the auth cookie.
    """
    dev_user = UserInDB(
        google_sub="mock_dev_user_sub",
        email="dev.user@meetingai.local",
        display_name="Demo User",
        picture_url="https://api.dicebear.com/7.x/bottts/svg?seed=meetingai",
    )
    db_user = await repo.upsert_by_google_sub(dev_user)

    jwt_token = create_access_token(
        user_id=db_user.id,
        email=db_user.email,
        display_name=db_user.display_name,
        picture_url=db_user.picture_url,
        google_sub=db_user.google_sub,
    )

    frontend_url = settings.cors_origins_list[0] if settings.cors_origins_list else "http://localhost:5173"
    response = RedirectResponse(url=frontend_url + "/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=jwt_token,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        max_age=settings.jwt_expiry_minutes * 60,
        path="/",
    )
    return response


@router.get("/google")
async def google_login(request: Request):
    """
    Redirects the browser to Google's OAuth consent screen.

    Stores a CSRF `state` token in the session cookie so the callback
    can verify the response came from Google.
    """
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
        )

    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state

    redirect_uri = settings.google_redirect_uri or str(request.url_for("google_callback"))
    return await oauth.google.authorize_redirect(request, redirect_uri, state=state)


@router.get("/google/callback", name="google_callback")
async def google_callback(
    request: Request,
    repo: UserRepository = Depends(get_user_repository),
):
    """
    Handles the OAuth callback from Google.

    Exchanges the authorization code for tokens, fetches user info,
    upserts the user in MongoDB, signs a JWT, and sets it as an httpOnly
    cookie before redirecting to the frontend.
    """
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured.",
        )

    # Verify CSRF state
    expected_state = request.session.get("oauth_state")
    received_state = request.query_params.get("state")
    if not expected_state or expected_state != received_state:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid OAuth state — possible CSRF attack",
        )

    # Exchange code for tokens
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo", {})
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch user info from Google",
        )

    # Upsert user in MongoDB
    user = UserInDB(
        google_sub=user_info["sub"],
        email=user_info.get("email", ""),
        display_name=user_info.get("name", ""),
        picture_url=user_info.get("picture", ""),
    )
    db_user = await repo.upsert_by_google_sub(user)

    # Sign JWT
    jwt_token = create_access_token(
        user_id=db_user.id,
        email=db_user.email,
        display_name=db_user.display_name,
        picture_url=db_user.picture_url,
        google_sub=db_user.google_sub,
    )

    # Set cookie and redirect to frontend root
    frontend_url = settings.cors_origins_list[0] if settings.cors_origins_list else "http://localhost:5173"
    response = RedirectResponse(url=frontend_url + "/")
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=jwt_token,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        max_age=settings.jwt_expiry_minutes * 60,
        path="/",
    )
    # Clean up session state
    request.session.pop("oauth_state", None)
    return response


@router.post("/logout")
async def logout(response: Response):
    """Clears the access token cookie."""
    response.delete_cookie(key=ACCESS_TOKEN_COOKIE, path="/")
    return {"detail": "Logged out"}


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Returns the current user's info from the JWT payload."""
    return {
        "sub": current_user.get("sub", ""),
        "email": current_user.get("email", ""),
        "display_name": current_user.get("display_name", ""),
        "picture_url": current_user.get("picture_url", ""),
    }
