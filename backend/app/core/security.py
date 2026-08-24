"""Cryptographic primitives - the ONLY module that touches raw crypto.

Everything security-relevant is centralized here so it can be audited in one
place:

* Session tokens: random 256-bit values; only a SHA-256 hash is persisted.
* OAuth tokens at rest: Fernet (AES-128-CBC + HMAC) with a key derived from
  ``SECRET_KEY`` via SHA-256 domain separation.
* OAuth ``state`` parameter: HMAC-SHA256 signed JSON with expiry + nonce,
  giving us single-use-looking CSRF protection without server-side storage.

No homegrown cryptography beyond standard library / `cryptography` usage.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from cryptography.fernet import Fernet, InvalidToken

# Domain separation so one secret can safely serve multiple purposes.
_TOKEN_ENC_INFO = b"mailsweep/oauth-token-encryption/v1"
_STATE_SIGNING_INFO = b"mailsweep/oauth-state-signing/v1"

_STATE_TTL_SECONDS = 600
_KEK_CACHE: dict[bytes, Fernet] = {}


# --------------------------------------------------------------------- sessions
def new_session_token() -> str:
    """Opaque bearer value placed in the session cookie."""
    return secrets.token_urlsafe(32)


def hash_session_token(raw_token: str) -> str:
    """Deterministic hash stored in the DB instead of the raw cookie value."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# --------------------------------------------------------------- token vault
def _fernet_from_secret(secret_key_bytes: bytes) -> Fernet:
    digest = hashlib.sha256(_TOKEN_ENC_INFO + b"\x00" + secret_key_bytes).digest()
    if digest not in _KEK_CACHE:
        _KEK_CACHE[digest] = Fernet(base64.urlsafe_b64encode(digest))
    return _KEK_CACHE[digest]


def encrypt_text(plaintext: str, *, secret_key: bytes) -> str:
    """Encrypt a short secret (OAuth access/refresh token) for DB storage."""
    return _fernet_from_secret(secret_key).encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_text(ciphertext: str, *, secret_key: bytes) -> str:
    """Decrypt a stored secret. Raises ValueError on tampering/wrong key."""
    try:
        return (
            _fernet_from_secret(secret_key)
            .decrypt(ciphertext.encode("ascii"))
            .decode("utf-8")
        )
    except InvalidToken as exc:  # pragma: no cover - defensive path
        raise ValueError("Decryption failed: ciphertext invalid or key mismatch") from exc


# ------------------------------------------------------------- oauth state
def sign_oauth_state(payload: dict, *, secret_key: bytes) -> str:
    """Serialize+sign an arbitrary small payload for the OAuth state param."""
    body = {
        "p": payload,
        "exp": int(time.time()) + _STATE_TTL_SECONDS,
        "n": secrets.token_urlsafe(8),  # uniqueness; old states fail expiry check fast
    }
    raw = base64.urlsafe_b64encode(
        json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signing_key = _STATE_SIGNING_INFO + b"\x00" + secret_key
    signature = hmac.new(signing_key, raw, hashlib.sha256).hexdigest()
    return f"{raw.decode('ascii')}.{signature}"


def verify_oauth_state(state: str | None, *, secret_key: bytes) -> dict | None:
    """Validate signature + TTL; return the payload dict or None."""
    if not state or "." not in state:
        return None
    raw_b64, _, signature = state.rpartition(".")
    try:
        raw = raw_b64.encode("ascii")
    except UnicodeEncodeError:
        return None
    expected = hmac.new(_STATE_SIGNING_INFO + b"\x00" + secret_key, raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        body = json.loads(base64.urlsafe_b64decode(raw))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(body, dict) or body.get("exp", 0) < time.time():
        return None
    payload = body.get("p")
    return payload if isinstance(payload, dict) else None
