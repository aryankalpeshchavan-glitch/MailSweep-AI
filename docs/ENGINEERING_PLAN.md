# Engineering Plan & Architecture Decisions

Living document. Each section states *what*, *why*, and rejected alternatives.
ADRs live beside this file (`docs/ADR-*.md`).

## Goals

Safety-first Gmail cleanup: metadata analysis → explainable recommendations →
explicit human approval → Trash-only execution → audit trail. Backend-only
until the API contract stabilizes.

## Core safety principles (non-negotiable)

1. Analysis never modifies Gmail. Only an approved cleanup plan executes.
2. The only destructive verb is **Trash** (reversible by Gmail for ~30 days).
3. Protection rules outrank everything, including AI output.
4. Uncertainty resolves to REVIEW/KEEP, never deletion.
5. Email content is untrusted data — never instructions (prompt-injection).
6. Every executed change leaves a per-message audit record.

## Confidence vs Risk (definitions used by the engine)

These are deliberately different axes:

- **Confidence** ∈ [0,1]: probability that the assigned category/action is
  correct. Derived from classifier agreement across signals (formula in the
  recommendation module docstring; every adjustment step is named in code).
- **Risk** ∈ {LOW, MEDIUM, HIGH}: expected damage of a wrong removal.
  Raised by: starred, important-flagged, attachment-bearing, keyword matches
  (invoice/receipt/contract…), personal category, protection-rule adjacency.
- A recommendation may be confidence=0.99 AND risk=HIGH ("this is definitely a
  receipt" ⇒ keep it). Action thresholds consider BOTH.

## Decision records (summary)

| ADR | Decision | Why / rejected alternative |
|---|---|---|
| 0001 | Sync SQLAlchemy everywhere | Celery workers are sync; async adds greenlet/session complexity with no throughput need at this scale. FastAPI runs sync handlers on a threadpool. Rejected: async ORM. |
| 0002 | `pg8000` driver | Pure Python ⇒ zero wheel/build risk on Windows + Python 3.14 today. Performance gap irrelevant here. Swap path documented. |
| 0003 | Opaque DB-backed sessions, HttpOnly cookie; CSRF = SameSite=Lax + Origin allowlist on unsafe methods | Revocable instantly (disconnect), no JWT secret rotation, auditable. Rejected: JWT-in-localStorage (XSS-prone), double-submit tokens (extra state). |
| 0004 | Scopes: openid/email/profile + gmail.modify | See docs/ADR-0004-gmail-scopes.md. gmail.modify is required for Trash; narrower read scope exists but write access inherently includes read. |
| 0005 | Dispatcher abstraction (Celery prod / inline dev+test) | Whole pipeline testable without Redis; Windows-friendly dev. Rejected: requiring Docker for tests. |
| 0006 | Metadata-only ingestion; bodies never fetched/stored/sent | Privacy + cost + shrinks prompt-injection surface. |
| 0007 | Deterministic rules first; AI only for ambiguous band; provider behind interface | Cost, latency, privacy, determinism; avoids vendor lock-in. |
| 0008 | Idempotency via plan state machine + atomic status transition guard | Duplicate approve/exec requests cannot double-execute (DB-level WHERE status='APPROVED' gate + per-item ledger). |
| 0009 | SQLite for unit/API tests; Postgres only in integration/deploy | Hermetic CI. Models restricted to portable column types (Uuid-as-guid, JSON not JSONB, native_enum=False). |

## Threat model (abridged)

| Threat | Mitigation |
|---|---|
| Prompt injection via email | Bodies never fetched; subjects wrapped as quoted data in a strict system prompt; JSON-schema-validated output; AI cannot execute anything — it only suggests categories; application rules + user approval authoritative. |
| CSRF on cookie auth | SameSite=Lax + Origin/Referer allowlist enforced server-side on unsafe methods. |
| Session theft | HttpOnly + Secure(prod) + SameSite cookies; hashed-at-rest session ids; sliding expiry; revocation on logout/disconnect. |
| IDOR / cross-account access | Every query scoped by authenticated user id at the service layer; ownership asserted before any state change; tests cover user-A-cannot-read-user-B. |
| Token theft at rest | Fernet encryption keyed off SECRET_KEY (HKDF-style derivation); tokens never logged; redaction filter drops token-like fields from logs. |
| Duplicate destructive execution | Atomic status-transition UPDATE guard; per-plan unique execution ledger; second approve returns 409. |
| Quota abuse / runaway jobs | Bounded page size, max-messages cap, exponential backoff honoring Retry-After, per-endpoint rate limits, single active analysis per mailbox. |
| Secret leakage in errors/logs | Central error envelope strips internals in prod; log redaction filter; exceptions never embed provider payloads verbatim. |

## Testing strategy

- Unit: rule engine, classifiers, recommendation math, crypto helpers, state machine.
- API: TestClient against overridden dependencies (SQLite memory, fake services).
- Pipeline: fake Gmail client with scripted pages/failures asserts ingestion,
  classification, grouping, recommendation outputs end-to-end.
- Safety cases mandated by spec (starred⇒KEEP, protected domain⇒KEEP,
  low-confidence⇒REVIEW, unapproved⇒no Gmail call, duplicate-approve⇒single
  execution, cross-user denial) each have dedicated tests.

## Environments

`development` (SQLite fallback, inline jobs, verbose errors) · `test`
(hermetic fixtures, ephemeral SECRET_KEY allowed) · `production` (Postgres +
Redis required, secure cookies forced, fail-fast config validation, generic
error envelopes).

## Deployment direction

Render recommended: managed Postgres + Redis, separate web + worker services,
HTTPS + custom domains included, generous free tier for portfolio scale,
GitHub auto-deploy. Blueprint committed as `render.yaml`. Alternatives
(Railway, Fly.io) compared in docs when deployment milestone begins.
