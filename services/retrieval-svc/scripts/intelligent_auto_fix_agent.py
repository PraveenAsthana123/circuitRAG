import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

REPORTS = Path("reports")
BUGS_FILE = REPORTS / "bugs.json"
REPORT_FILE = REPORTS / "intelligent_auto_fix_report.json"
BACKUP_DIR = Path(".loop/intelligent_backups")


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
    return {
        "cmd": " ".join(cmd),
        "code": r.returncode,
        "stdout": r.stdout[-3000:],
        "stderr": r.stderr[-3000:],
        "ok": r.returncode == 0,
    }


def load_bugs():
    if not BUGS_FILE.exists():
        return []
    return json.loads(BUGS_FILE.read_text())


def backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKUP_DIR / datetime.now(UTC).strftime("backup_%Y%m%d_%H%M%S")
    shutil.copytree(
        ".",
        target,
        ignore=shutil.ignore_patterns(".venv", ".git", ".loop", "reports"),
    )
    return str(target)


def classify_bug(bug):
    source = bug.get("source", "").lower()
    message = bug.get("message", "").lower()

    if "ruff" in source or "lint" in message:
        return "LINT"
    if "pytest" in source or "failed" in message:
        return "TEST"
    if "openapi" in source:
        return "OPENAPI"
    if "health" in source or "api" in message:
        return "API"
    return "UNKNOWN"


def apply_fix(category):
    if category == "LINT":
        return [run(["ruff", "check", ".", "--fix"])]
    if category == "OPENAPI":
        return [run(["python", "scripts/testing_agent.py"])]
    if category == "TEST":
        return [run(["pytest", "-q", "-W", "ignore::pytest.PytestConfigWarning"])]
    if category == "API":
        return [run(["curl", "-s", "http://127.0.0.1:8000/health"])]
    return [run(["ruff", "check", ".", "--fix"])]


def main():
    REPORTS.mkdir(exist_ok=True)

    bugs = load_bugs()
    backup_path = backup()

    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "backup": backup_path,
        "initial_bugs": bugs,
        "actions": [],
        "final": "UNKNOWN",
    }

    if not bugs:
        report["final"] = "NO_BUGS"
        REPORT_FILE.write_text(json.dumps(report, indent=2))
        print("✅ No bugs found. Nothing to fix.")
        return

    for bug in bugs:
        category = classify_bug(bug)
        steps = apply_fix(category)
        report["actions"].append(
            {
                "bug": bug,
                "category": category,
                "steps": steps,
            }
        )

    validation = run(["./scripts/master_agent_pipeline.sh"])
    report["validation"] = validation

    if validation["ok"]:
        report["final"] = "FIXED"
        print("✅ Intelligent auto-fix succeeded.")
        print("Git ready:")
        print("git add . && git commit -m 'auto-fix: intelligent agent repair'")
    else:
        report["final"] = "FAILED_NEEDS_REVIEW"
        print("⚠️ Auto-fix incomplete. Review report.")

    REPORT_FILE.write_text(json.dumps(report, indent=2))
    print(f"Report: {REPORT_FILE}")


if __name__ == "__main__":
    main()
