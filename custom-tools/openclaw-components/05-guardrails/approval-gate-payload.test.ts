// Negative drills for Iter 87 (2026-05-18): ApprovalGate ticket
// payload contract. Mirrors iter 78/80/82 schema-fingerprint pattern.

import { describe, it, expect, vi } from "vitest";
import { ApprovalGate } from "./approval-gate";
import { GuardrailResult } from "./types";

const GATE = new ApprovalGate();

const REVIEW: GuardrailResult = {
  decision: "review",
  findings: [{ ruleId: "INPUT_PII_EMAIL", severity: "medium", message: "email seen" }],
  explanation: "review",
};
const BLOCK: GuardrailResult = {
  decision: "block",
  findings: [{ ruleId: "INPUT_PROMPT_INJECTION", severity: "high", message: "injection" }],
  explanation: "block",
};
const ALLOW: GuardrailResult = { decision: "allow", findings: [], explanation: "ok" };

function captureTicket(result: GuardrailResult): { ticketId: string; payload: Record<string, unknown> } {
  const log = vi.spyOn(console, "log").mockImplementation(() => {});
  try {
    const ticketId = GATE.createApprovalTicket(result);
    expect(log.mock.calls.length).toBe(1);
    return { ticketId, payload: JSON.parse(log.mock.calls[0][0] as string) };
  } finally {
    log.mockRestore();
  }
}

describe("Iter 87 — ApprovalGate ticket payload contract (P2)", () => {
  it("BACKDOOR: requiresHumanApproval true ONLY for review", () => {
    expect(GATE.requiresHumanApproval(REVIEW)).toBe(true);
    expect(GATE.requiresHumanApproval(BLOCK)).toBe(false);
    expect(GATE.requiresHumanApproval(ALLOW)).toBe(false);
  });

  it("BACKDOOR: ticket payload canonical 5-field set", () => {
    const { payload } = captureTicket(REVIEW);
    expect(payload.type).toBe("approval_ticket");
    expect(typeof payload.ticketId).toBe("string");
    expect(payload.decision).toBe("review");
    expect(payload.findings).toEqual(REVIEW.findings);
    expect(typeof payload.timestamp).toBe("string");
  });

  it("BACKDOOR: EXACT key set (schema fingerprint)", () => {
    const { payload } = captureTicket(REVIEW);
    const keys = Object.keys(payload).sort();
    expect(keys).toEqual(["decision", "findings", "ticketId", "timestamp", "type"].sort());
  });

  it("BACKDOOR: returned ticketId matches the one in the logged payload", () => {
    const { ticketId, payload } = captureTicket(REVIEW);
    expect(payload.ticketId).toBe(ticketId);
  });

  it("each call yields a UNIQUE ticketId (UUID, no recycling)", () => {
    const a = captureTicket(REVIEW);
    const b = captureTicket(REVIEW);
    expect(a.ticketId).not.toBe(b.ticketId);
    expect(a.ticketId).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
  });

  it("ticket created for BLOCK decision too (audit trail covers block, not just review)", () => {
    const { payload } = captureTicket(BLOCK);
    expect(payload.decision).toBe("block");
    expect(payload.findings).toEqual(BLOCK.findings);
  });

  it("findings serialization preserves severity + ruleId + message fields", () => {
    const result: GuardrailResult = {
      decision: "review",
      findings: [
        { ruleId: "A", severity: "low", message: "m1" },
        { ruleId: "B", severity: "critical", message: "m2" },
      ],
      explanation: "ok",
    };
    const { payload } = captureTicket(result);
    const findings = payload.findings as Array<Record<string, string>>;
    expect(findings.length).toBe(2);
    expect(findings[0]).toEqual({ ruleId: "A", severity: "low", message: "m1" });
    expect(findings[1]).toEqual({ ruleId: "B", severity: "critical", message: "m2" });
  });

  it("empty findings array preserved (not omitted)", () => {
    const result: GuardrailResult = {
      decision: "review", findings: [], explanation: "review-no-findings",
    };
    const { payload } = captureTicket(result);
    expect(payload.findings).toEqual([]);
  });

  it("payload is single-line newline-free JSON", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      GATE.createApprovalTicket(REVIEW);
      expect((log.mock.calls[0][0] as string)).not.toContain("\n");
    } finally {
      log.mockRestore();
    }
  });

  it("timestamp parseable ISO-8601 within 5s of now", () => {
    const { payload } = captureTicket(REVIEW);
    const d = new Date(payload.timestamp as string);
    expect(d.toISOString()).toBe(payload.timestamp);
    expect(Math.abs(d.getTime() - Date.now())).toBeLessThan(5000);
  });
});
