# Dockerfile for MailSweep AI backend (multi-stage)
#
# Build:  install deps into a shared layer we reuse for both the API and
#         the Celery worker (same image, different entrypoints).
# Runtime: slimmer image, non-root user, gunicorn+uvicorn workers for the
#          API and a plain celery worker for background tasks.

# ── Builder ──────────────────────────────────────────────────────────────
FROM python:3.14-slim AS builder

# Install system packages needed by cryptography + pg8000 wheels (none needed,
# both are pure-Python, but gcc/musl-dev can help if a transitive dep breaks).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# Pre-cache dependencies: copy only requirements first so Docker layer caching
# keeps `pip install` off the slow path during code iteration.
WORKDIR /build

# Install dependencies as a virtualenv we can copy whole, avoiding
# recompilation of the entire image when only source changes.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/requirements.txt backend/requirements-dev.txt* ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r requirements-dev.txt

# Install the app package in editable-free production mode (copy source next).
COPY backend/ .

# ── Runtime ──────────────────────────────────────────────────────────────
FROM python:3.14-slim AS runtime

# Non-root user for the application process.
RUN groupadd --system appgroup && useradd --system --gid appgroup --uid 1001 appuser

WORKDIR /app

# Reuse the pre-built venv from the builder.
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Copy installed site-packages that the venv doesn't already contain (should be
# none, but ensures a clean transition). Copy app source separately.
COPY backend/ .

# Runtime needs its own tmp dir.
RUN mkdir -p /tmp/uploads && chown -R appuser:appgroup /app /tmp/uploads

USER appuser

# Health check: hit the readiness endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health', timeout=3).status==200 else 1)"]

# Default: API server (4 uvicorn workers via gunicorn). Override at runtime
# for the worker:  CMD ["celery","-A","app.workers.celery_app:get_celery_app","worker","-l","info"]
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", \
     "--workers", "4", "--timeout", "60", "app.main:app"]
