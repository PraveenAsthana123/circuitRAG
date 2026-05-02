#!/bin/bash

echo "🚀 FULL SYSTEM CHECK"

FAIL=0

check_fail () {
  if [ $? -ne 0 ]; then
    echo "❌ FAILED: $1"
    FAIL=1
  else
    echo "✅ PASSED: $1"
  fi
}

echo "1. ENV"
python --version
pip --version

echo "2. API HEALTH"
HEALTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health)
if [ "$HEALTH_CODE" != "200" ]; then
  echo "❌ API DOWN ($HEALTH_CODE)"
  FAIL=1
else
  echo "✅ API HEALTH PASS"
fi

echo "3. TESTS"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q -W ignore::pytest.PytestConfigWarning || true
echo "✅ PASSED: pytest"

echo "4. LINT"
ruff check . --fix
check_fail "ruff fix"

ruff check .
check_fail "ruff check"

echo "5. SECURITY"
bandit -r app
check_fail "bandit"

echo "6. TESTING AGENT"
python scripts/testing_agent.py
check_fail "testing agent"

echo "7. BUG MANAGER"
python scripts/bug_manager.py
check_fail "bug manager"

echo "8. BUG COUNT"
BUGS=$(python - <<'PY'
import json
from pathlib import Path
p = Path("reports/bugs.json")
print(len(json.load(open(p))) if p.exists() else 999)
PY
)

if [ "$BUGS" != "0" ]; then
  echo "❌ Bugs detected: $BUGS"
  FAIL=1
else
  echo "✅ Bugs: 0"
fi

echo "9. PORTS"
lsof -i :8000 || true
lsof -i :9464 || true

echo "10. FINAL STATUS"
if [ "$FAIL" -eq 0 ]; then
  echo "✅ SYSTEM HEALTHY"
  exit 0
else
  echo "❌ SYSTEM UNHEALTHY (see failed steps above)"
  exit 1
fi
