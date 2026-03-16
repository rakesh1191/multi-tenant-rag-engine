#!/usr/bin/env bash
# One-command bootstrap for local development.
# Usage: bash scripts/setup.sh
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
die()  { echo -e "${RED}✗${NC} $*"; exit 1; }

echo "=== RAG Engine — Local Setup ==="
echo ""

# ── Prereqs ──────────────────────────────────────────────────────────────────
command -v docker   >/dev/null 2>&1 || die "Docker is required. Install: https://docs.docker.com/get-docker/"
command -v python3  >/dev/null 2>&1 || die "Python 3.12+ is required."
command -v node     >/dev/null 2>&1 || warn "Node.js not found — UI setup will be skipped."

PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" 2>/dev/null; then
  ok "Python ${PYTHON_VER}"
else
  die "Python 3.12+ required (found ${PYTHON_VER})"
fi

# ── .env ─────────────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env
  ok "Created .env from .env.example"
else
  ok ".env already exists"
fi

# ── Python deps ───────────────────────────────────────────────────────────────
echo "Installing Python dependencies..."
pip install -e ".[dev]" -q
ok "Python dependencies installed"

# ── UI deps ───────────────────────────────────────────────────────────────────
if command -v node >/dev/null 2>&1; then
  echo "Installing UI dependencies..."
  (cd ui && npm ci --silent)
  ok "UI dependencies installed"
fi

# ── Infrastructure ────────────────────────────────────────────────────────────
echo "Starting infrastructure (postgres, redis, minio)..."
docker compose up -d postgres redis minio

echo "Waiting for postgres to be ready..."
for i in $(seq 1 30); do
  if docker compose exec -T postgres pg_isready -U rag -d ragdb >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker compose exec -T postgres pg_isready -U rag -d ragdb >/dev/null || die "Postgres did not start in time"
ok "Postgres ready"

echo "Waiting for Redis..."
for i in $(seq 1 20); do
  if docker compose exec -T redis redis-cli ping >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
ok "Redis ready"

echo "Waiting for MinIO..."
for i in $(seq 1 20); do
  if curl -sf http://localhost:9000/minio/health/live >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
ok "MinIO ready"

# ── Migrations ────────────────────────────────────────────────────────────────
echo "Running database migrations..."
alembic upgrade head
ok "Migrations applied"

# ── Test database ─────────────────────────────────────────────────────────────
docker compose exec -T postgres createdb -U rag ragdb_test 2>/dev/null || true
ok "Test database ready (ragdb_test)"

# ── Ollama check ─────────────────────────────────────────────────────────────
if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  ok "Ollama detected at localhost:11434"
  if curl -sf http://localhost:11434/api/tags | grep -q "nomic-embed-text"; then
    ok "nomic-embed-text model available"
  else
    warn "nomic-embed-text not found. Pull it: ollama pull nomic-embed-text"
  fi
else
  warn "Ollama not running. Start it and pull models:"
  warn "  ollama serve"
  warn "  ollama pull nomic-embed-text"
  warn "  ollama pull qwen2.5:14b   (optional, for LLM)"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "==================================================="
echo -e "${GREEN}Setup complete!${NC} Next steps:"
echo ""
echo "  make dev        → start API (http://localhost:8000/docs)"
echo "  make worker     → start Celery ingestion worker"
echo "  make ui         → start Next.js UI (http://localhost:3000)"
echo "  make test       → run the test suite"
echo "  make seed       → seed sample data"
echo ""
echo "  MinIO console   → http://localhost:9001  (minioadmin / minioadmin)"
echo "==================================================="
