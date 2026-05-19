// Iter 118b (2026-05-18): canonical ToolSelectionEvalCorpus.
//
// Evaluates a ToolSelector on the name-pattern routing contract:
// step.requiredTool wins; "quality"-named steps route to
// quality_scorer; "approval"-named steps route to human_approval;
// everything else defaults to default_agent_executor.
//
// Future iter swaps in policy-driven selector (tenant/role/cost
// aware) → same corpus → instant comparative metric.

import { EvalCorpus } from "./eval-corpus";
import { ToolSelector } from "../10-agent-workflow/tool-selector";
import { WorkflowStep } from "../10-agent-workflow/types";

interface CorpusSample {
  id: string;
  category: "explicit_tool" | "name_pattern_quality" | "name_pattern_approval" | "default";
  step: WorkflowStep;
  expectedTool: string;
  note?: string;
}

const SAMPLES: readonly CorpusSample[] = [
  {
    id: "sel-explicit-1",
    category: "explicit_tool",
    step: {
      stepId: "s1", name: "any_step", goal: "x", requiresApproval: false,
      status: "pending", requiredTool: "calculator",
    },
    expectedTool: "calculator",
    note: "requiredTool always wins",
  },
  {
    id: "sel-explicit-2",
    category: "explicit_tool",
    step: {
      stepId: "s2", name: "quality_review", goal: "x", requiresApproval: false,
      status: "pending", requiredTool: "custom_tool_explicit",
    },
    expectedTool: "custom_tool_explicit",
    note: "explicit beats name-pattern (even when name says 'quality')",
  },
  {
    id: "sel-quality-1",
    category: "name_pattern_quality",
    step: {
      stepId: "s3", name: "quality_review", goal: "x", requiresApproval: false,
      status: "pending",
    },
    expectedTool: "quality_scorer",
  },
  {
    id: "sel-quality-2",
    category: "name_pattern_quality",
    step: {
      stepId: "s4", name: "assess_quality_metrics", goal: "x", requiresApproval: false,
      status: "pending",
    },
    expectedTool: "quality_scorer",
  },
  {
    id: "sel-approval-1",
    category: "name_pattern_approval",
    step: {
      stepId: "s5", name: "approval_step", goal: "x", requiresApproval: true,
      status: "pending",
    },
    expectedTool: "human_approval",
  },
  {
    id: "sel-default-1",
    category: "default",
    step: {
      stepId: "s6", name: "understand_goal", goal: "x", requiresApproval: false,
      status: "pending",
    },
    expectedTool: "default_agent_executor",
  },
  {
    id: "sel-default-2",
    category: "default",
    step: {
      stepId: "s7", name: "execute_task", goal: "x", requiresApproval: false,
      status: "pending",
    },
    expectedTool: "default_agent_executor",
  },
];

export function buildCanonicalToolSelectionCorpus(): EvalCorpus<
  { step: WorkflowStep },
  { expectedTool: string },
  { actualTool: string },
  ToolSelector
> {
  return {
    corpusId: "openclaw-canonical-tool-selection-v1",
    samples: SAMPLES.map((s) => ({
      id: s.id,
      category: s.category,
      note: s.note,
      input: { step: s.step },
      expected: { expectedTool: s.expectedTool },
    })),
    async evaluate(selector, sample) {
      const actualTool = selector.select(sample.input.step);
      return {
        sampleId: sample.id,
        pass: actualTool === sample.expected.expectedTool,
        actual: { actualTool },
        details: { category: (sample as { category?: string }).category },
      };
    },
    computeAggregates(outcomes) {
      const correctness =
        outcomes.filter((o) => o.pass).length / Math.max(1, outcomes.length);
      // Per-category breakdown for dashboards.
      const byCategory: Record<string, number> = {};
      for (const cat of ["explicit_tool", "name_pattern_quality",
                          "name_pattern_approval", "default"]) {
        const subset = outcomes.filter(
          (o) => (o.details as { category?: string })?.category === cat,
        );
        if (subset.length > 0) {
          byCategory[`accuracy_${cat}`] =
            subset.filter((o) => o.pass).length / subset.length;
        }
      }
      return { selection_correctness: correctness, ...byCategory };
    },
  };
}

export const CANONICAL_TOOL_SELECTION_THRESHOLDS = {
  passRate: 1.0,
  selection_correctness: 1.0,
};
