// Iter 113 (2026-05-18): canonical eval-set scaffold.
//
// Per Agentic Plan §"Evaluation": "Add offline eval sets for
// planning correctness, tool selection, RAG citation accuracy,
// guardrail effectiveness, answer quality, cost control. Track
// success rate, hallucination rate, citation precision, tool
// error rate, review rate, cost/request. Block release if eval
// metrics regress beyond threshold."
//
// Per CLAUDE.md §48.7 + §59.4 (TDDD eval discipline) + §38
// (Eval gate for AI changes). This iter defines the canonical
// EvalSample + EvalCorpus + EvalResult + EvalRunner shapes;
// in-memory implementations work for unit tests; future iters
// wire to Ragas / DeepEval / custom-runner offline pipelines.

/**
 * One labelled sample in an eval corpus. The shape is open
 * (each eval type extends it with its own expectations) but
 * MUST carry id + input + expected — the minimum forensic
 * substrate.
 */
export interface EvalSample<Input = unknown, Expected = unknown> {
  id: string;
  category?: string;       // sub-grouping for reporting (e.g., "phrase-match")
  input: Input;
  expected: Expected;
  note?: string;           // human-readable annotation
}

/**
 * Per-sample evaluation outcome. `pass` is the binary verdict;
 * `actual` carries what the system produced; `details` is
 * free-shape per eval type (similarity score, citation overlap,
 * disposition, latency).
 */
export interface EvalOutcome<Actual = unknown> {
  sampleId: string;
  pass: boolean;
  actual: Actual;
  details?: Record<string, unknown>;
}

/**
 * Aggregate report over a corpus run. The default contract:
 * passCount / failCount / passRate + per-sample outcomes.
 * Extensions add domain-specific aggregate metrics (precision,
 * recall, F1, TPR, FPR, citation accuracy).
 */
export interface EvalReport<Actual = unknown> {
  corpusId: string;
  passCount: number;
  failCount: number;
  totalCount: number;
  passRate: number;            // 0..1
  outcomes: EvalOutcome<Actual>[];
  thresholds?: EvalThresholds; // when set, report.meetsThresholds is computed
  meetsThresholds?: boolean;
  aggregateMetrics?: Record<string, number>;
}

/**
 * Pre-deploy gate per CLAUDE.md §48.8. Eval runner asserts each
 * threshold and sets `meetsThresholds` so CI can fail-closed.
 */
export interface EvalThresholds {
  passRate?: number;           // ≥ to pass (e.g., 0.95)
  [aggregateMetricName: string]: number | undefined;
}

/**
 * An eval corpus — collection of samples + an evaluator function
 * that, given a system-under-test, runs each sample and returns
 * the outcome.
 *
 * Generic over Input/Expected/Actual so different eval types
 * (planning, tool-selection, citation, guardrail) can carry
 * their own labelled shapes.
 */
export interface EvalCorpus<Input, Expected, Actual, SUT> {
  corpusId: string;
  samples: readonly EvalSample<Input, Expected>[];
  /**
   * Per-sample evaluator. Given the system-under-test (SUT) and
   * a sample, returns the outcome. Must be pure-ish — repeated
   * runs against the same SUT + sample should yield the same
   * outcome (deterministic eval).
   */
  evaluate(sut: SUT, sample: EvalSample<Input, Expected>): Promise<EvalOutcome<Actual>>;
  /**
   * Optional aggregate-metric computer. Called after every sample
   * has been evaluated. Returns metric-name → value (e.g.,
   * precision, recall, citation accuracy). Used by the runner to
   * populate report.aggregateMetrics.
   */
  computeAggregates?(outcomes: EvalOutcome<Actual>[]): Record<string, number>;
}

/**
 * Run a corpus end-to-end against a SUT. Optionally enforces
 * thresholds (passRate + any aggregate metrics named in
 * `thresholds`); when set, `report.meetsThresholds` is populated.
 *
 * Per §38 release-gate contract: a release blocking on eval
 * regression calls this with thresholds, and refuses promotion
 * if meetsThresholds is false.
 */
export async function runEval<Input, Expected, Actual, SUT>(
  corpus: EvalCorpus<Input, Expected, Actual, SUT>,
  sut: SUT,
  thresholds?: EvalThresholds,
): Promise<EvalReport<Actual>> {
  const outcomes: EvalOutcome<Actual>[] = [];
  for (const sample of corpus.samples) {
    outcomes.push(await corpus.evaluate(sut, sample));
  }
  const passCount = outcomes.filter((o) => o.pass).length;
  const failCount = outcomes.length - passCount;
  const totalCount = outcomes.length;
  const passRate = totalCount === 0 ? 0 : passCount / totalCount;
  const aggregateMetrics = corpus.computeAggregates?.(outcomes) ?? {};

  let meetsThresholds: boolean | undefined;
  if (thresholds !== undefined) {
    meetsThresholds = true;
    if (thresholds.passRate !== undefined && passRate < thresholds.passRate) {
      meetsThresholds = false;
    }
    for (const [name, minValue] of Object.entries(thresholds)) {
      if (name === "passRate" || minValue === undefined) continue;
      if ((aggregateMetrics[name] ?? -Infinity) < minValue) {
        meetsThresholds = false;
      }
    }
  }

  return {
    corpusId: corpus.corpusId,
    passCount, failCount, totalCount, passRate,
    outcomes,
    thresholds,
    meetsThresholds,
    aggregateMetrics: Object.keys(aggregateMetrics).length > 0 ? aggregateMetrics : undefined,
  };
}

// ─────────────────────────────────────────────────────────────
// Four canonical corpus shapes (per Agentic Plan).
// Each is a TypeScript type alias narrowing EvalCorpus to the
// expected input/expected/actual/SUT shapes for that domain.
// In-memory implementations are trivial — pass `samples + evaluate`.
// ─────────────────────────────────────────────────────────────

/**
 * Planning eval: given a user goal, does the planner produce a
 * plan that matches the expected plan structure?
 */
export type PlanningEvalCorpus<Plan, Planner> = EvalCorpus<
  { goal: string },
  { plan: Plan },
  { plan: Plan },
  Planner
>;

/**
 * Tool-selection eval: given a step description, does the selector
 * pick the expected tool?
 */
export type ToolSelectionEvalCorpus<Selector> = EvalCorpus<
  { stepDescription: string; availableTools: string[] },
  { expectedTool: string },
  { actualTool: string },
  Selector
>;

/**
 * Citation eval: given a query, does the orchestrator produce an
 * answer whose citations match the expected chunk IDs?
 */
export type CitationEvalCorpus<Orchestrator> = EvalCorpus<
  { query: string },
  { expectedChunkIds: string[] },
  { actualChunkIds: string[]; precision?: number; recall?: number },
  Orchestrator
>;

/**
 * Guardrail eval: given an input, does the guardrail return the
 * expected disposition (allow/review/block)?
 */
export type GuardrailEvalCorpus<Guardrail> = EvalCorpus<
  { inputText: string },
  { expectedDisposition: "allow" | "review" | "block" },
  { actualDisposition: "allow" | "review" | "block" },
  Guardrail
>;
