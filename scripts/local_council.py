"""Local council runner — schema-aware author + critique reviewer + advisor.

Per CLAUDE.md §50 (issue dispatcher) + this iteration's Tier 1 #1
hardening (Pydantic CouncilProposal schema).

WHY THIS EXISTS
===============

The global ~/.claude/scripts/issue_dispatcher.py emits free-text
council output. Empirical session evidence: 0 of 6 attempts produced
applicable diffs. The fix is **schema-as-contract**: AUTHOR must
emit a CouncilProposal-shaped JSON OR be rejected at the validator.

This module replaces the daemon's `run_council()` call to the global
dispatcher with a local runner that:

  1. AUTHOR (deepseek-coder:6.7b-instruct) gets a schema-aware prompt
     with PROMPT_ADDENDUM appended.
  2. AUTHOR's output is parsed via validate_council_proposal() — a
     None result is logged and the issue is escalated.
  3. REVIEWER (codegemma:7b-instruct) reviews ONLY the validated
     proposal (no broken inputs through review).
  4. ADVISOR (codellama:7b-instruct) synthesizes the AUTHOR proposal
     against REVIEWER critique.
  5. Audit row written in the same shape as the dispatcher's output
     so downstream code (task board, daemon) reads it identically.

The global dispatcher stays as a fallback for projects that haven't
adopted the schema; this module is the project-local upgraded path.

USAGE FROM DAEMON
=================

    from scripts.local_council import run_local_council
    proposal = run_local_council(issue_id, REPO)
    if proposal is None:
        # AUTHOR rejected; gate skips apply, escalates to human-review
        return
    # proposal.unified_diff is schema-validated; daemon applies it.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AUDIT = REPO / ".loop" / "issue_audit.jsonl"

sys.path.insert(0, str(REPO / "scripts"))
from council_schemas import (  # noqa: E402
    PROMPT_ADDENDUM,
    CouncilProposal,
    validate_council_proposal,
)
from rule_fix_strategy import (  # noqa: E402
    get_prompt_template,
    get_strategy,
    is_human_only,
)

COUNCIL_ROLES: dict[str, dict[str, str]] = {
    "researcher": {
        "model": "qwen2.5:latest",
        "system": (
            "You are RESEARCHER. Investigate the symbol the rule cites in the "
            "context + grep references provided. Decide if it is dead code, "
            "real bug, or pattern-known issue. Reply in 3-6 lines of plain "
            "text — no JSON, no diff. AUTHOR reads your brief before proposing."
        ),
    },
    "author": {
        "model": "deepseek-coder:6.7b-instruct",
        "system": (
            "You are AUTHOR. Propose a minimal unified-diff fix for one "
            "lint/type/security finding. Output the structured JSON only."
        ),
    },
    "reviewer": {
        "model": "codegemma:7b-instruct",
        "system": (
            "You are REVIEWER. The AUTHOR's structured proposal is given. "
            "Critique correctness, completeness, and risks. Reply in 3-6 "
            "lines of plain text — no JSON, no diff."
        ),
    },
    "advisor": {
        "model": "codellama:7b-instruct",
        "system": (
            "You are ADVISOR. Synthesize AUTHOR proposal + REVIEWER critique. "
            "If you would propose an alternative diff, emit a fresh JSON "
            "matching CouncilProposal; otherwise reply 'CONCUR' + one-line "
            "reason."
        ),
    },
}

# 5-role aliasing layer (matrix row: Agent Council / 5-role rename).
# The underlying 4-role council runs unchanged; this map gives
# downstream consumers (drills, dashboards, MCP clients) a stable
# 5-role vocabulary without forking the council code path.
#
# Aliases route to the existing COUNCIL_ROLES entries:
#   Planner   → author    (proposes the structural plan/diff)
#   Retriever → researcher (gathers context + grep refs)
#   Risk      → reviewer   (critiques correctness + risks)
#   Evaluator → advisor    (synthesizes; CONCUR or alternative)
#   Writer    → author     (produces the final structured proposal —
#                           same model lane as Planner; the split
#                           exists at the *role-label* layer so a
#                           future iteration can swap Writer to a
#                           dedicated model without rewiring callers)
#
# Per CLAUDE.md §47 (architecture: explicit aliases stay reversible)
# + §43 (drill_council_5_role_aliasing locks the contract).
COUNCIL_ROLE_ALIASES: dict[str, str] = {
    "Planner": "author",
    "Retriever": "researcher",
    "Risk": "reviewer",
    "Evaluator": "advisor",
    "Writer": "author",
}


def resolve_role(name: str) -> str:
    """Translate a 5-role label to the underlying 4-role canonical key.

    Accepts either nomenclature (case-insensitive); returns the
    canonical 4-role key suitable for COUNCIL_ROLES lookup. Raises
    KeyError on unknown labels — silent fallback would mask typos.
    """
    if name in COUNCIL_ROLES:
        return name
    # 5-role aliases (case-insensitive on the alias side)
    for alias, canonical in COUNCIL_ROLE_ALIASES.items():
        if alias.lower() == name.lower():
            return canonical
    raise KeyError(
        f"unknown council role: {name!r}; valid 4-role: "
        f"{sorted(COUNCIL_ROLES)}; valid 5-role aliases: "
        f"{sorted(COUNCIL_ROLE_ALIASES)}"
    )


OLLAMA_URL = "http://localhost:11434/api/generate"

# PolisAI integration scopes — emitted by the local council host to
# satisfy the policy rules in config/policies/agent_dispatch.json. In
# production these come from the JWT scope claim; in local-dev the
# council process is the trust boundary.
COUNCIL_OLLAMA_SCOPES = ("ollama:call",)


class OllamaPolicyDenied(RuntimeError):
    """Raised when PolisAI denies the Ollama call before it fires.

    Distinct from RuntimeError("ollama call failed: ...") so callers
    can tell a policy denial apart from a network/server fault.
    Carries the PolicyDecision for the audit row.
    """

    def __init__(self, decision) -> None:  # decision: PolicyDecision
        self.decision = decision
        super().__init__(
            f"PolisAI denied ollama:generate for actor={decision.actor!r}: "
            f"{decision.reason} (rule={decision.rule_matched})"
        )


def _polisai_gate(actor: str) -> None:
    """Check the policy gate BEFORE the actual Ollama call.

    Audit row lands in .loop/policy_audit.jsonl regardless of decision,
    per §38 / §48.4. On deny, raises OllamaPolicyDenied — the council
    treats this as a hard stop (the decision is logged, the request is
    rejected, the role's chain entry records 'policy_denied').
    """
    # Local import to avoid a hard cycle if policy_check is missing
    # in some embedded test envs. Importing inside the function also
    # means the side-effect of loading the policy file happens only
    # when an Ollama call is attempted, not on module import.
    try:
        from policy_check import evaluate as _policy_evaluate
    except ImportError:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent))
        from policy_check import evaluate as _policy_evaluate

    decision = _policy_evaluate(
        actor=actor,
        tool="ollama:generate",
        scopes_granted=list(COUNCIL_OLLAMA_SCOPES),
        persist_audit=True,
    )
    if not decision.allow:
        raise OllamaPolicyDenied(decision)


def call_ollama(
    model: str,
    system: str,
    prompt: str,
    timeout: float = 180.0,
    *,
    actor: str = "council:unknown",
) -> tuple[str, int]:
    """One Ollama generate call, gated by PolisAI.

    The actor kwarg names which council role is calling; it is matched
    against the rules in config/policies/agent_dispatch.json. The
    default 'council:unknown' is a deliberate trip-wire — any call site
    that forgot to pass actor will hit default-deny + a loud audit row
    rather than silently bypassing the gate.

    Returns (response_text, tokens_used). Raises OllamaPolicyDenied if
    PolisAI rejects the call; RuntimeError on actual Ollama faults.
    """
    _polisai_gate(actor)

    payload = {
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 1024},
    }
    proc = subprocess.run(
        ["curl", "-s", "--max-time", str(int(timeout)),
         "-X", "POST", OLLAMA_URL,
         "-H", "Content-Type: application/json",
         "-d", json.dumps(payload)],
        capture_output=True, text=True, timeout=timeout + 5,
    )
    if proc.returncode != 0:
        # Stage-2 — try the LiteLLM fallback path before giving up.
        # Per the 2026-05-04 tool-evaluation, LiteLLM is the unified
        # gateway alternative. Only fires when:
        #   1. Direct curl actually failed (not a "preventive" detour)
        #   2. LITELLM_ENABLED=1 in environment
        #   3. litellm is pip-installed in the running interpreter
        # If any of those is false, re-raise the original curl error
        # so the diagnostic stays clear (operator sees curl's stderr,
        # not "litellm not configured").
        original_err = f"ollama curl failed: {proc.stderr.strip()[:200]}"
        try:
            return _litellm_fallback(model, system, prompt, timeout, actor)
        except _LiteLLMNotApplicable:
            raise RuntimeError(original_err)  # noqa: B904 — preserve original
    try:
        body = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ollama returned non-JSON: {proc.stdout[:200]}") from exc
    return body.get("response", ""), int(body.get("eval_count", 0))


class _LiteLLMNotApplicable(Exception):
    """Internal — litellm fallback isn't available (flag off OR not installed).

    Distinct from OllamaPolicyDenied + LiteLLMUnavailable so the
    fallback dispatcher can re-raise the ORIGINAL curl error
    (operator-readable diagnostic), not "litellm not configured."
    """


def _litellm_fallback(
    model: str, system: str, prompt: str, timeout: float, actor: str,
) -> tuple[str, int]:
    """Try LiteLLM. Raises _LiteLLMNotApplicable when the path isn't
    available so call_ollama can re-raise the original curl error.

    Stage-3 (this commit): pass _skip_gate=True to litellm_adapter.complete
    since call_ollama already fired the PolisAI gate at line 174.
    Eliminates the duplicate audit row from Stage-2's double-gate.

    Stage-2 had two audit rows per fallback (one per call_ollama gate,
    one per adapter gate). Same decision both times — harmless but
    storage cost. Stage-3 is the consolidation: gate once, audit once.
    """
    try:
        from litellm_adapter import (  # noqa: PLC0415
            LiteLLMUnavailable,
        )
        from litellm_adapter import (
            complete as _litellm_complete,
        )
    except ImportError as exc:
        raise _LiteLLMNotApplicable() from exc

    try:
        # Stage-3: _skip_gate=True. The adapter trusts that we already
        # gated (call_ollama line 174). Drill enforces the contract:
        # the adapter's _skip_gate kwarg is keyword-only + underscore-
        # prefixed; no public caller may set it. The fallback
        # dispatcher is one of the SHORT list of trusted callers.
        return _litellm_complete(
            model=model, system=system, prompt=prompt,
            timeout=timeout, actor=actor,
            _skip_gate=True,
        )
    except LiteLLMUnavailable as exc:
        raise _LiteLLMNotApplicable() from exc


def _researcher_prompt(issue: dict, context: str, grep_refs: str) -> str:
    """Tier 1 #1.4: RESEARCHER builds a brief BEFORE AUTHOR fires.

    Only invoked when strategy.needs_grep_refs=True (investigation +
    type-fix rules). Brief synthesizes the file context + grep
    references into 3-6 lines of plain-text guidance for AUTHOR.
    """
    return (
        f"Investigate this finding before AUTHOR proposes a fix.\n\n"
        f"Rule: {issue['code']}\n"
        f"File: {issue['file']}:{issue['line']}\n"
        f"Rule message: {issue['message']}\n"
        f"\n"
        f"Context (±lines around issue):\n```\n{context}\n```\n"
        f"\n"
        f"Grep references across repo:\n```\n{grep_refs[:3000]}\n```\n"
        f"\n"
        f"Reply with 3-6 lines of plain text answering:\n"
        f"  - Is the cited symbol dead code, real bug, or pattern-known?\n"
        f"  - What's the safest minimal fix?\n"
        f"  - Any risks AUTHOR must know?\n"
    )


def _prior_fix_section(issue: dict) -> str:
    """Tier 2 #2.6 — query prior-fix RAG; return prompt section or ''.

    Empty string when no preference data accumulated yet (zero-data
    behavior). Wired into AUTHOR prompt for ALL rule categories,
    not just investigation — past mechanical fixes are also useful
    few-shot examples.
    """
    try:
        sys.path.insert(0, str(REPO / "scripts"))
        from prior_fix_rag import query_similar_fixes, render_few_shot  # noqa: E402
    except ImportError:
        return ""
    examples = query_similar_fixes(
        query=issue.get("message", ""),
        rule_code=issue.get("code", ""),
        limit=3,
    )
    return render_few_shot(examples)


def _author_prompt(issue: dict, context: str, *, grep_refs: str = "", research_brief: str = "") -> str:
    """Build the AUTHOR prompt using the per-rule strategy.

    Per Tier 1 #1.3 (strategy table) + #1.4 (research brief).
    F841 gets the investigation prompt + grep-references + research
    brief; UP035 gets the mechanical-rewrite prompt with no extras.
    One generic prompt for all rules was empirically wrong.
    """
    strategy = get_strategy(issue.get("code", ""))
    rule_specific = get_prompt_template(strategy)
    refs_section = ""
    if strategy.needs_grep_refs and grep_refs:
        refs_section = f"\n\nReferences (grep across repo):\n```\n{grep_refs[:3000]}\n```\n"
    brief_section = ""
    if research_brief:
        brief_section = (
            f"\n\nResearch brief (from RESEARCHER model — read carefully):\n"
            f"```\n{research_brief}\n```\n"
        )
    # Tier 2 #2.6 — prior-fix RAG few-shot. Returns "" when no
    # operator preference data; doesn't bloat the prompt.
    prior_fix_section = _prior_fix_section(issue)
    return (
        rule_specific
        + "\n"
        + f"Issue ID: {issue['id']}\n"
        + f"Rule: {issue['code']}\n"
        + f"File: {issue['file']}:{issue['line']}\n"
        + f"Message: {issue['message']}\n"
        + brief_section
        + prior_fix_section
        + "\n"
        + f"Context (±{strategy.context_lines} lines around the issue):\n"
        + f"```\n{context}\n```"
        + refs_section
        + "\n"
        + PROMPT_ADDENDUM
    )


def _reviewer_prompt(issue: dict, proposal: CouncilProposal, *, verification: dict | None = None) -> str:
    """Build REVIEWER prompt; embed Tier 2 #2.4 verification result if present."""
    verification_section = ""
    if verification is not None:
        rc = verification.get("ruff_exit_code")
        ruff_out = verification.get("ruff_output", "")
        err = verification.get("error")
        if err:
            verification_section = (
                f"\n\nVerification result (from in-loop ruff run):\n"
                f"  diff applied: NO — {err}\n"
                f"  → AUTHOR's diff is malformed or doesn't apply cleanly.\n"
                f"  → recommend SCORE: 1-3 unless the rejection reason is trivial.\n"
            )
        else:
            verdict = "ruff CLEAN" if rc == 0 else f"ruff still has issues (exit={rc})"
            ruff_preview = ruff_out[:800] if ruff_out else "(no ruff output)"
            verification_section = (
                f"\n\nVerification result (from in-loop ruff run):\n"
                f"  diff applied + reverted: yes\n"
                f"  ruff verdict: {verdict}\n"
                f"  ruff output:\n```\n{ruff_preview}\n```\n"
                f"  → If ruff is CLEAN, the fix DOES resolve the rule violation.\n"
                f"  → If ruff still has issues, identify which violation remains.\n"
            )
    return (
        f"AUTHOR proposed a fix for {issue['id']} (rule {issue['code']}).\n\n"
        f"AUTHOR summary: {proposal.summary}\n"
        f"AUTHOR confidence: {proposal.confidence}\n"
        f"AUTHOR diff:\n```\n{proposal.unified_diff}\n```\n\n"
        f"Issue message: {issue['message']}"
        + verification_section
        + "\n\n"
        "Critique. Is the diff correct? Does it actually resolve the\n"
        "rule violation? Any side effects? 3-6 lines plain text."
    )


def _advisor_prompt(issue: dict, proposal: CouncilProposal, reviewer: str) -> str:
    return (
        f"AUTHOR proposed for {issue['id']} (rule {issue['code']}).\n\n"
        f"AUTHOR diff:\n```\n{proposal.unified_diff}\n```\n\n"
        f"REVIEWER critique:\n{reviewer}\n\n"
        f"Synthesize. Reply either 'CONCUR' + one-line reason OR an\n"
        f"alternative CouncilProposal JSON if you'd propose differently."
        + PROMPT_ADDENDUM
    )


def _file_context(repo: Path, file_rel: str, line_no: int, lines_around: int = 10) -> str:
    """Read ±lines_around lines around line_no. Strategy-table-driven
    per Tier 1 #1.3 — F841 gets ±30, mechanical rules get ±5."""
    try:
        lines = (repo / file_rel).read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, UnicodeDecodeError):
        return "(file not readable)"
    start = max(0, line_no - lines_around - 1)
    end = min(len(lines), line_no + lines_around)
    return "\n".join(f"{i + 1:4}: {lines[i]}" for i in range(start, end))


def _summarize_validation_failure(raw_text: str) -> str:
    """Extract a human-readable failure summary from a rejected AUTHOR
    output. Used to populate the retry prompt's <validation_feedback>
    section. Per Tier 2 #2.1.

    The validator returns None (no detail) so we re-validate here
    via Pydantic to capture the actual ValidationError messages.
    Multi-error: report top 3.
    """
    from pydantic import ValidationError
    sys.path.insert(0, str(REPO / "scripts"))
    from council_schemas import CouncilProposal, _first_balanced_object  # noqa: E402

    if not raw_text:
        return "Empty output. Emit the CouncilProposal JSON object."
    cleaned = raw_text
    for fence in ("```json", "```"):
        cleaned = cleaned.replace(fence, "")
    cleaned = cleaned.strip()
    candidate = _first_balanced_object(cleaned)
    if candidate is None:
        return (
            "No balanced JSON object found in output. "
            "Emit ONE CouncilProposal JSON; no prose; no markdown fences."
        )
    try:
        CouncilProposal.model_validate_json(candidate)
        return "Validation passed unexpectedly; no concrete error to report."
    except ValidationError as ve:
        errors = ve.errors()[:3]
        lines: list[str] = []
        for err in errors:
            loc = ".".join(str(p) for p in err.get("loc", ()))
            msg = err.get("msg", "")
            lines.append(f"  - field={loc!r} error={msg!r}")
        return "Pydantic ValidationError (top 3):\n" + "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        return f"JSON parse error: {type(exc).__name__}: {exc}"


def _git_apply_check_only(repo: Path, diff: str) -> dict:
    """Tier 1.3.b — pre-flight read-only `git apply --check`.

    Distinct from `_verify_diff_in_worktree` (which actually applies +
    runs ruff): this helper ONLY runs `git apply --check`, never
    mutates the worktree, completes in <1s on the local box, and is
    cheap enough to run inside the AUTHOR retry loop.

    Per the 2026-05-03 empirical finding (docs/architecture/
    apply-rate-empirical-finding.md), 5/8 historical apply failures
    were structurally-valid JSON proposals whose diff failed
    `git apply --check` for path / offset / line-content reasons. The
    schema-as-contract upgrade: every accepted proposal must pass
    BOTH schema validation AND apply-check.

    Returns dict with: ok (bool), error (str | "" if ok).
    """
    if not diff or not diff.strip():
        return {"ok": False, "error": "empty diff"}
    proc = subprocess.run(
        ["git", "apply", "-p0", "--check", "-"],
        cwd=repo, input=diff + "\n",
        capture_output=True, text=True, timeout=10,
    )
    if proc.returncode == 0:
        return {"ok": True, "error": ""}
    err = (proc.stderr.strip() or proc.stdout.strip())[:400]
    return {"ok": False, "error": err}


def _verify_diff_in_worktree(repo: Path, diff: str) -> dict:
    """Tier 2 #2.4 — apply the diff, run ruff, capture exit code, roll back.

    The REVIEWER prompt embeds this verification result so the model
    can say "ruff confirmed X" / "ruff still fails because Y" instead
    of guessing. The diff is rolled back after verification — daemon's
    apply gate still owns the actual mutation.

    Returns dict with: applied (bool), ruff_exit_code (int), ruff_output (str),
    error (str | None). Never raises — verification failure is captured,
    not propagated; REVIEWER sees the failure.
    """
    out: dict = {
        "applied": False,
        "ruff_exit_code": None,
        "ruff_output": "",
        "error": None,
    }
    if not diff.strip():
        out["error"] = "empty diff"
        return out
    # Apply with -p0 to match the daemon's gate logic.
    apply = subprocess.run(
        ["git", "apply", "-p0", "--check", "-"],
        cwd=repo, input=diff + "\n",
        capture_output=True, text=True, timeout=15,
    )
    if apply.returncode != 0:
        out["error"] = f"git apply --check failed: {apply.stderr.strip()[:200]}"
        return out
    real_apply = subprocess.run(
        ["git", "apply", "-p0", "-"],
        cwd=repo, input=diff + "\n",
        capture_output=True, text=True, timeout=15,
    )
    if real_apply.returncode != 0:
        out["error"] = f"git apply failed: {real_apply.stderr.strip()[:200]}"
        return out
    out["applied"] = True
    try:
        ruff = subprocess.run(
            [".venv/bin/ruff", "check",
             "services/agent-orchestrator-svc/app/", "libs/py/"],
            cwd=repo, capture_output=True, text=True, timeout=30,
        )
        out["ruff_exit_code"] = ruff.returncode
        out["ruff_output"] = ((ruff.stdout or "") + (ruff.stderr or ""))[:2000]
    except subprocess.TimeoutExpired:
        out["error"] = "ruff timed out (>30s)"
    finally:
        # ALWAYS roll back regardless of ruff outcome — verification
        # never leaves the worktree mutated.
        subprocess.run(
            ["git", "apply", "-p0", "-R", "-"],
            cwd=repo, input=diff + "\n",
            capture_output=True, text=True, timeout=15,
        )
    return out


def _grep_refs(repo: Path, message: str) -> str:
    """Extract a backticked symbol from rule msg + grep across repo.

    Used by investigation-category rules (F841, F811) where the
    council needs to know if the symbol has any references.
    """
    import re as _re
    m = _re.search(r"`([^`]+)`", message)
    if m is None:
        return ""
    symbol = m.group(1)
    try:
        proc = subprocess.run(
            ["grep", "-rn", "--include=*.py", symbol,
             "services/", "libs/", "scripts/", "mcp/"],
            cwd=repo, capture_output=True, text=True, timeout=20,
        )
        return (proc.stdout or "")[:4000]
    except Exception:
        return ""


def _write_audit(record: dict) -> None:
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def run_local_council(issue: dict, repo: Path | None = None) -> CouncilProposal | None:
    """Run the schema-aware 3-role council. Returns CouncilProposal or None.

    Audit is written to .loop/issue_audit.jsonl in the same shape as
    the global dispatcher's output, so the task-board / daemon can
    read either source uniformly.
    """
    repo = repo or REPO
    file_rel = issue["file"]
    line_no = issue["line"]

    # Tier 1 #1.3: per-rule strategy chooses context window + grep need
    strategy = get_strategy(issue.get("code", ""))
    if is_human_only(issue.get("code", "")):
        print(f"  SKIP: rule {issue.get('code')!r} is security-tier; never to model (per §50.5.3)")
        _write_audit({
            "id": issue["id"], "lane": "council_local",
            "chain": {}, "outcome": "skipped_human_only",
        })
        return None
    context = _file_context(repo, file_rel, line_no, lines_around=strategy.context_lines)
    grep_refs = _grep_refs(repo, issue.get("message", "")) if strategy.needs_grep_refs else ""

    audit_chain: dict[str, dict] = {
        "strategy": {
            "category": strategy.category,
            "context_lines": strategy.context_lines,
            "needs_grep_refs": strategy.needs_grep_refs,
            "model_tier": strategy.model_tier,
            "grep_refs_chars": len(grep_refs),
        },
    }

    # §47 Layer 3 — Agent Router cross-check. Every council run
    # classifies the issue's `message` field through the router.
    # The router's recommendation is recorded in the audit chain so
    # forensics can spot disagreements between upstream lane assignment
    # and the router's judgment. This is a CROSS-CHECK, not a gate;
    # the council still proceeds (issue was already routed to council
    # by issue_dispatcher.py based on rule code). Stage-2 would gate.
    try:
        from agent_router import classify as _router_classify
    except ImportError:
        sys.path.insert(0, str(REPO / "scripts"))
        from agent_router import classify as _router_classify
    try:
        router_decision = _router_classify(
            issue.get("message", "") or issue.get("id", ""),
            persist_audit=False,  # the council audit_chain captures it
        )
        audit_chain["agent_router"] = {
            "intent": router_decision.intent,
            "risk": router_decision.risk,
            "recommended_actor": router_decision.recommended_actor,
            "recommended_tool": router_decision.recommended_tool,
            "confidence": router_decision.confidence,
            "reasons": router_decision.reasons[:3],  # cap audit row size
            "disagrees_with_council": router_decision.recommended_actor not in (
                "council:author", "council:reviewer", "council:advisor",
                "council:researcher",
            ),
        }
        if audit_chain["agent_router"]["disagrees_with_council"]:
            print(
                f"  [router] WARNING — issue routed to council but router "
                f"recommends actor={router_decision.recommended_actor!r}; "
                f"continuing per upstream lane assignment"
            )
    except Exception as exc:  # noqa: BLE001 — router failure is non-fatal
        # Router classification is observability, not gate. Failure
        # should not block the council; it just leaves the audit row
        # without a router section.
        audit_chain["agent_router"] = {
            "error": str(exc)[:200],
            "fallback": "router_unavailable",
        }

    # Tier 1 #1.4: RESEARCHER fires for investigation + type-fix rules
    # so AUTHOR sees a synthesized brief instead of raw grep output.
    research_brief = ""
    if strategy.needs_grep_refs and grep_refs:
        print(f"\n  === RESEARCHER ({COUNCIL_ROLES['researcher']['model']}) ===")
        started = time.time()
        try:
            research_brief, research_tokens = call_ollama(
                COUNCIL_ROLES["researcher"]["model"],
                COUNCIL_ROLES["researcher"]["system"],
                _researcher_prompt(issue, context, grep_refs),
                timeout=120.0,  # qwen2.5 is fast; cap shorter than AUTHOR
                actor="council:researcher",
            )
        except Exception as e:
            print(f"  RESEARCHER error: {e}")
            audit_chain["researcher"] = {
                "model": COUNCIL_ROLES["researcher"]["model"],
                "outcome": "error",
                "error": str(e),
            }
            research_brief = ""  # AUTHOR proceeds without brief
        else:
            research_lat = time.time() - started
            audit_chain["researcher"] = {
                "model": COUNCIL_ROLES["researcher"]["model"],
                "tokens": research_tokens,
                "latency_s": round(research_lat, 1),
                "output": research_brief[:1500],
            }
            print(f"  [{research_tokens} tokens, {research_lat:.1f}s]")
            print(research_brief[:600])

    # Tier 2 #2.1: retry-with-feedback. AUTHOR fires twice when the
    # first output fails schema validation. Pass-2 prompt embeds the
    # validation error so the model can correct itself. Bounded at
    # 1 retry to cap token cost; if pass-2 also fails, escalate.
    proposal = None
    author_text = ""
    author_tokens = 0
    author_lat = 0.0
    feedback_for_retry = ""

    for attempt in range(2):
        retry_label = " (retry)" if attempt == 1 else ""
        print(f"\n  === AUTHOR{retry_label} ({COUNCIL_ROLES['author']['model']}) ===")
        prompt = _author_prompt(
            issue, context,
            grep_refs=grep_refs, research_brief=research_brief,
        )
        if attempt == 1 and feedback_for_retry:
            # Append the validation failure as explicit feedback so
            # AUTHOR knows what to correct.
            prompt = prompt + (
                "\n\n<validation_feedback>\n"
                "Your previous output FAILED schema validation. Reasons:\n"
                f"{feedback_for_retry}\n"
                "Re-emit the JSON correcting these issues. Same schema.\n"
                "</validation_feedback>\n"
            )
        started = time.time()
        try:
            author_text, author_tokens = call_ollama(
                COUNCIL_ROLES["author"]["model"],
                COUNCIL_ROLES["author"]["system"],
                prompt,
                actor="council:author",
            )
        except Exception as e:
            print(f"  AUTHOR error: {e}")
            audit_chain[f"author_attempt_{attempt + 1}"] = {
                "model": COUNCIL_ROLES["author"]["model"],
                "outcome": "error", "error": str(e),
            }
            _write_audit({
                "id": issue["id"], "lane": "council_local",
                "chain": audit_chain, "outcome": "error_author",
            })
            return None
        author_lat = time.time() - started
        audit_chain[f"author_attempt_{attempt + 1}"] = {
            "model": COUNCIL_ROLES["author"]["model"],
            "tokens": author_tokens,
            "latency_s": round(author_lat, 1),
            "output": author_text[:1500],
        }
        print(f"  [{author_tokens} tokens, {author_lat:.1f}s]")

        proposal = validate_council_proposal(author_text, repo=repo)
        if proposal is not None:
            # Tier 1.3.b — schema passed; now verify the diff ACTUALLY
            # applies. The empirical 2026-05-03 finding showed 5/8
            # failures were structurally-valid JSON whose diff failed
            # `git apply --check` (wrong file path, bad @@ offsets,
            # line-content mismatch). Schema-as-contract MUST include
            # "this output works", not just "this JSON parses."
            apply_check = _git_apply_check_only(repo, proposal.unified_diff)
            if apply_check["ok"]:
                audit_chain[f"author_attempt_{attempt + 1}"]["validation"] = "ok"
                audit_chain[f"author_attempt_{attempt + 1}"]["apply_check"] = "ok"
                audit_chain[f"author_attempt_{attempt + 1}"]["proposal"] = proposal.model_dump(mode="json")
                audit_chain["author"] = audit_chain[f"author_attempt_{attempt + 1}"]
                audit_chain["author"]["attempt"] = attempt + 1
                print(f"  AUTHOR proposal validated + apply-check OK (attempt {attempt + 1}): file={proposal.file_path} confidence={proposal.confidence}")
                break
            # Schema OK but diff doesn't apply — treat as rejection
            # AND feed the actual git error back to AUTHOR for retry.
            # This is the Tier 1.3.b upgrade: previously the apply-check
            # ran AFTER the retry loop, so apply-failures could not be
            # retried. Now they are.
            apply_err = apply_check["error"]
            audit_chain[f"author_attempt_{attempt + 1}"]["validation"] = "ok"
            audit_chain[f"author_attempt_{attempt + 1}"]["apply_check"] = "rejected"
            audit_chain[f"author_attempt_{attempt + 1}"]["apply_check_error"] = apply_err[:300]
            print(f"  AUTHOR pass-{attempt + 1} schema OK but diff FAILED git apply --check:")
            print(f"    {apply_err[:120]}")
            # Override feedback_for_retry with the apply error so the
            # retry prompt addresses the actual cause (path / offset /
            # line content) rather than schema shape.
            feedback_for_retry = (
                f"Schema OK, but diff failed `git apply --check`:\n"
                f"  {apply_err}\n\n"
                f"Common causes:\n"
                f"  - File path wrong (you wrote relative; we need repo-root-relative)\n"
                f"  - @@ line offsets don't match the source\n"
                f"  - Context lines (no `+`/`-` prefix) don't match what's at that line\n"
                f"Re-emit the proposal with the corrected diff."
            )
            proposal = None  # force retry path below
        else:
            # Failed schema validation — capture concrete feedback for retry.
            feedback_for_retry = _summarize_validation_failure(author_text)
            audit_chain[f"author_attempt_{attempt + 1}"]["validation"] = "rejected"
        audit_chain[f"author_attempt_{attempt + 1}"]["feedback_for_retry"] = feedback_for_retry[:300]
        if attempt == 0:
            print("  AUTHOR pass-1 REJECTED; retrying with feedback...")

    if proposal is None:
        # Both local attempts failed schema. Per Tier 2 #2.7,
        # check if we should escalate to Tier-B (Claude/Codex CLI)
        # before declaring schema-rejected. The escalation runs
        # through the SAME validator — no schema bypass.
        from tier_b_fallback import should_escalate_to_tier_b, try_tier_b  # noqa: E402
        if should_escalate_to_tier_b(audit_chain):
            print("  Local council exhausted; escalating to Tier-B...")
            tier_b_proposal = try_tier_b(
                issue, context, research_brief=research_brief,
            )
            if tier_b_proposal is not None:
                audit_chain["tier_b"] = {
                    "outcome": "validated",
                    "proposal": tier_b_proposal.model_dump(mode="json"),
                }
                _write_audit({
                    "id": issue["id"], "lane": "council_local",
                    "chain": audit_chain, "outcome": "tier_b_validated",
                })
                print(f"  Tier-B proposal validated: file={tier_b_proposal.file_path}")
                return tier_b_proposal
            audit_chain["tier_b"] = {
                "outcome": "unavailable_or_invalid",
                "reason": "no Tier-B binary on PATH OR output failed schema",
            }
        print("  AUTHOR proposal REJECTED both local + Tier-B; escalating to human")
        _write_audit({
            "id": issue["id"], "lane": "council_local",
            "chain": audit_chain, "outcome": "author_schema_rejected_after_retry",
        })
        return None

    # Tier 2 #2.4 — in-loop verification: actually apply the proposal,
    # run ruff, capture exit code; pass result to REVIEWER prompt so
    # critique is grounded in real test output instead of opinion.
    print("\n  === IN-LOOP VERIFY (apply + ruff + revert) ===")
    verification = _verify_diff_in_worktree(repo, proposal.unified_diff)
    audit_chain["verification"] = verification
    if verification.get("error"):
        print(f"  verify: error = {verification['error'][:80]}")
    else:
        rc = verification.get("ruff_exit_code")
        verdict = "CLEAN" if rc == 0 else f"still issues (exit={rc})"
        print(f"  verify: applied + reverted; ruff {verdict}")

    print(f"\n  === REVIEWER ({COUNCIL_ROLES['reviewer']['model']}) ===")
    started = time.time()
    try:
        reviewer_text, reviewer_tokens = call_ollama(
            COUNCIL_ROLES["reviewer"]["model"],
            COUNCIL_ROLES["reviewer"]["system"],
            _reviewer_prompt(issue, proposal, verification=verification),
            actor="council:reviewer",
        )
    except Exception as e:
        print(f"  REVIEWER error: {e}")
        audit_chain["reviewer"] = {"model": COUNCIL_ROLES["reviewer"]["model"], "outcome": "error", "error": str(e)}
        _write_audit({"id": issue["id"], "lane": "council_local", "chain": audit_chain, "outcome": "error_reviewer"})
        return proposal  # AUTHOR validated; return early so apply can still try
    reviewer_lat = time.time() - started
    audit_chain["reviewer"] = {
        "model": COUNCIL_ROLES["reviewer"]["model"],
        "tokens": reviewer_tokens,
        "latency_s": round(reviewer_lat, 1),
        "output": reviewer_text[:1500],
    }
    print(f"  [{reviewer_tokens} tokens, {reviewer_lat:.1f}s]")

    print(f"\n  === ADVISOR ({COUNCIL_ROLES['advisor']['model']}) ===")
    started = time.time()
    try:
        advisor_text, advisor_tokens = call_ollama(
            COUNCIL_ROLES["advisor"]["model"],
            COUNCIL_ROLES["advisor"]["system"],
            _advisor_prompt(issue, proposal, reviewer_text),
            actor="council:advisor",
        )
    except Exception as e:
        print(f"  ADVISOR error: {e}")
        audit_chain["advisor"] = {"model": COUNCIL_ROLES["advisor"]["model"], "outcome": "error", "error": str(e)}
        _write_audit({"id": issue["id"], "lane": "council_local", "chain": audit_chain, "outcome": "error_advisor"})
        return proposal
    advisor_lat = time.time() - started
    audit_chain["advisor"] = {
        "model": COUNCIL_ROLES["advisor"]["model"],
        "tokens": advisor_tokens,
        "latency_s": round(advisor_lat, 1),
        "output": advisor_text[:1500],
    }
    print(f"  [{advisor_tokens} tokens, {advisor_lat:.1f}s]")

    advisor_alt = validate_council_proposal(advisor_text, repo=repo)
    if advisor_alt is not None and advisor_alt.confidence > proposal.confidence:
        audit_chain["advisor"]["alternative_proposal"] = advisor_alt.model_dump(mode="json")
        print(f"  ADVISOR proposed ALTERNATIVE with higher confidence "
              f"({advisor_alt.confidence} > {proposal.confidence}); using it")
        proposal = advisor_alt

    _write_audit({
        "id": issue["id"], "lane": "council_local",
        "chain": audit_chain, "outcome": "council_complete",
    })
    # Phase C #3.1 — auto-capture pending operator rating. Every
    # successful council fire becomes one HitlScore row with
    # verdict='auto_capture'; operator later transitions via
    # `hitl_framework.py review` + record.
    try:
        from hitl_framework import auto_capture_council_outcome  # noqa: E402
        auto_capture_council_outcome(
            issue_id=issue["id"],
            rule_code=issue.get("code"),
            council_outcome="council_complete",
            author_model=COUNCIL_ROLES["author"]["model"],
            author_proposal_summary=proposal.summary,
            confidence=proposal.confidence,
        )
    except Exception:  # noqa: BLE001, S110
        # Auto-capture is fire-and-forget; if hitl_framework imports
        # fail (test environment, missing pydantic, etc.) the council
        # itself MUST NOT fail.
        pass
    return proposal


def main() -> int:
    """CLI entry — run council on one issue id from .loop/issue_checklist.jsonl."""
    import argparse
    parser = argparse.ArgumentParser(prog="local_council.py")
    parser.add_argument("--id", required=True, help="issue id from checklist")
    args = parser.parse_args()

    checklist = REPO / ".loop" / "issue_checklist.jsonl"
    issues = [json.loads(line) for line in checklist.read_text().splitlines() if line.strip()]
    issue = next((i for i in issues if i["id"] == args.id), None)
    if issue is None:
        print(f"x issue not found: {args.id}")
        return 1

    proposal = run_local_council(issue, repo=REPO)
    if proposal is None:
        print("\n✗ council returned no validated proposal")
        return 2
    print("\n✓ council returned validated proposal:")
    print(f"  file_path: {proposal.file_path}")
    print(f"  rule_code: {proposal.rule_code}")
    print(f"  confidence: {proposal.confidence}")
    print(f"  summary: {proposal.summary}")
    print(f"  diff_len: {len(proposal.unified_diff)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
