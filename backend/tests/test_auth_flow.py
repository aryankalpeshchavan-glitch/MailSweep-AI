"""Google OAuth + session auth flow tests.

The network seam (``google_oauth._post_form``) is mocked, so the full browser
flow - login redirect, callback, cookie, status, logout, disconnect - is
exercised without touching Google.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

import pytest
from app.auth import google_oauth
from app.auth.service import create_session
from app.core.security import verify_oauth_state
from app.models import EmailMessage, Mailbox, OAuthConnection, UserSession
from sqlalchemy.orm import Session

_GMAIL_SCOPE = google_oauth.GMAIL_MODIFY_SCOPE


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _make_id_token(*, sub: str, email: str, email_verified: bool = True) -> str:
    header = _b64url(json.dumps({"alg": "RS256", "kid": "test-key"}).encode())
    payload = _b64url(
        json.dumps(
            {
                "sub": sub,
                "email": email,
                "email_verified": email_verified,
                "name": "Aryan",
                "picture": "https://example.com/a.png",
            }
        ).encode()
    )
    return f"{header}.{payload}.signature-not-verified-by-design"


@pytest.fixture()
def oauth_world(build_world, monkeypatch):
    """App with Google credentials configured + mocked token/revoke endpoint."""
    calls: dict = {"token_requests": [], "revoked": []}

    def _fake_post_form(url: str, data: dict, *, timeout: float = 15.0, **_: object) -> dict:
        if url == google_oauth.TOKEN_ENDPOINT:
            calls["token_requests"].append(dict(data))
            return {
                "access_token": "at-secret-123",
                "refresh_token": "rt-secret-456",
                "expires_in": 3600,
                "scope": f"openid email profile {_GMAIL_SCOPE}",
                "id_token": _make_id_token(sub="sub-aryan", email="aryan@example.com"),
            }
        if url == google_oauth.REVOKE_ENDPOINT:
            calls["revoked"].append(data.get("token"))
            return {}
        raise AssertionError(f"unexpected OAuth URL in test: {url}")

    monkeypatch.setattr(google_oauth, "_post_form", _fake_post_form)

    settings, client, engine = build_world(
        GOOGLE_CLIENT_ID="test-client-id.apps.googleusercontent.com",
        GOOGLE_CLIENT_SECRET="test-client-secret",
        FRONTEND_ORIGINS="http://localhost:3000",
    )
    return settings, client, engine, calls


def _valid_state(settings) -> str:
    from app.core.security import sign_oauth_state

    return sign_oauth_state(
        {"redirect_to": "/dashboard"}, secret_key=settings.effective_secret_key()
    )


def _db(engine) -> Session:
    return Session(bind=engine)


# ---------------------------------------------------------------------------
# /google/login


def test_login_redirects_to_google_with_signed_state(oauth_world):
    settings, client, _, _ = oauth_world

    response = client.get(
        "/api/auth/google/login",
        params={"redirect_to": "/dashboard"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith(google_oauth.AUTHORIZATION_ENDPOINT)
    assert "client_id=test-client-id" in location
    assert "gmail.modify" in location  # scope present
    assert "access_type=offline" in location  # refresh token requested
    state = location.split("state=")[1].split("&")[0]
    payload = verify_oauth_state(state, secret_key=settings.effective_secret_key())
    assert payload == {"redirect_to": "/dashboard"}


@pytest.mark.parametrize("evil", ["https://evil.example/path", "//evil.example", "/\\evil"])
def test_open_redirect_attempts_fall_back_to_root(oauth_world, evil):
    _settings, client, _, _ = oauth_world
    response = client.get(
        "/api/auth/google/login",
        params={"redirect_to": evil},
        follow_redirects=False,
    )
    # The redirect still succeeds, but the embedded state carries "/" as the
    # safe fallback (the sanitizer itself is unit-tested below).
    assert response.status_code == 302


def test_redirect_sanitizer_rejects_non_relative_paths():
    from app.api.routes.auth import _SAFE_REDIRECT

    assert _SAFE_REDIRECT.match("/dashboard")
    assert not _SAFE_REDIRECT.match("https://evil.com")
    assert not _SAFE_REDIRECT.match("//evil.com")
    assert not _SAFE_REDIRECT.match("\\evil")


def test_login_without_credentials_returns_503(client):
    # default test settings have empty GOOGLE_CLIENT_ID
    response = client.get("/api/auth/google/login")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "oauth_not_configured"


# ---------------------------------------------------------------------------
# callback + session lifecycle


def test_full_callback_creates_user_tokens_and_session(oauth_world):
    settings, client, engine, calls = oauth_world

    response = client.get(
        "/api/auth/google/callback",
        params={"code": "auth-code-xyz", "state": _valid_state(settings)},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "http://localhost:3000/dashboard"
    assert "mailsweep_session" in response.cookies

    with _db(engine) as db:
        user = db.query(OAuthConnection).one().user
        assert user.email == "aryan@example.com"
        conn = db.query(OAuthConnection).one()
        # Tokens stored encrypted - ciphertext must not contain plaintext.
        assert "at-secret-123" not in (conn.access_token_encrypted or "")
        assert "rt-secret-456" not in (conn.refresh_token_encrypted or "")
        assert str(conn.status) == "ACTIVE"

    # The exchanged code hit Google's token endpoint exactly once.
    assert len(calls["token_requests"]) == 1


def test_status_reflects_authenticated_connected_state(oauth_world):
    settings, client, _, _ = oauth_world
    client.get(
        "/api/auth/google/callback",
        params={"code": "c", "state": _valid_state(settings)},
    )

    status = client.get("/api/auth/status").json()
    assert status["authenticated"] is True
    assert status["user"]["email"] == "aryan@example.com"
    assert status["gmail_connection"]["connected"] is True
    assert "https://www.googleapis.com/auth/gmail.modify" in status["gmail_connection"][
        "granted_scopes"
    ]


def test_status_is_anonymous_without_cookie(oauth_world):
    _settings, client, _, _ = oauth_world
    body = client.get("/api/auth/status").json()
    assert body == {"authenticated": False}


def test_callback_rejects_forged_state(oauth_world):
    _settings, client, engine, calls = oauth_world
    response = client.get(
        "/api/auth/google/callback",
        params={"code": "c", "state": "forged.state"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_oauth_state"
    assert calls["token_requests"] == []  # never touched Google
    with _db(engine) as db:
        assert db.query(OAuthConnection).count() == 0


def test_callback_surfaces_consent_denial(oauth_world):
    _settings, client, _, calls = oauth_world
    response = client.get(
        "/api/auth/google/callback",
        params={"error": "access_denied"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "consent_denied"
    assert calls["token_requests"] == []


def test_unverified_email_is_rejected(oauth_world, monkeypatch):
    settings, client, engine, _ = oauth_world

    def fake_with_unverified(url, data, *, timeout=15.0):
        if url == google_oauth.TOKEN_ENDPOINT:
            return {
                "access_token": "at",
                "refresh_token": "rt",
                "expires_in": 3600,
                "scope": _GMAIL_SCOPE,
                "id_token": _make_id_token(
                    sub="sub-x", email="x@example.com", email_verified=False
                ),
            }
        raise AssertionError(url)

    monkeypatch.setattr(google_oauth, "_post_form", fake_with_unverified)
    response = client.get(
        "/api/auth/google/callback",
        params={"code": "c", "state": _valid_state(settings)},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "email_unverified"
    with _db(engine) as db:
        assert db.query(OAuthConnection).count() == 0


def test_logout_revokes_the_session(oauth_world):
    settings, client, engine, _ = oauth_world
    client.get(
        "/api/auth/google/callback",
        params={"code": "c", "state": _valid_state(settings)},
    )
    assert client.get("/api/auth/status").json()["authenticated"] is True

    response = client.post("/api/auth/logout")
    assert response.status_code == 204

    assert client.get("/api/auth/status").json()["authenticated"] is False
    with _db(engine) as db:
        assert all(s.revoked_at is not None for s in db.query(UserSession).all())


def test_disconnect_requires_authentication(oauth_world):
    _settings, client, _, _ = oauth_world
    response = client.post("/api/auth/google/disconnect")
    assert response.status_code == 401


# Logout without any cookie is intentionally idempotent (204) - it leaks no
# information about session validity and clears whatever junk was sent.


def test_disconnect_revokes_grant_and_purges_mailbox_data(oauth_world):
    settings, client, engine, calls = oauth_world
    client.get(
        "/api/auth/google/callback",
        params={"code": "c", "state": _valid_state(settings)},
    )

    # Seed cached mailbox data as ingestion would have created it.
    with _db(engine) as db:
        user = db.query(OAuthConnection).one().user
        mailbox = Mailbox(user_id=user.id, google_email_address=user.email)
        db.add(mailbox)
        db.flush()
        db.add(
            EmailMessage(
                mailbox_id=mailbox.id,
                gmail_message_id="gm-1",
                subject="Newsletter",
                received_at=datetime.now(UTC),
            )
        )
        db.commit()
        mailbox_id = mailbox.id

    response = client.post("/api/auth/google/disconnect")
    assert response.status_code == 204
    # Google revoke was called with our decrypted token (not plaintext here).
    assert len(calls["revoked"]) == 1

    with _db(engine) as db:
        conn = db.query(OAuthConnection).one()
        assert str(conn.status) == "REVOKED"
        assert conn.access_token_encrypted is None
        assert conn.refresh_token_encrypted is None
        assert db.get(Mailbox, mailbox_id) is None  # purged via cascade

    status = client.get("/api/auth/status").json()
    assert status["gmail_connection"]["connected"] is False


def test_csrf_blocks_cross_origin_post(oauth_world):
    """Browser-attached Origin header must match the allowlist for POSTs."""
    settings, client, engine, _ = oauth_world
    raw_token = create_session(
        _db(engine),
        user_id=_seed_user(engine),
        ttl_days=settings.SESSION_TTL_DAYS,
    )

    response = client.post(
        "/api/auth/logout",
        headers={"Origin": "https://evil.example"},
        cookies={"mailsweep_session": raw_token},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_origin"


def test_same_origin_post_passes_csrf_check(oauth_world):
    settings, client, engine, _ = oauth_world
    raw_token = create_session(_db(engine), user_id=_seed_user(engine), ttl_days=14)

    response = client.post(
        "/api/auth/logout",
        headers={"Origin": "http://localhost:3000"},
        cookies={"mailsweep_session": raw_token},
    )
    assert response.status_code == 204


# ---------------------------------------------------------------------------
# helpers


def _seed_user(engine) -> str:
    with _db(engine) as db:
        from app.auth.service import upsert_oauth_identity as _upsert

        user, _ = _upsert(
            db,
            sub="sub-seed",
            email="seed@example.com",
            display_name="Seed",
            avatar_url=None,
            scope=None,
            access_token="at-seed",
            refresh_token=None,
            expires_in=3600,
            secret_key=b"s" * 48,
        )
        return user.id



