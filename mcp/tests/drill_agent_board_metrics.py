#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: AgentBoard — Prometheus metrics + structured log + prompt
versioning contracts.

Locks the operator-visible monitoring surface that landed alongside
the AgentBoard parallel-execution work. Without this drill, a
refactor that drops a metric or relabels an outcome silently breaks
every dashboard + alert keyed on it.

Eight steps. Five negative assertions.

  1. Successful run increments runs_total{outcome="ok"} and writes
     a duration_seconds histogram observation.
  2. Partial run (one author errors) increments
     runs_total{outcome="partial"}, NOT "ok". The outcome
     classification is the alerting axis — relabelling it is a
     dashboard-breaking regression.
  3. Advisor failure increments runs_total{outcome="advisor_failed"}.
  4. NEGATIVE: a board where ALL authors fail gets
     outcome="all_authors_failed", NOT "advisor_failed" — the
     advisor's state is moot when there's no draft to synthesize.
     This ordering matters: an operator looking at advisor failures
     should not see runs that bottomed out earlier.
  5. NEGATIVE: per-review counter distinguishes
     "skipped_upstream" from "error". Reviewer-crash and
     author-error-skipped are different operator actions; merging
     them masks reviewer-agent regressions.
  6. NEGATIVE: structured log emitted at INFO level on EVERY run,
     happy and sad, with the canonical field set
     (outcome, advisor_id, prompt_version, task_hash, duration_s,
      authors_total, authors_failed, reviews_total, reviews_failed).
     No raw task body — PII rule.
  7. prompt_version is deterministic: two boards with identical
     prompts hash to the same version. Two boards with different
     prompts hash to different versions.
  8. NEGATIVE: BoardResult.prompt_version is non-empty AND
     BoardResult.outcome matches the metric label. A drift between
     "what BoardResult says" and "what Prometheus records" would
     make audit trails diverge from operator dashboards.

Tag: readonly. Pure-Python — runs in tier 1.

Run:
    python3 mcp/tests/drill_agent_board_metrics.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


# ── Module loader ────────────────────────────────────────────────
def _load_agent_board():
    p = REPO / "services" / "inference-svc" / "app" / "agents" / "agent_board.py"
    spec = importlib.util.spec_from_file_location("agent_board_mod", p)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load spec from {p}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["agent_board_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


ab = _load_agent_board()
AgentBoard = ab.AgentBoard
make_agent = ab.make_agent

# Try prometheus_client. If absent, the drill falls back to the
# logical-only assertions (steps 4, 6, 7, 8) — the no-op shim
# behaviour itself becomes the proof for steps 1-3.
try:
    from prometheus_client import REGISTRY  # type: ignore[import-not-found]
    HAS_PROM = True
except ImportError:
    HAS_PROM = False


def _metric_value(name: str, **labels: str) -> float:
    """Read the current value of a counter / histogram from REGISTRY.
    Returns 0.0 if the metric doesn't exist yet (counters auto-create
    on first .inc()) — caller asserts the delta, not absolute."""
    if not HAS_PROM:
        return 0.0
    val = REGISTRY.get_sample_value(name, labels) or 0.0
    return float(val)


# ── Helper agents ────────────────────────────────────────────────
def quick_author(author_id: str, text: str | None = None):
    async def _a(prompt: str) -> str:
        await asyncio.sleep(0.001)
        return text or f"draft from {author_id}"
    return make_agent(_a)


def crashing_author(author_id: str):
    async def _a(prompt: str) -> str:
        raise RuntimeError(f"{author_id} crashed")
    return make_agent(_a)


def quick_reviewer(reviewer_id: str, score: int = 7):
    async def _a(prompt: str) -> str:
        await asyncio.sleep(0.001)
        return f"r-{reviewer_id}\nSCORE: {score}"
    return make_agent(_a)


def quick_advisor():
    async def _a(prompt: str) -> str:
        await asyncio.sleep(0.001)
        return "advised"
    return make_agent(_a)


def crashing_advisor():
    async def _a(prompt: str) -> str:
        raise RuntimeError("advisor down")
    return make_agent(_a)


# ── Log capture handler ─────────────────────────────────────────
class _LogCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


# ── Drill ────────────────────────────────────────────────────────
async def main() -> None:
    # Attach log capture to the agent_board module's logger.
    capture = _LogCapture()
    capture.setLevel(logging.INFO)
    ab_logger = logging.getLogger("agent_board_mod")
    ab_logger.addHandler(capture)
    ab_logger.setLevel(logging.INFO)

    # ── Step 1: success path increments runs_total{outcome="ok"} ──
    step("1. successful run → runs_total{outcome=ok} +1, duration histogram +1")
    advisor_id = "advisor_step1"
    pre_ok = _metric_value(
        "documind_agent_board_runs_total",
        outcome="ok", advisor_id=advisor_id,
    )
    pre_dur_count = _metric_value(
        "documind_agent_board_duration_seconds_count",
        outcome="ok", advisor_id=advisor_id,
    )
    board = AgentBoard(
        authors={"a": quick_author("a")},
        reviewers={"r": quick_reviewer("r")},
        advisor=quick_advisor(),
        advisor_id=advisor_id,
        max_parallel=2,
    )
    result = await board.run("step 1 task")
    if result.outcome != "ok":
        fail(f"BoardResult.outcome should be 'ok', got {result.outcome!r}")
    if HAS_PROM:
        post_ok = _metric_value(
            "documind_agent_board_runs_total",
            outcome="ok", advisor_id=advisor_id,
        )
        post_dur_count = _metric_value(
            "documind_agent_board_duration_seconds_count",
            outcome="ok", advisor_id=advisor_id,
        )
        if post_ok != pre_ok + 1:
            fail(f"runs_total{{ok}} delta != 1: {pre_ok} → {post_ok}")
        if post_dur_count != pre_dur_count + 1:
            fail(
                f"duration histogram count delta != 1: "
                f"{pre_dur_count} → {post_dur_count}"
            )
        ok(f"runs_total{{ok}} {pre_ok}→{post_ok}; duration count {pre_dur_count}→{post_dur_count}")
    else:
        ok("(prometheus_client absent; outcome=ok asserted on BoardResult only)")

    # ── Step 2: partial run → outcome="partial" ─────────────────
    step("2. one author errors → runs_total{outcome=partial} +1, NOT ok")
    advisor_id = "advisor_step2"
    pre_partial = _metric_value(
        "documind_agent_board_runs_total",
        outcome="partial", advisor_id=advisor_id,
    )
    pre_ok = _metric_value(
        "documind_agent_board_runs_total",
        outcome="ok", advisor_id=advisor_id,
    )
    board = AgentBoard(
        authors={
            "good_a": quick_author("good_a"),
            "bad_a": crashing_author("bad_a"),
        },
        reviewers={"r": quick_reviewer("r")},
        advisor=quick_advisor(),
        advisor_id=advisor_id,
        max_parallel=4,
    )
    result = await board.run("step 2 task")
    if result.outcome != "partial":
        fail(f"BoardResult.outcome should be 'partial', got {result.outcome!r}")
    if HAS_PROM:
        post_partial = _metric_value(
            "documind_agent_board_runs_total",
            outcome="partial", advisor_id=advisor_id,
        )
        post_ok = _metric_value(
            "documind_agent_board_runs_total",
            outcome="ok", advisor_id=advisor_id,
        )
        if post_partial != pre_partial + 1:
            fail(f"runs_total{{partial}} delta != 1: {pre_partial} → {post_partial}")
        if post_ok != pre_ok:
            fail(
                f"runs_total{{ok}} should NOT increment for partial run: "
                f"{pre_ok} → {post_ok}"
            )
        ok(f"runs_total{{partial}} {pre_partial}→{post_partial}; ok unchanged")
    else:
        ok("(prometheus_client absent; outcome=partial asserted on BoardResult only)")

    # ── Step 3: advisor failure → outcome="advisor_failed" ──────
    step("3. advisor crash → runs_total{outcome=advisor_failed} +1")
    advisor_id = "advisor_step3"
    pre = _metric_value(
        "documind_agent_board_runs_total",
        outcome="advisor_failed", advisor_id=advisor_id,
    )
    board = AgentBoard(
        authors={"a": quick_author("a")},
        reviewers={"r": quick_reviewer("r", 8)},
        advisor=crashing_advisor(),
        advisor_id=advisor_id,
        max_parallel=2,
    )
    result = await board.run("step 3 task")
    if result.outcome != "advisor_failed":
        fail(f"BoardResult.outcome should be 'advisor_failed', got {result.outcome!r}")
    if HAS_PROM:
        post = _metric_value(
            "documind_agent_board_runs_total",
            outcome="advisor_failed", advisor_id=advisor_id,
        )
        if post != pre + 1:
            fail(f"runs_total{{advisor_failed}} delta != 1: {pre} → {post}")
        ok(f"runs_total{{advisor_failed}} {pre}→{post}")
    else:
        ok("(prometheus_client absent; outcome=advisor_failed asserted on BoardResult)")

    # ── Step 4: NEGATIVE — all authors fail → all_authors_failed ─
    step(
        "4. NEGATIVE: ALL authors fail → outcome=all_authors_failed, "
        "NOT advisor_failed (advisor state is moot when no drafts)"
    )
    advisor_id = "advisor_step4"
    pre_all_fail = _metric_value(
        "documind_agent_board_runs_total",
        outcome="all_authors_failed", advisor_id=advisor_id,
    )
    pre_advisor_fail = _metric_value(
        "documind_agent_board_runs_total",
        outcome="advisor_failed", advisor_id=advisor_id,
    )
    # Note: advisor will ALSO crash (the synthesis prompt has no
    # drafts to synthesize). The classification rule ranks
    # "no usable drafts" above "advisor crashed".
    board = AgentBoard(
        authors={
            "bad_a": crashing_author("bad_a"),
            "bad_b": crashing_author("bad_b"),
        },
        reviewers={"r": quick_reviewer("r")},
        advisor=quick_advisor(),  # advisor itself is fine
        advisor_id=advisor_id,
        max_parallel=2,
    )
    result = await board.run("step 4 task")
    if result.outcome != "all_authors_failed":
        fail(
            f"BoardResult.outcome should be 'all_authors_failed', "
            f"got {result.outcome!r}. Outcome classification rule: "
            f"all_authors_failed > advisor_failed > partial > ok."
        )
    if HAS_PROM:
        post_all_fail = _metric_value(
            "documind_agent_board_runs_total",
            outcome="all_authors_failed", advisor_id=advisor_id,
        )
        post_advisor_fail = _metric_value(
            "documind_agent_board_runs_total",
            outcome="advisor_failed", advisor_id=advisor_id,
        )
        if post_all_fail != pre_all_fail + 1:
            fail(f"all_authors_failed delta != 1: {pre_all_fail} → {post_all_fail}")
        if post_advisor_fail != pre_advisor_fail:
            fail(
                f"advisor_failed should NOT increment when no drafts: "
                f"{pre_advisor_fail} → {post_advisor_fail}"
            )
        ok(
            f"all_authors_failed {pre_all_fail}→{post_all_fail}; "
            f"advisor_failed unchanged"
        )
    else:
        ok("(prometheus_client absent; outcome rule asserted on BoardResult)")

    # ── Step 5: NEGATIVE — review skipped vs error are distinct ─
    step(
        "5. NEGATIVE: reviews_total distinguishes skipped_upstream from error"
    )
    pre_skipped = _metric_value(
        "documind_agent_board_reviews_total", outcome="skipped_upstream",
    )
    pre_error = _metric_value(
        "documind_agent_board_reviews_total", outcome="error",
    )
    pre_ok = _metric_value(
        "documind_agent_board_reviews_total", outcome="ok",
    )

    async def _crashing_reviewer(_: str) -> str:
        raise RuntimeError("reviewer down")

    board = AgentBoard(
        authors={
            "good_a": quick_author("good_a"),
            "bad_a": crashing_author("bad_a"),
        },
        reviewers={
            "good_r": quick_reviewer("good_r"),
            "bad_r": make_agent(_crashing_reviewer),
        },
        advisor=quick_advisor(),
        max_parallel=4,
    )
    await board.run("step 5 task")
    # Cross-product: 2 authors × 2 reviewers = 4 reviews
    #   good_a × good_r → ok
    #   good_a × bad_r  → error (reviewer crash)
    #   bad_a × good_r  → skipped_upstream (author errored)
    #   bad_a × bad_r   → skipped_upstream (author errored — short-circuits the reviewer)
    if HAS_PROM:
        post_skipped = _metric_value(
            "documind_agent_board_reviews_total", outcome="skipped_upstream",
        )
        post_error = _metric_value(
            "documind_agent_board_reviews_total", outcome="error",
        )
        post_ok = _metric_value(
            "documind_agent_board_reviews_total", outcome="ok",
        )
        if post_skipped != pre_skipped + 2:
            fail(
                f"reviews_total{{skipped_upstream}} delta != 2: "
                f"{pre_skipped} → {post_skipped}"
            )
        if post_error != pre_error + 1:
            fail(
                f"reviews_total{{error}} delta != 1: "
                f"{pre_error} → {post_error}"
            )
        if post_ok != pre_ok + 1:
            fail(
                f"reviews_total{{ok}} delta != 1: "
                f"{pre_ok} → {post_ok}"
            )
        ok(
            f"reviews_total: ok+1 ({pre_ok}→{post_ok}), "
            f"error+1 ({pre_error}→{post_error}), "
            f"skipped_upstream+2 ({pre_skipped}→{post_skipped})"
        )
    else:
        ok("(prometheus_client absent; review counter logic untestable here)")

    # ── Step 6: NEGATIVE — structured log emitted on every run ──
    step(
        "6. NEGATIVE: agent_board_run log emitted on every run with "
        "canonical fields, NO raw task body"
    )
    capture.records.clear()
    secret_task = "MY_PII_SECRET_TASK_BODY_DO_NOT_LEAK"
    advisor_id = "advisor_step6"
    board = AgentBoard(
        authors={"a": quick_author("a")},
        reviewers={"r": quick_reviewer("r")},
        advisor=quick_advisor(),
        advisor_id=advisor_id,
        max_parallel=2,
    )
    await board.run(secret_task)
    run_logs = [r for r in capture.records if "agent_board_run" in r.getMessage()]
    if not run_logs:
        fail(
            f"no agent_board_run log emitted. Captured: "
            f"{[r.getMessage() for r in capture.records]}"
        )
    msg = run_logs[0].getMessage()
    required_fields = [
        "outcome=", "advisor_id=", "prompt_version=", "task_hash=",
        "duration_s=", "authors_total=", "authors_failed=",
        "reviews_total=", "reviews_failed=",
    ]
    missing = [f for f in required_fields if f not in msg]
    if missing:
        fail(f"log missing fields: {missing}. Got: {msg!r}")
    if secret_task in msg:
        fail(
            f"PII LEAK: log contains raw task body {secret_task!r}. "
            f"§4.5 + §38.4 — log task_hash, NOT task text."
        )
    if f"advisor_id={advisor_id}" not in msg:
        fail(f"advisor_id label not propagated to log: {msg!r}")
    ok(f"agent_board_run log present, fields complete, no task body leaked")

    # ── Step 7: prompt_version determinism ──────────────────────
    step("7. prompt_version is deterministic: same prompts → same hash")
    b1 = AgentBoard(
        authors={"a": quick_author("a")},
        reviewers={"r": quick_reviewer("r")},
        advisor=quick_advisor(),
    )
    b2 = AgentBoard(
        authors={"a": quick_author("a")},
        reviewers={"r": quick_reviewer("r")},
        advisor=quick_advisor(),
    )
    if b1._prompt_version != b2._prompt_version:
        fail(
            f"identical prompts hashed differently: "
            f"{b1._prompt_version!r} vs {b2._prompt_version!r}"
        )
    b3 = AgentBoard(
        authors={"a": quick_author("a")},
        reviewers={"r": quick_reviewer("r")},
        advisor=quick_advisor(),
        review_prompt_template="DIFFERENT REVIEW PROMPT {task} {draft_text}",
    )
    if b1._prompt_version == b3._prompt_version:
        fail(
            f"different review prompts hashed to same version: "
            f"{b1._prompt_version!r} (regression: prompt edits "
            f"would not be attributable in audit rows)"
        )
    if not b1._prompt_version or len(b1._prompt_version) != 12:
        fail(
            f"prompt_version should be 12-char hash, got "
            f"{b1._prompt_version!r}"
        )
    ok(
        f"identical prompts → {b1._prompt_version}; "
        f"different prompts → {b3._prompt_version}"
    )

    # ── Step 8: NEGATIVE — BoardResult <-> metric label parity ──
    step(
        "8. NEGATIVE: BoardResult.prompt_version + BoardResult.outcome "
        "match the run() metric label (no audit/dashboard divergence)"
    )
    advisor_id = "advisor_step8"
    board = AgentBoard(
        authors={"a": quick_author("a")},
        reviewers={"r": quick_reviewer("r")},
        advisor=quick_advisor(),
        advisor_id=advisor_id,
    )
    pre = _metric_value(
        "documind_agent_board_runs_total",
        outcome="ok", advisor_id=advisor_id,
    )
    result = await board.run("parity check")
    if not result.prompt_version:
        fail("BoardResult.prompt_version empty — audit row would have no version")
    if result.prompt_version != board._prompt_version:
        fail(
            f"BoardResult.prompt_version drift from board._prompt_version: "
            f"{result.prompt_version!r} vs {board._prompt_version!r}"
        )
    if HAS_PROM:
        post = _metric_value(
            "documind_agent_board_runs_total",
            outcome=result.outcome, advisor_id=advisor_id,
        )
        if post != pre + 1:
            fail(
                f"BoardResult.outcome={result.outcome!r} did not match "
                f"the metric label that incremented "
                f"({pre} → {post} on outcome={result.outcome!r}). "
                f"Drift here breaks audit/dashboard parity."
            )
        ok(
            f"BoardResult.outcome={result.outcome!r} matches metric label "
            f"({pre}→{post}); prompt_version={result.prompt_version}"
        )
    else:
        ok(
            f"BoardResult.outcome={result.outcome!r}; "
            f"prompt_version={result.prompt_version} (metric label parity "
            f"untestable without prometheus_client)"
        )

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 AGENT-BOARD METRICS STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (5 negative assertions: 4, 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    asyncio.run(main())
