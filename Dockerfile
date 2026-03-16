# --------------------------------------------------------------------------
# Stage 1: builder — install dependencies into an isolated venv
# --------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install deps into a venv so the runtime stage stays clean
RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

COPY pyproject.toml .
# Install base deps; add [gcs] on GCP builds via --build-arg EXTRAS=gcs
ARG EXTRAS=""
RUN pip install --no-cache-dir -e ".${EXTRAS:+[$EXTRAS]}"

# --------------------------------------------------------------------------
# Stage 2: runtime — minimal image, non-root user
# --------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1001 appuser \
    && useradd --uid 1001 --gid appuser --no-create-home appuser

# Copy venv from builder
COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"

# Copy application source (excludes .env, __pycache__, etc. via .dockerignore)
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .

USER appuser

# Default: API server (override command for Celery worker in K8s)
# CMD is intentionally not --reload in production
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--no-access-log"]

EXPOSE 8000

# Kubernetes liveness probe target
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
