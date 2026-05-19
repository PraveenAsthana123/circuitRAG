// Negative drills for Iter 112 (2026-05-18): WorkflowStatus
// transition graph validator. Locks the legal-transition contract
// so a refactor that adds a new status MUST update the graph; a
// move that skips an illegal transition fails loudly.

import { describe, it, expect } from "vitest";
import {
  LEGAL_TRANSITIONS,
  isLegalTransition,
  assertLegalTransition,
  isTerminal,
  reachableStatuses,
  WorkflowIllegalTransitionError,
} from "./workflow-status-transitions";
import { WorkflowStatus } from "./types";

const ALL_STATUSES: WorkflowStatus[] = [
  "created", "planning", "awaiting_approval", "executing",
  "replanning", "completed", "failed", "rolled_back",
];

describe("Iter 112 — WorkflowStatus transitions (P1)", () => {
  it("BACKDOOR: every WorkflowStatus has an entry in LEGAL_TRANSITIONS", () => {
    // If a future iter adds a new status to types.ts but forgets
    // to add it here, this drill fails.
    for (const s of ALL_STATUSES) {
      expect(LEGAL_TRANSITIONS[s]).toBeDefined();
      expect(Array.isArray(LEGAL_TRANSITIONS[s])).toBe(true);
    }
  });

  it("BACKDOOR: 'rolled_back' is terminal (zero legal next states)", () => {
    expect(LEGAL_TRANSITIONS.rolled_back).toEqual([]);
    expect(isTerminal("rolled_back")).toBe(true);
  });

  it("BACKDOOR: every non-terminal status has ≥1 legal next state", () => {
    for (const s of ALL_STATUSES) {
      if (s === "rolled_back") continue;
      expect(LEGAL_TRANSITIONS[s].length).toBeGreaterThan(0);
    }
  });

  it("BACKDOOR: every status (except 'created') is reachable from 'created'", () => {
    // If a new status lands and the graph doesn't connect it back
    // to the root, this drill fails. Forces the engine's lifecycle
    // graph to remain fully connected.
    const reach = reachableStatuses("created");
    reach.add("created");  // start node itself
    for (const s of ALL_STATUSES) {
      expect(reach.has(s)).toBe(true);
    }
  });

  it("BACKDOOR: 'completed' → 'executing' is ILLEGAL (cannot resume completed)", () => {
    expect(isLegalTransition("completed", "executing")).toBe(false);
    expect(() => assertLegalTransition("completed", "executing"))
      .toThrow(WorkflowIllegalTransitionError);
  });

  it("BACKDOOR: 'rolled_back' → anything is ILLEGAL (terminal)", () => {
    for (const target of ALL_STATUSES) {
      expect(isLegalTransition("rolled_back", target)).toBe(false);
    }
  });

  it("BACKDOOR: 'created' → 'completed' is ILLEGAL (must go through executing)", () => {
    // A workflow can't jump straight to completed without executing
    // at least one step.
    expect(isLegalTransition("created", "completed")).toBe(false);
  });

  it("BACKDOOR: 'executing' → 'executing' IS legal (continued step iteration)", () => {
    // Engine stays in executing across runNext() calls; identity
    // transition must be allowed.
    expect(isLegalTransition("executing", "executing")).toBe(true);
  });

  it("'executing' → 'replanning' is legal (recovery path)", () => {
    expect(isLegalTransition("executing", "replanning")).toBe(true);
  });

  it("'replanning' → 'executing' is legal (post-replan resumption)", () => {
    expect(isLegalTransition("replanning", "executing")).toBe(true);
  });

  it("'failed' → 'rolled_back' is legal (rollback recovery)", () => {
    expect(isLegalTransition("failed", "rolled_back")).toBe(true);
  });

  it("'failed' → 'replanning' is legal (operator-driven retry)", () => {
    expect(isLegalTransition("failed", "replanning")).toBe(true);
  });

  it("'completed' → 'rolled_back' is legal (post-hoc compensation)", () => {
    expect(isLegalTransition("completed", "rolled_back")).toBe(true);
  });

  it("'awaiting_approval' → 'rolled_back' is legal (rejected approval rollback)", () => {
    expect(isLegalTransition("awaiting_approval", "rolled_back")).toBe(true);
  });

  it("BACKDOOR: error message names BOTH from and to + lists legal options", () => {
    try {
      assertLegalTransition("rolled_back", "executing");
      throw new Error("expected throw");
    } catch (e) {
      expect(e).toBeInstanceOf(WorkflowIllegalTransitionError);
      const err = e as WorkflowIllegalTransitionError;
      expect(err.from).toBe("rolled_back");
      expect(err.to).toBe("executing");
      expect(err.message).toContain("rolled_back");
      expect(err.message).toContain("executing");
      expect(err.message).toContain("(terminal)");
    }
  });

  it("BACKDOOR: error message lists legal options on a NON-terminal violation", () => {
    try {
      assertLegalTransition("created", "completed");
      throw new Error("expected throw");
    } catch (e) {
      const err = e as WorkflowIllegalTransitionError;
      // Legal from 'created' is [planning, failed]
      expect(err.message).toContain("planning");
      expect(err.message).toContain("failed");
    }
  });

  it("WorkflowIllegalTransitionError instanceof Error + carries from/to", () => {
    const e = new WorkflowIllegalTransitionError("created", "completed");
    expect(e).toBeInstanceOf(Error);
    expect(e.name).toBe("WorkflowIllegalTransitionError");
    expect(e.from).toBe("created");
    expect(e.to).toBe("completed");
  });

  it("isTerminal only true for 'rolled_back' (the single terminal state today)", () => {
    for (const s of ALL_STATUSES) {
      expect(isTerminal(s)).toBe(s === "rolled_back");
    }
  });

  it("reachableStatuses from a terminal returns empty set", () => {
    expect(reachableStatuses("rolled_back").size).toBe(0);
  });

  it("reachableStatuses from 'created' covers all 8 statuses (full graph connectivity)", () => {
    const reach = reachableStatuses("created");
    // 'created' itself isn't in reachableStatuses(created) by
    // convention (it's the start node); the other 7 must be.
    expect(reach.size).toBe(7);
    expect(reach.has("completed")).toBe(true);
    expect(reach.has("rolled_back")).toBe(true);
  });
});
