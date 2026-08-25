"""Retry discipline + access-token lifecycle tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.auth import google_oauth
from app.auth.service import upsert_oauth_identity
from app.auth.tokens import get_valid_access_token
from app.core.errors import ExternalServiceError
from app.gmail.retry import (
    RateLimitedError,
    ServerUnavailableError,
    execute_with_retry,
)
from sqlalchemy.orm import Session

from tests.conftest import make_test_settings

_SECRET = b"t" * 48
_SETTINGS = make_test_settings()


# ---------------------------------------------------------------------------
# retry discipline


def test_retry_succeeds_after_transient_failures():
    sleeps: list[float] = []
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RateLimitedError(retry_after=0.5)
        return "payload"

    result = execute_with_retry(
        flaky, operation_name="test", sleep=sleeps.append, max_attempts=5
    )

    assert result == "payload"
    assert calls["n"] == 3
    # Both failures carried Retry-After=0.5; the header wins over backoff:
    assert sleeps == [0.5, 0.5]


def test_retry_exponential_backoff_with_jitter_when_no_header():
    sleeps: list[float] = []
    attempts = {"n": 0}

    def always_503():
        attempts["n"] += 1
        raise ServerUnavailableError()

    with pytest.raises(ServerUnavailableError):
        execute_with_retry(
            always_503, operation_name="test", sleep=sleeps.append, max_attempts=4
        )

    assert attempts["n"] == 4
    assert len(sleeps) == 3
    for observed, base in zip(sleeps, [1.0, 2.0, 4.0], strict=False):
        assert base <= observed <= base * 1.75 + 0.01


def test_retry_never_retries_client_errors():
    class Forbidden(RuntimeError):
        class resp:  # noqa: N801 - duck-typed namespace
            status = 403
            headers: dict = {}

    calls = {"n": 0}

    def forbidden():
        calls["n"] += 1
        raise Forbidden()

    with pytest.raises(Forbidden):
        execute_with_retry(forbidden, operation_name="test", sleep=lambda _: None)
    assert calls["n"] == 1  # immediate propagation, no retry


# ---------------------------------------------------------------------------
# access-token lifecycle (single explicit refresh path)


def _seed_connection(db: Session, *, expires_at: datetime | None):
    user, connection = upsert_oauth_identity(
        db,
        sub="sub-tok",
        email="tok@example.com",
        display_name=None,
        avatar_url=None,
        scope="scope",
        access_token="old-access-token",
        refresh_token="refresh-token-value",
        expires_in=3600,
        secret_key=_SECRET,
    )
    connection.token_expires_at = expires_at
    db.commit()
    return user


def test_valid_token_returned_without_network_call(db_engine, monkeypatch):
    db = Session(bind=db_engine)
    future = datetime.now(UTC) + timedelta(hours=1)
    user = _seed_connection(db, expires_at=future)

    def boom(*args, **kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(google_oauth, "_post_form", boom)
    token = get_valid_access_token(
        db, user=user, secret_key=_SECRET, settings=_SETTINGS
    )
    assert token == "old-access-token"


def test_expired_token_is_refreshed_and_persisted_encrypted(db_engine, monkeypatch):
    db = Session(bind=db_engine)
    past = datetime.now(UTC) - timedelta(minutes=30)
    user = _seed_connection(db, expires_at=past)

    seen: dict = {}

    def fake_post(url, data, *, timeout=15.0, **_):
        seen["url"], seen["data"] = url, dict(data)
        return {"access_token": "brand-new-access", "expires_in": 3600}

    monkeypatch.setattr(google_oauth, "_post_form", fake_post)

    token = get_valid_access_token(
        db, user=user, secret_key=_SECRET, settings=_SETTINGS
    )

    assert token == "brand-new-access"
    assert seen["data"]["refresh_token"] == "refresh-token-value"
    assert seen["data"]["grant_type"] == "refresh_token"

    from app.models import OAuthConnection

    conn = db.query(OAuthConnection).one()
    assert "brand-new-access" not in (conn.access_token_encrypted or "")  # ciphertext only
    assert conn.token_expires_at is not None and conn.token_expires_at > datetime.now(UTC)


def test_disconnected_account_raises_helpful_error(db_engine):
    db = Session(bind=db_engine)
    user = _seed_connection(db, expires_at=None)
    user.oauth_connection.status = "REVOKED"
    db.commit()

    with pytest.raises(ExternalServiceError, match="Reconnect"):
        get_valid_access_token(
            db, user=user, secret_key=_SECRET, settings=_SETTINGS
        )
