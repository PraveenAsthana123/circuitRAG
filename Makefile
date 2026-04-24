# ============================================================================
# DocuMind — Developer Makefile
# ============================================================================
# Self-documenting: `make help` shows every target with its description.
# Conventions:
#   *-up / *-down        : lifecycle targets for a layer
#   *-logs / *-shell     : operational access to a running layer
#   *-test / *-lint      : quality gates
# ============================================================================

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE ?= docker compose
PY ?= python3

# ----------------------------------------------------------------------------
# Help
# ----------------------------------------------------------------------------
.PHONY: help
help: ## Show this help
	@echo ""
	@echo "DocuMind — common developer targets"
	@echo "-----------------------------------"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z0-9_.-]+:.*?## / { printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST) | sort
	@echo ""

# ----------------------------------------------------------------------------
# Local dev environment (Docker Compose)
# ----------------------------------------------------------------------------
.PHONY: data-up data-down data-logs data-ps
data-up: ## Start all data stores (Postgres, Qdrant, Neo4j, Redis, Kafka, Ollama, MinIO)
	$(COMPOSE) -f docker-compose.yml up -d
	@echo ""
	@echo "Waiting for data stores to be healthy..."
	@sleep 5
	@$(MAKE) data-ps

data-down: ## Stop all data stores (preserves volumes)
	$(COMPOSE) -f docker-compose.yml stop

data-wipe: ## Stop data stores AND delete all volumes (destructive)
	$(COMPOSE) -f docker-compose.yml down -v

data-logs: ## Tail all data-store logs
	$(COMPOSE) -f docker-compose.yml logs -f --tail=100

data-ps: ## Show health of data stores
	$(COMPOSE) -f docker-compose.yml ps

# ----------------------------------------------------------------------------
# Ollama — pull models required by the stack
# ----------------------------------------------------------------------------
.PHONY: ollama-pull ollama-list
ollama-pull: ## Pull LLM + embedding models into local Ollama
	@echo "Pulling llama3.1:8b (LLM) ..."
	$(COMPOSE) exec ollama ollama pull llama3.1:8b || true
	@echo "Pulling nomic-embed-text (embeddings) ..."
	$(COMPOSE) exec ollama ollama pull nomic-embed-text || true

ollama-list: ## List locally available Ollama models
	$(COMPOSE) exec ollama ollama list

# ----------------------------------------------------------------------------
# Migrations — one target per service schema
# ----------------------------------------------------------------------------
.PHONY: migrate migrate-identity migrate-ingestion migrate-eval migrate-governance migrate-finops migrate-observability
migrate: migrate-identity migrate-ingestion migrate-eval migrate-governance migrate-finops migrate-observability ## Run ALL migrations

migrate-identity:
	@echo "→ identity"; $(PY) scripts/migrate.py services/identity-svc/migrations identity

migrate-ingestion:
	@echo "→ ingestion"; $(PY) scripts/migrate.py services/ingestion-svc/migrations ingestion

migrate-eval:
	@echo "→ eval"; $(PY) scripts/migrate.py services/evaluation-svc/migrations eval

migrate-governance:
	@echo "→ governance"; $(PY) scripts/migrate.py services/governance-svc/migrations governance

migrate-finops:
	@echo "→ finops"; $(PY) scripts/migrate.py services/finops-svc/migrations finops

migrate-observability:
	@echo "→ observability"; $(PY) scripts/migrate.py services/observability-svc/migrations observability

# ----------------------------------------------------------------------------
# Seed + smoke test
# ----------------------------------------------------------------------------
.PHONY: seed smoke
seed: ## Seed demo tenant + sample documents
	$(PY) scripts/seed_demo.py

smoke: ## Run end-to-end smoke test (upload → retrieve → generate)
	$(PY) scripts/smoke_test.py

# ----------------------------------------------------------------------------
# Services — native run (Docker Compose for data stores, process per service)
# ----------------------------------------------------------------------------
.PHONY: run-ingestion run-retrieval run-inference run-evaluation
run-ingestion: ## Run ingestion service on $INGESTION_HTTP_PORT
	cd services/ingestion-svc && uvicorn app.main:app --host 0.0.0.0 --port $${INGESTION_HTTP_PORT:-8082} --reload

run-retrieval: ## Run retrieval service on $RETRIEVAL_HTTP_PORT
	cd services/retrieval-svc && uvicorn app.main:app --host 0.0.0.0 --port $${RETRIEVAL_HTTP_PORT:-8083} --reload

run-inference: ## Run inference service on $INFERENCE_HTTP_PORT
	cd services/inference-svc && uvicorn app.main:app --host 0.0.0.0 --port $${INFERENCE_HTTP_PORT:-8084} --reload

run-evaluation: ## Run evaluation service on $EVALUATION_HTTP_PORT
	cd services/evaluation-svc && uvicorn app.main:app --host 0.0.0.0 --port $${EVALUATION_HTTP_PORT:-8085} --reload

.PHONY: run-gateway run-identity run-governance run-finops run-observability
run-gateway: ## Run API gateway (Go)
	cd services/api-gateway && go run ./cmd

run-identity: ## Run identity service (Go)
	cd services/identity-svc && go run ./cmd

run-governance: ## Run governance service (Go)
	cd services/governance-svc && go run ./cmd

run-finops: ## Run FinOps service (Go)
	cd services/finops-svc && go run ./cmd

run-observability: ## Run observability service (Go)
	cd services/observability-svc && go run ./cmd

.PHONY: run-frontend install-frontend
install-frontend: ## Install frontend dependencies
	cd services/frontend && (command -v pnpm >/dev/null && pnpm i) || (cd services/frontend && npm install)

run-frontend: ## Run frontend dev server (Next.js)
	cd services/frontend && npm run dev

# ----------------------------------------------------------------------------
# Quality gates
# ----------------------------------------------------------------------------
.PHONY: lint-py lint-go lint-js test-py test-go test-js test lint eval
lint: lint-py lint-go lint-js ## Lint everything

lint-py:
	ruff check libs/py services/ingestion-svc services/retrieval-svc services/inference-svc services/evaluation-svc scripts
	black --check libs/py services/ingestion-svc services/retrieval-svc services/inference-svc services/evaluation-svc scripts
	mypy --ignore-missing-imports libs/py services/ingestion-svc services/retrieval-svc services/inference-svc services/evaluation-svc

lint-go:
	cd libs/go && gofmt -l . | (! grep .)
	@for svc in api-gateway identity-svc governance-svc finops-svc observability-svc; do \
		echo "→ lint $$svc"; cd services/$$svc && gofmt -l . | (! grep .) && go vet ./... && cd -; \
	done

lint-js:
	cd services/frontend && npm run lint

test: test-py test-go test-js ## Test everything

test-py:
	pytest -q services/ingestion-svc/tests services/retrieval-svc/tests services/inference-svc/tests services/evaluation-svc/tests libs/py

test-go:
	@for svc in api-gateway identity-svc governance-svc finops-svc observability-svc; do \
		echo "→ test $$svc"; cd services/$$svc && go test -race ./... && cd -; \
	done

test-js:
	cd services/frontend && npm test

eval: ## Run full offline evaluation suite
	$(PY) scripts/run_eval.py

# ----------------------------------------------------------------------------
# Proto + event-schema generation
# ----------------------------------------------------------------------------
.PHONY: proto schemas
proto: ## Regenerate gRPC Python + Go clients from proto/
	$(PY) scripts/gen_proto.py

schemas: ## Validate all CloudEvents JSON schemas under schemas/events/
	$(PY) scripts/validate_event_schemas.py

# ----------------------------------------------------------------------------
# Chaos + regression
# ----------------------------------------------------------------------------
.PHONY: chaos regression
chaos: ## Inject fault scenarios (ollama down, Qdrant slow, etc.)
	$(PY) scripts/chaos.py

regression: ## Run regression gate against baseline
	$(PY) scripts/regression_gate.py

# ----------------------------------------------------------------------------
# Docs
# ----------------------------------------------------------------------------
.PHONY: docs-serve
docs-serve: ## Serve docs/ on port 8000 for local browsing
	$(PY) -m http.server 8000 --directory docs
