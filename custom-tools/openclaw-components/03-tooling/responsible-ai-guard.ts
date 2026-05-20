import { ToolRequest } from "./types";

export interface ResponsibleAIFinding {
  readonly ruleId: string;
  readonly message: string;
}

export interface ResponsibleAIClassification {
  readonly allowed: boolean;
  readonly findings: ResponsibleAIFinding[];
}

export interface ResponsibleAIClassifier {
  classify(request: ToolRequest): ResponsibleAIClassification;
}

export class PatternResponsibleAIClassifier implements ResponsibleAIClassifier {
  constructor(
    private readonly blockedPatterns: readonly string[] = [
      "delete system file",
      "steal password",
      "bypass security",
      "disable audit",
    ],
  ) {}

  classify(request: ToolRequest): ResponsibleAIClassification {
    const inputText = JSON.stringify(request.input).toLowerCase();
    const findings = this.blockedPatterns
      .filter((pattern) => inputText.includes(pattern))
      .map((pattern) => ({
        ruleId: pattern,
        message: `Responsible AI policy blocked tool call: ${pattern}`,
      }));

    return {
      allowed: findings.length === 0,
      findings,
    };
  }
}

export class ResponsibleAIGuard {
  constructor(
    private readonly classifier: ResponsibleAIClassifier = new PatternResponsibleAIClassifier(),
  ) {}

  validate(request: ToolRequest): void {
    const classification = this.classifier.classify(request);
    if (classification.allowed) return;

    const first = classification.findings[0];
    throw new Error(first?.message ?? "Responsible AI policy blocked tool call");
  }
}
