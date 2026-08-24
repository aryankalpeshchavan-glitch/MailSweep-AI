"""Central application configuration.

Every runtime value flows through :class:`Settings`. Values originate from
environment variables (with optional `.env` file support) and are validated
once, at startup, so misconfiguration fails loudly instead of mid-request.

* Production is strict: missing/weak ``SECRET_KEY``, missing Google OAuth
  credentials, a non-PostgreSQL database, or a missing Redis URL abort startup.
* Development/test are forgiving: SQLite fallback, ephemeral secret (logged).
* Secret *values* never appear in validation error messages.
"""

from __future__ import annotations

import logging
import secrets
from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_ENV_FILES = (".env", "../.env")

_EPHEMERAL_SECRET_WARNING = (
    "SECRET_KEY is empty - generated an EPHEMERAL in-memory key for this "
    "process. Sessions and encrypted OAuth tokens will NOT survive a restart. "
    "Set SECRET_KEY in your environment."
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ------------------------------------------------------------------ core
    APP_NAME: str = "MailSweep AI"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    LOG_LEVEL: str = "INFO"
    #: Verbose error bodies in development only. Never set in production.
    DEBUG: bool = False
    #: Root cryptographic secret (HMAC signing + Fernet key derivation).
    SECRET_KEY: str = ""
    #: Public base URL of THIS backend, no trailing slash.
    BASE_URL: str = "http://localhost:8000"
    #: Comma-separated origins allowed for CORS and CSRF Origin checking.
    FRONTEND_ORIGINS: str = "http://localhost:3000"

    # ------------------------------------------------------------ persistence
    DATABASE_URL: str = ""  # empty in dev => SQLite fallback; prod => Postgres
    REDIS_URL: str = ""  # empty in dev => inline jobs, no rate limiting

    # ----------------------------------------------------------- google oauth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    #: Usually empty: derived from BASE_URL.
    GOOGLE_REDIRECT_URI: str = ""

    # --------------------------------------------------------------- ai (opt)
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-3-5-haiku-latest"
    AI_MAX_MESSAGES_PER_JOB: int = 200

    # ----------------------------------------------------------------- tuning
    MAX_MESSAGES_PER_ANALYSIS: int = 20_000
    GMAIL_PAGE_SIZE: int = 500
    GMAIL_FETCH_CONCURRENCY: int = 8
    DEFAULT_RETENTION_YEARS: int = 3
    SESSION_TTL_DAYS: int = 14
    RATE_LIMIT_AUTH_PER_MINUTE: int = 10
    RATE_LIMIT_EXPENSIVE_PER_MINUTE: int = 5

    # ------------------------------------------------------------- validators
    @model_validator(mode="after")
    def _validate_environment_requirements(self) -> Settings:
        if not self.is_production:
            return self
        problems: list[str] = []
        if len(self.SECRET_KEY) < 32:
            problems.append("SECRET_KEY must be set with at least 32 characters")
        if not self.GOOGLE_CLIENT_ID or not self.GOOGLE_CLIENT_SECRET:
            problems.append("Google OAuth credentials are required")
        if self.normalized_database_url.startswith("sqlite"):
            problems.append("DATABASE_URL must point to PostgreSQL")
        if not self.REDIS_URL:
            problems.append("REDIS_URL is required")
        if problems:
            # Names only - never values.
            raise ValueError(
                "Refusing to start with invalid production configuration: "
                + "; ".join(problems)
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def normalized_database_url(self) -> str:
        """SQLAlchemy-ready URL; rewrites Render/Railway-style schemes to pg8000."""
        url = self.DATABASE_URL.strip()
        if not url:
            return "sqlite:///./mailsweep-dev.db"
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+pg8000://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+pg8000://", 1)
        return url

    @property
    def cors_allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.FRONTEND_ORIGINS.split(",") if o.strip()]

    @property
    def resolved_google_redirect_uri(self) -> str:
        return self.GOOGLE_REDIRECT_URI or f"{self.BASE_URL}/api/auth/google/callback"

    @property
    def ai_enabled(self) -> bool:
        return bool(self.ANTHROPIC_API_KEY)

    def effective_secret_key(self) -> bytes:
        """Bytes for HMAC signing and encryption-key derivation.

        Dev/test with no SECRET_KEY get a per-process ephemeral key (once,
        with a loud warning). Production refuses to boot without a real key.
        """
        global _EPHEMERAL_SECRET  # noqa: PLW0603
        if self.SECRET_KEY:
            return self.SECRET_KEY.encode("utf-8")
        if _EPHEMERAL_SECRET is None:
            _EPHEMERAL_SECRET = secrets.token_bytes(48)
            logger.warning(_EPHEMERAL_SECRET_WARNING)
        return _EPHEMERAL_SECRET


_EPHEMERAL_SECRET: bytes | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached accessor for workers/scripts. The API injects Settings via
    ``create_app()`` so tests stay process-state-free."""
    return Settings()

