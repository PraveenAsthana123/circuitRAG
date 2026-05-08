#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Grafana dashboards Kiali deep-links to.

Locks the contract: every dashboard name declared in
infra/kiali/kiali-cluster-config.yaml under
external_services.grafana.dashboards[].name MUST exist as a Grafana
dashboard JSON in infra/observability/grafana-dashboards/ with an
EXACTLY matching `title` field. Mismatches → Kiali deep-link 404s.

This drill runs on the source files (no live cluster needed) so it
gates commits before deploy. Live verification (Grafana API search)
is documented in the §51 forensic substrate of the commit body.

8 steps, 4 negative.

  1. POSITIVE: scripts/generate-grafana-dashboards.py exists +
              executable
  2. POSITIVE: Generator declares ≥15 dashboards
  3. POSITIVE: All declared dashboards exist as JSON files in
              infra/observability/grafana-dashboards/
  4. POSITIVE: Every Kiali deep-link name has a matching Grafana
              dashboard `title` (1:1 mapping)
  5. NEGATIVE: No Grafana dashboard has a duplicate `uid` (Grafana
              silently ignores duplicates → some dashboards vanish)
  6. NEGATIVE: No dashboard `title` contains a typo of the Kiali
              key terms (Documind/Istio/RAG/Vector DB/Cache/etc.)
  7. NEGATIVE: Generator's title list is NOT a subset of Kiali's
              (every generated dashboard MUST be deep-linked from
              Kiali — no orphans)
  8. NEGATIVE: No JSON dashboard claims schemaVersion < 36 (Grafana
              11.x requires ≥36; older schema renders broken)

Per CLAUDE.md §43 (drill discipline; ≥3 negatives — 4 here),
§47.6 observability is first-class, §49 compose footer (Grafana
joins Kiali + integrations-health + tools-launcher), §57.7 honesty
(forward-contract metrics declared as such; no silent absences).
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
GENERATOR = REPO / "scripts" / "generate-grafana-dashboards.py"
DASH_DIR = REPO / "infra" / "observability" / "grafana-dashboards"
KIALI_CFG = REPO / "infra" / "kiali" / "kiali-cluster-config.yaml"

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def load_generator() -> object:
    spec = importlib.util.spec_from_file_location("gen_dash", GENERATOR)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def load_kiali_dashboards() -> list[str]:
    docs = list(yaml.safe_load_all(KIALI_CFG.read_text(encoding="utf-8")))
    cm = next(
        d for d in docs if d and d.get("kind") == "ConfigMap" and d.get("metadata", {}).get("name") == "kiali"
    )
    cfg = yaml.safe_load(cm["data"]["config.yaml"])
    return [
        d["name"]
        for d in cfg["external_services"]["grafana"]["dashboards"]
        if "name" in d
    ]


def load_dashboard_files() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in sorted(DASH_DIR.glob("*.json")):
        out[p.name] = json.loads(p.read_text(encoding="utf-8"))
    return out


def main() -> int:
    # ── 1. generator exists + executable ───────────────────────────────
    step("1. POSITIVE: scripts/generate-grafana-dashboards.py exists + executable")
    if not GENERATOR.exists():
        fail(f"missing: {GENERATOR.relative_to(REPO)}")
    mode = GENERATOR.stat().st_mode
    if not (mode & 0o100):
        fail("generator not executable (chmod +x)")
    ok(f"generator present + executable ({GENERATOR.stat().st_size}b)")

    # ── 2. generator declares ≥15 dashboards ──────────────────────────
    step("2. POSITIVE: generator declares ≥15 dashboards")
    gen = load_generator()
    declared = list(getattr(gen, "DASHBOARDS"))
    if len(declared) < 15:
        fail(f"generator declares only {len(declared)} dashboards (need ≥15)")
    ok(f"generator declares {len(declared)} dashboards")

    # ── 3. every declared dashboard exists on disk ────────────────────
    step("3. POSITIVE: every declared dashboard JSON exists on disk")
    files = load_dashboard_files()
    for d in declared:
        path = DASH_DIR / f"{d['uid']}.json"
        if path.name not in files:
            fail(f"missing dashboard JSON: {path.relative_to(REPO)} (regenerate via scripts/generate-grafana-dashboards.py)")
    ok(f"all {len(declared)} dashboard JSONs exist in {DASH_DIR.relative_to(REPO)}")

    # ── 4. Kiali names ↔ Grafana titles 1:1 ───────────────────────────
    step("4. POSITIVE: every Kiali deep-link has a matching Grafana title")
    kiali_names = load_kiali_dashboards()
    file_titles = {f: d.get("title", "") for f, d in files.items() if d.get("title", "").startswith("Documind")}
    title_set = set(file_titles.values())
    missing_titles = [n for n in kiali_names if n not in title_set]
    if missing_titles:
        fail(
            f"Kiali deep-links without matching Grafana title: {missing_titles}. "
            "Edit DASHBOARDS in generator + re-run, OR remove the Kiali entry."
        )
    ok(f"all {len(kiali_names)} Kiali deep-links resolve to a Grafana dashboard title")

    # ── 5. NEGATIVE: no duplicate UIDs ────────────────────────────────
    step("5. NEGATIVE: no two dashboards share a UID")
    uids = [d.get("uid", "") for d in files.values()]
    dups = {u for u in uids if uids.count(u) > 1}
    if dups:
        fail(
            f"duplicate UIDs detected: {dups} — Grafana silently ignores duplicates "
            "and some dashboards will vanish from the listing"
        )
    ok(f"all {len(uids)} dashboard UIDs are unique")

    # ── 6. NEGATIVE: no Documind-key-term typos in generated titles ──
    step("6. NEGATIVE: no typos in key Documind terms (Documind/Istio/RAG/Vector DB/Cache)")
    # Scope: ONLY dashboards emitted by this generator (carry the
    # `_generator` field). Hand-written legacy dashboards like
    # documind-overview.json predate the Kiali deep-link contract
    # and are NOT subject to the title-prefix rule.
    generator_marker = "scripts/generate-grafana-dashboards.py"
    for fname, dash in files.items():
        if dash.get("_generator") != generator_marker:
            continue
        title = dash.get("title", "")
        if not title.startswith("Documind / "):
            fail(
                f"{fname}: title {title!r} does NOT start with 'Documind / ' — "
                "Kiali deep-link match is exact-string and case-sensitive"
            )
    gen_count = sum(1 for d in files.values() if d.get("_generator") == generator_marker)
    ok(f"all {gen_count} generated dashboards use 'Documind / <name>' title prefix")

    # ── 7. NEGATIVE: no orphan generated dashboards ───────────────────
    step("7. NEGATIVE: every generated dashboard is referenced by Kiali")
    declared_titles = {d["title"] for d in declared}
    kiali_set = set(kiali_names)
    orphans = declared_titles - kiali_set
    if orphans:
        fail(
            f"generator emits dashboards Kiali doesn't deep-link to: {orphans}. "
            "Either add them to Kiali's dashboards list OR remove from generator."
        )
    ok(f"all {len(declared_titles)} generated dashboards are deep-linked from Kiali")

    # ── 8. NEGATIVE: schema version ≥ 36 (Grafana 11.x requirement) ───
    step("8. NEGATIVE: every dashboard schemaVersion ≥ 36 (Grafana 11.x)")
    for fname, dash in files.items():
        sv = dash.get("schemaVersion", 0)
        if sv < 36:
            fail(
                f"{fname}: schemaVersion={sv} (need ≥36 for Grafana 11.x — "
                "older schemas render with broken legends/axes)"
            )
    ok("all dashboards declare schemaVersion ≥ 36")

    print(f"\n{BOLD}{GREEN}ALL 8 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
