import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

MAX_RETRIES = 3
REPORTS = Path("reports")
BUGS_FILE = REPORTS / "bugs.json"
FIX_REPORT = REPORTS / "auto_fix_report.json"
BACKUP_DIR = Path(".loop/backups")


def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    return {
        "cmd": " ".join(cmd),
        "code": result.returncode,
        "stdout": result.stdout[-3000:],
        "stderr": result.stderr[-3000:],
        "ok": result.returncode == 0,
    }


def load_bugs():
    if not BUGS_FILE.exists():
        return []
    return json.loads(BUGS_FILE.read_text())


def backup_project():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"backup_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    shutil.copytree(
        ".",
        backup,
        ignore=shutil.ignore_patterns(".venv", ".git", ".loop", "reports"),
    )
    return str(backup)


def restore_project(backup_path):
    backup = Path(backup_path)
    if not backup.exists():
        return False
    for item in backup.iterdir():
        target = Path(item.name)
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
    return True


def root_cause(bugs):
    causes = []
    for bug in bugs:
        msg = bug.get("message", "").lower()
        src = bug.get("source", "unknown")

        if "ruff" in msg or "lint" in src:
            category = "LINT_FORMATTING"
            fix = "Run ruff auto-fix"
        elif "pytest" in src or "failed" in msg:
            category = "TEST_FAILURE"
            fix = "Run tests, inspect failing traceback"
        elif "openapi" in src:
            category = "API_CONTRACT_FAILURE"
            fix = "Validate OpenAPI endpoint and HTTP status"
        else:
            category = "UNKNOWN"
            fix = "Manual investigation required"

        causes.append({"source": src, "category": category, "recommended_fix": fix})

    return causes


def attempt_fix():
    steps = []
    steps.append(run(["ruff", "check", ".", "--fix"]))
    steps.append(run(["ruff", "check", "."]))
    steps.append(run(["python", "scripts/testing_agent.py"]))
    steps.append(run(["python", "scripts/bug_manager.py"]))
    return steps


def bug_count():
    bugs = load_bugs()
    return len(bugs)


def main():
    REPORTS.mkdir(exist_ok=True)

    initial_bugs = load_bugs()
    backup = backup_project()

    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "backup": backup,
        "initial_bug_count": len(initial_bugs),
        "root_cause": root_cause(initial_bugs),
        "attempts": [],
        "final_status": "UNKNOWN",
    }

    if not initial_bugs:
        report["final_status"] = "NO_BUGS"
        FIX_REPORT.write_text(json.dumps(report, indent=2))
        print("✅ No bugs found. Nothing to fix.")
        return

    for i in range(1, MAX_RETRIES + 1):
        print(f"🔁 Auto-fix attempt {i}/{MAX_RETRIES}")
        steps = attempt_fix()
        current_bugs = bug_count()

        report["attempts"].append(
            {
                "attempt": i,
                "steps": steps,
                "remaining_bugs": current_bugs,
            }
        )

        if current_bugs == 0:
            report["final_status"] = "FIXED"
            FIX_REPORT.write_text(json.dumps(report, indent=2))
            print("✅ Auto-fix successful.")
            print("Next git command:")
            print("git add . && git commit -m 'auto-fix: resolve validation issues'")
            return

    restore_project(backup)
    report["final_status"] = "ROLLED_BACK"
    FIX_REPORT.write_text(json.dumps(report, indent=2))
    print("❌ Auto-fix failed. Rolled back to backup.")
    print(f"Report: {FIX_REPORT}")


if __name__ == "__main__":
    main()
