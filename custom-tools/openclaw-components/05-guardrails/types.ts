export type GuardrailDecision = "allow" | "review" | "block";

export interface GuardrailContext {
  requestId: string;
  sessionId: string;
  userId: string;
  tenantId: string;
  traceId?: string;
}

export interface GuardrailRequest {
  inputText: string;
  toolName?: string;
  context: GuardrailContext;
}

export interface GuardrailFinding {
  ruleId: string;
  severity: "low" | "medium" | "high" | "critical";
  message: string;
}

export interface GuardrailResult {
  decision: GuardrailDecision;
  findings: GuardrailFinding[];
  explanation: string;
}
