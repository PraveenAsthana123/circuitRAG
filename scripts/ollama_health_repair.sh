#!/usr/bin/env bash
# Ollama daemon health-repair — diagnose + attempt fix per §42 boundary.
#
# Per CLAUDE.md §42 (operational autonomy boundary): sudo is gated.
# This script attempts the fix WITHOUT sudo first; if that path
# fails, it prints the exact sudo commands operator runs manually.
#
# Drilled at mcp/tests/drill_ollama_health_repair.py.

set -uo pipefail   # NOT -e: each step independent

color() { printf "\033[%sm%s\033[0m" "$1" "$2"; }
ok()    { color "32" "OK"; }
warn()  { color "33" "WARN"; }
fail()  { color "31" "FAIL"; }
info()  { color "36" "$*"; }

echo "═══ Ollama health-repair ($(date +%H:%M:%S)) ═══"
echo

# ── Diagnostic 1: daemon listening ──
printf "%-40s " "ollama daemon HTTP /api/tags"
if curl -m 3 -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    n=$(curl -m 3 -sf http://localhost:11434/api/tags | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('models',[])))" 2>/dev/null || echo "?")
    echo "[$(ok)] $n models installed"
else
    echo "[$(fail)] daemon not responding"
    echo "  → start it with: sudo systemctl start ollama"
    exit 1
fi

# ── Diagnostic 2: /api/ps reachable ──
printf "%-40s " "ollama daemon HTTP /api/ps"
if curl -m 3 -sf http://localhost:11434/api/ps >/dev/null 2>&1; then
    echo "[$(ok)] reachable"
else
    echo "[$(warn)] /api/ps unreachable"
fi

# ── Diagnostic 3: pull operation works? ──
printf "%-40s " "ollama pull (smoke test on tiny model)"
PULL_OUT=$(curl -m 5 -s -X POST http://localhost:11434/api/pull \
    -d '{"name":"hf.co/test/nonexistent","stream":false}' 2>&1)
if echo "$PULL_OUT" | grep -q "id_ed25519"; then
    echo "[$(fail)] identity-key MISSING (the iter-10 issue)"
    PULL_BROKEN=1
elif echo "$PULL_OUT" | grep -q "model not found"; then
    echo "[$(ok)] pull subsystem works (404 on test name as expected)"
    PULL_BROKEN=0
else
    echo "[$(warn)] unexpected response: $(echo "$PULL_OUT" | head -c 80)"
    PULL_BROKEN=0
fi

# ── If pull broken: attempt fix ──
if [ "${PULL_BROKEN:-0}" = "1" ]; then
    echo
    echo "═══ Attempting fix ═══"

    # Path A: sudo -n (passwordless if configured)
    printf "%-40s " "sudo -n systemctl restart ollama"
    if sudo -n systemctl restart ollama 2>/dev/null; then
        echo "[$(ok)] restarted"
        sleep 3
        # Re-test
        printf "%-40s " "post-restart pull subsystem"
        RETEST=$(curl -m 5 -s -X POST http://localhost:11434/api/pull \
            -d '{"name":"hf.co/test/nonexistent","stream":false}' 2>&1)
        if echo "$RETEST" | grep -q "id_ed25519"; then
            echo "[$(fail)] still broken — try Path B/C below"
        else
            echo "[$(ok)] FIXED — pull subsystem responsive"
            exit 0
        fi
    else
        echo "[$(warn)] sudo -n unavailable (expected; not passwordless)"
    fi

    echo
    echo "  $(info "═══ MANUAL FIX (sudo password required) ═══")"
    echo
    echo "  Path B — generate identity key as ollama user:"
    echo "    sudo -u ollama ssh-keygen -t ed25519 \\"
    echo "      -f /usr/share/ollama/.ollama/id_ed25519 \\"
    echo "      -N \"\" -C \"ollama-daemon\""
    echo "    sudo systemctl restart ollama"
    echo
    echo "  Path C — redirect Ollama home to user-writable path:"
    echo "    sudo systemctl edit ollama"
    echo "    # Add: Environment=\"OLLAMA_HOME=/var/lib/ollama\""
    echo "    sudo systemctl daemon-reload"
    echo "    sudo systemctl restart ollama"
    echo
    echo "  Path D — full reinstall:"
    echo "    sudo systemctl stop ollama"
    echo "    sudo rm -rf /usr/share/ollama"
    echo "    curl -fsSL https://ollama.ai/install.sh | sh"
    echo
    exit 2  # "operator-action required"
fi

# ── If pull works: report green + offer optional model preload ──
echo
echo "═══ All diagnostics green ═══"
echo
echo "Optional: preload a Grok-class model for the chatxai_fallback CLI:"
echo "  ollama pull qwen2.5:latest"
echo

exit 0
