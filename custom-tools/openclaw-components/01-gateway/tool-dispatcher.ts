// ⚠️ STUB — this file was named in Component 1's folder layout but
//     NO source code was provided.
//
//     The intent appears to be a Gateway-side façade that delegates
//     to Component 3's real `ToolDispatcher` (`../03-tooling/tool-dispatcher.ts`).
//     Wiring it that way avoids duplication.
//
//     This stub re-exports so existing imports `from "./tool-dispatcher"`
//     resolve to the Component 3 implementation.
//
//     Replace with the real source if a Gateway-specific variant was
//     intended. See ../GAPS.md (Component 1 row).

export {
  ToolDispatcher,
} from "../03-tooling/tool-dispatcher";
export type {
  ToolRequest,
  ToolResult,
  ToolContext,
  ToolDefinition,
  RiskLevel,
} from "../03-tooling/types";
