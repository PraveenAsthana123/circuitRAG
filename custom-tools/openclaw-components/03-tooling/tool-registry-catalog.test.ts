import { describe, expect, it } from "vitest";
import { calculatorTool } from "./calculator-tool";
import {
  createToolSignature,
  ToolCatalogViolationError,
  ToolRegistry,
} from "./tool-registry";
import { ToolDefinition } from "./types";

const cloneTool = (overrides: Partial<ToolDefinition> = {}): ToolDefinition => ({
  ...calculatorTool,
  allowedRoles: [...calculatorTool.allowedRoles],
  ...overrides,
});

describe("ToolRegistry pinned catalog", () => {
  it("registers a tool whose metadata matches the pinned signature", () => {
    const signature = createToolSignature(calculatorTool);
    const registry = new ToolRegistry({
      catalog: [{ name: calculatorTool.name, signature }],
    });

    registry.register(calculatorTool);

    expect(registry.get("calculator")).toBe(calculatorTool);
    expect(registry.signatureFor("calculator")).toBe(signature);
  });

  it("BACKDOOR: rejects a tool not present in the pinned catalog", () => {
    const registry = new ToolRegistry({
      catalog: [{ name: "other", signature: "sha256-placeholder" }],
    });

    expect(() => registry.register(calculatorTool)).toThrow(ToolCatalogViolationError);
    expect(() => registry.get("calculator")).toThrow("Tool not found");
  });

  it("BACKDOOR: rejects metadata tampering after signature approval", () => {
    const signature = createToolSignature(calculatorTool);
    const tampered = cloneTool({ riskLevel: "high" });
    const registry = new ToolRegistry({
      catalog: [{ name: calculatorTool.name, signature }],
    });

    expect(() => registry.register(tampered)).toThrow("Tool signature mismatch");
  });

  it("role order does not change the signature", () => {
    const base = cloneTool({ allowedRoles: ["admin", "user"] });
    const reordered = cloneTool({ allowedRoles: ["user", "admin"] });

    expect(createToolSignature(base)).toBe(createToolSignature(reordered));
  });

  it("can publish signatures without enforcing catalog in local mode", () => {
    const registry = new ToolRegistry({
      catalog: [{ name: "other", signature: "sha256-placeholder" }],
      enforceCatalog: false,
    });

    registry.register(calculatorTool);

    expect(registry.signatureFor("calculator")).toBe(createToolSignature(calculatorTool));
  });
});
