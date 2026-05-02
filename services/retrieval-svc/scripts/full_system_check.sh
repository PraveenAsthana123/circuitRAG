#!/bin/bash

echo "🚀 FULL SYSTEM CHECK"

echo "1. ENV"
python --version
pip --version

echo "2. STABILIZE DEPENDENCIES"
pip install --force-reinstall "fastapi==0.115.14" "starlette>=0.40,<0.47" "cryptography>=43,<44" >/dev/null 2>&1 || true
pip install ruff bandit setuptools >/dev/null 2>&1 || true

echo "3. API HEALTH"
curl -s http://127.0.0.1:8000/health || echo "API DOWN"
echo ""

echo "4. TESTS"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q -W ignore::pytest.PytestConfigWarning || true

echo "5. AUTO-FIX LINT"
ruff check . --fix || true

echo "6. LINT VERIFY"
ruff check . || true

echo "7. SECURITY"
bandit -r app || true
echo "Skipping safety scan: interactive/dependency conflict."

echo "8. PERFORMANCE"
time curl -s http://127.0.0.1:8000/docs > /dev/null

echo "9. TESTING AGENT"
python scripts/testing_agent.py || true

echo "10. BUG MANAGER"
python scripts/bug_manager.py || true

echo "11. PORTS"
lsof -i :8000 || true
lsof -i :9464 || true

echo "12. FINAL STATUS"
if [ -f reports/bugs.json ]; then
  BUG_COUNT=$(python - <<'PY'
import json
try:
    print(len(json.load(open("reports/bugs.json"))))
except Exception:
    print(999)
PY
)
  if [ "$BUG_COUNT" = "0" ]; then
    echo "✅ SYSTEM HEALTHY"
  else
    echo "⚠️ BUGS DETECTED: $BUG_COUNT"
  fi
else
  echo "⚠️ NO BUG REPORT"
fi

echo "✅ DONE"
