// Iter 132 (2026-05-20): EU AI Act risk classification decision
// tree. Closes P1 GAPS row "Risk classification (§7) has 4 buckets
// but no decision tree for which bucket a use case falls into."
//
// Implements the EU AI Act risk classification (Regulation
// 2024/1689, Art. 5 prohibited + Art. 6 high-risk + Annex III +
// Art. 50 transparency). Operator describes the deployment via
// UseCaseDescriptor; classifyRisk() returns the bucket + obligations.
//
// The classification is INTENTIONALLY conservative — defaults flip
// toward higher-risk classification when in doubt. The §57.7 rule:
// a regulator audit penalizes under-classification, not over.
//
// Composes with iter 131 — every "high_risk" classification triggers
// the euAiActDisclosureSet() KPIs as mandatory; "minimal_risk" does
// not.
//
// Per CLAUDE.md §43 (drillable), §47.6 STRIDE (risk classification
// is the first STRIDE input — high-risk needs deeper threat model),
// §48 explainability (high-risk MUST satisfy §48.4 audit row +
// §48.7 counterfactual + §48.8 fairness), §53 item 47 strategic
// alignment (risk = portfolio control surface), §57.7 (drilled
// decision tree, not vibe), §59.4 ORF (high-risk metrics gate).

// ───────────────────────────── Types ─────────────────────────────

/** EU AI Act risk levels per Regulation 2024/1689. */
export type AIActRiskLevel =
  | "prohibited"     // Art. 5 — cannot deploy in EU
  | "high_risk"      // Art. 6 + Annex III — full compliance
  | "limited_risk"   // Art. 50 — transparency only
  | "minimal_risk";  // No AI Act obligations

/** Annex III use case categories (high-risk triggers). */
export type AnnexIIICategory =
  | "biometric_categorization"
  | "critical_infrastructure"
  | "education_vocational_training"
  | "employment_workers_management"   // recruitment, performance eval
  | "essential_private_public_services"  // credit scoring, social benefits
  | "law_enforcement"
  | "migration_asylum_border"
  | "administration_of_justice";

/** Art. 5 prohibited practices. */
export type ProhibitedPractice =
  | "subliminal_manipulation"
  | "exploitation_of_vulnerabilities"   // age / disability / socio-economic
  | "social_scoring_by_authority"
  | "biometric_categorization_protected_attrs"  // race / political / sexual orientation
  | "untargeted_facial_scraping"
  | "emotion_inference_workplace_education"
  | "predictive_policing_individual";

export interface UseCaseDescriptor {
  /** Operator-readable name for the deployment. */
  readonly name: string;
  /** Free-text description (for the audit row). */
  readonly description: string;
  /** If the use case matches an Art. 5 prohibited practice, name it. */
  readonly prohibitedPractice?: ProhibitedPractice;
  /** If the use case is in Annex III, name the category. */
  readonly annexIIICategory?: AnnexIIICategory;
  /** Does the AI interact directly with a natural person? (Art. 50 trigger) */
  readonly interactsWithHumans: boolean;
  /** Does the AI generate synthetic content (images / video / audio / text)?
   *  (Art. 50 trigger) */
  readonly generatesContent: boolean;
  /** Does the deployment process personal data (PII)? */
  readonly processesPII: boolean;
  /** Does the AI's output trigger automated decisions affecting humans? */
  readonly automatedDecisionsAffectingHumans: boolean;
  /** Does the deployment touch minors (under 18 in EU)? */
  readonly handlesMinors: boolean;
  /** Safety-critical (health, life, infrastructure)? */
  readonly safetyCritical: boolean;
  /** Regulated-data regime if any. */
  readonly regulatedDataRegime?: "GDPR" | "HIPAA" | "PCI" | "GLBA" | "none";
}

export interface RiskObligation {
  readonly clause: string;     // e.g., "Art. 13 transparency"
  readonly requirement: string; // operator-actionable
  readonly mandatory: boolean;  // false = recommended
}

export interface RiskClassification {
  readonly useCaseName: string;
  readonly level: AIActRiskLevel;
  /** The rule(s) that drove the classification. */
  readonly triggers: ReadonlyArray<string>;
  /** Concrete obligations the operator must satisfy. */
  readonly obligations: ReadonlyArray<RiskObligation>;
  /** True iff the iter 131 euAiActDisclosureSet KPIs are mandatory. */
  readonly requiresAIActKPIs: boolean;
  /** True iff §48 explainability (model card + audit row + counterfactual) is mandatory. */
  readonly requiresFullExplainability: boolean;
  /** True iff §48.7 counterfactual generation is mandatory (Art. 86). */
  readonly requiresCounterfactual: boolean;
  /** True iff §48.8 fairness pre-deploy gate is mandatory. */
  readonly requiresFairnessGate: boolean;
  readonly classifiedAt: string;
}

// ───────────────────────────── Classifier ─────────────────────────

export function classifyRisk(uc: UseCaseDescriptor): RiskClassification {
  const classifiedAt = new Date().toISOString();
  const triggers: string[] = [];

  // ─── Art. 5 prohibited check (highest precedence) ──────────
  if (uc.prohibitedPractice) {
    triggers.push(`Art. 5 prohibited practice: ${uc.prohibitedPractice}`);
    return {
      useCaseName: uc.name,
      level: "prohibited",
      triggers,
      obligations: [{
        clause: "Art. 5",
        requirement: `DO NOT DEPLOY. ${uc.prohibitedPractice} is prohibited in EU jurisdictions.`,
        mandatory: true,
      }],
      requiresAIActKPIs: false,         // moot — cannot deploy
      requiresFullExplainability: true,  // for audit of the refusal
      requiresCounterfactual: false,
      requiresFairnessGate: false,
      classifiedAt,
    };
  }

  // ─── Art. 6 + Annex III high-risk check ────────────────────
  // Conservative: a deployment that makes automated decisions
  // affecting humans is HIGH-RISK even if it doesn't fit a
  // named Annex III category exactly — better over-classify.
  const isHighRisk =
    Boolean(uc.annexIIICategory)
    || uc.safetyCritical
    || (uc.automatedDecisionsAffectingHumans && uc.processesPII);

  if (isHighRisk) {
    if (uc.annexIIICategory) triggers.push(`Annex III: ${uc.annexIIICategory}`);
    if (uc.safetyCritical) triggers.push("safety-critical");
    if (uc.automatedDecisionsAffectingHumans && uc.processesPII) {
      triggers.push("automated decisions on PII (conservative high-risk classification)");
    }
    if (uc.handlesMinors) {
      triggers.push("handles minors — heightened protection per Art. 9 GDPR");
    }

    return {
      useCaseName: uc.name,
      level: "high_risk",
      triggers,
      obligations: highRiskObligations(uc),
      requiresAIActKPIs: true,
      requiresFullExplainability: true,
      requiresCounterfactual: true,
      requiresFairnessGate: true,
      classifiedAt,
    };
  }

  // ─── Art. 50 limited-risk transparency check ───────────────
  const isLimitedRisk = uc.interactsWithHumans || uc.generatesContent;

  if (isLimitedRisk) {
    if (uc.interactsWithHumans) triggers.push("Art. 50 §1: AI interacts with natural persons");
    if (uc.generatesContent) triggers.push("Art. 50 §2: AI generates synthetic content (must be machine-readable as AI-generated)");

    return {
      useCaseName: uc.name,
      level: "limited_risk",
      triggers,
      obligations: [
        {
          clause: "Art. 50 §1",
          requirement: "Inform the user they are interacting with an AI system",
          mandatory: uc.interactsWithHumans,
        },
        {
          clause: "Art. 50 §2",
          requirement: "Mark AI-generated content as such (machine-readable + user-visible)",
          mandatory: uc.generatesContent,
        },
        {
          clause: "§48.5 RAG four-part contract",
          requirement: "If RAG-backed, persist retrieval trail + citation map + guardrail trace",
          mandatory: false,
        },
      ],
      requiresAIActKPIs: false,
      requiresFullExplainability: false,
      requiresCounterfactual: false,
      requiresFairnessGate: false,
      classifiedAt,
    };
  }

  // ─── Minimal risk ──────────────────────────────────────────
  triggers.push("No Art. 5 / Art. 6 / Annex III / Art. 50 triggers matched");
  return {
    useCaseName: uc.name,
    level: "minimal_risk",
    triggers,
    obligations: [
      {
        clause: "internal best practice",
        requirement: "Maintain §48.3 model card; no EU AI Act mandates apply",
        mandatory: false,
      },
    ],
    requiresAIActKPIs: false,
    requiresFullExplainability: false,
    requiresCounterfactual: false,
    requiresFairnessGate: false,
    classifiedAt,
  };
}

function highRiskObligations(uc: UseCaseDescriptor): ReadonlyArray<RiskObligation> {
  const base: RiskObligation[] = [
    {
      clause: "Art. 9", requirement: "Risk management system (continuous, iterative)", mandatory: true,
    },
    {
      clause: "Art. 10", requirement: "Data governance — training/validation/test data quality criteria", mandatory: true,
    },
    {
      clause: "Art. 11", requirement: "Technical documentation (Annex IV)", mandatory: true,
    },
    {
      clause: "Art. 12", requirement: "Logging — ≥ 6 months retention; covered by §48.4 decision audit row", mandatory: true,
    },
    {
      clause: "Art. 13", requirement: "Transparency to deployer (instructions, characteristics, capabilities, limitations)", mandatory: true,
    },
    {
      clause: "Art. 14", requirement: "Human oversight — HITL escalation path; covered by §48.6 agent audit", mandatory: true,
    },
    {
      clause: "Art. 15", requirement: "Robustness + accuracy — covered by iter 131 KPIs (TPR / citation accuracy)", mandatory: true,
    },
    {
      clause: "Art. 17", requirement: "Quality management system (ISO/IEC standards)", mandatory: true,
    },
    {
      clause: "Art. 86", requirement: "Right to explanation — §48.7 counterfactual generation", mandatory: true,
    },
  ];
  if (uc.handlesMinors) {
    base.push({
      clause: "GDPR Art. 8 + Art. 9", requirement: "Heightened protection for minor data subjects (parental consent flow)", mandatory: true,
    });
  }
  if (uc.regulatedDataRegime && uc.regulatedDataRegime !== "none") {
    base.push({
      clause: `${uc.regulatedDataRegime} compliance`, requirement: `Comply with ${uc.regulatedDataRegime} obligations layered on top of AI Act`, mandatory: true,
    });
  }
  return base;
}
