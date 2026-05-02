import json
import os
import subprocess
from datetime import UTC, datetime


def is_valid_json(data):
    try:
        json.loads(data)
        return True
    except Exception:
        return False

def run(args, env=None):
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    r = subprocess.run(  # noqa: S603
        args,
        capture_output=True,
        text=True,
        env=merged_env,
    )

    return {
        "cmd": " ".join(args),
        "status": "FAIL" if "failed" in (r.stdout + r.stderr).lower() else "PASS",
        "stdout": r.stdout if "openapi.json" in " ".join(args) else r.stdout[-2000:],
        "stderr": r.stderr[-2000:],
    }


results = {
    "timestamp": datetime.now(UTC).isoformat(),
    "sanitation": {
        "pytest": run(
            ["pytest", "-q", "-W", "ignore::pytest.PytestConfigWarning"],
            env={"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        ),
        "smoke_docs": run(["curl", "-s", "http://127.0.0.1:8000/docs"]),
        "openapi": run(
    ["curl", "-s", "-o", "reports/openapi.json", "-w", "%{http_code}", "http://127.0.0.1:8000/openapi.json"]
),
    },
}

os.makedirs("reports", exist_ok=True)

with open("reports/final_report.json", "w") as f:
    json.dump(results, f, indent=2)

print("✅ Report generated: reports/final_report.json")
print(json.dumps(results["sanitation"], indent=2))
