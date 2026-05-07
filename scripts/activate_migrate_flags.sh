#!/usr/bin/env bash
# activate_migrate_flags.sh — single-command operator activation for
# items 1, 2, 3, 5 from the iter-19 closing summary.
#
# Per CLAUDE.md §47.7 (expand→migrate→contract) + ADR-025
# (feature-flag-gated dual-write). Idempotent: if .env already has
# the flags, prints state + exits clean.
#
# Drilled at mcp/tests/drill_activate_migrate_flags.py.

set -uo pipefail

color() { printf "\033[%sm%s\033[0m" "$1" "$2"; }
ok()    { color "32" "OK"; }
info()  { color "36" "$*"; }
warn()  { color "33" "WARN"; }

REPO="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${REPO}/.env"

echo "═══ Activate migrate-phase flags ($(date +%H:%M:%S)) ═══"
echo

# ── Step 1: secrets.token_hex(32) for SESSION_TOKEN_SECRET ──
SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))' 2>/dev/null || echo "")
if [ -z "$SECRET" ]; then
    echo "[$(warn)] could not generate secret via python3"
    exit 1
fi

# ── Step 2: detect existing .env state ──
if [ -f "$ENV_FILE" ]; then
    echo "$(info "Existing .env found at $ENV_FILE")"
    EXISTING_FLAGS=$(grep -cE "^(MCP_GATEWAY_SQL_AUDIT_ENABLED|OPS_WORKER_SQL_ENABLED|MCP_TOOLS_SYNC_ENABLED|DOCUMIND_SESSION_TOKEN_SECRET)=" "$ENV_FILE" 2>/dev/null || echo "0")
    if [ "$EXISTING_FLAGS" -ge "4" ]; then
        echo "[$(ok)] all 4 autonomous-doable flags already present in .env"
        echo
        # Show current values (mask the secret)
        echo "Current state:"
        grep -E "^(MCP_GATEWAY_SQL_AUDIT_ENABLED|OPS_WORKER_SQL_ENABLED|MCP_TOOLS_SYNC_ENABLED|DOCUMIND_SESSION_TOKEN_SECRET|XAI_API_KEY)=" "$ENV_FILE" | \
            sed -E 's/(DOCUMIND_SESSION_TOKEN_SECRET=)([a-f0-9]{8})[a-f0-9]+/\1\2…<masked>/'
        echo
        echo "[$(info "Idempotent — no changes needed.")] To rotate the secret: rm .env; rerun."
        exit 0
    fi
    echo "[$(warn)] $EXISTING_FLAGS of 4 flags present; backing up + regenerating"
    cp "$ENV_FILE" "${ENV_FILE}.bak-$(date +%Y%m%d-%H%M%S)"
    echo "  backup → ${ENV_FILE}.bak-…"
fi

# ── Step 3: write .env ──
cat > "$ENV_FILE" <<EOF
# DocuMind .env — generated $(date +%Y-%m-%d) by activate_migrate_flags.sh
# Activates the 4 autonomous-doable flags from iter-19's 7-item summary.
# Per CLAUDE.md §47.7 + ADR-025. Default state of each migrate flag = OFF
# in .env.template; this file flips them ON for operator opt-in.

DOCUMIND_ENV=development
DOCUMIND_LOG_LEVEL=INFO
DOCUMIND_LOG_JSON=true

# §47.7 Migrate-phase opt-in flags (iters 11, 12, 13)
MCP_GATEWAY_SQL_AUDIT_ENABLED=1
OPS_WORKER_SQL_ENABLED=1
MCP_TOOLS_SYNC_ENABLED=1

# Iter 6 HMAC session-token secret (32 bytes hex = 64 chars)
DOCUMIND_SESSION_TOKEN_SECRET=${SECRET}

# Iter 10 ChatXAI: leave empty until operator obtains key from console.x.ai
XAI_API_KEY=
EOF

chmod 600 "$ENV_FILE"

echo "[$(ok)] wrote $(basename "$ENV_FILE") ($(wc -c < "$ENV_FILE") bytes; mode 600)"
echo

# ── Step 4: verify load via python ──
echo "$(info "Verifying flags load...")"
set -a; source "$ENV_FILE"; set +a
python3 -c "
import os
ok=True
for f, want in (
    ('MCP_GATEWAY_SQL_AUDIT_ENABLED', '1'),
    ('OPS_WORKER_SQL_ENABLED', '1'),
    ('MCP_TOOLS_SYNC_ENABLED', '1'),
):
    got = os.environ.get(f, '')
    print(f'  {f:35} = {got}')
    if got != want: ok=False
secret = os.environ.get('DOCUMIND_SESSION_TOKEN_SECRET', '')
if len(secret) == 64:
    print(f'  {\"DOCUMIND_SESSION_TOKEN_SECRET\":35} = {secret[:8]}…<masked> (64 chars)')
else:
    print(f'  DOCUMIND_SESSION_TOKEN_SECRET wrong length: {len(secret)}')
    ok=False
import sys
sys.exit(0 if ok else 1)
" || exit 1

echo
echo "[$(ok)] All 4 flags active in this shell."
echo
echo "$(info "Next steps:")"
echo "  1. Restart any running services to pick up the new env:"
echo "     docker compose restart  # OR systemctl restart documind-*"
echo "  2. Confirm migrate-phase status on the dashboard:"
echo "     # /admin/dashboard → Migrate-phase panel should show 3/3 flags ON"
echo "  3. Item 4 (XAI_API_KEY) requires operator credential:"
echo "     # echo \"XAI_API_KEY=xai-…\" >> .env  (after obtaining from console.x.ai)"
echo

exit 0
