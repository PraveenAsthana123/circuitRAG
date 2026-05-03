import json
from datetime import UTC, datetime
from pathlib import Path

REPORTS = Path("reports")
FINAL = REPORTS / "final_report.json"
BUGS = REPORTS / "bugs.json"
REG = REPORTS / "regression_score.json"
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
    }


def vote_bug(bugs):
    return {
        "agent": "bug",
        "vote": "PASS" if len(bugs) == 0 else "FAIL",
        "reason": f"{len(bugs)} bugs",
    }


def vote_regression(regression):
    score = regression.get("score", 0)
    return {
        "agent": "regression",
        "vote": "PASS" if score >= 80 else "FAIL",
        "reason": f"score={score}",
    }


def main():
    REPORTS.mkdir(exist_ok=True)

    final_report = load(FINAL, {})
    bugs = load(BUGS, [])
    regression = load(REG, {"score": 0})

    votes = [
        vote_testing(final_report),
        vote_bug(bugs),
        vote_regression(regression),
    ]

    failed = [vote for vote in votes if vote["vote"] != "PASS"]

    decision = {
        "timestamp": datetime.now(UTC).isoformat(),
        "votes": votes,
        "decision": "ALLOW" if not failed else "BLOCK",
        "failed_agents": failed,
    }

    OUT.write_text(json.dumps(decision, indent=2))
    print(json.dumps(decision, indent=2))

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
