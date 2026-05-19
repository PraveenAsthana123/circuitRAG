// ✅ P0 FIXED (2026-05-17): LLMClient is now ABSTRACT.
//     Pre-fix: `complete()` returned a fake string like "Model X
//     answered: <prompt>". Tests passed, demos worked, but every
//     deployment shipped fake responses with no warning.
//
//     Now: LLMClient is a base class with an abstract complete()
//     method. Concrete providers must subclass and implement.
//
//     This file also ships an EchoLLMClient subclass that
//     explicitly identifies itself as a NON-production stub, so
//     interview / demo code can still wire something up — but every
//     response carries `output: "[ECHO STUB - NOT PRODUCTION]: ..."`
//     so anyone reading downstream output sees the stub marker.
//
//     For real deployments, subclass LLMClient with
//     OpenAILLMClient / AnthropicLLMClient / BedrockLLMClient /
//     OllamaLLMClient bound to the real provider SDK.

import { LLMRequest, LLMResponse, ModelConfig } from "./types";

export abstract class LLMClient {
  readonly isProductionStub: boolean = false;

  constructor() {
    // TS `abstract` is compile-time only; this runtime guard
    // refuses construction if a caller circumvents the type
    // checker (e.g., via JS or @ts-ignore).
    if (new.target === LLMClient) {
      throw new Error(
        "LLMClient is abstract — subclass with a real provider " +
        "(OpenAILLMClient / AnthropicLLMClient / OllamaLLMClient / ...) " +
        "before constructing."
      );
    }
  }

  abstract complete(
    request: LLMRequest,
    model: ModelConfig
  ): Promise<LLMResponse>;

  /**
   * Shared cost estimator. Subclasses can override if their pricing
   * model differs (e.g., distinct prompt vs completion token cost).
   */
  protected estimateCostUsd(request: LLMRequest, model: ModelConfig): number {
    return (request.maxTokens / 1000) * model.costPer1kTokensUsd;
  }
}

/**
 * Non-production echo stub. Identifies itself with the
 * `[ECHO STUB - NOT PRODUCTION]:` prefix so downstream code or
 * humans can spot it in audit rows / logs.
 */
export class EchoLLMClient extends LLMClient {
  override readonly isProductionStub = true;

  async complete(
    request: LLMRequest,
    model: ModelConfig
  ): Promise<LLMResponse> {
    const start = Date.now();
    const output = `[ECHO STUB - NOT PRODUCTION]: Model ${model.modelId} would have answered: ${request.prompt}`;
    return {
      modelId: model.modelId,
      provider: model.provider,
      output,
      latencyMs: Date.now() - start,
      estimatedCostUsd: this.estimateCostUsd(request, model),
      explanation:
        `EchoLLMClient is a stub; selected ${model.modelId} per routing policy ` +
        `but did NOT call a real provider. Replace with a real subclass before deploy.`,
    };
  }
}


export interface OllamaLLMClientOptions {
  baseUrl?: string;
  timeoutMs?: number;
}

interface OllamaGenerateResponse {
  response?: unknown;
  model?: unknown;
  total_duration?: unknown;
}

/**
 * Real Ollama HTTP client for local/self-hosted models. It calls
 * POST /api/generate with stream=false and maps the response into
 * the shared LLMResponse contract.
 */
export class OllamaLLMClient extends LLMClient {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;

  constructor(options: OllamaLLMClientOptions = {}) {
    super();
    this.baseUrl = (options.baseUrl ?? process.env.OLLAMA_BASE_URL ?? "http://localhost:11434")
      .replace(/\/+$/, "");
    this.timeoutMs = options.timeoutMs ?? 30_000;
    if (!Number.isInteger(this.timeoutMs) || this.timeoutMs <= 0) {
      throw new Error("OllamaLLMClient timeoutMs must be a positive integer");
    }
  }

  async complete(request: LLMRequest, model: ModelConfig): Promise<LLMResponse> {
    if (model.provider !== "ollama") {
      throw new Error(`OllamaLLMClient cannot call provider ${model.provider}`);
    }

    const start = Date.now();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const response = await fetch(`${this.baseUrl}/api/generate`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          model: model.modelId,
          prompt: request.prompt,
          stream: false,
          options: {
            num_predict: request.maxTokens,
          },
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`Ollama request failed with HTTP ${response.status}`);
      }

      const body = await response.json() as OllamaGenerateResponse;
      if (typeof body.response !== "string" || body.response.length === 0) {
        throw new Error("Ollama response missing non-empty response text");
      }

      return {
        modelId: typeof body.model === "string" ? body.model : model.modelId,
        provider: "ollama",
        output: body.response,
        latencyMs: Date.now() - start,
        estimatedCostUsd: this.estimateCostUsd(request, model),
        explanation:
          `OllamaLLMClient called ${this.baseUrl}/api/generate for ${model.modelId}`,
      };
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        throw new Error(`Ollama request timed out after ${this.timeoutMs} ms`, { cause: error });
      }
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  }
}
