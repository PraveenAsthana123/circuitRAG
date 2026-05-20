import { describe, it, expect } from "vitest";
import {
  PatternResponsibleAIClassifier,
  ResponsibleAIGuard,
  ResponsibleAIClassifier,
} from "./responsible-ai-guard";
import { ToolRequest } from "./types";

const REQ = (input: Record<string, unknown>): ToolRequest => ({
  toolName: "any-tool",
  input,
  context: {
    requestId: "r",
    sessionId: "s",
    userId: "u",
    tenantId: "t",
    traceId: "tr",
  },
});

describe("Iter 109 - ResponsibleAIGuard classifier seam", () => {
  it("uses an injected classifier to block without local substring rules", () => {
    class TestClassifier implements ResponsibleAIClassifier {
      classify() {
        return {
          allowed: false,
          findings: [{
            ruleId: "MODEL_POLICY",
            message: "Responsible AI policy blocked tool call: MODEL_POLICY",
          }],
        };
      }
    }

    const guard = new ResponsibleAIGuard(new TestClassifier());

    expect(() => guard.validate(REQ({ query: "benign" })))
      .toThrow(/MODEL_POLICY/);
  });

  it("uses an injected classifier to allow text that default patterns would block", () => {
    class AllowAllClassifier implements ResponsibleAIClassifier {
      classify() {
        return { allowed: true, findings: [] };
      }
    }

    const guard = new ResponsibleAIGuard(new AllowAllClassifier());

    expect(() => guard.validate(REQ({ cmd: "delete system file" })))
      .not.toThrow();
  });

  it("default pattern classifier preserves blocked phrase behavior", () => {
    const guard = new ResponsibleAIGuard();

    expect(() => guard.validate(REQ({ cmd: "STEAL PASSWORD now" })))
      .toThrow(/steal password/);
  });

  it("default pattern classifier does not block benign split-keyword prompts", () => {
    const classifier = new PatternResponsibleAIClassifier();

    expect(classifier.classify(REQ({
      question: "How should we audit password storage and delete temporary files?",
    }))).toEqual({ allowed: true, findings: [] });
  });

  it("custom pattern classifier supports local policy override rules", () => {
    const guard = new ResponsibleAIGuard(
      new PatternResponsibleAIClassifier(["export credential vault"]),
    );

    expect(() => guard.validate(REQ({ cmd: "export credential vault" })))
      .toThrow(/export credential vault/);
  });
});
