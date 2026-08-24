# Security Policy

## Supported version

The `main` branch is the only supported line while MailSweep AI is in active
development.

## Reporting a vulnerability

**Please do NOT open a public GitHub issue for security problems.**

Email the maintainer via the address on the GitHub profile
(@aryankalpeshchavan-glitch) with:

- a description of the issue,
- steps to reproduce (or a proof of concept),
- the potential impact.

You will receive an acknowledgement, and a fix or mitigation will be tracked
privately until release. This is a student portfolio project — response times
are best-effort, but reports are taken seriously.

## Secret handling rules used in this repository

1. All secrets live in environment variables, never in source code.
2. `.env` is git-ignored. `.env.example` documents variable names with empty values.
3. OAuth access/refresh tokens are **encrypted at rest** (Fernet, key derived from
   `SECRET_KEY`) before being written to the database.
4. Session cookies contain only an opaque random identifier; the database stores
   a SHA-256 hash of it, so a database leak does not yield usable session tokens.
5. Logs never intentionally contain: email bodies, tokens, secrets, or full
   recipient addresses beyond what is needed for debugging identifiers.
6. Exceptions surfaced to clients never embed internal details (stack traces,
   SQL, provider errors) in production mode.

## OAuth design notes

- Google OAuth 2.0 Authorization Code flow with offline access (refresh tokens).
- The OAuth `state` parameter is an HMAC-signed, short-lived, single-use value to
  prevent CSRF on the callback.
- Requested Gmail scope is `https://www.googleapis.com/auth/gmail.modify`, the
  narrowest published scope that permits moving messages to Trash. See
  `docs/ADR-0004-gmail-scopes.md` for why broader/narrower scopes were rejected.
- Disconnecting an account revokes the Google grant and deletes the encrypted
  tokens from our database.

## Known limitations (honest disclosure)

- Rate limiting falls back to **disabled** when Redis is unavailable
  (development mode only; production requires Redis).
- The application has no formal security audit. It follows OWASP-aligned
  practices for a project of this scale but makes no compliance claims.
- Gmail bodies are never fetched by design (metadata-only), which drastically
  limits prompt-injection surface — but subject lines are still untrusted data
  and are treated as such by the AI layer.
