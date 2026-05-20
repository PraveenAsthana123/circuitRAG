// Iter 125 (2026-05-19): the unified safety-classifier core that
// production safety adapters (Llama Guard, Bedrock Guardrails,
// ProtectAI, etc.) should bind to ONCE — not once per per-component
// interface.
//
// The four per-component interfaces (PromptInjectionClassifier,
// PIIProvider, SafetyGateClassifier, ResponsibleAIClassifier) all
// answer the same underlying question — "is this text safe under
// policy K?" — in four different output shapes. Until this iter,
// the architecture claim "a single Llama Guard adapter satisfies
// all four" was a vibe in commit messages. This iter PROVES that
// claim by:
//
//   1. Defining a UnifiedSafetyClassifier interface and a reference
//      RuleBasedUnifiedSafetyClassifier that decides per policy kind.
//   2. Shipping four thin adapters (one per per-component interface)
//      that delegate to the unified core.
//   3. A drill (unified-safety-classifier.test.ts) that feeds the
//      SAME blocking-triggering text into all four adapters and
//      asserts they each produce a per-interface decision that is
//      semantically equivalent (detected/!safe/!allowed). Cross-shape
//      drift is a regression.
//
// This is §59.1 MDD applied to safety boundaries: the core IS the
// model; each per-component interface is one derivation; a future
// Llama Guard adapter implements the core ONCE and inherits all
// four interface bindings free.
//
// Per CLAUDE.md §43 (drilled invariants), §47.6 STRIDE (one
// hardened core defends Tampering/InfoDisclosure/Elevation at one
// boundary), §52 (row 23 boundary integration), §57.7 (claim
// proved by drill, not vibe), §59.1 (MDD core).
//
// What this iter is NOT:
//   - Not a replacement for the per-component interfaces. Those
//     stay; this iter is the implementation pattern production
//     adapter authors follow to satisfy all four without
//     rewriting the model wrapping logic four times.
//   - Not a Llama Guard adapter. That requires the SDK + auth +
//     a running classifier service. This is the contract; a
//     future iter ships the adapter binding the contract to the
//     real model.

/** Severity union — matches GuardrailFinding's severity field
 *  so the unified output composes with §38 audit row population
 *  without per-interface re-mapping. */
export type UnifiedSeverity = "low" | "medium" | "high" | "critical";

/** A single safety finding from the unified core. The four
 *  per-interface shapes (PromptInjectionClassification,
 *  PIIDetection, SafetyGateFinding, ResponsibleAIFinding) project
 *  from this in their respective adapters. */
export interface UnifiedFinding {
  readonly ruleId: string;
  readonly severity: UnifiedSeverity;
  readonly message: string;
}

/** The unified output. `blocked === true` iff at least one finding
 *  has severity >= the per-policy threshold (currently any finding
 *  blocks — production adapters can refine). */
export interface UnifiedSafetyDecision {
  readonly blocked: boolean;
  readonly findings: UnifiedFinding[];
}

/** The four policy kinds. A real Llama Guard adapter inspects
 *  `kind` to choose the right model prompt template / category. */
export type UnifiedSafetyKind =
  | "prompt_injection"
  | "pii"
  | "llm_safety"
  | "responsible_ai";

/** The unified contract. One implementation; four adapter bindings. */
export interface UnifiedSafetyClassifier {
  decide(text: string, kind: UnifiedSafetyKind): UnifiedSafetyDecision;
}

// ───────────────────────────── Reference impl ─────────────────────────────

/**
 * Reference rule-based unified classifier. Production replaces this
 * with a real model adapter (LlamaGuardUnifiedClassifier, etc.).
 *
 * The reference impl uses a per-kind rule map so the drill can prove
 * each adapter routes correctly to its policy — e.g., "ignore previous
 * instructions" triggers `prompt_injection` rules but not `pii` rules.
 */
export interface UnifiedRuleSet {
  readonly prompt_injection: ReadonlyArray<UnifiedRule>;
  readonly pii: ReadonlyArray<UnifiedRule>;
  readonly llm_safety: ReadonlyArray<UnifiedRule>;
  readonly responsible_ai: ReadonlyArray<UnifiedRule>;
}

export interface UnifiedRule {
  readonly pattern: string;
  readonly ruleId: string;
  readonly severity: UnifiedSeverity;
  readonly message: string;
}

const DEFAULT_RULESET: UnifiedRuleSet = {
  prompt_injection: [
    { pattern: "ignore previous instructions", ruleId: "PROMPT_INJECTION", severity: "high",
      message: "Prompt injection: ignore previous instructions" },
  ],
  pii: [
    { pattern: "@example.com", ruleId: "PII_EMAIL", severity: "medium",
      message: "PII: email-like pattern present" },
  ],
  llm_safety: [
    { pattern: "disable guardrails", ruleId: "MODEL_POLICY", severity: "critical",
      message: "Safety gate: disable guardrails" },
  ],
  responsible_ai: [
    { pattern: "steal password", ruleId: "RAI_POLICY", severity: "critical",
      message: "Responsible AI: steal password" },
  ],
};

export class RuleBasedUnifiedSafetyClassifier implements UnifiedSafetyClassifier {
  constructor(private readonly ruleset: UnifiedRuleSet = DEFAULT_RULESET) {}

  decide(text: string, kind: UnifiedSafetyKind): UnifiedSafetyDecision {
    const normalized = text.toLowerCase();
    const rules = this.ruleset[kind];
    const findings: UnifiedFinding[] = rules
      .filter((rule) => normalized.includes(rule.pattern))
      .map((rule) => ({
        ruleId: rule.ruleId,
        severity: rule.severity,
        message: rule.message,
      }));
    return {
      blocked: findings.length > 0,
      findings,
    };
  }
}
