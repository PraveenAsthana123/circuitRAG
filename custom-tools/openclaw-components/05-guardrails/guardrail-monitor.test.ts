import { describe, it, expect } from "vitest";
import { GuardrailEngine } from "./guardrail-engine";
import { PIIDetector } from "./pii-detector";
import { PromptInjectionDetector } from "./prompt-injection-detector";
import { PolicyEngine } from "./policy-engine";
import { ApprovalGate } from "./approval-gate";
import {
  MetricsGuardrailDecisionMonitor,
  NoopGuardrailDecisionMonitor,
} from "./guardrail-monitor";
import {
  InMemoryEventSink,
  InMemoryMetricsSink,
  MetricRecord,
} from "../06-observability/sinks";
import { MetricsRecorder } from "../06-observability/metrics";

const CTX = {
  requestId: "req-1",
  sessionId: "sess-1",
  userId: "user-1",
  tenantId: "tenant-A",
  traceId: "trace-1",
};

function buildEngine(metricsSink: InMemoryMetricsSink): GuardrailEngine {
  const metrics = new MetricsRecorder({}, metricsSink);
  const monitor = new MetricsGuardrailDecisionMonitor(metrics);
  return new GuardrailEngine(
    new PIIDetector(),
    new PromptInjectionDetector(),
    new PolicyEngine(),
    new ApprovalGate(new InMemoryEventSink()),
    new InMemoryEventSink(),
    monitor,
  );
}

function findMetric(
  records: MetricRecord[],
  name: string,
  labels: Record<string, string>,
): MetricRecord | undefined {
  return records.find((record) => {
    if (record.name !== name) return false;
    return Object.entries(labels).every(([key, value]) => record.labels[key] === value);
  });
}

describe("Iter 104 - guardrail decision monitoring", () => {
  it("records per-tenant clean evaluation counters without high-cardinality labels", () => {
    const metricsSink = new InMemoryMetricsSink();
    const engine = buildEngine(metricsSink);

    engine.evaluateRequest({ inputText: "clean operational message", context: CTX });

    const records = metricsSink.list();
    expect(findMetric(records, "guardrail_evaluations_total", {
      component: "guardrails",
      tenantId: "tenant-A",
      side: "input",
      decision: "allow",
    })?.value).toBe(1);
    expect(findMetric(records, "guardrail_clean_evaluations_total", {
      component: "guardrails",
      tenantId: "tenant-A",
      side: "input",
    })?.value).toBe(1);
    expect(findMetric(records, "guardrail_flagged_evaluations_total", {
      component: "guardrails",
      tenantId: "tenant-A",
      side: "input",
    })?.value).toBe(0);

    const labelKeys = new Set(records.flatMap((record) => Object.keys(record.labels)));
    expect(labelKeys.has("requestId")).toBe(false);
    expect(labelKeys.has("sessionId")).toBe(false);
    expect(labelKeys.has("traceId")).toBe(false);
    expect(labelKeys.has("userId")).toBe(false);
  });

  it("records flagged findings with tenant, side, rule, and severity labels", () => {
    const metricsSink = new InMemoryMetricsSink();
    const engine = buildEngine(metricsSink);

    const result = engine.evaluateRequest({
      inputText: "Contact alice@example.com for the escalation notes",
      context: CTX,
    });

    expect(result.decision).toBe("review");
    const records = metricsSink.list();
    expect(findMetric(records, "guardrail_evaluations_total", {
      component: "guardrails",
      tenantId: "tenant-A",
      side: "input",
      decision: "review",
    })?.value).toBe(1);
    expect(findMetric(records, "guardrail_flagged_evaluations_total", {
      component: "guardrails",
      tenantId: "tenant-A",
      side: "input",
    })?.value).toBe(1);
    expect(findMetric(records, "guardrail_findings_total", {
      component: "guardrails",
      tenantId: "tenant-A",
      side: "input",
      ruleId: "INPUT_PII_EMAIL",
      severity: "medium",
    })?.value).toBe(1);
  });

  it("keeps default no-op monitoring behavior compatible with existing event emission", () => {
    const sink = new InMemoryEventSink();
    const engine = new GuardrailEngine(
      new PIIDetector(),
      new PromptInjectionDetector(),
      new PolicyEngine(),
      new ApprovalGate(new InMemoryEventSink()),
      sink,
      new NoopGuardrailDecisionMonitor(),
    );

    engine.evaluateResponse("clean response", CTX);

    expect(sink.size()).toBe(1);
    expect(sink.list()[0].type).toBe("guardrail_evaluation");
    expect(sink.list()[0].side).toBe("output");
  });
});
