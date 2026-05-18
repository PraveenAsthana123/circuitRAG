// Negative drills for Iter 78 (2026-05-17): ExplainabilityRecorder
// log-payload contract drill.
//
// Pre-fix: ExplainabilityRecorder.recordDecision() emits one
// JSON log line per tool dispatch, but the payload SHAPE was never
// drilled. Per CLAUDE.md §48 this log is the foundation of tool-
// decision audit + explainability for compliance review. Downstream
// log shippers, SIEM parsers, and dashboards all consume this
// payload by field name; silent shape drift breaks all of them at
// once with no compile-time signal.
//
// This drill locks the wire-level payload contract so a refactor
// that renames "toolName" → "tool" (or similar) fails loudly at
// PR time rather than silently breaking production observability.

import { describe, it, expect, vi } from "vitest";
import { ExplainabilityRecorder } from "./explainability-recorder";
import { ToolRequest, ToolResult } from "./types";

const RECORDER = new ExplainabilityRecorder();

const REQ: ToolRequest = {
  toolName: "calculator",
  input: { expression: "1+1" },
  idempotencyKey: "idem-1",
  context: {
    requestId: "req-1",
    sessionId: "sess-1",
    userId: "user-1",
    tenantId: "tenant-1",
    traceId: "trace-1",
  },
};

const OK_RESULT: ToolResult = {
  success: true,
  output: { result: 2 },
  durationMs: 42,
};

const FAIL_RESULT: ToolResult = {
  success: false,
  error: "tool blew up",
  durationMs: 10,
};

// Capture the parsed payload from a single recordDecision call.
function captureOne(
  request: ToolRequest = REQ,
  result: ToolResult = OK_RESULT,
  reason: string = "passed",
): Record<string, unknown> {
  const log = vi.spyOn(console, "log").mockImplementation(() => {});
  try {
    RECORDER.recordDecision(request, result, reason);
    expect(log.mock.calls.length).toBe(1);
    const raw = log.mock.calls[0][0] as string;
    return JSON.parse(raw) as Record<string, unknown>;
  } finally {
    log.mockRestore();
  }
}

describe("Iter 78 — ExplainabilityRecorder payload contract (P1)", () => {
  it("BACKDOOR: payload carries the canonical field set", () => {
    const payload = captureOne();
    // These field NAMES are the contract — downstream parsers
    // depend on each by name. A refactor that renames any of
    // these breaks log shippers, SIEM rules, dashboards.
    expect(payload.type).toBe("explainability");
    expect(payload.requestId).toBe("req-1");
    expect(payload.sessionId).toBe("sess-1");
    expect(payload.toolName).toBe("calculator");
    expect(payload.reason).toBe("passed");
    expect(payload.success).toBe(true);
    expect(payload.durationMs).toBe(42);
    expect(typeof payload.timestamp).toBe("string");
  });

  it("BACKDOOR: emits EXACTLY one log line per recordDecision call", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      RECORDER.recordDecision(REQ, OK_RESULT, "passed");
      expect(log.mock.calls.length).toBe(1);
    } finally {
      log.mockRestore();
    }
  });

  it("payload.timestamp is a valid ISO-8601 string (parseable Date)", () => {
    const payload = captureOne();
    const parsed = new Date(payload.timestamp as string);
    expect(parsed.toISOString()).toBe(payload.timestamp);
    // Within 5s of now (test execution).
    expect(Math.abs(parsed.getTime() - Date.now())).toBeLessThan(5000);
  });

  it("payload reflects failure result with success=false (regression)", () => {
    const payload = captureOne(REQ, FAIL_RESULT, "validation failed");
    expect(payload.success).toBe(false);
    expect(payload.reason).toBe("validation failed");
    expect(payload.durationMs).toBe(10);
    // Failure-side payload does NOT leak the error message into
    // the explainability log (that's the dispatcher's logger.error
    // job, not the explainability log). Locks the separation
    // of concerns.
    expect(payload.error).toBeUndefined();
  });

  it("payload does NOT echo the raw tool input (privacy: input may contain user PII)", () => {
    // The current contract: explainability captures decision-shape,
    // NOT raw caller input. A future "enrich explainability with
    // input snapshot" feature must explicitly opt-in via a separate
    // field (e.g., inputDigest). Lock the current omission so a
    // refactor that adds payload.input doesn't silently leak PII
    // into the audit log.
    const sensitive: ToolRequest = {
      ...REQ,
      input: { ssn: "123-45-6789", email: "user@example.com" },
    };
    const payload = captureOne(sensitive);
    expect(payload.input).toBeUndefined();
    // And the raw values don't appear ANYWHERE in the JSON string.
    const raw = JSON.stringify(payload);
    expect(raw).not.toContain("123-45-6789");
    expect(raw).not.toContain("user@example.com");
  });

  it("payload does NOT echo the raw tool output (similar privacy contract)", () => {
    const sensitive: ToolResult = {
      success: true,
      output: { creditCard: "4111111111111111" },
      durationMs: 5,
    };
    const payload = captureOne(REQ, sensitive, "ok");
    expect(payload.output).toBeUndefined();
    expect(JSON.stringify(payload)).not.toContain("4111111111111111");
  });

  it("payload does NOT include tenantId (multi-tenant log-shipping consideration)", () => {
    // tenantId is in request.context but NOT in the current payload.
    // Some log-shipping setups route by tenantId at the ingestion
    // boundary; others rely on traceId-based correlation. Lock the
    // current omission so a refactor that adds payload.tenantId
    // doesn't silently change the routing topology assumption.
    const payload = captureOne();
    expect(payload.tenantId).toBeUndefined();
  });

  it("payload does NOT include traceId either (same contract)", () => {
    const payload = captureOne();
    expect(payload.traceId).toBeUndefined();
  });

  it("payload does NOT include idempotencyKey (caller's correlation token)", () => {
    const payload = captureOne();
    expect(payload.idempotencyKey).toBeUndefined();
  });

  it("invariant: payload field set is EXACTLY these 7 keys + nothing more", () => {
    // The strongest contract assertion — if a future refactor adds
    // ANY new field to the payload, this drill fails loudly. Forces
    // a deliberate decision (update this test + audit downstream
    // consumers) rather than silent shape drift.
    const payload = captureOne();
    const keys = Object.keys(payload).sort();
    expect(keys).toEqual(
      ["durationMs", "reason", "requestId", "sessionId", "success", "timestamp", "toolName", "type"].sort(),
    );
  });

  it("payload is single-line newline-free JSON (log shipper safety)", () => {
    // Log shippers that split on \n must see one record per line.
    // If JSON.stringify ever switched to pretty-printing, that
    // assumption breaks silently. Lock it.
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      RECORDER.recordDecision(REQ, OK_RESULT, "passed");
      const raw = log.mock.calls[0][0] as string;
      expect(raw).not.toContain("\n");
    } finally {
      log.mockRestore();
    }
  });
});
