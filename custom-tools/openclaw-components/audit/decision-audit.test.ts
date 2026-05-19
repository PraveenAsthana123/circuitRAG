// Negative drills for Iter 110 (2026-05-18): DecisionAuditWriter
// schema-fingerprint + sink-injection. Locks the §38-compliant
// agentic-decision audit row contract.

import { describe, it, expect, vi } from "vitest";
import {
  DecisionAuditWriter,
  DecisionAuditRow,
  DecisionKind,
  hashContent,
} from "./decision-audit";
import {
  InMemoryEventSink,
  EventSink,
  EventRecord,
} from "../06-observability/sinks";

const BASE: Omit<DecisionAuditRow, "auditId" | "schemaVersion" | "timestamp"> = {
  requestId: "r-1",
  tenantId: "t-1",
  userId: "u-1",
  kind: "tool",
  disposition: "allow",
  actor: "agent",
};

describe("Iter 110 — DecisionAuditWriter (P0)", () => {
  it("BACKDOOR: default sink emits to console; row populates auto-fields", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const row = new DecisionAuditWriter().write(BASE);
      // Auto-populated:
      expect(row.auditId).toMatch(/^[0-9a-f-]{36}$/);
      expect(row.schemaVersion).toBe(1);
      expect(row.timestamp).toBeDefined();
      expect(new Date(row.timestamp).toISOString()).toBe(row.timestamp);
      // One log emission with the canonical type.
      const events = log.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "decision_audit");
      expect(events.length).toBe(1);
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: injected sink captures the row; console silent", () => {
    const sink = new InMemoryEventSink();
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new DecisionAuditWriter(sink).write(BASE);
      expect(sink.size()).toBe(1);
      expect(sink.list()[0].type).toBe("decision_audit");
      expect(sink.list()[0].kind).toBe("tool");
      expect(log.mock.calls.length).toBe(0);
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: schemaVersion is locked to 1 (caller cannot override)", () => {
    const sink = new InMemoryEventSink();
    // TypeScript prevents passing schemaVersion in the input;
    // attempting to bypass via spread should still be overridden.
    const writer = new DecisionAuditWriter(sink);
    const row = writer.write({
      ...BASE,
      // @ts-expect-error caller shouldn't pass these
      schemaVersion: 999,
      auditId: "FAKE",
    });
    expect(row.schemaVersion).toBe(1);  // not 999
    expect(row.auditId).not.toBe("FAKE");
  });

  it("each write yields a UNIQUE auditId (no recycling)", () => {
    const sink = new InMemoryEventSink();
    const writer = new DecisionAuditWriter(sink);
    const a = writer.write(BASE);
    const b = writer.write(BASE);
    expect(a.auditId).not.toBe(b.auditId);
  });

  it("BACKDOOR: every DecisionKind is accepted (enum coverage)", () => {
    const kinds: DecisionKind[] = [
      "plan", "tool", "llm", "rag", "guardrail", "approval", "rollback", "abandon",
    ];
    const sink = new InMemoryEventSink();
    const writer = new DecisionAuditWriter(sink);
    for (const kind of kinds) {
      writer.write({ ...BASE, kind });
    }
    expect(sink.size()).toBe(8);
    const seen = new Set(sink.list().map((r) => r.kind));
    expect(seen.size).toBe(8);
  });

  it("BACKDOOR: every disposition is accepted (enum coverage)", () => {
    const sink = new InMemoryEventSink();
    const writer = new DecisionAuditWriter(sink);
    for (const disp of ["allow", "review", "block", "fail"] as const) {
      writer.write({ ...BASE, disposition: disp });
    }
    const dispositions = sink.list().map((r) => r.disposition).sort();
    expect(dispositions).toEqual(["allow", "block", "fail", "review"]);
  });

  it("optional fields ride through unchanged (forensic completeness)", () => {
    const sink = new InMemoryEventSink();
    const writer = new DecisionAuditWriter(sink);
    writer.write({
      ...BASE,
      traceId: "tr-1",
      sessionId: "s-1",
      workflowId: "wf-1",
      stepId: "st-1",
      modelId: "gpt-4o",
      toolName: "calculator",
      durationMs: 42,
      confidence: 0.87,
      inputHash: hashContent({ q: "hi" }),
      outputHash: hashContent({ a: "ok" }),
      policyVersion: "v3",
      rulesApplied: ["pii-mask", "tenant-isolation"],
      explanation: {
        method: "shap",
        topFactors: [{ name: "income", weight: 0.43 }, { name: "history", weight: 0.31 }],
        counterfactual: "If income > $50k, decision would be approve",
        modelCardId: "gpt-4o:2024-08",
        promptVersion: "v12",
      },
      citations: [
        { chunkId: "c-1", documentId: "d-1", spanStart: 100, spanEnd: 150, score: 0.91 },
      ],
    });
    const r = sink.list()[0];
    expect(r.traceId).toBe("tr-1");
    expect(r.workflowId).toBe("wf-1");
    expect(r.modelId).toBe("gpt-4o");
    expect(r.confidence).toBe(0.87);
    expect((r.explanation as { method: string }).method).toBe("shap");
    expect((r.citations as unknown[]).length).toBe(1);
    expect((r.rulesApplied as string[]).length).toBe(2);
  });

  it("BACKDOOR: hashContent is deterministic across runs", () => {
    const a = hashContent({ q: "hello", n: 42 });
    const b = hashContent({ q: "hello", n: 42 });
    expect(a).toBe(b);
    expect(a).toHaveLength(64);  // SHA-256 hex
  });

  it("hashContent yields DIFFERENT digests for different inputs", () => {
    expect(hashContent({ q: "a" })).not.toBe(hashContent({ q: "b" }));
    expect(hashContent({ q: "a" })).not.toBe(hashContent({ q: "A" }));
  });

  it("hashContent handles undefined / null / primitives", () => {
    expect(hashContent(undefined)).toBe(hashContent(null));
    expect(hashContent(42)).toHaveLength(64);
    expect(hashContent("string")).toHaveLength(64);
  });

  it("failure-decision shape carries error fields (kind === 'tool' + disposition === 'fail')", () => {
    const sink = new InMemoryEventSink();
    new DecisionAuditWriter(sink).write({
      ...BASE,
      disposition: "fail",
      errorName: "TimeoutError",
      errorMessage: "tool exceeded 5000ms",
      retryCount: 2,
    });
    const r = sink.list()[0];
    expect(r.disposition).toBe("fail");
    expect(r.errorName).toBe("TimeoutError");
    expect(r.errorMessage).toBe("tool exceeded 5000ms");
    expect(r.retryCount).toBe(2);
  });

  it("custom sink can route to durable Postgres audit table (extension point)", () => {
    const captured: EventRecord[] = [];
    class PostgresAuditSink implements EventSink {
      emit(r: EventRecord): void { captured.push(r); }
    }
    new DecisionAuditWriter(new PostgresAuditSink()).write(BASE);
    expect(captured.length).toBe(1);
    expect(captured[0].type).toBe("decision_audit");
  });

  it("payload is single-line newline-free JSON (log-shipper safety)", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new DecisionAuditWriter().write(BASE);
      expect((log.mock.calls[0][0] as string)).not.toContain("\n");
    } finally {
      log.mockRestore();
    }
  });

  it("schema-fingerprint: row's canonical keys lock the public contract", () => {
    const sink = new InMemoryEventSink();
    new DecisionAuditWriter(sink).write({
      ...BASE,
      traceId: "t", sessionId: "s", workflowId: "w", stepId: "st",
      modelId: "m", toolName: "tn", durationMs: 1, confidence: 0.5,
      inputHash: "h", outputHash: "h",
      explanation: { method: "rule" }, citations: [],
      policyVersion: "v1", rulesApplied: [], errorName: "E",
      errorMessage: "msg", retryCount: 0,
    });
    const r = sink.list()[0];
    // type prefix added by writer.
    expect(r.type).toBe("decision_audit");
    // Required keys MUST be present.
    expect(r.auditId).toBeDefined();
    expect(r.schemaVersion).toBe(1);
    expect(r.timestamp).toBeDefined();
    expect(r.requestId).toBeDefined();
    expect(r.tenantId).toBeDefined();
    expect(r.userId).toBeDefined();
    expect(r.kind).toBeDefined();
    expect(r.disposition).toBeDefined();
    expect(r.actor).toBeDefined();
  });
});
