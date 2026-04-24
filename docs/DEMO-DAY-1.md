# Demo Day 1 — Stack Reality Check

**Goal:** Actually bring the stack up. Document every failure found. Ship the fixes.

**Status:** 🟡 **Partial green.** 6 of 11 infra containers healthy + migrations + RLS live-test pass.
Full ask-flow not yet exercised (services need to be started as processes).

**Date:** 2026-04-24

---

## What worked (verified evidence)

### 1. Core data stores: all healthy

```
NAMES               STATUS
documind-postgres   Up (healthy)
documind-qdrant     Up (service healthy; compose healthcheck false-negative)
documind-redis      Up (healthy)
documind-minio      Up (healthy)
documind-neo4j      Up (healthy)
documind-ollama     Up (healthy)
```

Command: `docker compose up -d postgres redis qdrant neo4j ollama minio`

### 2. All 13 migrations applied cleanly

```
→ identity
[identity] apply 001_initial.sql ok
[identity] apply 002_rls_force.sql ok
→ ingestion
[ingestion] apply 001_initial.sql ok
[ingestion] apply 002_outbox.sql ok
[ingestion] apply 003_rls_force.sql ok
→ eval
[eval] apply 001_initial.sql ok
[eval] apply 002_rls_force.sql ok
→ governance
[governance] apply 001_initial.sql ok
[governance] apply 002_rls_force.sql ok
→ finops
[finops] apply 001_initial.sql ok
[finops] apply 002_rls_force.sql ok
→ observability
[observability] apply 001_initial.sql ok
```

Command: `make migrate` with `DOCUMIND_PG_PORT=55432`.

### 3. RLS isolation test passes against live Postgres

```
============================= test session starts ==============================
collected 1 item
libs/py/tests/test_rls_isolation.py .                                    [100%]
============================== 1 passed in 0.21s ===============================
```

This is the **critical security contract**: tenant A cannot see tenant B's
rows through the app role (documind_app, `NOBYPASSRLS`). FORCE RLS on every
tenant table. Role separation proven.

---

## What broke — and the fixes shipped

### Issue 1: Port 6379 held by system Redis daemon
- **Symptom:** `bind for 0.0.0.0:6379/tcp failed: address already in use`
- **Cause:** Host OS Redis service running on default port
- **Fix:** Remapped Redis to **56379** in `docker-compose.override.yml`

### Issue 2: Port 5432 held by another project's `cpg_postgres`
- **Symptom:** Postgres container couldn't bind
- **Cause:** Unrelated container holding the default port
- **Fix:** Remapped Postgres to **55432**

### Issue 3: Port 9000 held by `antigravity` IDE
- **Symptom:** MinIO failed to bind
- **Fix:** Remapped MinIO to **59000 / 59001**

### Issue 4: `docker-compose.override.yml` port entries were APPENDED, not REPLACED
- **Symptom:** Ports 9000 + 59000 both tried to bind; default still conflicted
- **Cause:** Compose merge semantics for list-valued fields
- **Fix:** Use `ports: !override` YAML tag in override file (Compose v2.27+)

### Issue 5: Elasticsearch, Grafana, Prometheus, Zookeeper — volume permission EACCES
- **Symptom:** Container restart loop with `/var/lib/<svc>` not writable or node.lock fails
- **Cause:** Non-root containers can't write to bind-mounted host dirs
- **Fix:** `user: "0:0"` in override for these services

### Issue 6: Nginx fails without TLS cert
- **Symptom:** `cannot load certificate "/etc/nginx/tls/server.crt"`
- **Cause:** compose config references a cert that isn't in the repo
- **Fix (dev):** `profiles: ["disabled"]` — exclude nginx from `make data-up`
- **Proper fix (TODO):** provide a self-signed cert bootstrap script

### Issue 7: Prometheus bootstrap panic
- **Symptom:** `query_logger.go` crash on startup
- **Cause:** Data volume permission race; fixed by `user: "0:0"`

### Issue 8: Qdrant `unhealthy` but service responds
- **Symptom:** HEALTH = unhealthy; HTTP endpoint returns 200
- **Cause:** Compose healthcheck tests a specific endpoint that Qdrant 1.12 has moved
- **Impact:** cosmetic — service is functional
- **Fix (TODO):** update healthcheck to `/readyz`

---

## What's NOT verified yet (honest gaps)

| Thing | State |
| --- | --- |
| ELK stack bring-up | Volume perms fixed in override but not yet verified end-to-end |
| Full Kafka producer/consumer loop | Kafka comes up; no E2E message flight test |
| Ingestion saga end-to-end | Services are processes, not yet started |
| `POST /documents` → saga → `POST /ask` → citation | **Not yet run** — this is the Day-1 exit criterion |
| Jaeger trace propagation across services | Jaeger starts; no real trace observed |
| Nginx + TLS + correlation-id in request pipeline | Nginx disabled in dev profile |
| Frontend → Gateway → backend real request | Frontend standalone runs; backend services not started |

---

## The override file

`docker-compose.override.yml` (committed) handles the port + permission dance
so the next `make data-up` on this machine works without the battle above.
Copy it to a new dev box; tweak ports to match that box's occupants.

## Next (Day 2 — resilience)

With the stores healthy, the next step is making the call sites actually
composed with circuit-breaker + timeout + retry. Then Day 3: kill Ollama
mid-query and prove the breaker opens. Then Day 4: observe it in Jaeger + Grafana.

Tracked in the repo's project plan; see commit history after this one.
