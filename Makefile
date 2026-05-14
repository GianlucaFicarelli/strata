# Strata — development Makefile
#
# Requires: python 3.14+, uv, node 22+, npm, docker, docker compose

.PHONY: help install install-backend install-frontend \
        dev dev-backend dev-frontend \
        build build-frontend \
        docker-build docker-up docker-up-collabora docker-down docker-logs \
        lint typecheck test clean

PYTHON   := python3.14
UV       := uv
BACKEND  := backend
FRONTEND := frontend

# ── Help ──────────────────────────────────────────────────────────────────────

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Install ───────────────────────────────────────────────────────────────────

compile-deps:  ## Create or update the lock file, without upgrading the version of the dependencies
	cd $(BACKEND) && uv lock

upgrade-deps:  ## Create or update the lock file, using the latest version of the dependencies
	cd $(BACKEND) && uv lock --upgrade

check-deps:  ## Check that the dependencies in the existing lock file are valid
	cd $(BACKEND) && uv lock --locked

install: install-backend install-frontend ## Install all dependencies

install-backend: ## Install Python dependencies with uv into backend/.venv
	cd $(BACKEND) && $(UV) sync --no-install-project --extra all

install-frontend: ## Install Node dependencies
	cd $(FRONTEND) && npm install

# ── Development servers ───────────────────────────────────────────────────────

dev: ## Run backend and frontend dev servers in parallel (requires tmux or similar)
	@echo "Starting backend on :8000 and frontend on :5173"
	@$(MAKE) -j2 dev-backend dev-frontend

dev-backend: ## Run the FastAPI backend with hot-reload
	cd $(BACKEND) && \
		STRATA_LOCAL_ROOT=$${STRATA_LOCAL_ROOT:-$$HOME} \
		.venv/bin/uvicorn strata.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend: ## Run the Vite dev server (proxies /api → :8000)
	cd $(FRONTEND) && npm run dev

# ── Build ─────────────────────────────────────────────────────────────────────

build: build-frontend ## Build all artefacts (currently just the frontend)

build-frontend: ## Compile the React frontend into frontend/dist/
	cd $(FRONTEND) && npm run build

# ── Docker ────────────────────────────────────────────────────────────────────

docker-build: ## Build the Docker image
	docker compose build

docker-up: ## Start Strata (without Collabora)
	docker compose up

docker-up-collabora: ## Start Strata with Collabora Online
	docker compose --profile collabora up

docker-down: ## Stop all services
	docker compose down

docker-logs: ## Tail logs for all services
	docker compose logs -f

# ── Code quality ──────────────────────────────────────────────────────────────

format: ## Run formatters over the backend
	cd $(BACKEND) && $(UV) run ruff format
	cd $(BACKEND) && $(UV) run ruff check --fix

lint: ## Run ruff linter over the backend
	cd $(BACKEND) && $(UV) run ruff format --check
	cd $(BACKEND) && $(UV) run ruff check

typecheck: ## Run pyright type checker over the backend
	cd $(BACKEND) && $(UV) run pyright .

test: test-backend test-frontend ## Run all tests (backend + frontend)

test-backend: ## Run pytest for the backend
	cd $(BACKEND) && $(UV) run pytest
	cd $(BACKEND) && $(UV) run coverage xml
	cd $(BACKEND) && $(UV) run coverage html

test-frontend: ## Run vitest for the frontend
	cd $(FRONTEND) && npm run test

# ── Clean ─────────────────────────────────────────────────────────────────────

clean: ## Remove build artefacts and caches
	rm -rf $(FRONTEND)/dist
	rm -rf $(BACKEND)/.venv
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
