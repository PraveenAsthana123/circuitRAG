import { GuardrailFinding } from "./types";

export class PromptInjectionDetector {
  detect(text: string): GuardrailFinding[] {
    const normalized = text.toLowerCase();

    const patterns = [
      "ignore previous instructions",
      "disregard all prior instructions",
      "reveal system prompt",
      "disable safety",
      "bypass policy",
      "print hidden instructions",
    ];

    return patterns
      .filter((p) => normalized.includes(p))
      .map((p) => ({
        ruleId: "PROMPT_INJECTION",
        severity: "high",
        message: `Prompt injection pattern detected: ${p}`,
      }));
  }
}
