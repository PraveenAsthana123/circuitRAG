import { LLMRequest } from "./types";

export interface SafetyGateFinding {
  readonly ruleId: string;
  readonly message: string;
}

export interface SafetyGateClassification {
  readonly safe: boolean;
  readonly findings: SafetyGateFinding[];
}

export interface SafetyGateClassifier {
  classify(request: LLMRequest): SafetyGateClassification;
}

export class PatternSafetyGateClassifier implements SafetyGateClassifier {
  constructor(
    private readonly blockedRules: readonly string[] = [
      "reveal system prompt",
      "disable guardrails",
      "bypass policy",
    ],
  ) {}

  classify(request: LLMRequest): SafetyGateClassification {
    const normalized = request.prompt.toLowerCase();
    const findings = this.blockedRules
      .filter((rule) => normalized.includes(rule))
      .map((rule) => ({
        ruleId: rule,
        message: `Safety gate blocked prompt: ${rule}`,
      }));

    return {
      safe: findings.length === 0,
      findings,
    };
  }
}

export class SafetyGate {
  constructor(
    private readonly classifier: SafetyGateClassifier = new PatternSafetyGateClassifier(),
  ) {}

  validate(request: LLMRequest): void {
    const classification = this.classifier.classify(request);
    if (classification.safe) return;

    const first = classification.findings[0];
    throw new Error(first?.message ?? "Safety gate blocked prompt");
  }
}
