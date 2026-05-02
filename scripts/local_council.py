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
    CouncilProposal,
    PROMPT_ADDENDUM,
    validate_council_proposal,
)
from rule_fix_strategy import (  # noqa: E402
    get_strategy,
    get_prompt_template,
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

OLLAMA_URL = "http://localhost:11434/api/generate"


def call_ollama(model: str, system: str, prompt: str, timeout: float = 180.0) -> tuple[str, int]:
    """One Ollama generate call. Returns (response_text, tokens_used)."""
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
        raise RuntimeError(f"ollama call failed: {proc.stderr.strip()[:200]}")
    try:
        body = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ollama returned non-JSON: {proc.stdout[:200]}") from exc
    return body.get("response", ""), int(body.get("eval_count", 0))


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
    return (
        rule_specific
        + "\n"
        + f"Issue ID: {issue['id']}\n"
        + f"Rule: {issue['code']}\n"
        + f"File: {issue['file']}:{issue['line']}\n"
        + f"Message: {issue['message']}\n"
        + brief_section
        + f"\n"
        + f"Context (±{strategy.context_lines} lines around the issue):\n"
        + f"```\n{context}\n```"
        + refs_section
        + "\n"
        + PROMPT_ADDENDUM
    )


def _reviewer_prompt(issue: dict, proposal: CouncilProposal) -> str:
    return (
        f"AUTHOR proposed a fix for {issue['id']} (rule {issue['code']}).\n\n"
        f"AUTHOR summary: {proposal.summary}\n"
        f"AUTHOR confidence: {proposal.confidence}\n"
        f"AUTHOR diff:\n```\n{proposal.unified_diff}\n```\n\n"
        f"Issue message: {issue['message']}\n\n"
        f"Critique. Is the diff correct? Does it actually resolve the\n"
        f"rule violation? Any side effects? 3-6 lines plain text."
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

    print(f"\n  === AUTHOR ({COUNCIL_ROLES['author']['model']}) ===")
    started = time.time()
    try:
        author_text, author_tokens = call_ollama(
            COUNCIL_ROLES["author"]["model"],
            COUNCIL_ROLES["author"]["system"],
            _author_prompt(issue, context, grep_refs=grep_refs, research_brief=research_brief),
        )
    except Exception as e:
        print(f"  AUTHOR error: {e}")
        audit_chain["author"] = {"model": COUNCIL_ROLES["author"]["model"], "outcome": "error", "error": str(e)}
        _write_audit({"id": issue["id"], "lane": "council_local", "chain": audit_chain, "outcome": "error_author"})
        return None
    author_lat = time.time() - started
    audit_chain["author"] = {
        "model": COUNCIL_ROLES["author"]["model"],
        "tokens": author_tokens,
        "latency_s": round(author_lat, 1),
        "output": author_text[:1500],
    }
    print(f"  [{author_tokens} tokens, {author_lat:.1f}s]")

    proposal = validate_council_proposal(author_text, repo=repo)
    if proposal is None:
        print(f"  AUTHOR proposal REJECTED at validator (schema invalid)")
        audit_chain["author"]["validation"] = "rejected"
        _write_audit({
            "id": issue["id"], "lane": "council_local",
            "chain": audit_chain, "outcome": "author_schema_rejected",
        })
        return None
    print(f"  AUTHOR proposal validated: file={proposal.file_path} confidence={proposal.confidence}")
    audit_chain["author"]["validation"] = "ok"
    audit_chain["author"]["proposal"] = proposal.model_dump(mode="json")

    print(f"\n  === REVIEWER ({COUNCIL_ROLES['reviewer']['model']}) ===")
    started = time.time()
    try:
        reviewer_text, reviewer_tokens = call_ollama(
            COUNCIL_ROLES["reviewer"]["model"],
            COUNCIL_ROLES["reviewer"]["system"],
            _reviewer_prompt(issue, proposal),
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
    return proposal


def main() -> int:
    """CLI entry — run council on one issue id from .loop/issue_checklist.jsonl."""
    import argparse
    parser = argparse.ArgumentParser(prog="local_council.py")
    parser.add_argument("--id", required=True, help="issue id from checklist")
    args = parser.parse_args()

    checklist = REPO / ".loop" / "issue_checklist.jsonl"
    issues = [json.loads(l) for l in checklist.read_text().splitlines() if l.strip()]
    issue = next((i for i in issues if i["id"] == args.id), None)
    if issue is None:
        print(f"x issue not found: {args.id}")
        return 1

    proposal = run_local_council(issue, repo=REPO)
    if proposal is None:
        print("\n✗ council returned no validated proposal")
        return 2
    print(f"\n✓ council returned validated proposal:")
    print(f"  file_path: {proposal.file_path}")
    print(f"  rule_code: {proposal.rule_code}")
    print(f"  confidence: {proposal.confidence}")
    print(f"  summary: {proposal.summary}")
    print(f"  diff_len: {len(proposal.unified_diff)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
