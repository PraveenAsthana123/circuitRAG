#!/usr/bin/env python3
"""Offline-safe readiness checker for Wazuh, Tetragon, and Tracee."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO / "infra" / "runtime-security"
KUSTOMIZATION = ROOT / "kustomization.yaml"
NAMESPACES = ROOT / "namespaces.yaml"
TETRAGON = ROOT / "tetragon-policies.yaml"
TRACEE = ROOT / "tracee-config.yaml"
WAZUH_COMPOSE = ROOT / "wazuh-compose.yml"
WAZUH_CONF = ROOT / "wazuh" / "ossec.conf"
TETRAGON_VALUES = ROOT / "helm-values" / "tetragon-values.yaml"
TRACEE_VALUES = ROOT / "helm-values" / "tracee-values.yaml"
CATALOG = REPO / "config" / "agentic_observability" / "oss_tooling_catalog.yaml"
OPA = shutil.which("opa")


def _docs(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [doc for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")) if doc]


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}


def _catalog_status() -> dict[str, Any]:
    data = _yaml(CATALOG)
    out: dict[str, Any] = {}
    for item in data.get("tools", []):
        name = item.get("name")
        if name in {"wazuh", "tetragon", "tracee"}:
            out[name] = {
                "status": item.get("status"),
                "category": item.get("category"),
                "install_path": item.get("install_path"),
            }
    return out


def _compile_rego(name: str, rego: str, query: str, input_doc: dict[str, Any]) -> dict[str, Any]:
    if OPA is None:
        return {"name": name, "compiled": False, "error": "opa binary not found", "violation_count": 0}
    with tempfile.TemporaryDirectory(prefix="documind-runtime-security-") as tmp:
        rego_path = Path(tmp) / f"{name}.rego"
        input_path = Path(tmp) / "input.json"
        rego_path.write_text(rego, encoding="utf-8")
        input_path.write_text(json.dumps(input_doc), encoding="utf-8")
        proc = subprocess.run(
            [OPA, "eval", "--format", "json", "--data", str(rego_path), "--input", str(input_path), query],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    if proc.returncode != 0:
        return {"name": name, "compiled": False, "error": (proc.stderr or proc.stdout)[:300], "violation_count": 0}
    try:
        body = json.loads(proc.stdout)
        value = body["result"][0]["expressions"][0]["value"]
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        return {"name": name, "compiled": False, "error": f"unexpected opa output: {exc}", "violation_count": 0}
    return {"name": name, "compiled": True, "error": "", "violation_count": len(value or [])}


def _tracee_rego_status() -> dict[str, Any]:
    configmaps = [doc for doc in _docs(TRACEE) if doc.get("kind") == "ConfigMap"]
    rules = next((cm for cm in configmaps if cm.get("metadata", {}).get("name") == "tracee-documind-rules"), {})
    rego = rules.get("data", {}).get("documind-rules.rego", "")
    sample = {
        "eventName": "execve",
        "args": {"pathname": "/bin/bash"},
    }
    return _compile_rego("tracee-documind-rules", rego, "data.tracee.documind.finding", sample)


def _tetragon_status() -> dict[str, Any]:
    policies = [doc for doc in _docs(TETRAGON) if doc.get("kind") == "TracingPolicy"]
    names = [doc.get("metadata", {}).get("name", "") for doc in policies]
    src = TETRAGON.read_text(encoding="utf-8") if TETRAGON.exists() else ""
    controls = {
        "sensitive_file_access": "security_file_open" in src,
        "privilege_and_shell_exec": "sys_execve" in src and "nsenter" in src and "unshare" in src,
        "network_egress_observe": "tcp_connect" in src,
        "post_actions": src.count("action: Post") >= 3,
        "helm_values": TETRAGON_VALUES.exists(),
    }
    return {
        "manifest_present": TETRAGON.exists(),
        "policy_count": len(policies),
        "policies": names,
        "controls": controls,
        "ready": bool(policies) and all(controls.values()),
    }


def _tracee_status() -> dict[str, Any]:
    docs = _docs(TRACEE)
    configmaps = [doc for doc in docs if doc.get("kind") == "ConfigMap"]
    names = [doc.get("metadata", {}).get("name", "") for doc in configmaps]
    src = TRACEE.read_text(encoding="utf-8") if TRACEE.exists() else ""
    rego = _tracee_rego_status()
    controls = {
        "rules_configmap": "tracee-documind-rules" in names,
        "values_configmap": "tracee-documind-values" in names,
        "json_output": "json: true" in src,
        "metrics_enabled": "metrics:" in src and "enabled: true" in src,
        "helm_values": TRACEE_VALUES.exists(),
        "container_escape_rule": "container_escape_attempt" in src,
        "sensitive_file_rule": "sensitive_file_access" in src,
    }
    return {
        "manifest_present": TRACEE.exists(),
        "configmaps": names,
        "controls": controls,
        "rego": rego,
        "ready": all(controls.values()) and rego["compiled"] and rego["violation_count"] >= 1,
    }


def _wazuh_status() -> dict[str, Any]:
    compose = _yaml(WAZUH_COMPOSE)
    services = compose.get("services", {})
    service_names = set(services)
    conf = WAZUH_CONF.read_text(encoding="utf-8") if WAZUH_CONF.exists() else ""
    required = {"wazuh-indexer", "wazuh-manager", "wazuh-dashboard"}
    controls = {
        "compose_present": WAZUH_COMPOSE.exists(),
        "manager_indexer_dashboard": required <= service_names,
        "manager_api_port": "55000:55000" in json.dumps(services.get("wazuh-manager", {}).get("ports", [])),
        "dashboard_port": "5602:5601" in json.dumps(services.get("wazuh-dashboard", {}).get("ports", [])),
        "tetragon_ingest": "tetragon.json" in conf,
        "tracee_ingest": "tracee.json" in conf,
        "json_alerts": "<jsonout_output>yes</jsonout_output>" in conf,
    }
    return {
        "compose_present": WAZUH_COMPOSE.exists(),
        "services": sorted(service_names),
        "controls": controls,
        "ready": all(controls.values()),
    }


def status() -> dict[str, Any]:
    namespaces = [doc.get("metadata", {}).get("name", "") for doc in _docs(NAMESPACES) if doc.get("kind") == "Namespace"]
    catalog = _catalog_status()
    components = {
        "wazuh": _wazuh_status(),
        "tetragon": _tetragon_status(),
        "tracee": _tracee_status(),
    }
    return {
        "runtime_security": {
            "kustomization_present": KUSTOMIZATION.exists(),
            "namespaces": sorted(namespaces),
            "required_namespaces_present": {"wazuh", "tetragon", "tracee"} <= set(namespaces),
            "catalog": catalog,
            "catalog_shipped": all(catalog.get(name, {}).get("status") == "shipped" for name in ("wazuh", "tetragon", "tracee")),
            "ready": all(component["ready"] for component in components.values()),
        },
        "components": components,
        "files": {
            "kustomization": str(KUSTOMIZATION.relative_to(REPO)),
            "tetragon": str(TETRAGON.relative_to(REPO)),
            "tracee": str(TRACEE.relative_to(REPO)),
            "wazuh_compose": str(WAZUH_COMPOSE.relative_to(REPO)),
            "wazuh_conf": str(WAZUH_CONF.relative_to(REPO)),
            "tetragon_values": str(TETRAGON_VALUES.relative_to(REPO)),
            "tracee_values": str(TRACEE_VALUES.relative_to(REPO)),
        },
        "recommendation": (
            "Apply infra/runtime-security for Kubernetes eBPF controls, and opt in "
            "to Wazuh with docker compose -f infra/runtime-security/wazuh-compose.yml up -d."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-on-not-ready", action="store_true")
    args = parser.parse_args()
    payload = status()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Runtime security ready={payload['runtime_security']['ready']}")
        for name, component in payload["components"].items():
            print(f"{name}: ready={component['ready']}")
    return 1 if args.fail_on_not_ready and not payload["runtime_security"]["ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
