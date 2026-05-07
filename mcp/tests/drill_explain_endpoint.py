# RESOURCES: evaluation
"""
Drill: §48 explainability endpoint — `/api/v1/explain?prediction_id=<id>`.

§48.12 says: "if a regulator demands explanation of a specific past
decision and you cannot produce one within minutes, your AI system
is not deployable in any regulated jurisdiction." This drill enforces
that the endpoint exists, returns the §48.4 row shape, 404s on
unknown IDs, and rejects malformed payloads.

The drill exercises the FastAPI app via TestClient (real app, real
Pydantic validation, real route resolution — no mocks of business
logic per §43). For the full-stack docker-compose drill, an operator
runs `EVAL_URL=http://localhost:<port> ...` against the live service;
TestClient is the gate that runs in CI without a stack.

Steps:

 1. POST /api/v1/decisions with a valid §48.4-shaped row → 201 +
    echoed body.
 2. GET /api/v1/explain?prediction_id=<id> → 200 + ExplainResponse
    shape with audit row included verbatim.
 3. NEGATIVE: GET /api/v1/explain?prediction_id=__phantom__ → 404
    with error_code=DECISION_NOT_FOUND. Lock: stub doesn't fabricate
    rows for unknown IDs.
 4. NEGATIVE: GET /api/v1/explain (no prediction_id) → 422 (FastAPI
    validation rejects missing required query param). Lock: caller
    cannot accidentally retrieve "the latest" decision.
 5. NEGATIVE: POST /api/v1/decisions with confidence=1.5 → 422.
    Lock: schema enforces 0.0 ≤ confidence ≤ 1.0.
 6. Verify ExplainResponse contains the four §48 surfaces:
    explanation_method, confidence, counterfactual, fairness_status,
    AND the full audit row echoed back.

Negative assertions per §43 are steps 3, 4, 5. They lock:
  - Phantom ID → 404 (no fabrication)
  - Missing param → 422 (no implicit "latest")
  - Bad confidence → 422 (schema gate works)

Run:
    .venv/bin/python mcp/tests/drill_explain_endpoint.py

Prereq: project .venv with FastAPI + pydantic + pydantic-settings.
The /tmp/pw-venv used by browser drills lacks FastAPI; this drill
needs the full project venv at .venv/.
"""
from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{NC} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{NC} {msg}")


def main() -> int:
    REPO = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(REPO / "services" / "evaluation-svc"))
    sys.path.insert(0, str(REPO / "libs" / "py"))

    try:
        from app.main import create_app
        from fastapi.testclient import TestClient
    except Exception as e:
        print(f"{RED}cannot import evaluation-svc app: {e}{NC}")
        print(f"  REPO={REPO}")
        return 1

    failures = 0
    app = create_app()
    client = TestClient(app)
    pid = f"drill-{uuid.uuid4().hex[:12]}"

    # 1. POST /api/v1/decisions with a valid row.
    payload = {
        "request_id": str(uuid.uuid4()),
        "prediction_id": pid,
        "timestamp": datetime.now(UTC).isoformat(),
        "tenant_id": "11111111-1111-1111-1111-111111111111",
        "user_id": "alice@example.com",
        "model_name": "demo-classifier",
        "model_version": "v0.3.1",
        "prompt_version": "p-2026-04-30",
        "input_features": {"income": 65000, "debt_ratio": 0.42},
        "input_hash": "sha256:abc",
        "prediction": "approve",
        "confidence": 0.87,
        "explanation": {
            "method": "shap",
            "top_features": [
                {"name": "income", "value": 65000, "contribution": 0.41},
                {"name": "debt_ratio", "value": 0.42, "contribution": -0.18},
            ],
            "counterfactual": (
                "If debt_ratio had been below 0.50 with income unchanged, "
                "decision would have been approve with confidence 0.92."
            ),
            "citations": [],
        },
        "rules_applied": ["min_income_floor", "debt_ceiling"],
        "guardrails_triggered": [],
        "human_override": False,
        "fairness_flag": "pass",
        "latency_ms": 42,
        "cost_tokens": None,
    }
    r = client.post("/api/v1/decisions", json=payload)
    if r.status_code == 201 and r.json().get("prediction_id") == pid:
        ok(f"step 1: POST /api/v1/decisions → 201; pid={pid}")
    else:
        fail(f"step 1: POST decisions failed status={r.status_code} body={r.text[:300]}")
        failures += 1

    # 2. GET /api/v1/explain?prediction_id=<id>.
    r = client.get(f"/api/v1/explain?prediction_id={pid}")
    if r.status_code == 200:
        body = r.json()
        if body.get("audit", {}).get("prediction_id") == pid:
            ok("step 2: GET explain → 200 with matching prediction_id")
        else:
            fail(f"step 2: response missing audit.prediction_id, body={body}")
            failures += 1
    else:
        fail(f"step 2: GET explain failed status={r.status_code} body={r.text[:300]}")
        failures += 1

    # 3. NEGATIVE: phantom prediction_id → 404.
    r = client.get("/api/v1/explain?prediction_id=__phantom_does_not_exist__")
    if r.status_code == 404:
        body = r.json()
        if body.get("error_code") == "DECISION_NOT_FOUND":
            ok("step 3 (negative): phantom prediction_id → 404 + error_code=DECISION_NOT_FOUND")
        else:
            fail(f"step 3 (negative): 404 OK but error_code wrong: body={body}")
            failures += 1
    else:
        fail(f"step 3 (negative): expected 404, got {r.status_code}: {r.text[:200]}")
        failures += 1

    # 4. NEGATIVE: missing query param → 422.
    r = client.get("/api/v1/explain")
    if r.status_code == 422:
        ok("step 4 (negative): missing prediction_id → 422 (no implicit 'latest')")
    else:
        fail(f"step 4 (negative): expected 422, got {r.status_code}: {r.text[:200]}")
        failures += 1

    # 5. NEGATIVE: confidence > 1.0 → 422.
    bad = dict(payload)
    bad["prediction_id"] = f"{pid}-bad"
    bad["confidence"] = 1.5
    r = client.post("/api/v1/decisions", json=bad)
    if r.status_code == 422:
        ok("step 5 (negative): confidence=1.5 → 422 (schema gate locks 0.0–1.0)")
    else:
        fail(f"step 5 (negative): expected 422, got {r.status_code}: {r.text[:200]}")
        failures += 1

    # 6. Verify §48 four-surface response shape.
    r = client.get(f"/api/v1/explain?prediction_id={pid}")
    body = r.json()
    required_top = {"audit", "explanation_method", "confidence", "counterfactual", "fairness_status"}
    missing = required_top - set(body.keys())
    if not missing:
        ok(
            "step 6: ExplainResponse has all 5 §48 surfaces "
            "(audit + explanation_method + confidence + counterfactual + fairness_status)"
        )
    else:
        fail(f"step 6: missing keys {missing} in response: {body}")
        failures += 1

    print()
    if failures == 0:
        print(f"{GREEN}{BOLD}ALL 6 STEPS PASSED{NC}")
        return 0
    print(f"{RED}{BOLD}{failures} STEP(S) FAILED{NC}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
