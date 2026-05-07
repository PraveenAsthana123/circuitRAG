# RESOURCES: readonly
"""
Drill: inference-svc Kafka EventProducer lifespan wiring.

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §44 (autonomous
loop one-thing-per-iter), §45.4 (no checkbox flips without code),
§47 (architecture: observability + decision audit at the event-bus
boundary), §47.7 (expand-phase: lifespan wiring ships first; per-route
publish points wire on opt-in basis), §51 (forensic substrate).

Architecture matrix listed Event Bus / aiokafka producer/consumer
wiring as ⚠️ partial 'infra up; some services not yet publishing'.
inference-svc had ZERO Kafka wiring. Iter-50 ships the lifespan:

  * EventProducer lazily-imported (no hard dep at module-load)
  * Opt-in via DOCUMIND_KAFKA_BOOTSTRAP — empty/unset → producer=None
  * Boot-time Kafka unreachable → log + None (service still starts)
  * On shutdown, producer.stop() in try/except (best-effort)
  * app.state.event_producer surfaces the handle to routers

Locks (positive):
  L1. Source mentions DOCUMIND_KAFKA_BOOTSTRAP env-flag
  L2. Source imports EventProducer (lazy, inside the lifespan body
      so it doesn't hard-fail when documind_core is missing during
      build-time tooling)
  L3. app.state.event_producer is initialized (None or producer)

Locks (negative — ≥3 per §43):
  N1. Producer creation wrapped in try/except — Kafka unreachable
      at boot must NOT crash inference-svc startup (per §47 fail-safe)
  N2. Shutdown path includes producer.stop() guarded by try/except
      so a Kafka-down-at-shutdown doesn't mask other shutdown errors
  N3. The default state (env-var unset) is producer=None — the
      operator must explicitly opt in. Implicit truthy interpretation
      (`bool(getenv(...))`) would treat `0` / `false` as on.
  N4. Source documents the §47.7 expand-phase boundary — lifespan
      ships now; per-route publish points are subsequent commits.
      A future maintainer who adds a publish call without seeing the
      doc would have to read the source comment first.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INFERENCE_MAIN = REPO / "services" / "inference-svc" / "app" / "main.py"

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
    if not INFERENCE_MAIN.exists():
        fail(f"missing: {INFERENCE_MAIN.relative_to(REPO)}")

    src = INFERENCE_MAIN.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: env-flag DOCUMIND_KAFKA_BOOTSTRAP referenced
    # ------------------------------------------------------------------
    step("1. DOCUMIND_KAFKA_BOOTSTRAP env-flag referenced")
    if "DOCUMIND_KAFKA_BOOTSTRAP" not in src:
        fail(
            "inference-svc main.py has no DOCUMIND_KAFKA_BOOTSTRAP — "
            "kafka publishing must be opt-in via env-flag"
        )
    ok("env-flag DOCUMIND_KAFKA_BOOTSTRAP referenced")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: EventProducer imported (lazy)
    # ------------------------------------------------------------------
    step("2. EventProducer imported via documind_core.kafka_client")
    if "documind_core.kafka_client" not in src or "EventProducer" not in src:
        fail("EventProducer import missing")
    # Verify it's a LAZY import inside the lifespan (not module-top)
    # so build-time tooling (mypy / ruff) doesn't choke if kafka_client
    # is missing in a stripped-down environment.
    module_top = src[:src.find("def create_app(")]
    if "from documind_core.kafka_client" in module_top:
        fail(
            "EventProducer imported at module top — should be inside the "
            "lifespan body (lazy) so the service can start without aiokafka "
            "in build/lint contexts"
        )
    ok("EventProducer imported lazily inside lifespan body")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: app.state.event_producer initialized
    # ------------------------------------------------------------------
    step("3. app.state.event_producer initialized (None or producer)")
    if "app.state.event_producer" not in src:
        fail(
            "no app.state.event_producer assignment — routers can't "
            "discover whether kafka is wired"
        )
    # Should be initialized to None FIRST, then conditionally set
    if not re.search(r"app\.state\.event_producer\s*=\s*None", src):
        fail(
            "app.state.event_producer never set to None — fall-through "
            "behavior is unsafe (None means 'kafka off' at the route layer)"
        )
    ok("app.state.event_producer initialized to None; conditionally set")

    # ------------------------------------------------------------------
    # Step 4 — NEGATIVE: producer creation wrapped in try/except
    # ------------------------------------------------------------------
    step("4. NEGATIVE: producer creation wrapped in try/except (boot fail-safe)")
    # Locate the kafka_bootstrap block and verify there's a try/except
    # around the EventProducer().start() call.
    bootstrap_block = re.search(
        r"kafka_bootstrap\s*=\s*os\.getenv.*?(?=\n        log\.info\(\"inference_service_ready)",
        src, re.DOTALL,
    )
    if bootstrap_block is None:
        fail(
            "could not locate kafka_bootstrap block; lifespan wiring "
            "may have refactored — refresh this drill"
        )
    block = bootstrap_block.group(0)
    if "try:" not in block or "except Exception" not in block:
        fail(
            "EventProducer creation NOT wrapped in try/except — "
            "Kafka unreachable at boot would crash inference-svc startup"
        )
    ok("EventProducer creation wrapped in try/except (boot fail-safe)")

    # ------------------------------------------------------------------
    # Step 5 — NEGATIVE: shutdown path stops producer in try/except
    # ------------------------------------------------------------------
    step("5. NEGATIVE: shutdown path stops producer in try/except")
    # Look for the shutdown path: it's after `finally:` and references
    # event_producer.stop().
    shutdown_match = re.search(
        r"finally:\s*\n(.*?)(?=\n    app = FastAPI)",
        src, re.DOTALL,
    )
    if shutdown_match is None:
        fail("could not locate finally: shutdown block")
    shutdown = shutdown_match.group(1)
    if "event_producer" not in shutdown:
        fail("shutdown does NOT call event_producer.stop()")
    if "stop()" not in shutdown:
        fail("shutdown missing producer.stop() invocation")
    # Each try/except in shutdown should pair stop with except — best-effort
    if shutdown.count("try:") < 1 or shutdown.count("except") < 1:
        fail(
            "producer.stop() not wrapped in try/except — Kafka-down at "
            "shutdown would mask other shutdown errors"
        )
    ok("shutdown stops producer with try/except (best-effort)")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: opt-in is .strip() check, not bool()
    # ------------------------------------------------------------------
    step("6. NEGATIVE: opt-in via .strip() check, not naive bool()")
    if 'bool(os.getenv("DOCUMIND_KAFKA_BOOTSTRAP"' in src:
        fail(
            "naive bool(getenv()) check — would treat '0'/'false' as truthy. "
            "Use `os.getenv(\"DOCUMIND_KAFKA_BOOTSTRAP\", \"\").strip()` instead."
        )
    ok("opt-in pattern is explicit (no naive bool truthy check)")

    # ------------------------------------------------------------------
    # Step 7 — NEGATIVE: §47.7 expand-phase boundary documented
    # ------------------------------------------------------------------
    step("7. NEGATIVE: §47.7 expand-phase boundary documented in comment")
    if "§47.7" not in src or "expand-phase" not in src:
        fail(
            "lifespan wiring missing §47.7 expand-phase comment — future "
            "maintainer wouldn't know per-route publish points are "
            "subsequent-commit territory"
        )
    ok("§47.7 expand-phase boundary documented in lifespan comment")

    print(f"\n{GREEN}{BOLD}ALL 7 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
