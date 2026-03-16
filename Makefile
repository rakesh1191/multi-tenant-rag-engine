.PHONY: help up down all dev worker ui migrate migrate-down migrate-history \
        test test-unit test-fast test-db-create lint format seed setup reset \
        logs shell clean build

PYTHON    := python3
COMPOSE   := docker compose
DB_USER   := rag
DB_NAME   := ragdb
TEST_DB   := ragdb_test

# ─────────────────────────────────────────────────────────────────────────────
# Help (default target)
# ─────────────────────────────────────────────────────────────────────────────

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} \
	/^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 } \
	/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) }' $(MAKEFILE_LIST)

# ─────────────────────────────────────────────────────────────────────────────
##@ Infrastructure
# ─────────────────────────────────────────────────────────────────────────────

up: ## Start infrastructure only (postgres, redis, minio)
	$(COMPOSE) up -d postgres redis minio
	@echo "Waiting for services to be healthy..."
	@$(COMPOSE) exec -T postgres pg_isready -U $(DB_USER) -d $(DB_NAME) --timeout=30 >/dev/null
	@echo "✓ Infra ready — postgres:5432  redis:6379  minio:9000 (console:9001)"

down: ## Stop and remove all containers
	$(COMPOSE) down

all: build ## Start full stack (infra + api + worker + ui) with hot-reload
	$(COMPOSE) up -d
	@echo ""
	@echo "✓ Full stack running:"
	@echo "   API     → http://localhost:8000"
	@echo "   Docs    → http://localhost:8000/docs"
	@echo "   UI      → http://localhost:3000"
	@echo "   MinIO   → http://localhost:9001  (user: minioadmin / minioadmin)"
	@echo ""
	@echo "  make logs    → tail logs"
	@echo "  make down    → stop everything"

build: ## Build Docker images
	$(COMPOSE) build

logs: ## Tail all container logs (Ctrl+C to exit)
	$(COMPOSE) logs -f

logs-api: ## Tail API logs only
	$(COMPOSE) logs -f app

logs-worker: ## Tail worker logs only
	$(COMPOSE) logs -f worker

reset: ## ⚠ Wipe all data volumes and restart fresh
	$(COMPOSE) down -v
	$(MAKE) up
	$(MAKE) migrate
	$(MAKE) test-db-create
	@echo "✓ Reset complete"

# ─────────────────────────────────────────────────────────────────────────────
##@ Local Development (no Docker for the app itself)
# ─────────────────────────────────────────────────────────────────────────────

dev: ## Run API locally with hot-reload (run `make up` first)
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app

worker: ## Run Celery worker locally with auto-restart
	watchmedo auto-restart --directory=app --pattern="*.py" --recursive \
	  -- celery -A app.ingestion.tasks worker --loglevel=info --concurrency=2 --pool=solo

worker-simple: ## Run Celery worker locally (no auto-restart)
	celery -A app.ingestion.tasks worker --loglevel=info --concurrency=2

ui: ## Run Next.js UI dev server (http://localhost:3000)
	cd ui && npm run dev

# ─────────────────────────────────────────────────────────────────────────────
##@ Database
# ─────────────────────────────────────────────────────────────────────────────

migrate: ## Run all pending Alembic migrations
	alembic upgrade head

migrate-down: ## Roll back one migration step
	alembic downgrade -1

migrate-history: ## Show migration history
	alembic history --verbose

migrate-status: ## Show current migration revision
	alembic current

test-db-create: ## Create ragdb_test database (safe to run multiple times)
	@$(COMPOSE) exec -T postgres createdb -U $(DB_USER) $(TEST_DB) 2>/dev/null \
	  && echo "✓ Created $(TEST_DB)" \
	  || echo "  $(TEST_DB) already exists"

shell: ## Open a psql shell
	$(COMPOSE) exec postgres psql -U $(DB_USER) -d $(DB_NAME)

shell-test: ## Open a psql shell on the test DB
	$(COMPOSE) exec postgres psql -U $(DB_USER) -d $(TEST_DB)

# ─────────────────────────────────────────────────────────────────────────────
##@ Testing
# ─────────────────────────────────────────────────────────────────────────────

test: test-db-create ## Run full test suite with coverage
	pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=html

test-fast: test-db-create ## Run tests, stop at first failure, no coverage
	pytest tests/ -v -x

test-unit: ## Run unit tests only (fast, no infra needed)
	pytest tests/ -v -m "unit"

test-auth: test-db-create ## Run auth tests only
	pytest tests/test_auth.py -v

test-docs: test-db-create ## Run document tests only
	pytest tests/test_documents.py -v

# ─────────────────────────────────────────────────────────────────────────────
##@ Code Quality
# ─────────────────────────────────────────────────────────────────────────────

lint: ## Run ruff linter + mypy type checker
	ruff check app/ tests/
	mypy app/ --strict

format: ## Auto-format and fix lint issues
	ruff format app/ tests/
	ruff check app/ tests/ --fix

security: ## Run bandit security scan + dependency audit
	bandit -r app/ -ll
	pip-audit

# ─────────────────────────────────────────────────────────────────────────────
##@ Seed & Utilities
# ─────────────────────────────────────────────────────────────────────────────

seed: ## Seed the database with sample tenants, users, and documents
	$(PYTHON) scripts/seed_data.py

setup: ## First-time setup: install deps, start infra, migrate, seed
	@echo "=== RAG Engine — First-time Setup ==="
	@test -f .env || (cp .env.example .env && echo "✓ Created .env from .env.example")
	pip install -e ".[dev]"
	cd ui && npm ci
	$(MAKE) up
	sleep 3
	$(MAKE) migrate
	$(MAKE) test-db-create
	@echo ""
	@echo "=== Setup complete ==="
	@echo "  make dev      → start API with hot-reload (http://localhost:8000)"
	@echo "  make worker   → start Celery worker"
	@echo "  make ui       → start Next.js UI (http://localhost:3000)"
	@echo "  make test     → run the test suite"
	@echo "  make all      → start everything in Docker"

clean: ## Remove Python cache and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
	rm -rf .coverage .pytest_cache htmlcov/ dist/ *.egg-info/
