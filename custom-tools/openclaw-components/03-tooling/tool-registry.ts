import { createHash } from "crypto";
import { ToolDefinition } from "./types";

export interface ToolCatalogEntry {
  name: string;
  signature: string;
}

export interface ToolRegistryOptions {
  /**
   * Optional pinned catalog. When present, every registered tool must
   * appear here and its metadata signature must match exactly.
   */
  catalog?: ToolCatalogEntry[];
  /**
   * Default true when catalog is present. Set false for tests or local
   * demos that want to publish signatures without fail-closed checks.
   */
  enforceCatalog?: boolean;
}

export class ToolCatalogViolationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ToolCatalogViolationError";
  }
}

export function createToolSignature(tool: ToolDefinition): string {
  const payload = JSON.stringify({
    name: tool.name,
    description: tool.description,
    riskLevel: tool.riskLevel,
    allowedRoles: [...tool.allowedRoles].sort(),
  });
  return createHash("sha256").update(payload).digest("hex");
}

export class ToolRegistry {
  private readonly tools = new Map<string, ToolDefinition>();
  private readonly catalog = new Map<string, string>();
  private readonly enforceCatalog: boolean;

  constructor(options: ToolRegistryOptions = {}) {
    for (const entry of options.catalog ?? []) {
      if (this.catalog.has(entry.name)) {
        throw new ToolCatalogViolationError(`Duplicate catalog entry: ${entry.name}`);
      }
      this.catalog.set(entry.name, entry.signature);
    }
    this.enforceCatalog = options.enforceCatalog ?? this.catalog.size > 0;
  }

  register(tool: ToolDefinition): void {
    if (this.tools.has(tool.name)) {
      throw new Error(`Tool already registered: ${tool.name}`);
    }

    this.verifyCatalog(tool);
    this.tools.set(tool.name, tool);
  }

  get(toolName: string): ToolDefinition {
    const tool = this.tools.get(toolName);

    if (!tool) {
      throw new Error(`Tool not found: ${toolName}`);
    }

    return tool;
  }

  list(): ToolDefinition[] {
    return Array.from(this.tools.values());
  }

  signatureFor(toolName: string): string {
    return createToolSignature(this.get(toolName));
  }

  private verifyCatalog(tool: ToolDefinition): void {
    if (!this.enforceCatalog) return;

    const expected = this.catalog.get(tool.name);
    if (!expected) {
      throw new ToolCatalogViolationError(`Tool is not in the pinned catalog: ${tool.name}`);
    }

    const actual = createToolSignature(tool);
    if (actual !== expected) {
      throw new ToolCatalogViolationError(`Tool signature mismatch: ${tool.name}`);
    }
  }
}
