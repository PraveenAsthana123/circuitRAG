import { afterEach, describe, expect, it, vi } from "vitest";
import { EchoLLMClient, OllamaLLMClient } from "./llm-client";
import { LLMRouter } from "./llm-router";
import { ModelRegistry } from "./model-registry";
import { RoutingPolicy } from "./routing-policy";
import { SafetyGate } from "./safety-gate";

const request = {
  requestId: "req-ollama",
  tenantId: "tenant-ollama",
  userId: "user-ollama",
  taskType: "chat" as const,
  prompt: "hello",
  maxTokens: 64,
  traceId: "trace-ollama",
};

const model = {
  modelId: "llama3.1",
  provider: "ollama" as const,
  supportedTasks: ["chat" as const],
  costPer1kTokensUsd: 0,
  maxContextTokens: 8192,
  priority: 1,
  enabled: true,
};

describe("OllamaLLMClient", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("calls Ollama /api/generate and maps the response", async () => {
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      expect(JSON.parse(String(init.body))).toMatchObject({
        model: "llama3.1",
        prompt: "hello",
        stream: false,
        options: { num_predict: 64 },
      });
      return new Response(JSON.stringify({ model: "llama3.1", response: "hi there" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = new OllamaLLMClient({ baseUrl: "http://ollama.local/" });
    const response = await client.complete(request, model);

    expect(fetchMock).toHaveBeenCalledWith("http://ollama.local/api/generate", expect.any(Object));
    expect(response).toMatchObject({
      modelId: "llama3.1",
      provider: "ollama",
      output: "hi there",
      estimatedCostUsd: 0,
    });
  });

  it("rejects non-Ollama model configs", async () => {
    const client = new OllamaLLMClient();
    await expect(client.complete(request, { ...model, provider: "openai" }))
      .rejects.toThrow(/cannot call provider openai/);
  });

  it("blocks EchoLLMClient in production router config", () => {
    expect(() => new LLMRouter(
      new ModelRegistry([model]),
      new RoutingPolicy(),
      new SafetyGate(),
      new EchoLLMClient(),
      undefined,
      { productionMode: true },
    )).toThrow(/cannot use a stub LLMClient/);
  });
});
