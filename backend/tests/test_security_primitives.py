"""Crypto primitive tests: encryption roundtrips, state signing, tamper detection."""

from __future__ import annotations

import time

import pytest
from app.core.config import Settings
from app.core.errors import install_error_handlers
from app.core.security import (
    decrypt_text,
    encrypt_text,
    hash_session_token,
    new_session_token,
    sign_oauth_state,
    verify_oauth_state,
)
from fastapi import FastAPI
from pydantic import ValidationError

from tests.conftest import make_test_settings

_KEY = b"k" * 48


def test_session_tokens_are_unique_and_hashable():
    a, b = new_session_token(), new_session_token()
    assert a != b
    # Hash is deterministic and never equals the raw value:
    assert hash_session_token(a) == hash_session_token(a)
    assert hash_session_token(a) != a


def test_encrypt_decrypt_roundtrip():
    token = "ya29.a0AfH6SM-example-access-token"
    ciphertext = encrypt_text(token, secret_key=_KEY)
    assert token not in ciphertext  # no plaintext leakage
    assert decrypt_text(ciphertext, secret_key=_KEY) == token


def test_decrypt_with_wrong_key_fails():
    ciphertext = encrypt_text("secret", secret_key=_KEY)
    with pytest.raises(ValueError):
        decrypt_text(ciphertext, secret_key=b"other-key".ljust(48, b"x"))


def test_oauth_state_roundtrip():
    payload = {"redirect_to": "/dashboard", "nonce": "abc"}
    state = sign_oauth_state(payload, secret_key=_KEY)
    assert verify_oauth_state(state, secret_key=_KEY) == payload


def test_oauth_state_rejects_tampering():
    state = sign_oauth_state({"a": 1}, secret_key=_KEY)
    tampered = state[:-1] + ("0" if state[-1] != "0" else "1")
    assert verify_oauth_state(tampered, secret_key=_KEY) is None


def test_oauth_state_rejects_wrong_key():
    state = sign_oauth_state({"a": 1}, secret_key=_KEY)
    assert verify_oauth_state(state, secret_key=b"w" * 48) is None


def test_oauth_state_rejects_expired(monkeypatch):
    from app.core import security as security_module

    state = sign_oauth_state({"a": 1}, secret_key=_KEY)

    class _FutureTime:
        @staticmethod
        def time() -> float:
            return time.time() + 10_000

    monkeypatch.setattr(security_module, "time", _FutureTime)
    assert verify_oauth_state(state, secret_key=_KEY) is None


# --------------------------------------------------------------------------
# Configuration validation: production must fail loudly and early.


def test_production_requires_critical_settings():
    with pytest.raises(ValidationError):
        make_test_settings(ENVIRONMENT="production")


def test_production_accepts_complete_configuration():
    settings = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="p" * 48,
        DATABASE_URL="postgresql://user:pass@db.example.com:5432/mailsweep",
        REDIS_URL="redis://redis.example.com:6379/0",
        GOOGLE_CLIENT_ID="client-id",
        GOOGLE_CLIENT_SECRET="client-secret",
    )
    assert settings.normalized_database_url == "postgresql+pg8000://user:pass@db.example.com:5432/mailsweep"
    assert settings.resolved_google_redirect_uri == "http://localhost:8000/api/auth/google/callback"


def test_database_url_scheme_normalization():
    settings = make_test_settings(DATABASE_URL="postgres://u:p@h:5432/db")
    assert settings.normalized_database_url.startswith("postgresql+pg8000://")


def test_cors_origin_parsing():
    settings = make_test_settings(FRONTEND_ORIGINS=" http://a.dev , http://b.dev ,")
    assert settings.cors_allowed_origins == ["http://a.dev", "http://b.dev"]


def test_unexpected_exceptions_are_hidden_without_debug():
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/boom")
    def boom():
        raise RuntimeError("internal SQL details leaked")

    from fastapi.testclient import TestClient

    with TestClient(app, raise_server_exceptions=False) as c:
        response = c.get("/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert "SQL" not in body["error"]["message"]
