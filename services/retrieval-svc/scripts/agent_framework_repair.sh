#!/bin/bash

echo "🧠 AGENT FRAMEWORK REPAIR + GOVERNANCE HARDENING"

mkdir -p reports logs scripts

echo "1. Install missing tools"
pip install ruff bandit httpx requests pydantic rich >/dev/null 2>&1 || true

echo "2. Check Ollama"
if ! command -v ollama >/dev/null 2>&1; then
  echo "❌ Ollama not installed"
  echo "Install: curl -fsSL https://ollama.com/install.sh | sh"
else
  echo "✅ Ollama installed"
fi

echo "3. Check Ollama server"
curl -s http://localhost:11434/api/tags >/dev/null \
  && echo "✅ Ollama server running" \
  || echo "⚠️ Ollama server not reachable. Run: ollama serve"

echo "4. Pull safe fallback model if missing"
ollama list | grep -q "qwen2.5" || ollama pull qwen2.5:latest || true

echo "5. Create Agent Monitor"
cat > scripts/agent_monitor.py <<'PY'
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

REPORT = Path("reports/agent_monitor_report.json")

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return {
        "cmd": " ".join(cmd),
        "code": r.returncode,
        "stdout": r.stdout[-3000:],
        "stderr": r.stderr[-3000:],
        "ok": r.returncode == 0,
    }

def ollama_status():
    tags = run(["curl", "-s", "http://localhost:11434/api/tags"])
    return {
        "server_ok": tags["ok"] and "models" in tags["stdout"],
        "raw": tags,
    }

def model_available(name):
    r = run(["ollama", "list"])
    return name in r["stdout"]

def main():
    models = {
        "primary": "qwen2.5:latest",
        "fallback": "llama3.1:latest",
    }

    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "ollama": ollama_status(),
        "models": {
            k: {
                "name": v,
                "available": model_available(v),
            }
            for k, v in models.items()
        },
        "recommendation": [],
    }

    if not report["ollama"]["server_ok"]:
        report["recommendation"].append("Start Ollama with: ollama serve")

    if not report["models"]["primary"]["available"]:
        report["recommendation"].append("Pull model: ollama pull qwen2.5:latest")

    REPORT.write_text(json.dumps(report, indent=2))
    print("✅ Agent monitor report:", REPORT)

if __name__ == "__main__":
    main()
PY

echo "6. Create Council Governance Gate"
cat > scripts/council_governance_gate.sh <<'SH2'
#!/bin/bash

echo "🛡️ COUNCIL GOVERNANCE GATE"

FAIL=0

echo "1. Run agent monitor"
python scripts/agent_monitor.py || FAIL=1

echo "2. Check Ollama server"
curl -s http://localhost:11434/api/tags >/dev/null || {
  echo "❌ Ollama unavailable"
  FAIL=1
}

echo "3. Check required model"
ollama list | grep -q "qwen2.5" || {
  echo "❌ Required model missing: qwen2.5:latest"
  FAIL=1
}

echo "4. Check validation report"
if grep -q '"status": "FAIL"' reports/final_report.json 2>/dev/null; then
  echo "❌ Validation failure found"
  FAIL=1
fi

echo "5. Check bug report"
BUGS=$(python - <<'PY'
import json
from pathlib import Path
p = Path("reports/bugs.json")
print(len(json.load(open(p))) if p.exists() else 0)
PY
)

if [ "$BUGS" != "0" ]; then
  echo "❌ Bugs found: $BUGS"
  FAIL=1
fi

echo "6. Block partial council runs if present in logs"
if grep -E "outcome=partial|agent_board_author_failed|reviews_failed=[1-9]|authors_failed=[1-9]" logs/*.log reports/*.json 2>/dev/null; then
  echo "❌ Council failure or partial outcome detected"
  FAIL=1
fi

if [ "$FAIL" -eq 1 ]; then
  echo "🚫 COUNCIL GOVERNANCE BLOCKED"
  exit 1
fi

echo "✅ Council governance passed"
SH2

chmod +x scripts/council_governance_gate.sh

echo "7. Create Agent Architecture Report"
cat > reports/agent_architecture.md <<'MD'
# Agent-First Engineering Framework

## Flow
User / Developer
→ Testing Agent
→ Bug Manager
→ Auto-Fix Agent
→ Self-Heal Loop
→ Council Governance Gate
→ Git Commit Agent
→ PR Agent

## Agent Roles
| Agent | Responsibility |
|---|---|
| Testing Agent | Runs pytest, smoke, OpenAPI checks |
| Bug Manager | Converts failed checks into bugs |
| Auto-Fix Agent | Applies safe fixes and reruns validation |
| Self-Heal Loop | Retries fixes and rolls back if needed |
| Agent Monitor | Checks Ollama/model/runtime health |
| Council Governance Gate | Blocks partial/failed council decisions |
| Git Commit Agent | Commits only after health + governance pass |
| PR Agent | Creates PR summary and PR command |

## Governance Rule
Commit is allowed only when:
- system health = PASS
- bugs = 0
- Ollama reachable
- required model available
- no partial council outcome
- no failed authors/reviewers
MD

echo "8. Run full validation"
./scripts/full_system_check.sh

echo "9. Run council governance gate"
./scripts/council_governance_gate.sh

echo "✅ AGENT FRAMEWORK REPAIR COMPLETE"
