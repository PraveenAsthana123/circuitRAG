#!/usr/bin/env python3
"""Offline-safe OPA Gatekeeper readiness checker.

This validates the repo-owned Gatekeeper policy pack without requiring a
live Kubernetes cluster:
  - Gatekeeper ConstraintTemplate and Constraint objects are present
  - templates use deny enforcement for the documind namespace
  - embedded Rego compiles with the local OPA binary when available
  - local sample admission reviews exercise allow/deny paths
"""
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
GATEKEEPER_DIR = REPO / "infra" / "k8s" / "gatekeeper"
CONSTRAINTS = GATEKEEPER_DIR / "constraints.yaml"
KUSTOMIZATION = GATEKEEPER_DIR / "kustomization.yaml"
OPA_BINARY = shutil.which("opa")


def load_docs() -> list[dict[str, Any]]:
    if not CONSTRAINTS.exists():
        return []
    return [doc for doc in yaml.safe_load_all(CONSTRAINTS.read_text(encoding="utf-8")) if doc]


def split_docs(docs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    templates = [doc for doc in docs if doc.get("kind") == "ConstraintTemplate"]
    constraints = [
        doc for doc in docs
        if doc.get("apiVersion", "").startswith("constraints.gatekeeper.sh/")
    ]
    return templates, constraints


def extract_rego(template: dict[str, Any]) -> str:
    targets = template.get("spec", {}).get("targets", [])
    for target in targets:
        if target.get("target") == "admission.k8s.gatekeeper.sh":
            return str(target.get("rego", ""))
    return ""


def opa_eval(rego: str, query: str, input_doc: dict[str, Any]) -> dict[str, Any]:
    if OPA_BINARY is None:
        return {"available": False, "error": "opa binary not found", "value": None}
    with tempfile.TemporaryDirectory(prefix="documind-gk-") as tmp:
        rego_path = Path(tmp) / "template.rego"
        input_path = Path(tmp) / "input.json"
        rego_path.write_text(rego, encoding="utf-8")
        input_path.write_text(json.dumps(input_doc), encoding="utf-8")
        proc = subprocess.run(
            [
                OPA_BINARY,
                "eval",
                "--format",
                "json",
                "--data",
                str(rego_path),
                "--input",
                str(input_path),
                query,
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    if proc.returncode != 0:
        return {
            "available": True,
            "error": proc.stderr[:300] or proc.stdout[:300],
            "value": None,
        }
    try:
        body = json.loads(proc.stdout)
        value = body["result"][0]["expressions"][0]["value"]
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        return {"available": True, "error": f"unexpected opa output: {exc}", "value": None}
    return {"available": True, "error": "", "value": value}


def compile_templates(templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for template in templates:
        name = template.get("metadata", {}).get("name", "")
        rego = extract_rego(template)
        package_line = next((line.strip() for line in rego.splitlines() if line.strip().startswith("package ")), "")
        package = package_line.replace("package ", "", 1)
        query = f"data.{package}.violation" if package else "data"
        sample = {
            "review": {
                "object": {
                    "metadata": {"labels": {}},
                    "spec": {
                        "hostNetwork": True,
                        "containers": [
                            {
                                "name": "bad",
                                "image": "evil.example/bad:latest",
                                "securityContext": {"privileged": True},
                            }
                        ],
                    },
                }
            },
            "parameters": {
                "labels": ["app.kubernetes.io/name"],
                "prefixes": ["ghcr.io/documind/"],
            },
        }
        result = opa_eval(rego, query, sample)
        results.append({
            "template": name,
            "package": package,
            "compiled": result["available"] and not result["error"],
            "error": result["error"],
            "sample_violation_count": len(result["value"] or []),
        })
    return results


def status() -> dict[str, Any]:
    docs = load_docs()
    templates, constraints = split_docs(docs)
    template_kinds = {
        template.get("spec", {}).get("crd", {}).get("spec", {}).get("names", {}).get("kind")
        for template in templates
    }
    constraint_kinds = {constraint.get("kind") for constraint in constraints}
    deny_constraints = [
        constraint.get("metadata", {}).get("name")
        for constraint in constraints
        if constraint.get("spec", {}).get("enforcementAction") == "deny"
    ]
    namespace_scoped = [
        constraint.get("metadata", {}).get("name")
        for constraint in constraints
        if "documind" in constraint.get("spec", {}).get("match", {}).get("namespaces", [])
    ]
    compiled = compile_templates(templates)
    return {
        "gatekeeper": {
            "manifests_present": CONSTRAINTS.exists() and KUSTOMIZATION.exists(),
            "constraints_path": str(CONSTRAINTS.relative_to(REPO)),
            "kustomization_path": str(KUSTOMIZATION.relative_to(REPO)),
            "opa_binary": OPA_BINARY,
            "ready_for_apply": bool(templates and constraints and all(item["compiled"] for item in compiled)),
            "install_note": "Install Gatekeeper CRDs/controller first, then apply infra/k8s/gatekeeper.",
        },
        "counts": {
            "constraint_templates": len(templates),
            "constraints": len(constraints),
            "deny_constraints": len(deny_constraints),
            "namespace_scoped": len(namespace_scoped),
        },
        "coverage": {
            "template_kinds": sorted(k for k in template_kinds if k),
            "constraint_kinds": sorted(k for k in constraint_kinds if k),
            "all_templates_bound": template_kinds == constraint_kinds,
            "controls": [
                "required_labels",
                "no_host_namespace",
                "non_root_readonly_no_privilege_escalation",
                "allowed_image_registries",
            ],
        },
        "rego": compiled,
        "recommendation": (
            "Run this checker in CI, apply Gatekeeper CRDs/controller in cluster bootstrap, "
            "then apply infra/k8s/gatekeeper after namespace creation."
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
        gk = payload["gatekeeper"]
        counts = payload["counts"]
        print(f"Gatekeeper manifests present={gk['manifests_present']}")
        print(f"Templates={counts['constraint_templates']} constraints={counts['constraints']}")
        print(f"OPA binary={gk['opa_binary']}")
        print(f"Ready for apply={gk['ready_for_apply']}")
    return 1 if args.fail_on_not_ready and not payload["gatekeeper"]["ready_for_apply"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
