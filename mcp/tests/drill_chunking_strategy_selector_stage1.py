#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Chunking Strategy Selector — Stage-1 (per §43 + §56).

Locks the operator-supplied chunking decision engine that maps
(file_type, use_case, cost_priority, accuracy_priority) → ChunkingStrategy.

Contract:
  - chunking_strategy_selector.py exists as a separate module
  - 5 contract surfaces: choose, status, ChunkingStrategy,
    ChunkingSelectorDisabled, supported_file_types
  - Default-deny: CHUNKING_STRATEGY_SELECTOR_ENABLED=1 required
  - Supports all 23 operator-spec file types (txt, pdf, docx, ppt,
    html, md, csv, xlsx, json, xml, logs, code, sql, api_docs, email,
    ticket, chat, image, audio, video, iot, geospatial, graph)
  - Use-case override path: legal/policy/compliance → hierarchical clause
  - Cost/accuracy modulation: high-accuracy shrinks chunks; low-cost
    enlarges them
  - Existing ingestion-svc Chunker source UNCHANGED (Stage-2 wires)

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SELECTOR = REPO / "scripts" / "chunking_strategy_selector.py"
INGESTION_CHUNKING = REPO / "services" / "ingestion-svc" / "app" / "chunking"
INGESTION_SAGA = REPO / "services" / "ingestion-svc" / "app" / "saga" / "document_saga.py"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod, spec


def main() -> int:
    print("-- 1. POSITIVE: chunking_strategy_selector.py exists + non-trivial --")
    if not SELECTOR.exists():
        print(f"x {SELECTOR} missing")
        return 1
    src = SELECTOR.read_text(encoding="utf-8")
    if len(src) < 6000:
        print(f"x selector module too short ({len(src)} chars)")
        return 1
    print(f"  ok: selector present ({len(src)} chars)")

    print("-- 2. NEGATIVE: chunking_strategy_selector doesn't IMPORT chunker/saga (clean layering) --")
    # Post-Stage-3 reality: saga DOES legitimately import the selector
    # (Stage-3 wire). The check now enforces the selector itself
    # doesn't reverse-import (cycle prevention).
    rev_import = re.compile(
        r"^\s*(from\s+.*ingestion|import\s+.*ingestion|from\s+app\.chunking|from\s+app\.saga)",
        re.MULTILINE,
    )
    if rev_import.search(src):
        print("x chunking_strategy_selector imports chunker / saga (cycle risk)")
        return 1
    print("  ok: selector doesn't import chunker / saga (clean layering)")

    print("-- 3. POSITIVE: 5 contract surfaces exported --")
    os.environ["CHUNKING_STRATEGY_SELECTOR_ENABLED"] = "1"
    mod, spec = _load_module(SELECTOR)
    for name in ("choose", "status", "ChunkingStrategy",
                 "ChunkingSelectorDisabled", "supported_file_types"):
        if not hasattr(mod, name):
            print(f"x chunking_strategy_selector.{name} missing")
            return 1
    print("  ok: 5 surfaces exported")

    print("-- 4. NEGATIVE: default-deny — choose() raises when env unset --")
    os.environ.pop("CHUNKING_STRATEGY_SELECTOR_ENABLED", None)
    spec.loader.exec_module(mod)
    raised = False
    try:
        mod.choose(file_type="pdf")
    except mod.ChunkingSelectorDisabled as exc:
        raised = True
        if "CHUNKING_STRATEGY_SELECTOR_ENABLED" not in str(exc):
            print(f"x error msg must cite env flag; got: {exc}")
            return 1
    if not raised:
        print("x choose() should raise when flag off")
        return 1
    print("  ok: default-deny preserved (cites env flag)")

    # Re-enable for the rest of the test
    os.environ["CHUNKING_STRATEGY_SELECTOR_ENABLED"] = "1"
    spec.loader.exec_module(mod)

    print("-- 5. NEGATIVE: all 23 operator-spec file types supported --")
    expected_types = {
        "txt", "pdf", "docx", "ppt", "html", "md", "csv", "xlsx",
        "json", "xml", "logs", "code", "sql", "api_docs", "email",
        "ticket", "chat", "image", "audio", "video", "iot",
        "geospatial", "graph",
    }
    supported = set(mod.supported_file_types())
    missing = expected_types - supported
    if missing:
        print(f"x missing file types: {sorted(missing)}")
        return 1
    if len(supported) != 23:
        print(f"x expected 23 supported types; got {len(supported)}")
        return 1
    print(f"  ok: all 23 file types supported")

    print("-- 6. NEGATIVE: use-case overrides for legal/policy/compliance --")
    # Per operator spec: legal/policy/compliance docs use clause-level
    # chunking with tighter overlap. Drill enforces this.
    for use in ("legal", "policy", "compliance"):
        s = mod.choose(file_type="pdf", use_case=use)
        if "clause" not in s.strategy_name and "hierarchical" not in s.strategy_name:
            print(f"x use_case={use!r} must yield hierarchical/clause strategy; got {s.strategy_name!r}")
            return 1
        if s.overlap_percent < 20:
            print(f"x use_case={use!r} must increase overlap (≥20); got {s.overlap_percent}")
            return 1
    print("  ok: legal/policy/compliance → hierarchical clause + tighter overlap")

    print("-- 7. NEGATIVE: cost/accuracy modulation actually changes chunk size --")
    # high accuracy shrinks chunks; low cost grows them.
    base = mod.choose(file_type="pdf")
    high_acc = mod.choose(file_type="pdf", accuracy_priority="high")
    low_cost = mod.choose(file_type="pdf", cost_priority="low")
    if high_acc.chunk_size_tokens >= base.chunk_size_tokens:
        print(f"x accuracy=high must SHRINK chunk size; base={base.chunk_size_tokens} high_acc={high_acc.chunk_size_tokens}")
        return 1
    if low_cost.chunk_size_tokens <= base.chunk_size_tokens:
        print(f"x cost=low must GROW chunk size; base={base.chunk_size_tokens} low_cost={low_cost.chunk_size_tokens}")
        return 1
    print(f"  ok: modulation works (base={base.chunk_size_tokens} high_acc={high_acc.chunk_size_tokens} low_cost={low_cost.chunk_size_tokens})")

    print("-- 8. POSITIVE: ChunkingStrategy schema matches operator's recommended JSON --")
    s = mod.choose(file_type="pdf", use_case="policy")
    d = s.as_dict()
    # Operator's schema: file_type + use_case + strategy + chunk_size_tokens
    # + overlap_percent + metadata_fields + quality_checks
    for required in ("strategy_name", "file_type", "use_case",
                     "chunk_size_tokens", "overlap_percent",
                     "metadata_fields", "quality_checks", "rationale"):
        if required not in d:
            print(f"x ChunkingStrategy missing field: {required}")
            return 1
    if not isinstance(d["metadata_fields"], list) or len(d["metadata_fields"]) < 2:
        print(f"x metadata_fields must be non-trivial list; got {d['metadata_fields']}")
        return 1
    if not isinstance(d["quality_checks"], list) or len(d["quality_checks"]) < 3:
        print(f"x quality_checks must be non-trivial list; got {d['quality_checks']}")
        return 1
    # status() reports stage + Stage-2 path
    st = mod.status()
    if st.get("stage") != 1:
        print(f"x status.stage must be 1; got {st.get('stage')}")
        return 1
    if "Stage-2" not in st["next_stage"]:
        print("x status.next_stage must reference Stage-2 wiring")
        return 1
    if "saga" not in st["next_stage"].lower() and "ingestion" not in st["next_stage"].lower():
        print("x status.next_stage must mention saga/ingestion (Stage-2 wiring site)")
        return 1
    print("  ok: schema matches operator JSON; status reports Stage-2 path")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
