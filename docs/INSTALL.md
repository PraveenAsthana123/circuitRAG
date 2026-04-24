# DocuMind — Install Guide

Three install paths. Pick one.

| Path | Use when | Time |
| --- | --- | --- |
| **Docker Compose** | You want the whole stack running locally (demo, dev, CI smoke) | ~10 min |
| **Native dev** | You're iterating on one service and want hot-reload | ~20 min |
| **Kubernetes / Helm** | You're preparing production or staging | ~1 hour |

---

## Prerequisites

| Tool | Version | Notes |
| --- | --- | --- |
| Docker | ≥ 24 | required for Compose path |
| Docker Compose | v2 | comes with modern Docker |
| Python | 3.11+ | required for native dev |
| Go | 1.22+ | required only if hacking the API gateway |
| Node.js | 20 LTS | required only for frontend native dev |
| `make` | any | orchestration |

---

## Path 1 — Docker Compose (fastest)

```bash
git clone <repo>
cd rag
cp .env.template .env
# edit .env: at minimum set DOCUMIND_JWT_SECRET to a strong random string

docker compose up -d

# Apply migrations across all services (idempotent)
make migrate

# Smoke check
curl http://localhost:8080/health    # gateway
curl http://localhost:3000           # frontend

# Seed a demo tenant + user
make seed-demo
```

Open <http://localhost:3000>. Upload a document, ask a question.

**Ports exposed on localhost:**

| Port | Service |
| --- | --- |
| 3000 | frontend (Next.js) |
| 8080 | api-gateway |
| 5432 | postgres |
| 6333 | qdrant |
| 6379 | redis |
| 9000 | minio |
| 9090 | prometheus |
| 3001 | grafana (admin/admin, change on first login) |
| 16686 | jaeger |
| 5601 | kibana |

**Tear down:** `docker compose down -v` (the `-v` drops volumes — your test data goes too).

---

## Path 2 — Native dev (one service at a time)

Spin up only the deps in Docker, run the service you're hacking on natively.

```bash
# Just the stateful infra
docker compose up -d postgres qdrant neo4j redis kafka ollama minio

# Create a Python venv for the workspace
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e 'libs/py[dev]'

# Pick a service, run it with reload
cd services/retrieval-svc
pip install -e .
uvicorn app.main:app --reload --port 8082
```

The service will use the Docker-hosted Postgres/Qdrant/etc via the defaults in `.env`. Run migrations from the service's own directory:

```bash
cd services/retrieval-svc
python -m app.migrate
```

**Frontend native dev:**

```bash
cd services/frontend
npm install
npm run dev   # http://localhost:3000 with hot reload
```

---

## Path 3 — Kubernetes / Helm

This is the production path. Assumes:

- K8s cluster ≥ 1.28
- Istio 1.23 installed (we rely on mTLS STRICT + AuthorizationPolicy)
- `kubectl` + `helm` 3.x

```bash
cd infra/helm
helm dependency update
helm install documind . \
  --namespace documind --create-namespace \
  --values values.prod.yaml \
  --set jwt.secret=<strong-secret> \
  --set db.password=<strong-db-password>
```

Production values.yaml enforces:

- `postgres.roles` with three separated roles (`documind` owner, `documind_app` runtime NOBYPASSRLS, `documind_ops` BYPASSRLS)
- Istio `AuthorizationPolicy` per-service
- `PodSecurityPolicy` (non-root, read-only root fs, no privilege escalation)
- `NetworkPolicy` denying egress to anything except the declared upstream services

See `infra/helm/values.prod.yaml` for the full manifest.

---

## Migrations

Every service owns its own migration folder under `services/<svc>/migrations/`. The `make migrate` target loops through them in version order.

```bash
make migrate                           # all services
make migrate SERVICE=ingestion-svc    # one service
```

Migrations are **forward-only**. A rollback is a new migration that reverses the change. Never edit a deployed migration.

---

## Verifying the install

```bash
# End-to-end smoke test
make smoke

# Security-critical: cross-tenant RLS test
DOCUMIND_PG_HOST=localhost \
  pytest libs/py/tests/test_rls_isolation.py -v
```

The RLS test **must** pass. If it doesn't, you have a tenant-data-leak bug — do not serve live traffic.

---

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `could not connect to Postgres` | `.env` password doesn't match Docker volume | `docker compose down -v && docker compose up -d` |
| Port 5432 in use | Host Postgres running | stop it, or set `DOCUMIND_PG_PORT=55432` and restart compose |
| `ollama: model 'llama3' not found` | Model not pulled | `docker exec documind-ollama ollama pull llama3` |
| Frontend shows "API unreachable" | Gateway not running / wrong URL | check `NEXT_PUBLIC_API_BASE_URL` in frontend `.env.local` |
| Test `test_cross_tenant_read_is_empty` fails | RLS broken (role or FORCE missing) | see [ARCHITECT-TALKING-POINTS.md §2](ARCHITECT-TALKING-POINTS.md) |
