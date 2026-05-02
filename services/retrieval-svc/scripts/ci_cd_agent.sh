#!/bin/bash

echo "🚀 CI/CD AGENT PIPELINE"
START=$(date +%s)

FAIL=0

step () {
  echo ""
  echo "▶️ $1"
}

run_step () {
  echo "$1"
  eval "$2"
  if [ $? -ne 0 ]; then
    echo "❌ FAILED: $1"
    FAIL=1
    exit 1
  else
    echo "✅ PASSED: $1"
  fi
}

step "1. Install dependencies"
pip install -r requirements.txt >/dev/null 2>&1 || true

step "2. Full system check"
run_step "System Validation" "./scripts/full_system_check.sh"

step "3. Auto-fix"
./scripts/auto_fix_agent.sh

step "4. Self-healing"
./scripts/self_heal_loop.sh

step "5. Governance gate"
run_step "Governance Gate" "./scripts/governance_gate.sh"

step "6. Generate artifacts"
mkdir -p artifacts
cp -r reports artifacts/ 2>/dev/null

step "7. Summary"
END=$(date +%s)
DURATION=$((END-START))

echo ""
echo "📊 CI RESULT"
echo "----------------------------"
echo "Status: SUCCESS"
echo "Duration: ${DURATION}s"
echo "Artifacts: ./artifacts"
echo "----------------------------"

echo "✅ CI/CD PIPELINE COMPLETE"
