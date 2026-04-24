# Phase 1 — Edge, Traffic, Security

API Gateway · CDN · Load Balancer · mTLS · Istio.
Every scenario below has a concrete verification command. If you can't run it, the scenario hasn't shipped.

---

## 1. API Gateway scenarios

### 1.1 JWT validation — happy path

- **Intent:** Valid signed JWT → gateway extracts tenant + scopes → forwards.
- **Verification:**
  ```bash
  TOKEN=$(curl -sX POST http://localhost:8080/api/v1/identity/token \
    -d '{"username":"demo","password":"demo"}' -H 'Content-Type: application/json' \
    | jq -r .access_token)
  curl -sf http://localhost:8080/api/v1/documents \
    -H "Authorization: Bearer $TOKEN"
  ```
- **Expected:** 200 + JSON body.
- **Failure test:** omit Authorization header → expect 401 + envelope `{"detail":"missing token","error_code":"AUTH_MISSING","correlation_id":"..."}`.

### 1.2 Invalid / expired JWT

- **Verification:**
  ```bash
  curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/api/v1/documents \
    -H "Authorization: Bearer invalid.jwt.here"
  ```
- **Expected:** `401`.
- **Fix:** client calls `/api/v1/identity/refresh` with refresh token.

### 1.3 Tenant claim propagation

- **Intent:** `tenant_id` from JWT reaches every downstream span + SQL `app.current_tenant`.
- **Verification:**
  ```bash
  CID=$(uuidgen)
  curl -s http://localhost:8080/api/v1/ask -H "X-Correlation-Id: $CID" \
    -H "Authorization: Bearer $TOKEN" -d '{"question":"hi"}'
  # Then look it up across every service log:
  docker logs documind-ingestion-svc 2>&1 | grep "$CID" | head -3
  docker logs documind-retrieval-svc 2>&1 | grep "$CID" | head -3
  # And in traces:
  curl -s "http://localhost:16686/api/traces?tag=correlation_id=$CID&limit=1" | jq '.data[0].spans | length'
  ```
- **Expected:** correlation-id appears in every log; span count > 1 in Jaeger.

### 1.4 Per-tenant rate limit

- **Intent:** Bursty tenant cannot exhaust others.
- **Verification:**
  ```bash
  for i in {1..120}; do \
    curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" \
      http://localhost:8080/api/v1/ask -d '{"question":"x"}'; \
  done | sort | uniq -c
  ```
- **Expected:** mostly `200`, then `429` beginning around the 100th request, with `Retry-After` header present.
- **Fix / Fallback:** client honors `Retry-After`.

### 1.5 Correlation-id auto-injection

- **Verification:**
  ```bash
  curl -s -o /dev/null -D - http://localhost:8080/api/v1/ask \
    -H "Authorization: Bearer $TOKEN" -d '{"question":"x"}' \
    | grep -i x-correlation-id
  ```
- **Expected:** response header `X-Correlation-Id: <uuid>` (injected if client omitted it).

### 1.6 CORS + security headers

- **Verification:**
  ```bash
  curl -sI http://localhost:8080/api/v1/documents -H "Origin: https://evil.example" \
    | grep -iE 'access-control-allow-origin|strict-transport-security|x-frame-options|content-security-policy'
  ```
- **Expected:** CORS rejects evil origin; HSTS + X-Frame-Options + CSP present.

### 1.7 Request size limit

- **Verification:**
  ```bash
  head -c 20M </dev/urandom | base64 | curl -s -o /dev/null -w '%{http_code}' \
    http://localhost:8080/api/v1/ask -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' --data-binary @-
  ```
- **Expected:** `413` Payload Too Large.

### 1.8 OpenAPI contract

- **Verification:** `curl -sf http://localhost:8080/api/docs.json | jq '.paths | keys | length'`
- **Expected:** non-zero count; matches exposed routes.

### 1.9 Routing to services

- **Verification:** `curl -sf http://localhost:8080/api/v1/health/services | jq`
- **Expected:** one entry per backend (ingestion / retrieval / inference / governance / …) with `status: "ok"`.

### 1.10 Degraded-mode response

- **Failure test:** stop retrieval-svc: `docker compose stop retrieval-svc`
- **Verification:** `curl -sf http://localhost:8080/api/v1/ask -d '{"question":"x"}' -H "Authorization: Bearer $TOKEN"`
- **Expected:** 503 envelope `{"detail":"retrieval temporarily unavailable","degraded":true,"correlation_id":"..."}`. Never 5xx unstructured.

---

## 2. CDN scenarios

### 2.1 Static asset via edge cache

- **Verification:**
  ```bash
  curl -sI https://app.documind.local/assets/main.js | grep -iE 'cache-control|x-cache'
  ```
- **Expected:** `Cache-Control: public, max-age=31536000, immutable`, `X-Cache: HIT` on repeat.

### 2.2 Conditional revalidation

- **Verification:**
  ```bash
  ETAG=$(curl -sI https://app.documind.local/assets/main.js | awk '/ETag/ {print $2}' | tr -d '\r')
  curl -s -o /dev/null -w '%{http_code}' -H "If-None-Match: $ETAG" https://app.documind.local/assets/main.js
  ```
- **Expected:** `304`.

### 2.3 Private RAG answer NEVER cached

- **Intent:** the single most important CDN rule in this product.
- **Verification:**
  ```bash
  curl -sI https://app.documind.local/api/v1/ask -X POST \
    -H "Authorization: Bearer $TOKEN" -d '{"question":"x"}' \
    | grep -iE 'cache-control'
  ```
- **Expected:** `Cache-Control: no-store, private`. If any `max-age` or `public` appears here the CDN rule is broken.

### 2.4 Signed URL for exported reports

- **Verification:** POST to `/api/v1/exports/:id` returns a URL with `?signature=...&expires=...`. Try it after `expires` → 403.

### 2.5 Edge WAF — common attacks blocked

- **Verification:**
  ```bash
  for path in "/?q=<script>alert(1)</script>" "/?q=' OR 1=1--" "/?q=../../etc/passwd"; do \
    curl -s -o /dev/null -w "$path %{http_code}\n" "https://app.documind.local$path"; \
  done
  ```
- **Expected:** 403 or 400 on each.

### 2.6 Cache purge on deploy

- **Verification:** CI job emits `curl -X POST $CDN_PURGE_API -d '{"prefix":"/assets"}'`; next request returns `X-Cache: MISS`, then `HIT`.

---

## 3. Load Balancer scenarios

### 3.1 Health-check routing

- **Verification:**
  ```bash
  # Kill one inference-svc pod; traffic should keep flowing.
  kubectl delete pod -l app=inference-svc --grace-period=0 --force -n documind | head -1
  for i in {1..20}; do curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/v1/ask \
    -H "Authorization: Bearer $TOKEN" -d '{"question":"x"}'; done | sort | uniq -c
  ```
- **Expected:** all 200s; killed pod is out of the LB pool within the readiness-probe interval.

### 3.2 Canary — weighted routing

- **Verification (via Istio VS):**
  ```yaml
  # v1 90%, v2 10% — see infra/istio/40-virtualservice-inference.yaml
  ```
  ```bash
  for i in {1..100}; do curl -s http://localhost:8080/api/v1/ask \
    -H "Authorization: Bearer $TOKEN" -d '{"question":"x"}' \
    | jq -r '.model_version'; done | sort | uniq -c
  ```
- **Expected:** ~90 × v1, ~10 × v2.

### 3.3 Sticky session avoidance

- **Verification:** 10 requests from the same client; check response header `X-Served-By` distinct values.

### 3.4 Burst traffic handling

- **Verification:** `hey -n 10000 -c 200 ...` → p95 under SLA; no 5xx.

### 3.5 Failover between regions

- **Verification (requires multi-region):** simulate region A down via DNS; traffic shifts to B; p95 does not exceed cold-start window.

---

## 4. mTLS scenarios

### 4.1 Gateway → service traffic encrypted

- **Verification:**
  ```bash
  # Exec into a pod and try plain HTTP against the backend — should fail.
  kubectl exec -it deploy/debug-pod -n documind -- \
    curl -s -o /dev/null -w '%{http_code}' http://retrieval-svc:8082/health
  ```
- **Expected:** connection refused / 503. mTLS STRICT rejects non-TLS.

### 4.2 Service identity (SPIFFE)

- **Verification:**
  ```bash
  kubectl exec -it deploy/inference-svc -c istio-proxy -- \
    pilot-agent request GET certs | jq '.certificates[0].cert_chain[0].serial_number'
  ```
- **Expected:** valid cert; `spiffe://cluster.local/ns/documind/sa/inference-sa` in SAN.

### 4.3 Certificate rotation

- **Verification:** `istioctl pc secret deploy/inference-svc | jq '.dynamicActiveSecrets[].secret.tlsCertificate.certificateChain.inlineBytes' | head -1` before and after 24h; chain changed.

### 4.4 Namespace isolation

- **Verification:** deploy a pod in another namespace without permission; attempt to call retrieval-svc → 403 from AuthorizationPolicy.

### 4.5 Dev vs prod certs

- **Verification:** `istioctl analyze` returns clean in both envs; no shared root keys.

---

## 5. Istio scenarios

### 5.1 mTLS STRICT mesh-wide

- **Verification:**
  ```bash
  kubectl get peerauthentication -n documind -o yaml | grep 'mode:' | head
  ```
- **Expected:** every PeerAuthentication has `mode: STRICT`.

### 5.2 AuthorizationPolicy default-deny

- **Verification:**
  ```bash
  kubectl get authorizationpolicy -n documind -o json \
    | jq '.items[] | {name:.metadata.name, action:.spec.action, from:.spec.rules}'
  ```
- **Expected:** at least one `action: DENY` applying to everything; explicit `ALLOW` rules per legitimate peer.

### 5.3 VirtualService canary split

- **Verification:** `kubectl get virtualservice inference-canary -n documind -o jsonpath='{.spec.http[0].route}' | jq`
- **Expected:** two destinations with weights summing to 100.

### 5.4 DestinationRule outlier detection

- **Verification:**
  ```yaml
  outlierDetection:
    consecutive5xxErrors: 5
    interval: 30s
    baseEjectionTime: 30s
    maxEjectionPercent: 50
  ```
  ```bash
  kubectl get destinationrule inference -n documind -o yaml | grep -A6 outlierDetection
  ```

### 5.5 Retry policy

- **Verification:** `retries: { attempts: 3, perTryTimeout: 2s, retryOn: 5xx,connect-failure }` in VS.

### 5.6 Fault injection (chaos)

- **Verification:**
  ```bash
  # Apply a 30% 500 injection on retrieval-svc
  kubectl apply -f - <<EOF
  apiVersion: networking.istio.io/v1beta1
  kind: VirtualService
  metadata: {name: retrieval-chaos, namespace: documind}
  spec:
    hosts: [retrieval-svc]
    http:
    - fault: { abort: { httpStatus: 500, percentage: { value: 30 } } }
      route: [{destination: {host: retrieval-svc}}]
  EOF
  # Run 100 requests; expect ~30 failures; CB opens.
  ```

### 5.7 AuthorizationPolicy per service

- **Verification:** matrix (who can call whom):
  | Source | Target | Expected |
  |---|---|---|
  | api-gateway | ingestion-svc | ALLOW |
  | api-gateway | retrieval-svc | ALLOW |
  | inference-svc | retrieval-svc | ALLOW |
  | retrieval-svc | inference-svc | DENY (no reverse call) |
  | random-ns | any documind svc | DENY |

### 5.8 Traffic mirroring (shadow)

- **Verification:** `mirror: { host: inference-svc, subset: v2 }, mirrorPercentage: 100` in VS; v2 receives 100% shadow traffic; users never see v2 response.

### 5.9 Telemetry v2

- **Verification:** Grafana panel `istio_requests_total{destination_service=~"retrieval-svc.*"}` non-empty.

### 5.10 Service → DestinationRule → VirtualService mapping

| Service | DestinationRule | VirtualService | Purpose |
| --- | --- | --- | --- |
| api-gateway | `dr-api-gateway` | `vs-api-gateway` | 3 retries on 5xx, 5s timeout |
| retrieval-svc | `dr-retrieval` | `vs-retrieval` | outlier detection, 2s timeout |
| inference-svc | `dr-inference-canary` | `vs-inference-canary` | 90/10 canary, 3 retries, CB limits |
| governance-svc | `dr-governance` | `vs-governance` | strict authz, 1s timeout |
| any-svc | `dr-default` | `vs-default` | fallback policy |

---

## 6. Failure tests (Phase 1 chaos drills)

| Drill | Command | Expected behaviour |
| --- | --- | --- |
| Kill gateway pod | `kubectl delete pod -l app=api-gateway -n documind` | LB reroutes; zero 5xx for > 5 consecutive requests |
| Revoke JWT signing key | edit identity-svc ConfigMap; rotate | existing tokens rejected within JWKS cache TTL; new tokens work |
| Exceed rate limit | 200 RPS from one tenant | 429 + Retry-After; other tenants unaffected |
| Sidecar crash on one pod | `kubectl exec <pod> -c istio-proxy -- kill 1` | Istio restarts sidecar; app pod continues |
| Certificate expiry | set PeerAuth TTL 1m, wait | rotation succeeds; zero downtime |
| CDN origin down | stop backend | CDN serves cached static; `/api/*` returns 503 with envelope |
| mTLS misconfig | apply a bad AuthPolicy | `istioctl analyze` flags it; rollback via `kubectl apply -f <prev>` |

---

## 7. Demo script — Phase 1 (10 min)

1. **[0:00]** `kubectl get pods -n documind` → all Ready
2. **[0:30]** Login flow: `curl .../identity/token` → token
3. **[1:00]** Simple GET: `curl /api/v1/documents -H "Authorization: Bearer $TOKEN"` → 200
4. **[1:30]** Correlation-id: grab it from response headers; open Jaeger; click the trace
5. **[3:00]** Rate limit: run the burst loop → 429 + Retry-After
6. **[4:00]** Canary: run 100 requests → ~10 hit v2
7. **[5:30]** mTLS: exec into a pod, try plain HTTP → refused
8. **[6:30]** AuthorizationPolicy: show DENY matrix
9. **[7:30]** Chaos: apply 30% 500 fault injection on retrieval; watch CB open in Grafana
10. **[9:00]** Recover: remove fault; CB HALF_OPEN → CLOSED

---

## 8. Metrics to show

| Panel | Prometheus query |
| --- | --- |
| Gateway p95 latency | `histogram_quantile(0.95, sum(rate(documind_request_duration_seconds_bucket{service="api-gateway"}[5m])) by (le))` |
| 429 rate by tenant | `sum(rate(documind_request_total{code="429"}[5m])) by (tenant_id)` |
| Canary ratio | `sum(rate(istio_requests_total{destination_version="v2"}[5m])) / sum(rate(istio_requests_total[5m]))` |
| CB state by name | `documind_circuit_breaker_state` |
| mTLS coverage | `istio_tcp_connections_opened_total{security_policy="mutual_tls"}` divided by total |

---

## 9. Gaps this phase should close (brutal list)

| Gap | State |
| --- | --- |
| `infra/istio/` manifests never `kubectl apply`'d in this session | **Open** — requires a `kind`/minikube cluster |
| AuthorizationPolicy DENY matrix not documented as a table | **Closed by this doc** (§5.7) |
| Fault-injection chaos drill not yet scripted into CI | **Open** — `make chaos-phase-1` target is the deliverable |
| `make smoke` hits only `/health`; doesn't run §6 drills | **Open** — extend to cover §6 table |
| Correlation-id propagation not verified end-to-end | **Open** — §1.3 verification command is the test |
| CDN rule "never cache private answers" not enforced in code | **Open** — inspect gateway response headers on `/api/v1/ask` |

Every row labeled "Open" here is a concrete unit of Day-2 / Day-3 work.
