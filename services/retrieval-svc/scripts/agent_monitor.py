import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

REPORT = Path("reports/agent_monitor_report.json")

def run(cmd):
    r = subprocess.run(  # noqa: S603
        cmd, capture_output=True, text=True)
    return {
        "cmd": " ".join(cmd),
        "code": r.returncode,
        "stdout": r.stdout[-3000:],
        "stderr": r.stderr[-3000:],
        "ok": r.returncode == 0,
    }

def ollama_status():
    tags = run(["curl", "-s", "http://localhost:11434/api/tags"])
    return {
        "server_ok": tags["ok"] and "models" in tags["stdout"],
        "raw": tags,
    }

def model_available(name):
    r = run(["ollama", "list"])
    return name in r["stdout"]

def main():
    models = {
        "primary": "qwen2.5:latest",
        "fallback": "llama3.1:latest",
    }

    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "ollama": ollama_status(),
        "models": {
            k: {
                "name": v,
                "available": model_available(v),
            }
            for k, v in models.items()
        },
        "recommendation": [],
    }

    if not report["ollama"]["server_ok"]:
        report["recommendation"].append("Start Ollama with: ollama serve")

    if not report["models"]["primary"]["available"]:
        report["recommendation"].append("Pull model: ollama pull qwen2.5:latest")

    REPORT.write_text(json.dumps(report, indent=2))
    print("✅ Agent monitor report:", REPORT)

if __name__ == "__main__":
    main()
