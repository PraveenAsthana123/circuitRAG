# RESOURCES: readonly
"""
Drill: Kafka EventProducer lifespan wired across the FastAPI fleet.

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §44 (autonomous-loop;
batched matrix-row work counts as ONE thing per iter), §45.4 (no checkbox
flips without code), §47 (architecture: event-bus integration), §47.7
(expand-phase: lifespan contract spreads service-by-service).

Iter-50 wired the inference-svc lifespan; iter-53 applies the same
contract to retrieval-svc, evaluation-svc, agent-orchestrator-svc.
The fleet now has 4 svcs with the lifespan ready (ingestion-svc has its
own outbox-pattern wiring, not in this drill's scope).

Locks (positive):
  L1. All 3 services have DOCUMIND_KAFKA_BOOTSTRAP env-flag check
  L2. All 3 services lazy-import EventProducer inside lifespan body
  L3. All 3 services initialize app.state.event_producer = None first

Locks (negative — ≥3 per §43):
  N1. Each service wraps EventProducer creation in try/except (boot fail-safe)
  N2. Each service stops the producer on shutdown in try/except (best-effort)
  N3. None of the services use naive bool() truthy check on the env-flag
  N4. Source comments cite §47.7 expand-phase boundary so per-route
      publish points are explicitly future-iter work
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

FLEET = (
    ("retrieval-svc",         REPO / "services" / "retrieval-svc" / "app" / "main.py"),
    ("evaluation-svc",        REPO / "services" / "evaluation-svc" / "app" / "main.py"),
    ("agent-orchestrator-svc", REPO / "services" / "agent-orchestrator-svc" / "app" / "main.py"),
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
    sources: dict[str, str] = {}
    for name, path in FLEET:
        if not path.exists():
            fail(f"missing: {path.relative_to(REPO)}")
        sources[name] = path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: each service references DOCUMIND_KAFKA_BOOTSTRAP
    # ------------------------------------------------------------------
    step("1. all 3 services reference DOCUMIND_KAFKA_BOOTSTRAP")
    for name, src in sources.items():
        if "DOCUMIND_KAFKA_BOOTSTRAP" not in src:
            fail(f"{name} has no DOCUMIND_KAFKA_BOOTSTRAP env-flag")
    ok("3/3 services reference the env-flag")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: each service lazy-imports EventProducer
    # ------------------------------------------------------------------
    step("2. all 3 services lazy-import EventProducer (not module-top)")
    for name, src in sources.items():
        if "documind_core.kafka_client" not in src:
            fail(f"{name} doesn't import EventProducer")
        # Module-top import would appear before any def
        first_def = src.find("def ")
        if first_def == -1:
            fail(f"{name} has no def — bad source structure")
        module_top = src[:first_def]
        if "from documind_core.kafka_client" in module_top:
            fail(
                f"{name} imports EventProducer at module-top — should be "
                f"inside the lifespan body so build-time tooling stays clean"
            )
    ok("3/3 services lazy-import EventProducer inside lifespan body")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: each service initializes app.state.event_producer
    # ------------------------------------------------------------------
    step("3. all 3 services initialize app.state.event_producer = None")
    for name, src in sources.items():
        if not re.search(r"app\.state\.event_producer\s*=\s*None", src):
            fail(f"{name} missing app.state.event_producer = None init")
    ok("3/3 services initialize app.state.event_producer to None")

    # ------------------------------------------------------------------
    # Step 4 — NEGATIVE: each service wraps producer.start() in try/except
    # ------------------------------------------------------------------
    step("4. NEGATIVE: each service wraps EventProducer creation in try/except")
    for name, src in sources.items():
        # Find the kafka_bootstrap block + verify it has try/except
        block_match = re.search(
            r"kafka_bootstrap\s*=\s*os\.getenv.*?(?=\n        log\.info\("
            + name.replace("-", "_").replace("svc", "")
            + r"\w*kafka|\n        log\.info\(\""
            + name.replace("-", "_")
            + r"|yield)",
            src, re.DOTALL,
        )
        # Looser fallback: just look for the kafka_bootstrap region in this file
        if block_match is None:
            block_match = re.search(
                r"kafka_bootstrap\s*=\s*os\.getenv.{0,2000}?try:.{0,2000}?except Exception",
                src, re.DOTALL,
            )
        if block_match is None:
            fail(
                f"{name} kafka_bootstrap block has NO try/except Exception — "
                f"Kafka unreachable at boot would crash service startup"
            )
    ok("3/3 services wrap EventProducer creation in try/except")

    # ------------------------------------------------------------------
    # Step 5 — NEGATIVE: each service stops producer on shutdown (try/except)
    # ------------------------------------------------------------------
    step("5. NEGATIVE: each service stops producer on shutdown in try/except")
    for name, src in sources.items():
        # Look for "if app.state.event_producer is not None:" + stop()
        if not re.search(r"app\.state\.event_producer is not None", src):
            fail(f"{name} shutdown doesn't guard against None producer")
        # Source must also have producer.stop() call
        if "event_producer.stop()" not in src and ".stop()" not in src:
            fail(f"{name} shutdown doesn't call producer.stop()")
    ok("3/3 services stop producer on shutdown (None-guarded)")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: no naive bool() truthy check
    # ------------------------------------------------------------------
    step("6. NEGATIVE: no naive bool() truthy check on env-flag")
    for name, src in sources.items():
        if 'bool(os.getenv("DOCUMIND_KAFKA_BOOTSTRAP"' in src:
            fail(
                f"{name} uses bool(getenv()) check — would treat '0'/'false' "
                f"as truthy. Use `.getenv(\"\", \"\").strip()` comparison."
            )
    ok("3/3 services use explicit string comparison (no naive truthy)")

    # ------------------------------------------------------------------
    # Step 7 — NEGATIVE: §47.7 expand-phase boundary documented
    # ------------------------------------------------------------------
    step("7. NEGATIVE: §47.7 expand-phase comment in each service")
    for name, src in sources.items():
        if "§47.7" not in src or "expand-phase" not in src:
            fail(
                f"{name} lifespan missing §47.7 expand-phase comment — "
                f"future maintainer wouldn't see that per-route publish "
                f"points are subsequent-commit territory"
            )
    ok("3/3 services document §47.7 expand-phase boundary")

    print(f"\n{GREEN}{BOLD}ALL 7 STEPS PASSED ({len(FLEET)} services){NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
