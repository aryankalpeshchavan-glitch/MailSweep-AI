"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth.service import resolve_session
from app.core.errors import AuthenticationError
from app.core.logging import bind_user_id
from app.db.session import get_db
from app.models import User

#: Opaque session cookie name (value is a random token, DB stores its hash).
SESSION_COOKIE_NAME = "mailsweep_session"


def get_current_user_optional(
    request: Request, db: Session = Depends(get_db)
) -> User | None:
    """Resolve the session cookie to a user, or None for anonymous access."""
    user = resolve_session(db, request.cookies.get(SESSION_COOKIE_NAME))
    if user is not None:
        bind_user_id(user.id)
    return user


def get_current_user(user: User | None = Depends(get_current_user_optional)) -> User:
    """Require an authenticated user (401 otherwise)."""
    if user is None:
        raise AuthenticationError("Sign in to continue.")
    return user


def set_session_cookie(response, raw_token: str, settings) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=settings.SESSION_TTL_DAYS * 86_400,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
