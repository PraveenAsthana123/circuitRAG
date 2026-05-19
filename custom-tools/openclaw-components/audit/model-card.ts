// Iter 111 (2026-05-18): canonical ModelCard metadata interface.
//
// Per CLAUDE.md §48 + Agentic Plan §"Explainability":
// "Every model in registry MUST have a model card with intended use,
// performance/fairness, explainability artifact, limitations,
// owner/contact, last review date, version history. Updating the
// model without the card = release blocked."
//
// This interface is the canonical schema; the registry checks
// every model has one BEFORE allowing it into production routing.

/**
 * Performance metrics — kept as an open map so different model
 * classes can carry their own metric names (classification accuracy,
 * Ragas faithfulness, BLEU, etc). The convention is { metricName:
 * value }; values are 0..1 unless documented otherwise.
 */
export interface ModelPerformanceMetrics {
  [metricName: string]: number;
}

/**
 * Fairness assertions per CLAUDE.md §48.8. Disparate impact ≥ 0.8
 * and equal-opportunity gap < 5% are the pre-deploy thresholds
 * the §48 policy mandates; a card MUST state both or document why
 * it's not applicable (e.g., non-decision model).
 */
export interface ModelFairnessAssertions {
  disparateImpact?: number;            // ≥ 0.8 to pass
  equalOpportunityGapPercent?: number; // < 5 to pass
  notApplicable?: string;              // reason if not a decision model
}

/**
 * Explainability artifact pointer — where can a reader find the
 * model's global feature importance / SHAP plot / sample LIME
 * outputs? May be a URL, a CID, a local path.
 */
export interface ModelExplainabilityArtifact {
  globalShapUrl?: string;
  localExplanationApi?: string;        // e.g., /api/v1/explain?prediction_id=<id>
  method?: string;                     // "shap" | "lime" | "ig" | "anchor" | "rule"
}

/**
 * Owner / contact for audit + regulator queries.
 */
export interface ModelOwnership {
  team: string;
  contactEmail?: string;
  oncallRotation?: string;
}

/**
 * Per-version history entry. Cards accumulate these as the model
 * is retrained / re-released; allows rollback by version + audit
 * "what was deployed on date X".
 */
export interface ModelVersionEntry {
  version: string;
  releasedAt: string;                  // ISO-8601
  trainingDataHash?: string;
  evalReportUrl?: string;
  changeNotes?: string;
}

/**
 * Canonical ModelCard. Required fields lock the §48.3 minimum
 * disclosure contract; optional fields cover the §48 nice-to-haves.
 */
export interface ModelCard {
  // ── identity ─────────────────────────────────────────────
  modelId: string;                     // canonical id (e.g., "gpt-4o:2024-08")
  version: string;                     // current version string
  // ── intended use ─────────────────────────────────────────
  intendedUse: string;                 // 1-3 sentence summary
  outOfScopeUses?: string[];           // explicit anti-use list
  // ── data ─────────────────────────────────────────────────
  trainingDataSummary?: string;        // 1-paragraph summary
  trainingDataAsOf?: string;           // ISO-8601 cutoff
  // ── performance + fairness ───────────────────────────────
  performance?: ModelPerformanceMetrics;
  fairness?: ModelFairnessAssertions;
  // ── explainability ───────────────────────────────────────
  explainability?: ModelExplainabilityArtifact;
  // ── ownership + lifecycle ────────────────────────────────
  owner: ModelOwnership;
  lastReviewedAt: string;              // ISO-8601 (quarterly review)
  history?: ModelVersionEntry[];
  // ── limits ───────────────────────────────────────────────
  limitations?: string[];              // known failure modes
}

/**
 * Errors the ModelCardRegistry throws when validation fails.
 * Caller can `catch (e instanceof ...)` to discriminate.
 */
export class ModelCardMissingError extends Error {
  constructor(modelId: string) {
    super(`No model card registered for model "${modelId}"`);
    this.name = "ModelCardMissingError";
  }
}

export class ModelCardInvalidError extends Error {
  constructor(modelId: string, reason: string) {
    super(`Invalid model card for "${modelId}": ${reason}`);
    this.name = "ModelCardInvalidError";
  }
}

/**
 * Stub registry — in-memory map by modelId. Production replaces
 * with a Postgres-backed registry; this interface is the seam.
 *
 * Production-mode caller pattern (e.g., LLMRouter):
 *   if (productionMode) {
 *     registry.require(modelId);   // throws if missing or invalid
 *   }
 */
export class ModelCardRegistry {
  private readonly cards = new Map<string, ModelCard>();

  /**
   * Register a card. Validates basic shape before storage so the
   * registry never holds a half-populated card.
   */
  register(card: ModelCard): void {
    if (!card.modelId || card.modelId.trim() === "") {
      throw new ModelCardInvalidError(card.modelId ?? "(unset)", "modelId required");
    }
    if (!card.version || card.version.trim() === "") {
      throw new ModelCardInvalidError(card.modelId, "version required");
    }
    if (!card.intendedUse || card.intendedUse.trim() === "") {
      throw new ModelCardInvalidError(card.modelId, "intendedUse required");
    }
    if (!card.owner || !card.owner.team || card.owner.team.trim() === "") {
      throw new ModelCardInvalidError(card.modelId, "owner.team required");
    }
    if (!card.lastReviewedAt) {
      throw new ModelCardInvalidError(card.modelId, "lastReviewedAt required");
    }
    // Validate lastReviewedAt parses as ISO-8601.
    const parsed = new Date(card.lastReviewedAt);
    if (Number.isNaN(parsed.getTime())) {
      throw new ModelCardInvalidError(card.modelId, "lastReviewedAt must be ISO-8601");
    }
    this.cards.set(card.modelId, card);
  }

  /**
   * Returns the card or undefined. For production code paths use
   * require() which throws on absence.
   */
  get(modelId: string): ModelCard | undefined {
    return this.cards.get(modelId);
  }

  /**
   * Production-grade lookup. Throws ModelCardMissingError if absent.
   * Use this from the LLMRouter / planner before letting a model
   * serve traffic in production mode.
   */
  require(modelId: string): ModelCard {
    const card = this.cards.get(modelId);
    if (!card) throw new ModelCardMissingError(modelId);
    return card;
  }

  /**
   * Snapshot of all registered modelIds — for governance reports.
   */
  list(): string[] {
    return Array.from(this.cards.keys()).sort();
  }

  /**
   * Quarterly-review staleness check. Returns modelIds whose
   * lastReviewedAt is older than `maxAgeDays` days. Operators use
   * this for the §48 "Quarterly explainability review" gate.
   */
  staleReviews(maxAgeDays: number, now: Date = new Date()): string[] {
    if (maxAgeDays < 0) throw new Error("maxAgeDays must be >= 0");
    const cutoff = now.getTime() - maxAgeDays * 24 * 60 * 60 * 1000;
    const out: string[] = [];
    for (const [id, card] of this.cards) {
      if (new Date(card.lastReviewedAt).getTime() < cutoff) {
        out.push(id);
      }
    }
    return out.sort();
  }
}
