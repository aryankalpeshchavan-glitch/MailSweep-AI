# MailSweep AI

**Intelligent, explainable, privacy-conscious Gmail cleanup assistant.**

MailSweep connects to your Gmail via Google OAuth, analyzes mailbox *metadata*
(never bodies), groups similar mail, and produces **explainable** cleanup
recommendations — each with a category, confidence, risk level, and
human-readable reasons. **Nothing is deleted without your explicit review and
approval**, and the only destructive operation is **moving messages to Gmail
Trash** (recoverable for ~30 days by Gmail itself).

> Status: backend in active development. The frontend will be designed
> separately (Google Stitch → Next.js) once this API contract stabilizes.

---

## Overview

| | |
|---|---|
| **Problem** | Years of Gmail accumulation — newsletters, notifications, promotions — make mailboxes unusable and obscure important mail. Manual cleanup doesn't scale. |
| **Solution** | Deterministic, explainable analysis of mailbox metadata → grouped recommendations → human approval → safe, audited Trash execution. |
| **Differentiator** | Not `if old: delete()`. Every recommendation answers *why* with concrete signals, separates **confidence** (how sure the classifier is) from **risk** (how bad a mistake would be), and treats uncertainty as `REVIEW`, never as deletion. |

## Architecture

```
Browser (future frontend)
      │  HTTPS · HttpOnly session cookie · CORS allowlist
      ▼
FastAPI ───────────────► PostgreSQL
   │  ▲                    ▲
   │  │ job status/poll    │
   ▼  │                    │
Dispatcher ◄──────────────┘ reads/writes
   │  prod: Redis broker + Celery worker
   │  dev/test: inline execution (zero infra)
   ▼
Gmail API (metadata only)        Anthropic API (optional;
                                 ambiguous cases only)
```

- **API**: FastAPI, Pydantic v2, sync SQLAlchemy 2.0.
- **Jobs**: Celery + Redis in production; an inline dispatcher makes the exact
  same pipeline runnable (and testable) with zero infrastructure.
- **DB**: PostgreSQL (pure-Python `pg8000` driver — no compilation headaches),
  Alembic migrations.
- **Security**: opaque DB-backed sessions in HttpOnly cookies, Origin-allowlist
  CSRF defense, encrypted-at-rest OAuth tokens, per-resource authorization,
  rate limiting, structured logs with redaction.
- **Privacy**: metadata-only ingestion; email bodies are never fetched, stored,
  or sent to any third party. See [SECURITY.md](SECURITY.md).

Full rationale: [docs/ENGINEERING_PLAN.md](docs/ENGINEERING_PLAN.md).

## Features (implemented)

- ✅ Health/readiness endpoint with DB + Redis component checks
- ✅ Google OAuth 2.0 (authorization-code + offline refresh), disconnect/revoke
- ✅ OAuth tokens encrypted at rest; session identifiers stored hashed
- ✅ Metadata-only mailbox ingestion (paginated, bounded, retry/backoff)
- ✅ Deterministic classification engine (promotional, newsletter, social,
  automated notifications, receipts/invoices, personal, professional…)
- ✅ Extensible user rule engine — protection rules always outrank cleanup rules
- ✅ Explainable recommendation engine with documented confidence/risk formulas
- ✅ Email grouping (sender/domain/subject-pattern/category)
- ✅ Cleanup plans: full state machine, preview → approval → execution,
  idempotent, partial-failure aware, per-message ledger
- ✅ Move-to-Trash execution (permanent deletion intentionally absent)
- ✅ Audit log of security-relevant events
- ✅ Optional AI ambiguity-resolution (Anthropic) hardened against prompt
  injection — the app is fully functional without any AI key
- ✅ Rate limiting, security headers, JSON logging with request IDs
- ✅ Docker Compose (api, worker, postgres, redis) + GitHub Actions CI
- ✅ Hermetic test suite (unit + API + pipeline; all externals faked)

## Technology Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.12+ | Ecosystem, readability |
| API | FastAPI + Pydantic v2 | Typed contracts, OpenAPI for free |
| ORM/DB | SQLAlchemy 2.0 + Alembic + PostgreSQL | Mature, migration-safe |
| PG driver | `pg8000` | Pure Python → identical on Windows/macOS/Linux/CI |
| Jobs | Celery + Redis (prod), inline dispatcher (dev/test) | Standard; dev needs zero infra |
| Gmail | `google-api-python-client` + `google-auth` | Official client |
| AI | Anthropic Messages API via `httpx` (optional) | Thin, auditable, swappable |
| Auth | Google OAuth + own opaque sessions | Revocable and simple |
| Tests / Lint | pytest · ruff | Industry defaults |

## Setup (local development)

Prerequisites: **Python 3.12+**, **Git**. Docker optional.

```powershell
git clone https://github.com/aryankalpeshchavan-glitch/MailSweep-AI
cd MailSweep-AI

# venv — if this repo lives in OneDrive, keep .venv OUTSIDE the synced folder:
python -m venv "$env:LOCALAPPDATA\mailsweep\.venv"
& "$env:LOCALAPPDATA\mailsweep\.venv\Scripts\Activate.ps1"

pip install -r backend/requirements.txt -r backend/requirements-dev.txt
Copy-Item .env.example .env    # then edit values

cd backend
pytest                         # hermetic test suite
uvicorn app.main:app --reload  # → http://localhost:8000/docs
```

Key env vars (all documented inline in [.env.example](.env.example)):
`SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`,
`GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`, `ANTHROPIC_API_KEY` (optional),
`FRONTEND_ORIGINS`. Production startup **fails fast** if critical settings are
missing or weak.

### Google Cloud / Gmail OAuth

Guide: [docs/GOOGLE_OAUTH_SETUP.md](docs/GOOGLE_OAUTH_SETUP.md).
Scopes requested (rationale: docs/ADR-0004-gmail-scopes.md):
`openid`, `email`, `profile`, `https://www.googleapis.com/auth/gmail.modify`.

### Database & Redis

Dev without Docker: nothing to do (SQLite fallback, auto-created; jobs run
inline). With Docker: `docker compose up -d postgres redis`.
Schema changes via Alembic (`alembic revision --autogenerate`), never by hand
in production.

## Running Tests

```powershell
cd backend
pytest -k cleanup                     # subset
pytest --cov=app --cov-report=term-missing
```

Gmail, Anthropic, Redis and Postgres-specific behavior are faked — the suite
is hermetic, free, and deterministic.

## Docker

```powershell
docker compose up --build             # api :8000, worker, postgres :5432, redis :6379
docker compose exec api alembic upgrade head
```

## API Documentation

- Interactive: `http://localhost:8000/docs`
- Contract for the future frontend: [docs/API_CONTRACT.md](docs/API_CONTRACT.md)

## Security & Privacy

See [SECURITY.md](SECURITY.md) and the privacy table below. No compliance
certifications are claimed.

**Accessed:** message IDs, thread IDs, labels, From header, subject, dates,
size, attachment flags (metadata only). **Never accessed:** bodies or
attachments. **Stored:** that metadata (truncated subject), classifications,
recommendations, your rules/decisions, audit events. **Third parties:**
Google (inherent) and — only if enabled, only ambiguous subjects — Anthropic.
**Your controls:** disconnect revokes the Google grant and deletes tokens/data.
MailSweep only moves mail to Gmail **Trash**.

## Limitations (honest)

- Reply-detection is heuristic-limited by Gmail API economics (roadmap:
  opt-in deep scan). Age alone never deletes anything.
- Rate limiting requires Redis (dev without Redis runs unlimited).
- One Gmail account per user account; English-only reason strings.

## Roadmap

1. Cloud deployment (Render blueprint ready; awaiting account setup)
2. Preference learning ("You always keep university.edu — protect it?")
3. Incremental sync via Gmail `historyId`
4. Reply-awareness deep scan · 5. Frontend vs [docs/API_CONTRACT.md](docs/API_CONTRACT.md)

