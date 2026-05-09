#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Wazuh + Tetragon + Tracee runtime-security stack.

NEGATIVE: runtime-security tools must not be marked shipped without manifests.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))


def main() -> int:
    print("-- 1. POSITIVE: runtime_security_status exports stable payload --")
    import runtime_security_status

    payload = runtime_security_status.status()
    for key in ("runtime_security", "components", "files"):
        if key not in payload:
            print(f"x status missing key: {key}")
            return 1
    print("  ok: status shape stable")

    print("-- 2. POSITIVE: Wazuh, Tetragon, Tracee catalog entries are shipped --")
    rs = payload["runtime_security"]
    if not rs["catalog_shipped"]:
        print(f"x catalog entries not shipped: {rs['catalog']}")
        return 1
    print("  ok: catalog marks all three shipped")

    print("-- 3. POSITIVE: namespaces and kustomization are present --")
    if not rs["kustomization_present"] or not rs["required_namespaces_present"]:
        print(f"x namespace/kustomization missing: {rs}")
        return 1
    print("  ok: wazuh/tetragon/tracee namespaces defined")

    print("-- 4. POSITIVE: Tetragon policies cover file, exec, network, actions, and Helm values --")
    tetragon = payload["components"]["tetragon"]
    if tetragon["policy_count"] != 3:
        print(f"x expected 3 Tetragon policies: {tetragon}")
        return 1
    if not all(tetragon["controls"].values()):
        print(f"x Tetragon controls incomplete: {tetragon['controls']}")
        return 1
    print("  ok: Tetragon controls covered")

    print("-- 5. POSITIVE: Tracee has rules, metrics, JSON output, Helm values, and Rego sample hit --")
    tracee = payload["components"]["tracee"]
    if not all(tracee["controls"].values()):
        print(f"x Tracee controls incomplete: {tracee['controls']}")
        return 1
    if not tracee["rego"]["compiled"] or tracee["rego"]["violation_count"] < 1:
        print(f"x Tracee Rego did not compile/hit sample: {tracee['rego']}")
        return 1
    print("  ok: Tracee controls covered")

    print("-- 6. POSITIVE: Wazuh compose has indexer, manager, dashboard, and JSON ingest --")
    wazuh = payload["components"]["wazuh"]
    if set(wazuh["services"]) != {"wazuh-dashboard", "wazuh-indexer", "wazuh-manager"}:
        print(f"x Wazuh services drifted: {wazuh['services']}")
        return 1
    if not all(wazuh["controls"].values()):
        print(f"x Wazuh controls incomplete: {wazuh['controls']}")
        return 1
    print("  ok: Wazuh compose and ingest controls covered")

    print("-- 7. NEGATIVE: runtime security gate is red if any component is not ready --")
    if not rs["ready"]:
        print(f"x runtime-security stack not ready: {payload}")
        return 1
    print("  ok: full runtime-security gate is green")

    print("\nALL 7 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
