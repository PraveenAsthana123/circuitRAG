// ⚠️  SECURITY: This tool uses dynamic code execution via the Function
//     constructor. The regex allowlist is insufficient defense against
//     a determined attacker. See GAPS.md (Component 3, P0 row) for the
//     production fix (use `mathjs` with a restricted scope instead).
//     Kept verbatim from source paste for fidelity.

import { ToolDefinition } from "./types";

export const calculatorTool: ToolDefinition = {
  name: "calculator",
  description: "Performs safe arithmetic operations",
  riskLevel: "low",
  allowedRoles: ["user", "admin"],

  async execute(input) {
    const expression = String(input.expression ?? "");

    if (!/^[0-9+\-*/().\s]+$/.test(expression)) {
      throw new Error("Invalid arithmetic expression");
    }

    return {
      expression,
      result: Function(`"use strict"; return (${expression})`)(),
    };
  },
};
