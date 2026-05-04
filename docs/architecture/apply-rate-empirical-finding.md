# Apply-Rate Empirical Finding — 2026-05-03

> Per §55.3 outcome contract. The deferred empirical test ran on 2026-05-03
> and produced diagnostic data that locates the actual Tier 1 blocker.

## The signal

**Apply rate: 0 / 8 = 0.0%** over the prior council batch.

Surfaced in three places after this session's work:
- `bash scripts/run.sh status` → "0/8 applied"
- `bash scripts/run.sh paperclip` → `honesty_signal: "0/8 applied — apply_rate 0.0%"`
- `/admin/paperclip` → red badge with apply rate as headline metric

### Caveat — current scan is too clean to retest live

Commit `b208d3d` (lint cleanup, 25 files modified) closed 85 ruff issues
manually. A fresh `~/.claude/scripts/issue_scanner.py` produces only 3
pending entries, of which 2 are stale autofix references (the file is
already ruff-clean) and 1 is a human-review item (S110 / E722 class).

So this finding is **historical-empirical, not live-empirical** —
diagnostics from real past failures, but the engine has no comparable
load to reproduce on right now. To regenerate live load, deliberately
introduce a fixable issue (e.g. add an unused import to a known file)
and rerun the daemon. That's an exercise for the verification step
of the Tier 1.3.b fix below.

## The diagnostic breakdown

Reading `.loop/agent_task_board_apply.jsonl` for all 8 rejected attempts:

| # | Failure mode | Count | Root cause |
|---|--------------|-------|-----------|
| 1 | `no clean unified diff in author output` | 3 | Pydantic schema validates JSON structure but NOT patch-validity |
| 2 | `git apply --check`: wrong file path | 2 | Author writes `agent-orchestrator-svc/app/research.py` instead of `services/agent-orchestrator-svc/app/research.py` |
| 3 | `git apply --check`: corrupt patch | 2 | Line offsets in `@@` headers are wrong |
| 4 | `git apply --check`: patch failed | 1 | Line content doesn't match working tree |

## Why §55 Tier 1.1 (Pydantic schema) wasn't sufficient

The CouncilProposal schema validates:
- `rule_code` matches a known rule
- `unified_diff` is a non-empty string
- `confidence` is in [0, 1]
- `summary` is present

But it does **NOT** validate:
- The diff actually applies to the working tree (`git apply --check`)
- File paths in the diff resolve to real files in the repo
- `@@` line offsets match the source

That's why structure-valid garbage passes schema and falls over at apply time.

## The Tier 1.3.b fix (highest-leverage)

Add a `git apply --check` pre-flight to the council acceptance gate:

```python
# scripts/local_council.py — after schema validation, before audit row
def _verify_diff_applies(diff: str, repo: Path) -> tuple[bool, str]:
    """Pre-flight: does this unified diff apply cleanly?
    Returns (ok, error_message). Does NOT mutate the working tree —
    `git apply --check` is read-only.
    """
    proc = subprocess.run(
        ["git", "apply", "--check"],
        input=diff, cwd=repo, capture_output=True, text=True, timeout=10,
    )
    return (proc.returncode == 0, proc.stderr.strip()[:200])
```

Wire it in the council's per-role validation step. If it fails:
- Log the actual git error to the audit row (operator-readable)
- Trigger a retry with a corrected prompt that includes:
  - Full path from repo root (not relative)
  - The actual ±5 lines around the target line (so offsets are correct)
- Cap retries at 2 — beyond that, route to human-review

## Why this is the right Tier 1 next step

| Alternative | Effort | Coverage of 8 failures |
|-------------|--------|------------------------|
| Tier 2.1 verification loop | 8 hr | catches all 8 (post-apply revert) |
| **Tier 1.3.b apply-check pre-flight** | **2 hr** | **catches 5/8 (path + offset + match)** |
| Tier 3.1 LoRA fine-tune | 25 hr | catches 3/8 (clean-diff issue) |

Tier 1.3.b is the **best ROI** per hour: 2 hours → 62.5% of failures eliminated.

## The remaining 3/8 (clean-diff issue)

The "no clean unified diff" failures happen when Author writes its diff
inside markdown fences but the closing fence is missing OR tokenizer
artifacts (extra spaces in `@@` headers) corrupt parsing. These need:

- Stricter diff extraction regex (require both opening and closing fence)
- OR: Pydantic field validator that calls `git apply --check` directly
  (would convert this into a schema error, recoverable via retry)

That second option is cleaner — it makes "applies cleanly" part of the
schema contract per §55 Tier 1.1's intent.

## Next iteration — locked

| Task | Effort | Outcome |
|------|--------|---------|
| Add `_verify_diff_applies()` helper | 30 min | reusable across roles |
| Wire into AUTHOR validation step | 30 min | rejects un-applicable diffs at schema time |
| Add Pydantic field validator that runs `git apply --check` | 30 min | "applies cleanly" becomes schema-level invariant |
| Drill: synthetic-bad-diff → schema rejects with actionable error | 30 min | locks the contract |

## Composes with

- `scripts/local_council.py` — author/reviewer/advisor council loop the apply-rate measures
- `scripts/empirical_apply_test.py` — operator harness that produces the live retest numbers
- `scripts/paperclip_manager.py` — surfaces apply rate on the agent_task_board
- `scripts/autonomous_fix_daemon.py` — the loop being measured
- `mcp/tests/drill_apply_check_preflight.py` — locks Tier 1.3.b synthetic 8/8 outcome
- `mcp/tests/drill_empirical_apply_test.py` — locks the harness contract
- `docs/architecture/full-stack-architecture.md` — full system map this finding contributes to
- §43 — drill discipline; this finding has its own drill
- §52 — brutal tool review row 1 (CouncilProposal correctness)
- §55.2 Tier 1.3 — adaptive context (per-rule strategy + per-failure retry)
- §55.3 — apply rate as the outcome contract

## The brutal rule, restated

> Schema-as-contract must include "this output actually works." For a
> diff, "works" means `git apply --check` returns 0. For a SQL query,
> it means EXPLAIN doesn't error. For a function call, it means the
> arguments match the signature. Without an *executes-cleanly* check
> at validation time, the schema is just spell-check.
