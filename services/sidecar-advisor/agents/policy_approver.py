"""Policy Approver agent - the loop watcher.

Per the user's request "one agent must track this and approve":
this agent monitors the autonomous loop's iterations and decides
whether the next iteration may proceed. It checks:

  * The latest commit's drill output (all green?)
  * Tier-1 enrollment unchanged or growing
  * The commit touched only pre-approved scope per NEXT_POLICY.md
  * No scope-extension request is open without disposition
  * Composability: the commit composes with prior commits, not
    re-implementing them

It returns one of:
  - APPROVE: continue to next iteration
  - HOLD:    pause; specific concern stated for human review
  - REJECT:  this iteration's commit should be reverted

Why DeepSeek for the approver:
  * The approver compares structured artifacts (commit messages,
    drill output, ledger entries) against a policy doc. That's a
    text-comparison + rule-application task — same shape as the
    chair's synthesis, where DeepSeek is the strongest local model.
  * Using a DIFFERENT model from the chair would risk silent drift
    if the policy interpretation differs across models. Same model,
    different prompt template, different role.

Why role="approver" not "advisor":
  * Advisor synthesises drafts INTO a final answer (one task, many
    inputs).
  * Approver gates ITERATION CONTINUATION (many tasks, one output).
  * The role distinction lets the registry filter cleanly:
    by_role("approver") returns just the gatekeeper, not the chairs.

Phase 4+ wires this agent's output into a watch-loop. Phase 3D
(this commit) lands the agent file + registry entry. Without the
file, the agent can't be invoked at all — this is the foundation.
"""
from .base import CoderAgent

AGENT = CoderAgent(
    name="policy_approver",
    role="approver",
    model="deepseek-coder:6.7b-instruct",
    description="gates loop iteration continuation per NEXT_POLICY.md",
    prompt_template=(
        "You are the Policy Approver for an autonomous code loop. "
        "Decide if the next iteration may proceed by consulting the "
        "comprehensive proposed-approvals matrix in "
        "docs/NEXT_POLICY.md section 1.5.\n\n"
        "Inputs:\n"
        "  Latest commit: {commit_msg}\n"
        "  Files touched: {files_touched}\n"
        "  Drill outcome: {drill_outcome}\n"
        "  Ledger state:  {ledger_state}\n"
        "  Approval matrix excerpt: {policy_excerpt}\n\n"
        "Rules (apply in order; first match wins):\n"
        "  1. drill_outcome contains 'FAILED' -> REJECT 'drill_failed'.\n"
        "  2. Any file in files_touched matches a matrix row with "
        "disposition 'never' -> REJECT 'absolute_block'.\n"
        "  3. Any file matches a 'gated' row AND no scope-extension "
        "log entry exists -> HOLD 'scope_extension_needed'.\n"
        "  4. The commit re-implements work already shipped in a prior "
        "commit (no composition) -> HOLD 'composability'.\n"
        "  5. Same file touched in 3+ consecutive commits -> HOLD "
        "'iteration_thrash' (§44.6 red flag).\n"
        "  6. Otherwise -> APPROVE.\n\n"
        "Reply with ONE line: 'APPROVE' or 'HOLD: <reason>' or "
        "'REJECT: <reason>'."
    ),
)
