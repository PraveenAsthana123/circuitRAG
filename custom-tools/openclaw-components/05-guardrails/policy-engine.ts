import { GuardrailDecision, GuardrailFinding } from "./types";

export class PolicyEngine {
  decide(findings: GuardrailFinding[]): GuardrailDecision {
    const hasCritical = findings.some((f) => f.severity === "critical");
    const hasHigh = findings.some((f) => f.severity === "high");
    const hasMedium = findings.some((f) => f.severity === "medium");

    if (hasCritical) return "block";
    if (hasHigh) return "review";
    if (hasMedium) return "review";

    return "allow";
  }
}
