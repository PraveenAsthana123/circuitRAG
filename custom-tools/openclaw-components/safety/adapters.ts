// Iter 125 (2026-05-19): the four thin adapters that project a
// single UnifiedSafetyClassifier core onto each per-component
// safety interface. A future LlamaGuardUnifiedClassifier
// implementing UnifiedSafetyClassifier inherits all four bindings
// FREE — no per-interface re-wrap.
//
// Per CLAUDE.md §52 (boundary integration row 23): each adapter
// is < 25 lines, testable in isolation, and the
// UnifiedSafetyClassifier IS the dependency boundary.

import type {
  UnifiedSafetyClassifier,
  UnifiedFinding,
} from "./unified-safety-classifier";
import type {
  PromptInjectionClassifier,
  PromptInjectionClassification,
} from "../05-guardrails/prompt-injection-detector";
import type {
  PIIProvider,
  PIIDetection,
} from "../05-guardrails/pii-detector";
import type {
  SafetyGateClassifier,
  SafetyGateClassification,
} from "../08-llm-router/safety-gate";
import type {
  ResponsibleAIClassifier,
  ResponsibleAIClassification,
} from "../03-tooling/responsible-ai-guard";
import type { LLMRequest } from "../08-llm-router/types";
import type { ToolRequest } from "../03-tooling/types";

// ───────────────────────────── 1. PromptInjectionClassifier adapter ─────────────────────────────

export class UnifiedPromptInjectionAdapter implements PromptInjectionClassifier {
  constructor(private readonly core: UnifiedSafetyClassifier) {}

  classify(text: string): PromptInjectionClassification[] {
    const decision = this.core.decide(text, "prompt_injection");
    return decision.findings.map((f: UnifiedFinding) => ({
      detected: true,
      ruleId: f.ruleId,
      severity: f.severity,
      message: f.message,
    }));
  }
}

// ───────────────────────────── 2. PIIProvider adapter ─────────────────────────────

export class UnifiedPIIProviderAdapter implements PIIProvider {
  constructor(private readonly core: UnifiedSafetyClassifier) {}

  detect(text: string): PIIDetection[] {
    const decision = this.core.decide(text, "pii");
    return decision.findings.map((f: UnifiedFinding) => ({
      detected: true,
      ruleId: f.ruleId,
      severity: f.severity,
      message: f.message,
    }));
  }
}

// ───────────────────────────── 3. SafetyGateClassifier adapter ─────────────────────────────

export class UnifiedSafetyGateAdapter implements SafetyGateClassifier {
  constructor(private readonly core: UnifiedSafetyClassifier) {}

  classify(request: LLMRequest): SafetyGateClassification {
    const decision = this.core.decide(request.prompt, "llm_safety");
    return {
      safe: !decision.blocked,
      findings: decision.findings.map((f: UnifiedFinding) => ({
        ruleId: f.ruleId,
        message: f.message,
      })),
    };
  }
}

// ───────────────────────────── 4. ResponsibleAIClassifier adapter ─────────────────────────────

export class UnifiedResponsibleAIAdapter implements ResponsibleAIClassifier {
  constructor(private readonly core: UnifiedSafetyClassifier) {}

  classify(request: ToolRequest): ResponsibleAIClassification {
    const inputText = JSON.stringify(request.input);
    const decision = this.core.decide(inputText, "responsible_ai");
    return {
      allowed: !decision.blocked,
      findings: decision.findings.map((f: UnifiedFinding) => ({
        ruleId: f.ruleId,
        message: f.message,
      })),
    };
  }
}
