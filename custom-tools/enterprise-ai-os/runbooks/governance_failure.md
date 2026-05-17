# Runbook: Governance Failure

## Symptoms
- policy check failed
- missing approval
- high-risk action attempted
- audit evidence missing

## Immediate Action
1. Block release/action.
2. Create human approval request.
3. Capture audit evidence.
4. Notify governance owner.
5. Review policy result and missing controls.

## Recovery
- Complete missing checks.
- Add approval record.
- Re-run governance engine.
- Store audit pack.

## Escalation
- Sev1 for production/security/compliance action.
- Sev2 for non-production policy gap.

## Logs to Check
- `governance_checked`
- `approval_requested`
- `policy_failed`
- `audit_evidence_stored`
