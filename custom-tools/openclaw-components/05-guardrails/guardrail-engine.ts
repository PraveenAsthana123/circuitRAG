// ✅ P1 IMPROVED (Iter 40, 2026-05-17): added evaluateResponse() so
//     PII / injection that LEAKED OUT in the LLM's response gets
//     blocked too. Pre-fix the engine only checked request input —
//     a model that hallucinated a phone number or echoed a system
//     prompt would pass through unflagged. CLAUDE.md §48.5 RAG
//     four-part contract calls for output filtering as separate
//     from input filtering.
//
//     evaluateRequest(request)  — input check (the original
//                                 evaluate() now delegates here)
//     evaluateResponse(response, context) — output check
//
//     Each returns the same GuardrailResult shape so callers can
//     uniformly branch on decision.

import { PIIDetector } from "./pii-detector";
import { PromptInjectionDetector } from "./prompt-injection-detector";
import { PolicyEngine } from "./policy-engine";
import { ApprovalGate } from "./approval-gate";
import {
  GuardrailContext,
  GuardrailRequest,
  GuardrailResult,
  GuardrailFinding,
} from "./types";
import {
  EventSink,
  ConsoleEventSink,
} from "../06-observability/sinks";
import {
  GuardrailDecisionMonitor,
  NoopGuardrailDecisionMonitor,
} from "./guardrail-monitor";

export class GuardrailEngine {
  private readonly sink: EventSink;
  private readonly monitor: GuardrailDecisionMonitor;
  // Iter 97 (2026-05-18): pluggable sink for guardrail_evaluation
  // emissions. Default ConsoleEventSink preserves backcompat;
  // a future guardrail-decision audit store (Postgres append-only
  // per §38) plugs in unchanged. Reuses EventSink from M2.3 since
  // guardrail emissions are opaque event-shaped JSON.
  constructor(
    private readonly piiDetector: PIIDetector,
    private readonly injectionDetector: PromptInjectionDetector,
    private readonly policyEngine: PolicyEngine,
    private readonly approvalGate: ApprovalGate,
    sink?: EventSink,
    monitor?: GuardrailDecisionMonitor,
  ) {
    this.sink = sink ?? new ConsoleEventSink();
    this.monitor = monitor ?? new NoopGuardrailDecisionMonitor();
  }

  /** Backcompat alias for evaluateRequest. Pre-fix callers expect this. */
  evaluate(request: GuardrailRequest): GuardrailResult {
    return this.evaluateRequest(request);
  }

  evaluateRequest(request: GuardrailRequest): GuardrailResult {
    return this._evaluate(
      "input",
      request.inputText,
      request.context,
    );
  }

  /**
   * Output-side check. PII detection runs (an LLM that leaks a
   * phone number must be blocked). Injection detection runs too —
   * an LLM echoing system prompts back is the signal that prompt
   * extraction succeeded.
   */
  evaluateResponse(
    responseText: string,
    context: GuardrailContext,
  ): GuardrailResult {
    return this._evaluate("output", responseText, context);
  }

  private _evaluate(
    side: "input" | "output",
    text: string,
    context: GuardrailContext,
  ): GuardrailResult {
    const start = Date.now();

    const findings: GuardrailFinding[] = [
      ...this.piiDetector.detect(text).map(this._tagSide(side)),
      ...this.injectionDetector.detect(text).map(this._tagSide(side)),
    ];

    const decision = this.policyEngine.decide(findings);

    const result: GuardrailResult = {
      decision,
      findings,
      explanation:
        findings.length === 0
          ? `No policy violations detected (${side})`
          : `Detected ${findings.length} policy finding(s) (${side})`,
    };

    if (this.approvalGate.requiresHumanApproval(result)) {
      this.approvalGate.createApprovalTicket(result);
    }

    this.monitor.record({
      side,
      tenantId: context.tenantId,
      decision,
      findings,
    });

    this.sink.emit({
      type: "guardrail_evaluation",
      side,
      requestId: context.requestId,
      sessionId: context.sessionId,
      tenantId: context.tenantId,
      decision,
      findingCount: findings.length,
      durationMs: Date.now() - start,
      traceId: context.traceId,
      timestamp: new Date().toISOString(),
    });

    return result;
  }

  private _tagSide(side: "input" | "output") {
    return (f: GuardrailFinding): GuardrailFinding => ({
      ...f,
      ruleId: `${side.toUpperCase()}_${f.ruleId}`,
    });
  }
}
