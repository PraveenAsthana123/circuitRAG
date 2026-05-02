import json
import os
import uuid
from datetime import UTC, datetime


def generate():
    if not os.path.exists("reports/final_report.json"):
        print("No report found")
        return

    with open("reports/final_report.json") as f:
        report = json.load(f)

    bugs = []

    for k, v in report["sanitation"].items():
        if v["status"] != "PASS":
            bugs.append({
                "id": str(uuid.uuid4()),
                "source": k,
                "severity": "HIGH",
                "message": v.get("stdout","")[:200],
                "created_at": datetime.now(UTC).isoformat()
            })

    os.makedirs("reports", exist_ok=True)
    with open("reports/bugs.json","w") as f:
        json.dump(bugs,f,indent=2)

    print(f"🐞 Bugs: {len(bugs)}")

if __name__ == "__main__":
    generate()
