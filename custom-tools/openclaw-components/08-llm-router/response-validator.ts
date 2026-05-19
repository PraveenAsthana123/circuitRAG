import { LLMResponse, ModelProvider } from "./types";

const PROVIDERS: ReadonlySet<ModelProvider> = new Set([
  "openai",
  "anthropic",
  "bedrock",
  "ollama",
]);

export class LLMResponseValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "LLMResponseValidationError";
  }
}

export function validateLLMResponse(response: unknown): asserts response is LLMResponse {
  if (typeof response !== "object" || response === null) {
    throw new LLMResponseValidationError("LLM response must be an object");
  }

  const candidate = response as Record<string, unknown>;
  requireNonEmptyString(candidate, "modelId");
  requireProvider(candidate.provider);
  requireNonEmptyString(candidate, "output");
  requireNonNegativeNumber(candidate, "latencyMs");
  requireNonNegativeNumber(candidate, "estimatedCostUsd");
  requireNonEmptyString(candidate, "explanation");

  if (candidate.fallbackUsed !== undefined && typeof candidate.fallbackUsed !== "boolean") {
    throw new LLMResponseValidationError("fallbackUsed must be a boolean when present");
  }
  if (candidate.primaryAttempted !== undefined && typeof candidate.primaryAttempted !== "string") {
    throw new LLMResponseValidationError("primaryAttempted must be a string when present");
  }
  if (candidate.primaryError !== undefined && typeof candidate.primaryError !== "string") {
    throw new LLMResponseValidationError("primaryError must be a string when present");
  }
}

function requireNonEmptyString(candidate: Record<string, unknown>, key: string): void {
  if (typeof candidate[key] !== "string" || candidate[key].trim() === "") {
    throw new LLMResponseValidationError(`${key} must be a non-empty string`);
  }
}

function requireNonNegativeNumber(candidate: Record<string, unknown>, key: string): void {
  if (typeof candidate[key] !== "number" || !Number.isFinite(candidate[key]) || candidate[key] < 0) {
    throw new LLMResponseValidationError(`${key} must be a non-negative finite number`);
  }
}

function requireProvider(provider: unknown): void {
  if (typeof provider !== "string" || !PROVIDERS.has(provider as ModelProvider)) {
    throw new LLMResponseValidationError("provider must be a supported provider");
  }
}
