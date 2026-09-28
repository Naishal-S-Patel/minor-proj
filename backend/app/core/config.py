"""
Centralized, typed application configuration.

Why this exists:
    Scattering `os.getenv("SOME_KEY")` calls across the codebase is a common
    source of production bugs — typos in env var names fail silently (you get
    None instead of an error), there's no validation, and no single place to
    see what config the app actually needs.

    Pydantic's BaseSettings solves this: it reads from environment variables
    (and a local .env file in dev), validates types, and raises a clear
    startup error if something required is missing — instead of failing
    mysteriously three requests into runtime.

Usage:
    from app.core.config import settings
    settings.mongodb_uri
"""

from functools import lru_cache
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- App metadata ---
    app_name: str = "AI Meeting Intelligence"
    environment: str = "development"  # development | staging | production
    debug: bool = True

    # --- Database ---
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "meeting_ai"

    # When true, the app skips connecting to a real MongoDB at startup.
    # Set via TESTING=true in the test environment (see tests/conftest.py).
    # This exists because FastAPI's lifespan startup runs even when tests
    # only need route-level logic via a faked repository -- without this
    # flag, every route test would require a real MongoDB just to let the
    # app boot, even tests that never touch the database at all.
    testing: bool = False

    # --- CORS ---
    # Comma-separated list of allowed frontend origins. In production this
    # should be locked to your actual deployed frontend URL, never "*".
    allowed_origins: str = "http://localhost:5173"

    # --- Auth (Phase 4) ---
    jwt_secret_key: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60 * 24  # 24 hours

    # --- Google OAuth (Phase 4) ---
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    session_secret_key: str = "dev-session-secret-change-me"

    # --- Whisper / Audio (Phase 2) ---
    whisper_provider: str = "local"  # "local" uses openai-whisper package
    whisper_model: str = "base"      # tiny, base, small, medium, large
    audio_max_size_mb: int = 25      # Max audio file size in MB
    audio_max_duration_seconds: int = 7200  # 2 hours safety cap

    # --- LLM Extraction (Phase 3) ---
    # Supports multiple LLM providers: gemini (free), groq (free), grok (paid)
    llm_provider: str = "groq"  # "gemini" or "groq" (both free) or "grok" (paid)
    gemini_api_key: str = ""      # Get free key at https://aistudio.google.com/apikey
    gemini_model: str = "gemini-3.6-flash"
    groq_api_key: str = ""        # Get FREE key at https://console.groq.com/
    groq_model: str = "llama-3.3-70b-versatile"  # Free, fast, excellent quality
    grok_api_key: str = ""        # Get key at https://console.x.ai/ ($5 minimum)
    grok_model: str = "grok-4.7"  # Latest xAI Grok model (paid)
    llm_max_output_tokens: int = 2048
    llm_request_timeout_seconds: int = 60
    llm_max_retries: int = 2

    # --- Search (Phase 5) ---
    use_atlas_search: bool = False
    atlas_search_index: str = "meeting_search"

    # --- Export (Phase 5) ---
    export_max_size_mb: int = 10

    # --- Chat (Feature 1) ---
    chat_max_question_length: int = 500

    # Tells Pydantic to read local .env files (checks both backend folder and cwd)
    model_config = SettingsConfigDict(
        env_file=(
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Splits the comma-separated origins string into a clean list."""
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """
    Returns a cached Settings instance.

    lru_cache ensures the .env file / environment is only read once per
    process, not on every single request — Settings() parsing has a real
    (if small) cost, and config doesn't change during the app's lifetime.
    """
    return Settings()


# Most of the codebase imports this directly for convenience.
settings = get_settings()
