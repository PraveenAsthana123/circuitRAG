# Approval policy — Rego mirror of approval_agent/rules.json.
#
# When DOCUMIND_APPROVAL_ENGINE=opa is set, approval_agent.decide()
# delegates to `opa eval` against this file. OPA is the default engine;
# the Python evaluator stays as the fallback and explicit override path.
# drill_opa_approval_parity.py asserts both backends produce the same
# decision for the same input.
#
# Inputs (passed via stdin):
#   {
#     "task": {"id": "...", "action": "...", "type": "...", "risk": "low|medium|high|critical"},
#     "test_result": "PASS"|"FAIL",
#     "governance_result": "ALLOW"|"DENY",
#     "reviewer_decision": "APPROVED"|"REVISION_REQUIRED"|"SKIPPED",
#     "confidence": 0.85
#   }
#
# Output (queried as data.approval_agent.decision):
#   "AUTO_APPROVED" | "HUMAN_REQUIRED" | "DENY" | "REVISION_REQUIRED"

package approval_agent

import rego.v1

# Static rule data — kept in sync with rules.json (drill enforces parity).
blocked_actions := {
    "delete_system_file", "delete_history", "delete_audit",
    "modify_os_config", "access_secret", "run_destructive_command",
    "force_push_main", "modify_security_policy_without_approval",
}

human_required_actions := {
    "code_merge", "file_write", "infrastructure_change",
    "permission_change", "deploy_production", "delete_data",
    "delete_file", "modify_security_policy", "send_external_email",
    "modify_billing",
}

human_required_types := {
    "code_merge", "production_deploy", "delete_file",
    "secret_change", "policy_change", "external_communication",
}

auto_approve_types := {
    "documentation_update", "plan_creation", "research_summary",
    "test_report", "dashboard_update", "recommendation",
    "code_suggestion",
}

risk_rank := {"low": 1, "medium": 2, "high": 3, "critical": 4}

max_risk_rank := 2  # max_risk = "medium"
min_confidence := 0.7

# ---------------------------------------------------------------------------
# Decision rules — first match wins. Rule order matters:
#  1. blocked_action → DENY
#  2. human_required action/type → HUMAN_REQUIRED
#  3. risk above max → HUMAN_REQUIRED
#  4. failed gates → REVISION_REQUIRED
#  5. type not in auto-allowlist → HUMAN_REQUIRED
#  6. all gates passed → AUTO_APPROVED
# ---------------------------------------------------------------------------

action := lower(input.task.action)
ttype := lower(input.task.type)
risk := lower(input.task.risk)
risk_n := risk_rank[risk]

# Rule 1: blocked
decision := "DENY" if {
    action in blocked_actions
}

# Rule 2: human-required action
decision := "HUMAN_REQUIRED" if {
    not action in blocked_actions
    action in human_required_actions
}

decision := "HUMAN_REQUIRED" if {
    not action in blocked_actions
    not action in human_required_actions
    ttype in human_required_types
}

# Rule 3: risk above max
decision := "HUMAN_REQUIRED" if {
    not action in blocked_actions
    not action in human_required_actions
    not ttype in human_required_types
    risk_n > max_risk_rank
}

# Rule 4: failed quality gates → REVISION_REQUIRED
decision := "REVISION_REQUIRED" if {
    not action in blocked_actions
    not action in human_required_actions
    not ttype in human_required_types
    risk_n <= max_risk_rank
    upper(input.test_result) != "PASS"
}

decision := "REVISION_REQUIRED" if {
    not action in blocked_actions
    not action in human_required_actions
    not ttype in human_required_types
    risk_n <= max_risk_rank
    upper(input.test_result) == "PASS"
    input.confidence < min_confidence
}

decision := "REVISION_REQUIRED" if {
    not action in blocked_actions
    not action in human_required_actions
    not ttype in human_required_types
    risk_n <= max_risk_rank
    upper(input.test_result) == "PASS"
    input.confidence >= min_confidence
    upper(input.governance_result) != "ALLOW"
}

decision := "REVISION_REQUIRED" if {
    not action in blocked_actions
    not action in human_required_actions
    not ttype in human_required_types
    risk_n <= max_risk_rank
    upper(input.test_result) == "PASS"
    input.confidence >= min_confidence
    upper(input.governance_result) == "ALLOW"
    not upper(input.reviewer_decision) in {"APPROVED", "SKIPPED"}
}

# Rule 5: type not in auto-allowlist
decision := "HUMAN_REQUIRED" if {
    not action in blocked_actions
    not action in human_required_actions
    not ttype in human_required_types
    risk_n <= max_risk_rank
    upper(input.test_result) == "PASS"
    input.confidence >= min_confidence
    upper(input.governance_result) == "ALLOW"
    upper(input.reviewer_decision) in {"APPROVED", "SKIPPED"}
    ttype != ""
    not ttype in auto_approve_types
}

# Rule 6: all gates passed
decision := "AUTO_APPROVED" if {
    not action in blocked_actions
    not action in human_required_actions
    not ttype in human_required_types
    risk_n <= max_risk_rank
    upper(input.test_result) == "PASS"
    input.confidence >= min_confidence
    upper(input.governance_result) == "ALLOW"
    upper(input.reviewer_decision) in {"APPROVED", "SKIPPED"}
    type_ok
}

# Helper rule: type either empty (no constraint) OR in the auto-allowlist.
type_ok if ttype == ""
type_ok if ttype in auto_approve_types
