import { PIIDetector } from "./pii-detector";
import { PromptInjectionDetector } from "./prompt-injection-detector";
import { PolicyEngine } from "./policy-engine";
import { ApprovalGate } from "./approval-gate";
import {
  GuardrailRequest,
  GuardrailResult,
  GuardrailFinding,
} from "./types";

export class GuardrailEngine {
  constructor(
    private readonly piiDetector: PIIDetector,
    private readonly injectionDetector: PromptInjectionDetector,
    private readonly policyEngine: PolicyEngine,
    private readonly approvalGate: ApprovalGate
  ) {}

  evaluate(request: GuardrailRequest): GuardrailResult {
    const start = Date.now();

    const findings: GuardrailFinding[] = [
      ...this.piiDetector.detect(request.inputText),
      ...this.injectionDetector.detect(request.inputText),
    ];

    const decision = this.policyEngine.decide(findings);

    const result: GuardrailResult = {
      decision,
      findings,
      explanation:
        findings.length === 0
          ? "No policy violations detected"
          : `Detected ${findings.length} policy finding(s)`,
    };

    if (this.approvalGate.requiresHumanApproval(result)) {
      this.approvalGate.createApprovalTicket(result);
    }

    console.log(JSON.stringify({
      type: "guardrail_evaluation",
      requestId: request.context.requestId,
      sessionId: request.context.sessionId,
      tenantId: request.context.tenantId,
      decision,
      findingCount: findings.length,
      durationMs: Date.now() - start,
      traceId: request.context.traceId,
      timestamp: new Date().toISOString(),
    }));

    return result;
  }
}
