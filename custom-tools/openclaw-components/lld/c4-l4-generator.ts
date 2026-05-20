// Iter 136 (2026-05-20): C4 L4 (component-level) Mermaid diagram
// generator. Closes P1 GAPS row "§1–§3 C4 diagrams have no L4 (code)
// level — that's where most production gaps actually live."
//
// L4 is the code-level C4 view: each component's PUBLIC interfaces +
// errors + DI seams + runtime dependencies. The §47.2 CLAUDE.md
// L1-L7 catalog calls L4 mandatory; until this iter we had L1-L3
// in docs but no L4. This iter generates L4 mechanically from the
// iter 135 LLD registry, so:
//
//   1. The diagram stays current automatically — when a new seam
//      lands in the registry, the diagram updates on next generation.
//   2. The §59.1 MDD payoff compounds: registry = model, LLD JSON =
//      one derivation, Mermaid diagram = second derivation.
//   3. The diagram source is committed to git (not a runtime-only
//      artifact) so reviewers can read it without running code.
//
// Two diagram modes:
//   generateComponentL4(id) — focused L4 for one component: interfaces
//                              + seams + this component's external edges
//   generateSystemL4()     — full dependency graph across all 10
//                              components (composes-with edges only)
//
// Per CLAUDE.md §43 (drillable — structural validity asserted),
// §47.2 (L1-L7 C4 catalog; this iter is the L4 piece), §53 item 42
// (the diagram is the operator-readable visual artifact),
// §57.7 (generated from registry, not hand-drawn — can't drift),
// §59.1 MDD.

import {
  COMPONENT_LLDS,
  ComponentId,
  lldFor,
  componentsThatCompose,
  ComponentLLD,
  InterfaceDef,
} from "./component-lld";

// ───────────────────────────── Helpers ────────────────────────────

/** Convert a ComponentId (e.g., "05-guardrails") into a Mermaid-
 *  safe node ID (no dashes — Mermaid treats them as range operators). */
function nodeId(id: ComponentId): string {
  return id.replace(/-/g, "_");
}

/** Mermaid-safe symbol name. */
function symbolId(componentId: ComponentId, name: string): string {
  return `${nodeId(componentId)}__${name.replace(/[^A-Za-z0-9_]/g, "_")}`;
}

/** Escape brackets / quotes that Mermaid mis-parses. */
function escapeLabel(s: string): string {
  return s.replace(/["[\]]/g, "");
}

// ───────────────────────────── Per-component L4 ───────────────────

export function generateComponentL4(id: ComponentId): string {
  const lld = lldFor(id);
  if (!lld) throw new Error(`Unknown component: ${id}`);

  const lines: string[] = [];
  lines.push(`%% Iter 136 — C4 L4 for ${id} (auto-generated from LLD registry; do not edit by hand)`);
  lines.push(`%% Owner: ${lld.owner}  Risk: ${lld.riskCategories.join(",")}`);
  lines.push("flowchart TB");

  // Subgraph for the focal component with its interfaces inside.
  lines.push(`  subgraph ${nodeId(id)}["${escapeLabel(id)} — ${escapeLabel(lld.description.slice(0, 60))}…"]`);
  lines.push("    direction TB");
  for (const iface of lld.primaryInterfaces) {
    const node = symbolId(id, iface.name);
    // Seam = dashed-border subgraph-style ("/X/"); plain = box ("[X]").
    const shape = iface.isSeam ? `[/"${escapeLabel(iface.name)} (seam)"/]` : `["${escapeLabel(iface.name)}"]`;
    lines.push(`    ${node}${shape}`);
  }
  // Error envelopes as a distinct row of cylinder-shaped nodes.
  for (const env of lld.errorEnvelopes) {
    const node = symbolId(id, "err_" + env.className);
    lines.push(`    ${node}[("${escapeLabel(env.className)}")]`);
  }
  lines.push("  end");

  // External composes-with edges (this component depends on these).
  for (const dep of lld.composesWith) {
    const depLld = lldFor(dep);
    if (!depLld) continue;
    lines.push(`  ${nodeId(id)} -->|composes with| ${nodeId(dep)}["${escapeLabel(dep)}"]`);
  }

  // Reverse-dep edges (these components depend on the focal component).
  for (const reverseDep of componentsThatCompose(id)) {
    lines.push(`  ${nodeId(reverseDep)}["${escapeLabel(reverseDep)}"] -.->|depends on| ${nodeId(id)}`);
  }

  return lines.join("\n");
}

// ───────────────────────────── System-wide L4 ─────────────────────

export function generateSystemL4(): string {
  const lines: string[] = [];
  lines.push("%% Iter 136 — System-wide C4 L4 (composes-with graph across all openclaw components)");
  lines.push("%% Auto-generated from LLD registry; do not edit by hand");
  lines.push("flowchart LR");

  // Every component as a node.
  for (const c of COMPONENT_LLDS) {
    const seamCount = c.primaryInterfaces.filter((i) => i.isSeam).length;
    const label = `${c.id}<br/>${seamCount} seam${seamCount === 1 ? "" : "s"} • ${c.owner}`;
    lines.push(`  ${nodeId(c.id)}["${escapeLabel(label)}"]`);
  }

  lines.push("");

  // Every composes-with edge.
  for (const c of COMPONENT_LLDS) {
    for (const dep of c.composesWith) {
      lines.push(`  ${nodeId(c.id)} --> ${nodeId(dep)}`);
    }
  }

  return lines.join("\n");
}

// ───────────────────────────── Structured introspection ───────────

/** Returns the set of (source, target) edges produced by the
 *  system-wide L4. Used by the drill to confirm every composesWith
 *  resolves to a Mermaid arrow. */
export interface L4Edge {
  readonly source: ComponentId;
  readonly target: ComponentId;
}

export function systemL4Edges(): ReadonlyArray<L4Edge> {
  const edges: L4Edge[] = [];
  for (const c of COMPONENT_LLDS) {
    for (const dep of c.composesWith) {
      edges.push({ source: c.id, target: dep });
    }
  }
  return edges;
}

/** Returns the set of interface nodes that would appear in a
 *  focused L4 for `id`. Used by drills to confirm coverage. */
export function componentL4Nodes(id: ComponentId): ReadonlyArray<string> {
  const lld = lldFor(id);
  if (!lld) return [];
  return [
    ...lld.primaryInterfaces.map((i) => i.name),
    ...lld.errorEnvelopes.map((e) => e.className),
  ];
}

/** Reports any orphan components (no incoming AND no outgoing edges)
 *  — these would be code-level dead-ends in the system graph. */
export function findOrphans(): ReadonlyArray<ComponentId> {
  return COMPONENT_LLDS
    .filter((c) => c.composesWith.length === 0 && componentsThatCompose(c.id).length === 0)
    .map((c) => c.id);
}

/** Returns components that compose into many others (high fan-out).
 *  Useful for §52 brutal review — high-fan-out boundaries get
 *  extra scrutiny. */
export function highFanOut(threshold: number = 3): ReadonlyArray<{ id: ComponentId; outDegree: number }> {
  return COMPONENT_LLDS
    .map((c) => ({ id: c.id, outDegree: c.composesWith.length }))
    .filter((r) => r.outDegree >= threshold)
    .sort((a, b) => b.outDegree - a.outDegree);
}

/** Returns components depended-on by many others (high fan-in).
 *  These are the foundational components whose failure cascades widely. */
export function highFanIn(threshold: number = 3): ReadonlyArray<{ id: ComponentId; inDegree: number }> {
  return COMPONENT_LLDS
    .map((c) => ({ id: c.id, inDegree: componentsThatCompose(c.id).length }))
    .filter((r) => r.inDegree >= threshold)
    .sort((a, b) => b.inDegree - a.inDegree);
}

/** Touch a typed accessor so importers know the ComponentLLD +
 *  InterfaceDef types are part of this module's public surface. */
export type { ComponentLLD, InterfaceDef };
