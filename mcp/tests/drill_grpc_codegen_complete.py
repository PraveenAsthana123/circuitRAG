# RESOURCES: readonly
"""
Drill: gRPC codegen artifacts present for all 6 services.

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §45.4 (no checkbox
flips without code), §47 (architecture: gRPC service-to-service via
proto contracts).

Architecture matrix listed API Gateway / gRPC service-to-service as
⚠️ partial 'protos not codegen'd yet'. Empirical: 4 of 6 service
domains had Python codegen (common/identity/inference/retrieval); the
2 newer ones (paperclip, openclaw) had .proto files only. Iter-40
runs grpcio-tools to fill the gap.

Locks (positive):
  L1. All 6 service domains have a .proto file
  L2. All 6 service domains have a *_pb2.py + *_pb2_grpc.py codegen
      pair (Python message + grpc stub)
  L3. Each codegen dir has __init__.py (importable as a package)

Locks (negative — ≥3 per §43):
  N1. No .proto file is OLDER than its codegen siblings (would mean
      the codegen is stale w.r.t. the contract — drill catches drift)
  N2. No codegen file imports beyond grpc, protobuf, or its sibling
      pb2 module (a leak from generated code into runtime code is a
      code-smell that breaks the proto-as-contract boundary)
  N3. The gen-proto.sh script exists + is documented (operator can
      regenerate without operator-help-from-Slack)
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROTO_DIR = REPO / "proto"
GEN_SCRIPT = REPO / "scripts" / "gen-proto.sh"

EXPECTED_DOMAINS = (
    "common",
    "identity",
    "inference",
    "openclaw",
    "paperclip",
    "retrieval",
)

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


def main() -> int:
    if not PROTO_DIR.exists():
        fail(f"proto/ directory missing at {PROTO_DIR.relative_to(REPO)}")

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: all 6 domains have a .proto file
    # ------------------------------------------------------------------
    step("1. all 6 service domains have a .proto contract")
    for d in EXPECTED_DOMAINS:
        proto = PROTO_DIR / d / "v1" / f"{d}.proto"
        if not proto.exists():
            fail(f"missing proto: {proto.relative_to(REPO)}")
    ok(f"all {len(EXPECTED_DOMAINS)} domains have v1/<domain>.proto")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: all 6 domains have pb2 + pb2_grpc codegen
    # ------------------------------------------------------------------
    step("2. all 6 domains have *_pb2.py + *_pb2_grpc.py codegen")
    missing: list[str] = []
    for d in EXPECTED_DOMAINS:
        v1 = PROTO_DIR / d / "v1"
        pb2 = v1 / f"{d}_pb2.py"
        pb2_grpc = v1 / f"{d}_pb2_grpc.py"
        if not pb2.exists():
            missing.append(str(pb2.relative_to(REPO)))
        if not pb2_grpc.exists():
            missing.append(str(pb2_grpc.relative_to(REPO)))
    if missing:
        fail(
            f"{len(missing)} codegen artifact(s) missing: {missing[:3]}. "
            "Run scripts/gen-proto.sh to regenerate."
        )
    ok(f"all {len(EXPECTED_DOMAINS) * 2} codegen artifacts present "
       f"({len(EXPECTED_DOMAINS)} pb2 + {len(EXPECTED_DOMAINS)} pb2_grpc)")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: each codegen dir has __init__.py
    # ------------------------------------------------------------------
    step("3. each codegen dir has __init__.py (importable as package)")
    for d in EXPECTED_DOMAINS:
        v1 = PROTO_DIR / d / "v1"
        init = v1 / "__init__.py"
        if not init.exists():
            fail(f"missing {init.relative_to(REPO)} — package import broken")
    ok(f"all {len(EXPECTED_DOMAINS)} codegen dirs have __init__.py")

    # ------------------------------------------------------------------
    # Step 4 — NEGATIVE: no .proto is newer than its codegen siblings
    # ------------------------------------------------------------------
    step("4. NEGATIVE: no .proto is newer than its codegen (stale check)")
    stale: list[str] = []
    for d in EXPECTED_DOMAINS:
        v1 = PROTO_DIR / d / "v1"
        proto = v1 / f"{d}.proto"
        pb2 = v1 / f"{d}_pb2.py"
        pb2_grpc = v1 / f"{d}_pb2_grpc.py"
        proto_mtime = proto.stat().st_mtime
        for sibling in (pb2, pb2_grpc):
            if sibling.stat().st_mtime < proto_mtime:
                stale.append(
                    f"{sibling.relative_to(REPO)} "
                    f"(older than {proto.name})"
                )
    if stale:
        fail(
            f"{len(stale)} codegen file(s) older than their .proto: {stale[:3]}. "
            "Run scripts/gen-proto.sh to refresh."
        )
    ok("no stale codegen (all artifacts ≥ proto mtime)")

    # ------------------------------------------------------------------
    # Step 5 — NEGATIVE: codegen files have no runtime-side imports
    # ------------------------------------------------------------------
    step("5. NEGATIVE: codegen has no runtime-side imports (proto contract)")
    # Generated files should only import from grpc, google.protobuf, and
    # their sibling pb2 module. A runtime import (services/* or libs/py/*)
    # would mean someone hand-edited generated code — a code-smell.
    forbidden = ("from services.", "from libs.", "import services", "import libs.")
    leaks: list[str] = []
    for d in EXPECTED_DOMAINS:
        v1 = PROTO_DIR / d / "v1"
        for f in (v1 / f"{d}_pb2.py", v1 / f"{d}_pb2_grpc.py"):
            content = f.read_text(encoding="utf-8")
            for pat in forbidden:
                if pat in content:
                    leaks.append(f"{f.relative_to(REPO)}: {pat!r}")
    if leaks:
        fail(
            f"codegen has runtime-side imports (hand-edit smell): {leaks[:3]}"
        )
    ok("no runtime-side imports in codegen (proto contract preserved)")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: gen-proto.sh exists + is documented
    # ------------------------------------------------------------------
    step("6. NEGATIVE: scripts/gen-proto.sh exists + is operator-readable")
    if not GEN_SCRIPT.exists():
        fail(f"gen-proto.sh missing at {GEN_SCRIPT.relative_to(REPO)}")
    src = GEN_SCRIPT.read_text(encoding="utf-8")
    if "Install:" not in src and "install" not in src.lower():
        fail("gen-proto.sh missing install instructions for tooling")
    if "grpcio-tools" not in src or "protoc-gen-go" not in src:
        fail("gen-proto.sh doesn't mention both Python + Go tooling")
    ok("gen-proto.sh exists + documents Python+Go tooling install")

    print(f"\n{GREEN}{BOLD}ALL 6 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
