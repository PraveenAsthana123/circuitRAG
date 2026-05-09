#!/bin/bash
# Single-command status / restore script for circuitRAG.
# Restores dead daemons, runs every readiness probe, prints a verdict.
#
# Usage from repo root:
#   bash scripts/circuitrag-status.sh                    # full check + restore
#   bash scripts/circuitrag-status.sh --no-restore       # status only, don't touch daemons
#   bash scripts/circuitrag-status.sh --quiet            # one-line summary only
#
# Exit codes:
#   0  all-green
#   1  one or more probes red
#   2  daemon restart failed

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

RESTORE=true
QUIET=false
for arg in "$@"; do
  case "$arg" in
    --no-restore) RESTORE=false ;;
    --quiet)      QUIET=true ;;
    -h|--help)
      sed -n '2,12p' "$0"; exit 0 ;;
  esac
done

GREEN='\033[32m'; RED='\033[31m'; YELLOW='\033[33m'; GRAY='\033[90m'
BOLD='\033[1m'; NC='\033[0m'

# Track failures for final exit code
fails=0
warns=0

step()  { $QUIET || echo -e "\n${BOLD}── $1 ──${NC}"; }
ok()    { $QUIET || echo -e "  ${GREEN}✓${NC} $1"; }
warn()  { $QUIET || echo -e "  ${YELLOW}⚠${NC} $1"; warns=$((warns+1)); }
bad()   { $QUIET || echo -e "  ${RED}✗${NC} $1"; fails=$((fails+1)); }

# ── 1. Daemon restart (idempotent) ───────────────────────────────────
if $RESTORE; then
  step "1. Daemon restore (idempotent)"

  # Kiali port-forward (dies on shell rotation; setsid+nohup helps but
  # not perfectly across all parent-shell signals)
  if ! curl -sf -o /dev/null http://localhost:20001/kiali/healthz 2>/dev/null; then
    bash scripts/kiali-port-forward.sh > /tmp/kiali-pf-restore.log 2>&1 \
      && ok "Kiali port-forward restored (:20001)" \
      || { bad "Kiali port-forward FAILED — see /tmp/kiali-pf-restore.log"; }
  else
    ok "Kiali port-forward already alive (:20001)"
  fi

  # Agent-orchestrator-svc
  if ! curl -sf -o /dev/null http://localhost:8050/health/live 2>/dev/null; then
    bash scripts/agent-orchestrator-up.sh > /tmp/orch-restore.log 2>&1 \
      && ok "agent-orchestrator-svc restored (:8050)" \
      || { bad "agent-orchestrator-svc FAILED — see /tmp/orch-restore.log"; }
  else
    ok "agent-orchestrator-svc already alive (:8050)"
  fi
else
  step "1. Daemon restore SKIPPED (--no-restore)"
fi

# ── 2. Live BFF — 19 tools traffic-light ────────────────────────────
step "2. Live BFF — 19-tool integrations-health"
BFF_JSON=$(curl -sf http://localhost:3000/api/v1/integrations-health 2>/dev/null || echo "")
if [[ -n "$BFF_JSON" ]]; then
  COUNTS=$(echo "$BFF_JSON" | python3 -c "
import json,sys
d=json.load(sys.stdin)
c={}
for t in d['tools']:
    c[t['status']]=c.get(t['status'],0)+1
for s in ['HEALTHY','DEGRADED','UNREACHABLE','NOT_CONFIGURED','TCP_ONLY']:
    if c.get(s):
        print(f'{s}={c[s]}', end=' ')
" 2>/dev/null)
  HEALTHY=$(echo "$BFF_JSON" | python3 -c "import json,sys; d=json.load(sys.stdin); print(sum(1 for t in d['tools'] if t['status']=='HEALTHY'))" 2>/dev/null)
  TOTAL=$(echo "$BFF_JSON" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['tools']))" 2>/dev/null)
  if [[ "$HEALTHY" == "$TOTAL" ]]; then
    ok "all $HEALTHY/$TOTAL tools HEALTHY  ($COUNTS)"
  else
    bad "$HEALTHY/$TOTAL tools HEALTHY — $COUNTS"
  fi
else
  bad "frontend BFF unreachable on :3000"
fi

# ── 3. Agent-readiness — 7 dimensions ───────────────────────────────
step "3. Agent-readiness — 7 dimensions"
AR_JSON=$(curl -sf http://localhost:3000/api/v1/agent-readiness 2>/dev/null || echo "")
if [[ -n "$AR_JSON" ]]; then
  YES=$(echo "$AR_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['by_status'].get('YES',0))" 2>/dev/null)
  NO=$(echo "$AR_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['by_status'].get('NO',0))" 2>/dev/null)
  TOTAL_AR=$((YES + NO))
  if [[ "$NO" == "0" ]]; then
    ok "all $YES/$TOTAL_AR agent-readiness dimensions YES"
  else
    bad "$YES YES / $NO NO of $TOTAL_AR — see /admin/agent-readiness"
  fi
else
  warn "agent-readiness BFF unreachable (frontend down?)"
fi

# ── 4. Ollama smoke (cached result) ─────────────────────────────────
step "4. Ollama models (cached smoke)"
if [[ -f .loop/ollama_smoke_results.json ]]; then
  python3 -c "
import json,sys
d=json.load(open('.loop/ollama_smoke_results.json'))
c=d['by_status']
total=sum(c.values())
working=c.get('WORKING',0)
print(f\"  {working}/{total} models WORKING — last smoked {d['smoked_at'][:19]}\")
if working == total:
    sys.exit(0)
else:
    print(f\"  bad: {dict((k,v) for k,v in c.items() if k!='WORKING')}\")
    sys.exit(1)
" && ok "models smoke green" || warn "some models not WORKING (re-run: scripts/ollama_all_models_smoke.py)"
else
  warn "no ollama_smoke_results.json — run scripts/ollama_all_models_smoke.py"
fi

# ── 5. Parallel-stream readiness probes ─────────────────────────────
step "5. Parallel-stream readiness (rebuff / opa-gatekeeper / observability triad)"
python3 scripts/rebuff_status.py > /tmp/rebuff-status.log 2>&1
if grep -q "Ready for real detection=False" /tmp/rebuff-status.log 2>/dev/null; then
  warn "Rebuff: env-gated (set REBUFF_ENABLED=1 + REBUFF_API_TOKEN for real detection)"
elif grep -q "importable=True" /tmp/rebuff-status.log 2>/dev/null; then
  ok "Rebuff: importable + env-gated path ready"
else
  bad "Rebuff: see /tmp/rebuff-status.log"
fi

if python3 scripts/opa_gatekeeper_status.py --fail-on-not-ready > /tmp/opa-status.log 2>&1; then
  ok "OPA Gatekeeper pack ready_for_apply=true"
else
  warn "OPA Gatekeeper pack NOT ready — see /tmp/opa-status.log"
fi

if python3 scripts/observability_triad_status.py --fail-on-not-ready > /tmp/triad-status.log 2>&1; then
  ok "Observability triad (Jaeger/Prom/Grafana/OTel) ready"
else
  bad "Observability triad NOT ready — see /tmp/triad-status.log"
fi

# ── 6. Catalog drift ─────────────────────────────────────────────────
step "6. Catalog drift (catalog_status=shipped vs probe)"
DRIFT=$(python3 scripts/catalog_tools_probe.py --format tsv 2>/dev/null \
  | awk -F'\t' 'NR>1 && $4=="NOT_INSTALLED" && $3=="shipped"' | wc -l)
HEALTHY_CAT=$(python3 scripts/catalog_tools_probe.py --format tsv 2>/dev/null \
  | awk -F'\t' 'NR>1 && $4=="HEALTHY"' | wc -l)
if [[ "$DRIFT" -gt 10 ]]; then
  warn "$HEALTHY_CAT HEALTHY / $DRIFT catalog rows say 'shipped' but artifact missing — known catalog drift (see catalog_tools_probe.py)"
elif [[ "$DRIFT" -gt 0 ]]; then
  warn "$HEALTHY_CAT HEALTHY / $DRIFT catalog 'shipped' rows missing — refresh recommended"
else
  ok "$HEALTHY_CAT HEALTHY / 0 catalog drift"
fi

# ── 7. Drill scoreboard freshness ───────────────────────────────────
step "7. Drill scoreboard freshness"
if [[ -f .loop/last_drill_outcome.json ]]; then
  AGE_S=$(($(date +%s) - $(stat -c %Y .loop/last_drill_outcome.json 2>/dev/null || echo 0)))
  AGE_M=$((AGE_S / 60))
  FAILED_COUNT=$(python3 -c "import json; d=json.load(open('.loop/last_drill_outcome.json')); print(len(d.get('failed_drills',[])))" 2>/dev/null || echo "?")
  if [[ "$AGE_M" -lt 60 && "$FAILED_COUNT" == "0" ]]; then
    ok "scoreboard fresh ($AGE_M min) · 0 failed drills"
  elif [[ "$FAILED_COUNT" == "0" ]]; then
    warn "scoreboard $AGE_M min old · 0 failed drills (refresh: python3 scripts/run_drills.py --parallel 4)"
  else
    warn "scoreboard $AGE_M min old · $FAILED_COUNT failed drills (refresh: python3 scripts/run_drills.py --parallel 4)"
  fi
else
  warn "no last_drill_outcome.json — run python3 scripts/run_drills.py --parallel 4"
fi

# ── Final verdict ────────────────────────────────────────────────────
echo ""
if [[ "$fails" == "0" && "$warns" == "0" ]]; then
  echo -e "${BOLD}${GREEN}═══ ALL GREEN ═══${NC}"
  exit 0
elif [[ "$fails" == "0" ]]; then
  echo -e "${BOLD}${YELLOW}═══ GREEN with $warns warning(s) ═══${NC}"
  exit 0
else
  echo -e "${BOLD}${RED}═══ $fails failure(s), $warns warning(s) ═══${NC}"
  exit 1
fi
