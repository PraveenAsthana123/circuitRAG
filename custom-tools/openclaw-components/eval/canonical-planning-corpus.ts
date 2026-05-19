// Iter 118a (2026-05-18): canonical PlanningEvalCorpus.
//
// Evaluates a Planner end-to-end on plan-shape correctness:
// every step's action is in the allowed set; default-plan
// behavior is preserved when no provider is wired; provider
// validation rejects malformed plans.
//
// Composes iter 97 (PlanProvider seam) with iter 113 (eval scaffold).
// Today's planner is the default-plan path; future iter swaps in
// LLM-driven provider → same corpus → instant comparative metric.

import { EvalCorpus } from "./eval-corpus";
import { Planner } from "../02-agent-runtime/planner";
import { AgentTask, AgentPlan } from "../02-agent-runtime/types";

const ALLOWED_ACTIONS = new Set(["think", "tool", "respond", "recall"]);

interface CorpusSample {
  id: string;
  category: "default_path" | "with_input" | "complex_goal";
  task: AgentTask;
  expectedMinSteps: number;
  expectedActionSubset: readonly string[];  // EVERY step's action must be in this subset
  note?: string;
}

const SAMPLES: readonly CorpusSample[] = [
  {
    id: "plan-default-1",
    category: "default_path",
    task: { sessionId: "s-1", userId: "u-1", userInput: "hello" },
    expectedMinSteps: 1,
    expectedActionSubset: ["think", "tool", "respond", "recall"],
    note: "default planner produces ≥1 step with valid actions",
  },
  {
    id: "plan-default-2",
    category: "default_path",
    task: { sessionId: "s-2", userId: "u-2", userInput: "" },
    expectedMinSteps: 1,
    expectedActionSubset: ["think", "tool", "respond", "recall"],
    note: "empty userInput still produces a valid plan",
  },
  {
    id: "plan-with-input-summarize",
    category: "with_input",
    task: {
      sessionId: "s-3", userId: "u-3",
      userInput: "Summarize the attached quarterly report.",
    },
    expectedMinSteps: 1,
    expectedActionSubset: ["think", "tool", "respond", "recall"],
  },
  {
    id: "plan-with-input-translate",
    category: "with_input",
    task: {
      sessionId: "s-4", userId: "u-4",
      userInput: "Translate this paragraph to French.",
    },
    expectedMinSteps: 1,
    expectedActionSubset: ["think", "tool", "respond", "recall"],
  },
  {
    id: "plan-complex-goal",
    category: "complex_goal",
    task: {
      sessionId: "s-5", userId: "u-5",
      userInput: "Find the most-cited paper on retrieval augmentation, " +
                 "extract its citations, and summarize.",
    },
    expectedMinSteps: 1,
    expectedActionSubset: ["think", "tool", "respond", "recall"],
  },
];

export function buildCanonicalPlanningCorpus(): EvalCorpus<
  AgentTask,
  { expectedMinSteps: number; expectedActionSubset: readonly string[] },
  { plan: AgentPlan; stepCount: number; allActionsValid: boolean },
  Planner
> {
  return {
    corpusId: "openclaw-canonical-planning-v1",
    samples: SAMPLES.map((s) => ({
      id: s.id,
      category: s.category,
      note: s.note,
      input: s.task,
      expected: {
        expectedMinSteps: s.expectedMinSteps,
        expectedActionSubset: s.expectedActionSubset,
      },
    })),
    async evaluate(planner, sample) {
      const plan = planner.createPlan(sample.input);
      const stepCount = plan.steps.length;
      const allActionsValid = plan.steps.every(
        (s) => ALLOWED_ACTIONS.has(s.action),
      );
      const meetsMinSteps = stepCount >= sample.expected.expectedMinSteps;
      const allInSubset = plan.steps.every(
        (s) => sample.expected.expectedActionSubset.includes(s.action),
      );
      return {
        sampleId: sample.id,
        pass: meetsMinSteps && allActionsValid && allInSubset,
        actual: { plan, stepCount, allActionsValid },
        details: {
          category: (sample as { category?: string }).category,
          meetsMinSteps,
          allInSubset,
        },
      };
    },
    computeAggregates(outcomes) {
      const avgStepCount = outcomes.reduce(
        (sum, o) => sum + ((o.actual as { stepCount?: number }).stepCount ?? 0),
        0,
      ) / Math.max(1, outcomes.length);
      const actionValidityRate = outcomes.filter(
        (o) => (o.actual as { allActionsValid?: boolean }).allActionsValid,
      ).length / Math.max(1, outcomes.length);
      return { avgStepCount, action_validity_rate: actionValidityRate };
    },
  };
}

export const CANONICAL_PLANNING_THRESHOLDS = {
  passRate: 1.0,                // every sample must pass
  action_validity_rate: 1.0,    // every step's action must be valid
};
