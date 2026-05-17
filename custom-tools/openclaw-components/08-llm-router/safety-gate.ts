import { LLMRequest } from "./types";

export class SafetyGate {
  validate(request: LLMRequest): void {
    const normalized = request.prompt.toLowerCase();

    const blocked = [
      "reveal system prompt",
      "disable guardrails",
      "bypass policy",
    ];

    for (const rule of blocked) {
      if (normalized.includes(rule)) {
        throw new Error(`Safety gate blocked prompt: ${rule}`);
      }
    }
  }
}
