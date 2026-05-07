#!/usr/bin/env python3
"""Doc-framework registry loader + validator.

Per ADR-029. Reads docs/templates/doc_framework/registry.yaml and
exposes the parsed entries via a typed dataclass surface so the
generation workflow (iter-74) and review API (iter-72) consume one
canonical source.

The loader VALIDATES the registry — every entry must have all
required fields + values must follow the constants in this module.
A registry that fails validation raises at load time so the workflow
can't start with a malformed contract.

CLI:
  python3 scripts/doc_framework_registry.py            # human-readable
  python3 scripts/doc_framework_registry.py --json     # JSON dump
  python3 scripts/doc_framework_registry.py --doc srs  # one entry
  python3 scripts/doc_framework_registry.py --roles    # unique role list
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REGISTRY_YAML = REPO / "docs" / "templates" / "doc_framework" / "registry.yaml"

# Allowed roles — locked here so registry can't introduce a typo'd
# role name. Adding a new role = explicit code change + drill update.
ALLOWED_ROLES: frozenset[str] = frozenset({
    "business_analyst",
    "product_manager",
    "sponsor",
    "stakeholder",
    "architect",
    "engineering_manager",
    "tech_lead",
    "senior_engineer",
    "qa_lead",
    "devops_lead",
    "sre",
    "security_lead",
    "compliance_officer",
    "project_manager",
    "hr_lead",
    "finance_lead",
    "procurement_lead",
})

# Allowed KPI dimensions — same lock pattern. Per ADR-029 each doc
# type defines a 5-dimension set; novel dimensions need explicit
# code change.
ALLOWED_KPI_DIMENSIONS: frozenset[str] = frozenset({
    # Cross-cutting
    "completeness", "clarity", "testability", "traceability",
    "non_functional_coverage",
    # Business
    "business_value", "scope_clarity", "stakeholder_coverage",
    "success_criteria", "constraints_documented",
    # Architecture
    "scalability", "security", "cost", "fault_tolerance",
    "implementability", "api_contract_clarity", "data_model_coverage",
    "error_handling", "test_alignment",
    "c4_completeness", "cross_cutting_concerns", "adr_linkage",
    "tech_choice_justification", "migration_strategy",
    # Test
    "requirement_coverage", "edge_case_coverage",
    "test_data_completeness", "acceptance_criteria",
    # Infra / DevOps / SRE
    "capacity_planning", "high_availability", "disaster_recovery",
    "network_topology", "cost_estimate",
    "ci_cd_completeness", "rollback_strategy", "monitoring_hooks",
    "secrets_management", "runbook_quality",
    # Security
    "threat_model", "controls_coverage", "compliance_mapping",
    "incident_response", "audit_trail",
    # PM / planning
    "milestone_clarity", "dependency_mapping", "critical_path",
    "communication_plan", "success_metrics",
    "release_strategy", "rollback_plan", "validation_steps",
    "downtime_budget",
    "load_projection", "growth_assumptions", "bottleneck_analysis",
    "scaling_strategy", "cost_at_capacity",
    "work_breakdown", "effort_basis", "risk_buffer",
    "dependency_estimate", "methodology_documented",
    "skill_match", "availability_validated", "ramp_up_time",
    "backup_assignments", "utilization_target",
    "line_item_completeness", "tco_breakdown", "contingency_buffer",
    "cost_attribution", "benchmark_comparison",
    "identification", "probability", "impact", "mitigation",
    "monitoring",
    "task_clarity", "assignee_match", "dependency_visibility",
    "effort_estimate",
    "role_definitions", "skill_coverage", "reporting_lines",
    "communication_pattern", "onboarding_plan",
    "quality_metrics", "test_strategy", "acceptance_gates",
    "tooling_choice", "feedback_loop",
    "vendor_evaluation", "sla_terms", "cost_breakdown",
    "risk_assessment", "exit_strategy",
})


@dataclass(frozen=True)
class DocEntry:
    doc_type: str
    display_name: str
    owner_role: str
    reviewer_roles: tuple[str, ...]
    interdept_required: bool
    template_path: str
    prompt_path: str
    kpi_dimensions: tuple[str, ...]
    min_kpi: float


@dataclass(frozen=True)
class Registry:
    version: int
    default_min_kpi: float
    docs: tuple[DocEntry, ...]


class RegistryError(ValueError):
    """Raised when registry.yaml fails validation."""


def _load_yaml(path: Path) -> dict:
    """Read YAML; tolerate the common case of PyYAML missing by hand-
    parsing the limited subset we use (registry.yaml is hand-authored
    + simple). Production install: PyYAML is in requirements."""
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-not-found]
        return yaml.safe_load(text)
    except ImportError:
        # Hand-parse fallback. Limited but works for our shape:
        # top-level keys + list-of-dicts under `docs:`.
        return _hand_parse_yaml(text)


def _hand_parse_yaml(text: str) -> dict:
    """Minimal YAML subset parser — registry.yaml shape only.

    Handles: scalars, lists with [a, b, c] inline, indented dicts,
    list-of-dicts with `- key: value` entries.
    Does NOT handle: multi-line strings, anchors, complex nesting.
    """
    # The registry's shape is regular enough that we can do a
    # line-based parse. Stage-1 fallback only; production uses PyYAML.
    out: dict = {"docs": []}
    current_doc: dict = {}
    in_docs = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        if not line.startswith(" "):
            # Top-level key
            if line == "docs:":
                in_docs = True
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                v = v.strip()
                if v:
                    out[k.strip()] = _coerce(v)
            continue
        # Indented — inside docs:
        if in_docs:
            stripped = line.strip()
            if stripped.startswith("- "):
                if current_doc:
                    out["docs"].append(current_doc)
                current_doc = {}
                stripped = stripped[2:]
            if stripped.startswith("- "):
                # nested list item — we're inside reviewer_roles or kpi_dimensions
                continue
            if ":" in stripped:
                k, v = stripped.split(":", 1)
                k = k.strip()
                v = v.strip()
                if v.startswith("[") and v.endswith("]"):
                    items = v[1:-1].split(",")
                    current_doc[k] = [i.strip() for i in items if i.strip()]
                elif v:
                    current_doc[k] = _coerce(v)
                else:
                    # The next lines are list items
                    current_doc[k] = []
                    current_doc["__pending_list_key__"] = k
            elif stripped.startswith("- "):
                key = current_doc.get("__pending_list_key__")
                if key:
                    current_doc[key].append(stripped[2:].strip())
    if current_doc:
        out["docs"].append(current_doc)
    # Strip helper key
    for d in out["docs"]:
        d.pop("__pending_list_key__", None)
    return out


def _coerce(v: str) -> object:
    """Coerce string scalar to int/float/bool/str."""
    s = v.strip().strip('"').strip("'")
    if s.lower() in ("true", "yes"):
        return True
    if s.lower() in ("false", "no"):
        return False
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return s


def load_registry(path: Path = REGISTRY_YAML) -> Registry:
    """Load + validate the registry. Raises RegistryError on any
    contract violation."""
    if not path.exists():
        raise RegistryError(f"registry not found at {path}")
    raw = _load_yaml(path)
    if not isinstance(raw, dict):
        raise RegistryError("registry root must be a mapping")
    version = int(raw.get("version", 0))
    if version != 1:
        raise RegistryError(
            f"registry version={version}; this loader expects version=1"
        )
    default_min_kpi = float(raw.get("default_min_kpi", 1.0))
    if not 0.0 <= default_min_kpi <= 1.0:
        raise RegistryError(
            f"default_min_kpi={default_min_kpi} not in [0, 1]"
        )

    docs_raw = raw.get("docs") or []
    if not isinstance(docs_raw, list):
        raise RegistryError("registry.docs must be a list")

    seen_types: set[str] = set()
    docs: list[DocEntry] = []
    for d in docs_raw:
        for required in (
            "doc_type", "display_name", "owner_role",
            "reviewer_roles", "interdept_required",
            "template_path", "prompt_path", "kpi_dimensions",
        ):
            if required not in d:
                raise RegistryError(
                    f"doc entry missing field {required!r}: {d.get('doc_type', '?')}"
                )
        doc_type = str(d["doc_type"]).strip()
        if doc_type in seen_types:
            raise RegistryError(f"duplicate doc_type: {doc_type}")
        seen_types.add(doc_type)
        if not doc_type or not doc_type.replace("_", "").isalnum():
            raise RegistryError(f"invalid doc_type slug: {doc_type!r}")

        owner = str(d["owner_role"]).strip()
        if owner not in ALLOWED_ROLES:
            raise RegistryError(
                f"doc {doc_type}: owner_role {owner!r} not in ALLOWED_ROLES"
            )

        reviewers_raw = d["reviewer_roles"] or []
        reviewers = tuple(str(r).strip() for r in reviewers_raw)
        bad_reviewers = [r for r in reviewers if r not in ALLOWED_ROLES]
        if bad_reviewers:
            raise RegistryError(
                f"doc {doc_type}: reviewer_roles {bad_reviewers!r} not in ALLOWED_ROLES"
            )

        kpi_raw = d["kpi_dimensions"] or []
        kpi_dims = tuple(str(k).strip() for k in kpi_raw)
        if len(kpi_dims) < 3:
            raise RegistryError(
                f"doc {doc_type}: requires ≥3 kpi_dimensions; got {len(kpi_dims)}"
            )
        bad_kpi = [k for k in kpi_dims if k not in ALLOWED_KPI_DIMENSIONS]
        if bad_kpi:
            raise RegistryError(
                f"doc {doc_type}: kpi_dimensions {bad_kpi!r} not in "
                f"ALLOWED_KPI_DIMENSIONS"
            )

        min_kpi = float(d.get("min_kpi", default_min_kpi))
        if not 0.0 <= min_kpi <= 1.0:
            raise RegistryError(
                f"doc {doc_type}: min_kpi={min_kpi} not in [0, 1]"
            )

        interdept = bool(d["interdept_required"])
        template_path = str(d["template_path"])
        prompt_path = str(d["prompt_path"])

        docs.append(DocEntry(
            doc_type=doc_type,
            display_name=str(d["display_name"]),
            owner_role=owner,
            reviewer_roles=reviewers,
            interdept_required=interdept,
            template_path=template_path,
            prompt_path=prompt_path,
            kpi_dimensions=kpi_dims,
            min_kpi=min_kpi,
        ))

    if len(docs) != 20:
        raise RegistryError(
            f"registry must define exactly 20 doc types per ADR-029; "
            f"got {len(docs)}"
        )

    return Registry(version=version, default_min_kpi=default_min_kpi,
                    docs=tuple(docs))


def unique_roles(reg: Registry) -> set[str]:
    """All distinct roles across owner + reviewer fields."""
    roles: set[str] = set()
    for d in reg.docs:
        roles.add(d.owner_role)
        roles.update(d.reviewer_roles)
    return roles


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true",
                        help="emit JSON dump instead of human-readable")
    parser.add_argument("--doc", type=str, default=None,
                        help="filter to one doc_type (slug)")
    parser.add_argument("--roles", action="store_true",
                        help="list unique roles")
    args = parser.parse_args()

    try:
        reg = load_registry()
    except RegistryError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if args.roles:
        roles = sorted(unique_roles(reg))
        if args.json:
            print(json.dumps(roles, indent=2))
        else:
            print(f"Unique roles: {len(roles)}")
            for r in roles:
                print(f"  - {r}")
        return 0

    docs_to_show = reg.docs
    if args.doc:
        docs_to_show = tuple(d for d in reg.docs if d.doc_type == args.doc)
        if not docs_to_show:
            print(f"ERROR: no doc with doc_type={args.doc!r}", file=sys.stderr)
            return 1

    if args.json:
        out = {
            "version": reg.version,
            "default_min_kpi": reg.default_min_kpi,
            "docs": [asdict(d) for d in docs_to_show],
        }
        print(json.dumps(out, indent=2))
        return 0

    print(f"Doc Framework Registry — version {reg.version}")
    print(f"  default_min_kpi: {reg.default_min_kpi}")
    print(f"  doc count: {len(reg.docs)}")
    print(f"  unique roles: {len(unique_roles(reg))}")
    print()
    for d in docs_to_show:
        print(f"  {d.doc_type:6s} {d.display_name}")
        print(f"         owner: {d.owner_role}")
        print(f"         reviewers: {', '.join(d.reviewer_roles)}")
        print(f"         kpi: {len(d.kpi_dimensions)} dims; min={d.min_kpi:.0%}")
        print(f"         interdept: {d.interdept_required}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
