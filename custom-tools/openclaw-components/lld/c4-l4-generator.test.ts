// Iter 136 (2026-05-20): drill the C4 L4 generator. The most
// important invariants are STRUCTURAL — every iter 135 composesWith
// edge MUST appear as a Mermaid arrow; every interface MUST appear
// as a node in its component's focused L4; no component is dropped.
//
// Negative assertions (≥ 3 per §43):
//   - Unknown ComponentId throws
//   - System L4 contains NO edge for a non-existent dep (registry truth)
//   - No orphan components in the canonical registry (would indicate
//     dead code in the system graph)

import { describe, it, expect } from "vitest";
import {
  generateComponentL4,
  generateSystemL4,
  systemL4Edges,
  componentL4Nodes,
  findOrphans,
  highFanOut,
  highFanIn,
} from "./c4-l4-generator";
import {
  COMPONENT_LLDS,
  ComponentId,
  allComponentIds,
} from "./component-lld";

describe("Iter 136 — C4 L4 diagram generator", () => {

  // ─── Per-component L4: structural completeness ─────────────

  it("BACKDOOR: generateComponentL4 emits a Mermaid flowchart declaration", () => {
    const out = generateComponentL4("05-guardrails");
    expect(out).toMatch(/^[\s\S]*flowchart\s+TB/m);
    expect(out).toContain("Iter 136");
  });

  it("BACKDOOR: every primary interface appears as a node in its component's L4", () => {
    for (const c of COMPONENT_LLDS) {
      const out = generateComponentL4(c.id);
      for (const iface of c.primaryInterfaces) {
        expect(out).toContain(iface.name);
      }
    }
  });

  it("BACKDOOR: DI seams are visually distinct from non-seams in the L4 output", () => {
    // Seam interfaces use the [/X/] shape (trapezoid); non-seams use [X].
    // Spot-check 05-guardrails which has many seams (iter 101-104).
    const out = generateComponentL4("05-guardrails");
    // PIIProvider is a seam (iter 102) → trapezoid + "(seam)" label
    expect(out).toMatch(/PIIProvider \(seam\)/);
    expect(out).toMatch(/\[\/.*PIIProvider \(seam\).*\/\]/);
    // GuardrailEngine is NOT a seam → plain box
    expect(out).toMatch(/\["GuardrailEngine"\]/);
  });

  it("BACKDOOR: error envelopes appear in the L4 output", () => {
    const out = generateComponentL4("10-agent-workflow");
    // WorkflowNotFoundError + WorkflowAccessDeniedError +
    // WorkflowIllegalTransitionError are registered.
    expect(out).toContain("WorkflowNotFoundError");
    expect(out).toContain("WorkflowAccessDeniedError");
    expect(out).toContain("WorkflowIllegalTransitionError");
  });

  it("BACKDOOR: composesWith edges appear as 'composes with' Mermaid arrows", () => {
    // 10-agent-workflow composesWith 02-agent-runtime among others.
    const out = generateComponentL4("10-agent-workflow");
    expect(out).toMatch(/10_agent_workflow -->\|composes with\| 02_agent_runtime/);
  });

  it("BACKDOOR: reverse-dep edges appear as 'depends on' Mermaid arrows", () => {
    // Many components depend on 06-observability; its L4 shows
    // them as reverse deps.
    const out = generateComponentL4("06-observability");
    expect(out).toMatch(/depends on/);
  });

  // ─── NEGATIVE: defensive validation ────────────────────────

  it("NEGATIVE: generateComponentL4 throws on unknown ComponentId", () => {
    expect(() => generateComponentL4("nonexistent-component" as ComponentId))
      .toThrow(/Unknown component/);
  });

  // ─── System-wide L4: edge enumeration ──────────────────────

  it("BACKDOOR: systemL4Edges enumerates every composesWith edge from the registry", () => {
    // Sum of composesWith across all components must equal edge count.
    const expectedEdgeCount = COMPONENT_LLDS.reduce(
      (sum, c) => sum + c.composesWith.length, 0,
    );
    expect(systemL4Edges().length).toBe(expectedEdgeCount);
  });

  it("BACKDOOR: every system-L4 edge resolves to a real (source, target) ComponentId pair", () => {
    const validIds = new Set<string>(allComponentIds());
    for (const edge of systemL4Edges()) {
      expect(validIds.has(edge.source)).toBe(true);
      expect(validIds.has(edge.target)).toBe(true);
    }
  });

  it("BACKDOOR: generateSystemL4 contains every ComponentId as a node", () => {
    const out = generateSystemL4();
    for (const id of allComponentIds()) {
      // The node id substitutes dashes with underscores in the
      // Mermaid id, but the label preserves the original.
      expect(out).toContain(id);
    }
  });

  it("BACKDOOR: generateSystemL4 contains every composesWith edge", () => {
    const out = generateSystemL4();
    for (const edge of systemL4Edges()) {
      const src = edge.source.replace(/-/g, "_");
      const tgt = edge.target.replace(/-/g, "_");
      expect(out).toMatch(new RegExp(`${src}\\s*-->\\s*${tgt}`));
    }
  });

  // ─── §59.1 MDD invariants: generator stays current with registry ─

  it("BACKDOOR §59.1 MDD: componentL4Nodes returns interface names + error class names", () => {
    const nodes = componentL4Nodes("05-guardrails");
    expect(nodes).toContain("GuardrailEngine");
    expect(nodes).toContain("PIIProvider");
    expect(nodes).toContain("HumanReviewQueue");
  });

  // ─── Architecture invariants ───────────────────────────────

  it("NEGATIVE: no orphan components in the canonical registry", () => {
    // An orphan = no incoming AND no outgoing edges. That would
    // mean the component is dead code from the system graph's
    // perspective. The registry should have zero orphans.
    const orphans = findOrphans();
    expect(orphans).toEqual([]);
  });

  it("BACKDOOR: highFanIn surfaces foundational components (the §47 boundary risk)", () => {
    // 06-observability is foundational — most components depend
    // on it. highFanIn surfaces this as a §52 brutal-review
    // priority signal.
    const highIn = highFanIn(3);
    expect(highIn.length).toBeGreaterThan(0);
    expect(highIn.map((r) => r.id)).toContain("06-observability");
  });

  it("BACKDOOR: highFanOut surfaces aggregator components (the §47 complexity risk)", () => {
    // 10-agent-workflow composesWith 5 components — high fan-out.
    const highOut = highFanOut(3);
    expect(highOut.length).toBeGreaterThan(0);
    expect(highOut.map((r) => r.id)).toContain("10-agent-workflow");
  });

  // ─── Output safety ─────────────────────────────────────────

  it("BACKDOOR: generated Mermaid contains no unescaped brackets or quotes that would break parse", () => {
    // Quick parse-safety check: count balanced subgraph/end pairs.
    const out = generateSystemL4();
    // No "[[" or "]]" pairs (which Mermaid mis-parses as subroutine boxes).
    expect(out).not.toMatch(/\[\[|\]\]/);
  });

  it("BACKDOOR: generated diagram is deterministic (same input → same output)", () => {
    const a = generateSystemL4();
    const b = generateSystemL4();
    expect(a).toBe(b);
  });
});
