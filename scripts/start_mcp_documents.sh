#!/usr/bin/env bash
# start_mcp_documents.sh — launch the documents MCP server.
#
# Per CLAUDE.md §44 (autonomous-loop iter-62 ships the launcher for
# iter-61's mcp/server_documents.py), §47 (architecture: each MCP
# server runs on its own port; documents = port 8094, leaving 8090-8093
# for hr/itsm/observe/research/etc.), §47.6 (security: read-only
# server, no SUDO needed; runs as the calling user).
#
# Usage:
#   bash scripts/start_mcp_documents.sh             # foreground
#   bash scripts/start_mcp_documents.sh &           # background
#   MCP_DOCUMENTS_PORT=8095 bash scripts/start_mcp_documents.sh
#
# Activation in inference-svc:
#   export DOCUMIND_MCP_DOCUMENTS_URL=http://localhost:8094
#   docker compose restart inference-svc
#
# Drilled at mcp/tests/drill_start_mcp_documents.py.

set -uo pipefail

case "${1:-}" in
    -h|--help)
        cat <<'EOF'
start_mcp_documents.sh — launcher for the documents MCP server

USAGE
    bash scripts/start_mcp_documents.sh
    MCP_DOCUMENTS_PORT=8095 bash scripts/start_mcp_documents.sh

ENV
    MCP_DOCUMENTS_PORT  Port to bind (default: 8094)
    DOCUMIND_DATABASE_URL  Postgres DSN for documents.db_query_select
                          (optional; tool reports available:False without it)

ACTIVATION (inference-svc side)
    export DOCUMIND_MCP_DOCUMENTS_URL=http://localhost:8094
    docker compose restart inference-svc

OPTIONS
    -h, --help      Print this help and exit

EXIT CODES
    0   server started + listening
    1   bind failed / venv missing
EOF
        exit 0
        ;;
esac

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

PORT="${MCP_DOCUMENTS_PORT:-8094}"
VENV_PYTHON="$REPO/.venv/bin/python3"

if [ ! -x "$VENV_PYTHON" ]; then
    echo "error: venv python not found at $VENV_PYTHON" >&2
    echo "       run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

echo "═══ documents MCP server ($(date +%H:%M:%S)) ═══"
echo "  port:   $PORT"
echo "  python: $VENV_PYTHON"
echo "  health: http://localhost:$PORT/health"
echo "  tools:  http://localhost:$PORT/tools/list"
echo

export PYTHONPATH="$REPO"
export MCP_DOCUMENTS_PORT="$PORT"

# Launch via uvicorn — same pattern other MCP servers follow when
# operator wants a real ASGI server (FastAPI app exposed at
# mcp.server_documents:app). Falls back to python invocation if
# uvicorn is missing in the venv.
if "$VENV_PYTHON" -c "import uvicorn" 2>/dev/null; then
    exec "$VENV_PYTHON" -m uvicorn mcp.server_documents:app \
        --host 0.0.0.0 --port "$PORT" --log-level info
else
    echo "[warn] uvicorn not in venv; running via python -m" >&2
    exec "$VENV_PYTHON" -m mcp.server_documents
fi
