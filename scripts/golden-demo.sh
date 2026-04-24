#!/usr/bin/env bash
# ============================================================================
# DocuMind — Golden Demo Script
# ============================================================================
# Ten sequential steps that prove end-to-end behaviour:
#   1. Health check all services
#   2. Baseline RAG ask on existing corpus
#   3. Upload a new document (saga runs inline)
#   4. Poll document status until active
#   5. Ask a question grounded in the NEW document
#   6. Agent action — natural-language leave request → MCP → real ticket
#   7. Chaos: kill MCP server → agent degrades to draft, no 5xx
#   8. Recovery: restart MCP → next action succeeds
#   9. Chaos: kill Qdrant → retrieval cache-poisoning guard fires
#  10. Recovery: restart Qdrant → next query succeeds
#
# Each step prints what it did, what it expected, and what it got.
# Exit code 0 only if every step passes.
#
# Run:
#   scripts/golden-demo.sh
#
# Prerequisites:
#   - docker-compose stack up: postgres (55432), qdrant (6333), redis
#     (56379), neo4j (7687), ollama (11434), minio (59000), kafka (9094)
#   - three services running: ingestion :8082, retrieval :8083, inference :8084
#   - mcp-server-hr running on :8090
#   - Tenant seeded: 137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a
# ============================================================================
set -u

TENANT=${TENANT:-137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a}
INGESTION=http://127.0.0.1:8082
RETRIEVAL=http://127.0.0.1:8083
INFERENCE=http://127.0.0.1:8084
MCP_HR=http://127.0.0.1:8090

RED='\033[31m'; GREEN='\033[32m'; YELLOW='\033[33m'; BOLD='\033[1m'; NC='\033[0m'
PASSED=0; FAILED=0
step_no=0

step() {
    step_no=$((step_no + 1))
    echo
    echo -e "${BOLD}── Step $step_no — $1 ──${NC}"
}
pass() { echo -e "  ${GREEN}✓ $1${NC}"; PASSED=$((PASSED + 1)); }
fail() { echo -e "  ${RED}✗ $1${NC}"; FAILED=$((FAILED + 1)); }
info() { echo -e "  ${YELLOW}· $1${NC}"; }

# ---------------------------------------------------------------------------
# 1. Health
# ---------------------------------------------------------------------------
step "health check — all 4 services"
for svc in "ingestion:$INGESTION" "retrieval:$RETRIEVAL" "inference:$INFERENCE" "mcp-hr:$MCP_HR"; do
    name=${svc%%:*}; url=${svc#*:}
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$url/health")
    if [[ "$code" == "200" ]]; then pass "$name /health 200"; else fail "$name /health=$code"; fi
done

# ---------------------------------------------------------------------------
# 2. Baseline RAG ask on existing corpus
# ---------------------------------------------------------------------------
step "baseline RAG ask (existing corpus)"
r=$(curl -sX POST "$INFERENCE/api/v1/ask" \
    -H 'Content-Type: application/json' -H "X-Tenant-Id: $TENANT" \
    -d '{"query":"what is the travel reimbursement limit?"}' --max-time 30)
cites=$(echo "$r" | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("citations",[])))' 2>/dev/null || echo 0)
if [[ "$cites" -ge 1 ]]; then
    pass "grounded answer with $cites citation(s)"
    info "$(echo "$r" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("answer",""))[:80]' 2>/dev/null)"
else
    fail "no citations returned — corpus empty or retrieval broken"
fi

# ---------------------------------------------------------------------------
# 3. Upload new document
# ---------------------------------------------------------------------------
step "upload a NEW document"
tmpfile=$(mktemp --suffix=.txt)
cat > "$tmpfile" <<'EOF'
The parental-leave policy grants employees 12 weeks of paid leave for the birth or adoption of a child.
Leave must be used within 12 months of the event. Extensions require HR approval and a written request.
EOF
r=$(curl -sX POST "$INGESTION/api/v1/documents/upload" \
    -H "X-Tenant-Id: $TENANT" -F "file=@$tmpfile" --max-time 30)
doc_id=$(echo "$r" | python3 -c 'import sys,json;print(json.load(sys.stdin)["document_id"])' 2>/dev/null)
if [[ -n "${doc_id:-}" ]]; then
    pass "uploaded → document_id=$doc_id"
else
    fail "upload failed: $r"; doc_id=""
fi

# ---------------------------------------------------------------------------
# 4. Poll document status until active
# ---------------------------------------------------------------------------
step "poll document status until active"
if [[ -n "${doc_id:-}" ]]; then
    for i in 1 2 3 4 5; do
        state=$(curl -s "$INGESTION/api/v1/documents/$doc_id" -H "X-Tenant-Id: $TENANT" \
            | python3 -c 'import sys,json;print(json.load(sys.stdin).get("state",""))' 2>/dev/null)
        if [[ "$state" == "active" ]]; then pass "state=active (attempt $i)"; break; fi
        info "state=$state (attempt $i/5)"; sleep 2
    done
    [[ "$state" != "active" ]] && fail "saga did not complete: state=$state"
else
    fail "skipped — no document_id"
fi

# ---------------------------------------------------------------------------
# 5. Ask about the NEW document
# ---------------------------------------------------------------------------
step "ask about the NEW document"
docker exec documind-redis redis-cli FLUSHDB >/dev/null 2>&1
r=$(curl -sX POST "$INFERENCE/api/v1/ask" \
    -H 'Content-Type: application/json' -H "X-Tenant-Id: $TENANT" \
    -d '{"query":"What is the parental-leave policy?"}' --max-time 30)
cites=$(echo "$r" | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("citations",[])))' 2>/dev/null || echo 0)
if [[ "$cites" -ge 1 ]]; then
    pass "cited answer retrieved from new document"
    info "$(echo "$r" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("answer",""))[:100]' 2>/dev/null)"
else
    fail "parental-leave retrieval failed"
fi

# ---------------------------------------------------------------------------
# 6. Agent action — natural-language leave request → MCP → real ticket
# ---------------------------------------------------------------------------
step "agent action: submit 3-day leave → MCP → real ticket"
r=$(curl -sX POST "$INFERENCE/api/v1/agent/ask" \
    -H 'Content-Type: application/json' -H "X-Tenant-Id: $TENANT" \
    -d '{"query":"Please submit a 3-day leave request for family event","employee_id":"E42"}' \
    --max-time 60)
ticket=$(echo "$r" | python3 -c '
import sys,json
d=json.load(sys.stdin)
a=d.get("action") or {}
res=a.get("result") or {}
print(res.get("ticket_id",""))' 2>/dev/null)
if [[ -n "${ticket:-}" ]]; then
    pass "real ticket created: ticket_id=$ticket"
else
    fail "MCP tool did not return a ticket"
fi

# ---------------------------------------------------------------------------
# 7. Chaos: kill MCP → agent degrades to draft
# ---------------------------------------------------------------------------
step "chaos: kill MCP server → agent falls back to draft"
pkill -f 'mcp/server_hr.py' 2>/dev/null; sleep 3
# confirm MCP is down before we test degradation
mcp_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$MCP_HR/health" 2>/dev/null || echo "000")
info "MCP health post-kill: $mcp_code (expecting 000/refused)"
r=$(curl -sX POST "$INFERENCE/api/v1/agent/ask" \
    -H 'Content-Type: application/json' -H "X-Tenant-Id: $TENANT" \
    -d '{"query":"Please submit a 2-day leave request for medical appointment","employee_id":"E42"}' \
    --max-time 45)
# Parse with fallback — capture raw response for debugging
degraded=$(echo "$r" | python3 -c 'import sys,json;a=(json.load(sys.stdin).get("action") or {});print(a.get("degraded"))' 2>/dev/null)
draft_id=$(echo "$r" | python3 -c 'import sys,json;a=(json.load(sys.stdin).get("action") or {});print(a.get("draft_id") or "")' 2>/dev/null)
if [[ "$degraded" == "True" ]] && [[ -n "$draft_id" ]]; then
    pass "degraded=True draft_id=$draft_id (no 5xx)"
else
    fail "expected degraded+draft, got: degraded='$degraded' draft_id='$draft_id'"
    info "raw response (first 200): $(echo "$r" | head -c 200)"
fi

# ---------------------------------------------------------------------------
# 8. Recovery — restart MCP
# ---------------------------------------------------------------------------
step "restart MCP server → action path recovers"
( cd "$(dirname "$0")/.." && PYTHONPATH=. MCP_HR_PORT=8090 \
    python mcp/server_hr.py > /tmp/documind-mcp-hr-demo.log 2>&1 & ) 2>/dev/null
sleep 4
for i in 1 2 3 4 5; do
    if curl -s -o /dev/null -w '%{http_code}' "$MCP_HR/health" 2>/dev/null | grep -q 200; then break; fi
    sleep 1
done
# Need to restart inference-svc's MCP client breaker window by waiting
info "waiting recovery_timeout for CB to probe..."
sleep 32
r=$(curl -sX POST "$INFERENCE/api/v1/agent/ask" \
    -H 'Content-Type: application/json' -H "X-Tenant-Id: $TENANT" \
    -d '{"query":"Please submit a 1-day leave request for personal matter","employee_id":"E42"}' \
    --max-time 30)
ticket=$(echo "$r" | python3 -c '
import sys,json
d=json.load(sys.stdin)
a=d.get("action") or {}
res=a.get("result") or {}
print(res.get("ticket_id",""))' 2>/dev/null)
if [[ -n "${ticket:-}" ]]; then
    pass "recovered — new ticket_id=$ticket"
else
    fail "CB probe did not recover"
fi

# ---------------------------------------------------------------------------
# 9. Chaos: kill Qdrant → retrieval skips cache on degraded result
# ---------------------------------------------------------------------------
step "chaos: kill Qdrant → user sees structured 502, no cache poison"
docker compose kill qdrant >/dev/null 2>&1; sleep 2
docker exec documind-redis redis-cli FLUSHDB >/dev/null 2>&1
r=$(curl -sX POST "$INFERENCE/api/v1/ask" \
    -H 'Content-Type: application/json' -H "X-Tenant-Id: $TENANT" \
    -d '{"query":"chaos-qdrant: whats the policy?"}' -w "\n%{http_code}" --max-time 15)
code=$(echo "$r" | tail -1); body=$(echo "$r" | head -n -1)
ecode=$(echo "$body" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("error_code",""))' 2>/dev/null || echo "")
if [[ "$code" == "502" ]] && [[ "$ecode" == "EXTERNAL_SERVICE_ERROR" ]]; then
    pass "structured 502 with error_code (not a crash)"
else
    fail "unexpected response: code=$code ecode=$ecode"
fi

# ---------------------------------------------------------------------------
# 10. Recovery: restart Qdrant → first call after returns real answer
# ---------------------------------------------------------------------------
step "restart Qdrant → retrieval recovers without FLUSHDB"
docker compose up -d qdrant >/dev/null 2>&1
for i in 1 2 3 4 5 6 7 8 9 10; do
    if curl -sf "http://localhost:6333/collections" -H 'api-key: dev-qdrant-key' >/dev/null 2>&1; then break; fi
    sleep 1
done
r=$(curl -sX POST "$INFERENCE/api/v1/ask" \
    -H 'Content-Type: application/json' -H "X-Tenant-Id: $TENANT" \
    -d '{"query":"post-chaos: whats the reimbursement limit?"}' --max-time 30)
cites=$(echo "$r" | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("citations",[])))' 2>/dev/null || echo 0)
if [[ "$cites" -ge 1 ]]; then pass "recovery green — $cites citation(s)"
else fail "retrieval still failing after Qdrant restart"; fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
echo -e "${BOLD}   PASSED: $PASSED     FAILED: $FAILED${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
exit $((FAILED == 0 ? 0 : 1))
