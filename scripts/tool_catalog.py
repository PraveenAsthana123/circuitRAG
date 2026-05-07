"""Tool catalog loader + validator (iter-74).

Loads `config/tool_catalog/*.yaml` and validates each entry against the
9-axis schema documented in `config/tool_catalog/README.md`.

Per CLAUDE.md §44 (iter-74), §47 (architecture observable),
§50.5.3 (read-only), §51 (forensic substrate).

Public API
----------
- ALLOWED_STATUS_TARGETS: frozenset of valid status_target values
- REQUIRED_AXES: tuple of the 9 top-level YAML keys every entry MUST have
- ToolCatalogEntry: dataclass shape returned by `load_entry()`
- load_catalog(path=None) -> dict[str, ToolCatalogEntry]
- validate_entry(entry: dict) -> list[str]   # empty list = valid

CLI
---
$ python3 scripts/tool_catalog.py             # validate all entries
$ python3 scripts/tool_catalog.py --json      # emit JSON-rendered catalog
$ python3 scripts/tool_catalog.py --only slack
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-not-found]
except ImportError:
    print("ERROR: pyyaml not installed; pip install pyyaml", file=sys.stderr)
    sys.exit(2)

REPO = Path(__file__).resolve().parent.parent
CATALOG_DIR = REPO / "config" / "tool_catalog"

ALLOWED_STATUS_TARGETS = frozenset({"WORKING", "DEGRADED-OK", "OPTIONAL"})

REQUIRED_AXES = (
    "fallback",
    "io",
    "integration",
    "testing",
    "monitoring",
    "visualization",
    "policy",
    "observability",
    "runbook",
)

REQUIRED_FALLBACK_KEYS = ("on_unreachable", "on_failing", "on_not_installed")
REQUIRED_INTEGRATION_KEYS = ("upstream", "downstream", "contracts")
REQUIRED_TESTING_KEYS = ("drill", "smoke_cmd", "cadence")
REQUIRED_MONITORING_KEYS = ("metrics", "alerts")
REQUIRED_VISUALIZATION_KEYS = ("ui_page", "embed_in", "panels")
REQUIRED_POLICY_KEYS = ("opa_bundle", "rules", "default")
REQUIRED_OBSERVABILITY_KEYS = ("otel", "jaeger", "kibana", "log_fields")
ALLOWED_SIDE_EFFECTS = frozenset({"read", "write"})


@dataclass
class ToolCatalogEntry:
    namespace: str
    status_target: str
    owner: str
    raw: dict[str, Any] = field(repr=False)

    @property
    def io(self) -> list[dict[str, Any]]:
        return self.raw.get("io", []) or []

    @property
    def tools(self) -> list[str]:
        return [t["tool"] for t in self.io if "tool" in t]


def validate_entry(entry: dict[str, Any]) -> list[str]:
    """Return list of error strings; empty list = valid."""
    errors: list[str] = []

    ns = entry.get("namespace")
    if not isinstance(ns, str) or not ns:
        errors.append("namespace: missing or empty")
        return errors

    if entry.get("status_target") not in ALLOWED_STATUS_TARGETS:
        errors.append(
            f"status_target: {entry.get('status_target')!r} not in "
            f"{sorted(ALLOWED_STATUS_TARGETS)}"
        )

    if not entry.get("owner"):
        errors.append("owner: missing or empty")

    for axis in REQUIRED_AXES:
        if axis not in entry:
            errors.append(f"missing required axis: {axis}")

    fallback = entry.get("fallback") or {}
    if isinstance(fallback, dict):
        for k in REQUIRED_FALLBACK_KEYS:
            if not fallback.get(k):
                errors.append(f"fallback.{k}: missing or empty")

    io = entry.get("io") or []
    if not isinstance(io, list) or not io:
        errors.append("io: must be non-empty list")
    else:
        for i, t in enumerate(io):
            if not isinstance(t, dict):
                errors.append(f"io[{i}]: not a dict")
                continue
            tool = t.get("tool", "")
            if not tool.startswith(f"{ns}."):
                errors.append(
                    f"io[{i}].tool: {tool!r} doesn't start with {ns!r}."
                )
            if t.get("side_effects") not in ALLOWED_SIDE_EFFECTS:
                errors.append(
                    f"io[{i}].side_effects: {t.get('side_effects')!r} "
                    f"not in {sorted(ALLOWED_SIDE_EFFECTS)}"
                )
            for k in ("input_schema_ref", "output_schema_ref", "process"):
                if not t.get(k):
                    errors.append(f"io[{i}].{k}: missing or empty")

    integration = entry.get("integration") or {}
    if isinstance(integration, dict):
        for k in REQUIRED_INTEGRATION_KEYS:
            if k not in integration:
                errors.append(f"integration.{k}: missing")

    testing = entry.get("testing") or {}
    if isinstance(testing, dict):
        for k in REQUIRED_TESTING_KEYS:
            if not testing.get(k):
                errors.append(f"testing.{k}: missing or empty")
        # drill path must look real
        drill = testing.get("drill", "")
        if drill and not drill.startswith(("mcp/tests/", "tests/")):
            errors.append(
                f"testing.drill: {drill!r} should start with mcp/tests/ or tests/"
            )

    monitoring = entry.get("monitoring") or {}
    if isinstance(monitoring, dict):
        for k in REQUIRED_MONITORING_KEYS:
            if k not in monitoring:
                errors.append(f"monitoring.{k}: missing")
        metrics = monitoring.get("metrics") or []
        if not isinstance(metrics, list) or not metrics:
            errors.append("monitoring.metrics: must be non-empty list")

    viz = entry.get("visualization") or {}
    if isinstance(viz, dict):
        for k in REQUIRED_VISUALIZATION_KEYS:
            if k not in viz:
                errors.append(f"visualization.{k}: missing")
        ui_page = viz.get("ui_page", "")
        if ui_page and not ui_page.startswith("/admin/"):
            errors.append(
                f"visualization.ui_page: {ui_page!r} should start with /admin/"
            )

    policy = entry.get("policy") or {}
    if isinstance(policy, dict):
        for k in REQUIRED_POLICY_KEYS:
            if k not in policy:
                errors.append(f"policy.{k}: missing")
        if policy.get("default") != "deny":
            errors.append(
                f"policy.default: {policy.get('default')!r} must be 'deny' "
                f"(default-deny per §47.6)"
            )
        opa = policy.get("opa_bundle", "")
        if opa and not opa.endswith(".rego"):
            errors.append(
                f"policy.opa_bundle: {opa!r} doesn't point at a .rego file"
            )

    obs = entry.get("observability") or {}
    if isinstance(obs, dict):
        for k in REQUIRED_OBSERVABILITY_KEYS:
            if k not in obs:
                errors.append(f"observability.{k}: missing")
        otel = obs.get("otel") or {}
        if isinstance(otel, dict):
            span = otel.get("span_name", "")
            if span and not span.startswith(f"mcp.{ns}."):
                errors.append(
                    f"observability.otel.span_name: {span!r} should start "
                    f"with 'mcp.{ns}.'"
                )
        log_fields = obs.get("log_fields") or []
        for required_field in ("request_id", "tenant_id"):
            if required_field not in log_fields:
                errors.append(
                    f"observability.log_fields: missing canonical field "
                    f"{required_field!r}"
                )

    runbook = entry.get("runbook", "")
    if not runbook.startswith("ops/runbook/"):
        errors.append(
            f"runbook: {runbook!r} should start with 'ops/runbook/'"
        )

    return errors


def load_entry(path: Path) -> ToolCatalogEntry:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top-level YAML must be a mapping")
    if raw.get("namespace") != path.stem:
        raise ValueError(
            f"{path}: namespace={raw.get('namespace')!r} != filename={path.stem!r}"
        )
    return ToolCatalogEntry(
        namespace=raw["namespace"],
        status_target=raw.get("status_target", ""),
        owner=raw.get("owner", ""),
        raw=raw,
    )


def load_catalog(path: Path | None = None) -> dict[str, ToolCatalogEntry]:
    """Load all *.yaml entries under the catalog dir; returns ns -> entry."""
    catalog_dir = path or CATALOG_DIR
    out: dict[str, ToolCatalogEntry] = {}
    for f in sorted(catalog_dir.glob("*.yaml")):
        entry = load_entry(f)
        out[entry.namespace] = entry
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true", help="emit JSON catalog")
    p.add_argument("--only", help="only validate this namespace")
    args = p.parse_args()

    catalog = load_catalog()
    if args.only:
        catalog = {k: v for k, v in catalog.items() if k == args.only}
        if not catalog:
            print(f"no entries match --only={args.only!r}", file=sys.stderr)
            return 2

    all_errors: dict[str, list[str]] = {}
    for ns, entry in catalog.items():
        errors = validate_entry(entry.raw)
        if errors:
            all_errors[ns] = errors

    if args.json:
        print(json.dumps(
            {ns: e.raw for ns, e in catalog.items()},
            indent=2, default=str,
        ))
        return 1 if all_errors else 0

    print(f"Loaded {len(catalog)} catalog entries:")
    for ns, entry in catalog.items():
        marker = "✗" if all_errors.get(ns) else "✓"
        print(f"  {marker} {ns:<24} ({len(entry.tools)} tools, owner={entry.owner})")

    if all_errors:
        print("\nVALIDATION ERRORS:", file=sys.stderr)
        for ns, errs in all_errors.items():
            print(f"\n  [{ns}]", file=sys.stderr)
            for e in errs:
                print(f"    - {e}", file=sys.stderr)
        return 1

    print(f"\nALL {len(catalog)} ENTRIES VALID")
    return 0


if __name__ == "__main__":
    sys.exit(main())
