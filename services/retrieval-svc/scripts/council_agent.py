import json
from datetime import UTC, datetime
from pathlib import Path

REPORTS = Path("reports")
FINAL = REPORTS / "final_report.json"
BUGS = REPORTS / "bugs.json"
REG = REPORTS / "regression_score.json"
PERF = REPORTS / "performance_report.json"
OUT = REPORTS / "council_decision.json"


def load(path, default):
    if not path.exists():
        return default
    with path.open() as f:
        return json.load(f)


def vote_testing(final_report):
    checks = final_report.get("sanitation", final_report)
    failed = []

    for key, value in checks.items():
        if isinstance(value, dict):
            if value.get("status") != "PASS":
                failed.append(key)
        elif isinstance(value, str):
            if value != "PASS":
                failed.append(key)
        else:
            failed.append(key)

    return {
        "agent": "testing",
        "vote": "PASS" if not failed else "FAIL",
        "reason": "All testing checks passed" if not failed else f"Failed checks: {failed}",
        "weight": 35,
    }


def vote_bug(bugs):
    return {
        "agent": "bug",
        "vote": "PASS" if len(bugs) == 0 else "FAIL",
        "reason": f"{len(bugs)} bugs",
        "weight": 25,
    }


def vote_regression(regression):
    score = regression.get("score", 0)
    return {
        "agent": "regression",
        "vote": "PASS" if score >= 80 else "FAIL",
        "reason": f"score={score}",
        "weight": 25,
    }


def vote_performance(perf):
    status = perf.get("status", "SKIP")
    p95 = perf.get("p95_ms", 9999)
    return {
        "agent": "performance",
        "vote": "PASS" if status in ["PASS", "SKIP"] else "FAIL",
        "reason": f"status={status}, p95={p95}ms",
        "weight": 15,
    }


def main():
    REPORTS.mkdir(exist_ok=True)

    votes = [
        vote_testing(load(FINAL, {})),
        vote_bug(load(BUGS, [])),
        vote_regression(load(REG, {"score": 0})),
        vote_performance(load(PERF, {"status": "SKIP"})),
    ]

    passed_weight = sum(v["weight"] for v in votes if v["vote"] == "PASS")
    failed = [v for v in votes if v["vote"] != "PASS"]

    decision = {
        "timestamp": datetime.now(UTC).isoformat(),
        "votes": votes,
        "score": passed_weight,
        "threshold": 80,
        "decision": "ALLOW" if passed_weight >= 80 and not failed else "BLOCK",
        "failed_agents": failed,
    }

    OUT.write_text(json.dumps(decision, indent=2))
    print(json.dumps(decision, indent=2))

    if decision["decision"] == "BLOCK":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
