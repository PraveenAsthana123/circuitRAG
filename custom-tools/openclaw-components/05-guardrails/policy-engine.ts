// ✅ P2 IMPROVED (Iter 46, 2026-05-17): severity → decision is
//     config-driven. Pre-fix the mapping was hardcoded if/else:
//     critical→block, high→review, medium→review, else→allow.
//     A medical RAG might need high→block; a low-risk demo might
//     accept medium→allow. The old code forced the same policy
//     on every caller.
//
//     Now: PolicyEngine takes a SeverityMap (severity → decision)
//     and a per-rule override map for surgical control:
//     "this specific PII_SSN rule blocks regardless of severity tier."
//     Decision precedence: per-rule override > severity tier >
//     default allow.
//
//     When multiple findings exist, the most-restrictive decision
//     wins (block > review > allow).

import { GuardrailDecision, GuardrailFinding } from "./types";

export type SeverityMap = Record<
  "critical" | "high" | "medium" | "low",
  GuardrailDecision
>;

export const DEFAULT_SEVERITY_MAP: SeverityMap = {
  critical: "block",
  high: "review",
  medium: "review",
  low: "allow",
};

export interface PolicyEngineConfig {
  severityMap?: Partial<SeverityMap>;
  /** Per-rule override. Wins over severity tier when present. */
  ruleOverrides?: Record<string, GuardrailDecision>;
}

const DECISION_PRIORITY: Record<GuardrailDecision, number> = {
  allow: 0,
  review: 1,
  block: 2,
};

function moreRestrictive(a: GuardrailDecision, b: GuardrailDecision): GuardrailDecision {
  return DECISION_PRIORITY[a] >= DECISION_PRIORITY[b] ? a : b;
}

export class PolicyEngine {
  private readonly severityMap: SeverityMap;
  private readonly ruleOverrides: Record<string, GuardrailDecision>;

  constructor(config: PolicyEngineConfig = {}) {
    this.severityMap = { ...DEFAULT_SEVERITY_MAP, ...config.severityMap };
    this.ruleOverrides = config.ruleOverrides ?? {};
  }

  decide(findings: GuardrailFinding[]): GuardrailDecision {
    if (findings.length === 0) return "allow";

    let worst: GuardrailDecision = "allow";
    for (const f of findings) {
      const override = this.ruleOverrides[f.ruleId];
      const decision = override ?? this.severityMap[f.severity] ?? "allow";
      worst = moreRestrictive(worst, decision);
    }
    return worst;
  }
}
