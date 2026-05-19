import { MetricsRecorder } from "../06-observability/metrics";
import { GuardrailDecision, GuardrailFinding } from "./types";

export interface GuardrailDecisionObservation {
  readonly side: "input" | "output";
  readonly tenantId: string;
  readonly decision: GuardrailDecision;
  readonly findings: GuardrailFinding[];
}

export interface GuardrailDecisionMonitor {
  record(observation: GuardrailDecisionObservation): void;
}

export class NoopGuardrailDecisionMonitor implements GuardrailDecisionMonitor {
  record(_observation: GuardrailDecisionObservation): void {
    // intentionally empty
  }
}

export class MetricsGuardrailDecisionMonitor implements GuardrailDecisionMonitor {
  constructor(private readonly metrics: MetricsRecorder = new MetricsRecorder()) {}

  record(observation: GuardrailDecisionObservation): void {
    const baseLabels = {
      component: "guardrails",
      tenantId: observation.tenantId,
      side: observation.side,
    };

    this.metrics.counter("guardrail_evaluations_total", 1, {
      ...baseLabels,
      decision: observation.decision,
    });

    const clean = observation.findings.length === 0;
    this.metrics.counter("guardrail_clean_evaluations_total", clean ? 1 : 0, baseLabels);
    this.metrics.counter("guardrail_flagged_evaluations_total", clean ? 0 : 1, baseLabels);

    for (const finding of observation.findings) {
      this.metrics.counter("guardrail_findings_total", 1, {
        ...baseLabels,
        ruleId: finding.ruleId,
        severity: finding.severity,
      });
    }
  }
}
