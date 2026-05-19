import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AgentWorkflowEngine } from "./agent-workflow-engine";
import { WorkflowPlanner } from "./planner";
import { Replanner } from "./replanner";
import { ToolSelector } from "./tool-selector";
import { HumanApprovalGate } from "./human-approval";
import { WorkflowStateStore } from "./workflow-state-store";
import { ObservedWorkflowMonitor } from "./workflow-monitor";
import { WorkflowDelegator } from "./workflow-delegator";
import { JobScheduler } from "./job-scheduler";
import { ToolDispatcher } from "../03-tooling/tool-dispatcher";
import { ToolRegistry } from "../03-tooling/tool-registry";
import { Logger } from "../03-tooling/logger";
import { Telemetry } from "../03-tooling/telemetry";
import { ResponsibleAIGuard } from "../03-tooling/responsible-ai-guard";
import { ExplainabilityRecorder } from "../03-tooling/explainability-recorder";
import { MetricsRecorder } from "../06-observability/metrics";
import { Tracer } from "../06-observability/tracer";

function parse(line: unknown): Record<string, unknown> {
  return JSON.parse(String(line));
}

function dispatcher(): ToolDispatcher {
  const registry = new ToolRegistry();
  registry.register({
    name: "default_agent_executor",
    description: "observability test tool",
    riskLevel: "low",
    allowedRoles: ["agent"],
    async execute(input, context) {
      return {
        stepName: input.stepName,
        traceId: context.traceId,
        tenantId: context.tenantId,
      };
    },
  });
  return new ToolDispatcher(
    registry,
    new Logger(),
    new Telemetry(),
    new ResponsibleAIGuard(),
    new ExplainabilityRecorder(),
  );
}

describe("Workflow delegation, monitoring, and tracing integration", () => {
  const logs: string[] = [];
  const warns: string[] = [];
  const errors: string[] = [];

  beforeEach(() => {
    logs.length = 0;
    warns.length = 0;
    errors.length = 0;
    vi.spyOn(console, "log").mockImplementation((msg?: unknown) => { logs.push(String(msg)); });
    vi.spyOn(console, "warn").mockImplementation((msg?: unknown) => { warns.push(String(msg)); });
    vi.spyOn(console, "error").mockImplementation((msg?: unknown) => { errors.push(String(msg)); });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("delegates agent work through the scheduler and preserves traceId across delegate -> workflow -> tool", async () => {
    const monitor = new ObservedWorkflowMonitor(
      new MetricsRecorder({ maxSeriesPerMetric: 20 }),
      new Tracer(),
    );
    const store = new WorkflowStateStore();
    const engine = new AgentWorkflowEngine(
      new WorkflowPlanner(),
      new Replanner(),
      new ToolSelector(),
      new HumanApprovalGate(),
      store,
      {
        toolDispatcher: dispatcher(),
        requireRealToolDispatcher: true,
        monitor,
      },
    );
    const workflow = engine.start({
      workflowId: "wf-observe-1",
      requestId: "req-observe-1",
      tenantId: "tenant-observe",
      userId: "user-observe",
      traceId: "trace-observe-1",
      sessionId: "session-observe-1",
      roles: ["agent"],
    }, "run delegated work");

    const delegator = new WorkflowDelegator(engine, {
      scheduler: new JobScheduler({ now: () => 1_000, random: () => 0 }),
      monitor,
    });
    const job = delegator.delegateRunNext(workflow.context, 10);
    const result = await delegator.runDue();

    expect(result).toMatchObject({ started: 1, succeeded: 1 });
    expect(job.type).toBe("workflow.run_next");
    expect(store.get(workflow.context.workflowId, "tenant-observe").steps[0].status).toBe("completed");

    const payloads = logs.map(parse);
    const delegatedTrace = payloads.find((p) => p.type === "trace" && p.spanName === "workflow.delegated");
    const workflowTrace = payloads.find((p) => p.type === "trace" && p.spanName === "workflow.run_step");
    const toolTrace = payloads.find((p) => p.type === "trace" && p.span === "tool.dispatch");

    expect((delegatedTrace?.attributes as Record<string, unknown>).traceId).toBe("trace-observe-1");
    expect((workflowTrace?.attributes as Record<string, unknown>).traceId).toBe("trace-observe-1");
    expect((toolTrace?.attributes as Record<string, unknown>).traceId).toBe("trace-observe-1");

    const metricNames = payloads
      .filter((p) => p.type === "metric")
      .map((p) => p.name);
    expect(metricNames).toContain("workflow_delegated_total");
    expect(metricNames).toContain("workflow_started_total");
    expect(metricNames).toContain("workflow_step_started_total");
    expect(metricNames).toContain("workflow_step_completed_total");
    expect(metricNames).toContain("workflow_step_duration_ms");
  });

  it("monitors workflow dispatch failures and records replan outcome", async () => {
    const monitor = new ObservedWorkflowMonitor(new MetricsRecorder(), new Tracer());
    const registry = new ToolRegistry();
    registry.register({
      name: "default_agent_executor",
      description: "failing tool",
      riskLevel: "low",
      allowedRoles: ["agent"],
      async execute() { throw new Error("delegate backend down"); },
    });
    const failingDispatcher = new ToolDispatcher(
      registry, new Logger(), new Telemetry(), new ResponsibleAIGuard(), new ExplainabilityRecorder(),
    );
    const store = new WorkflowStateStore();
    const engine = new AgentWorkflowEngine(
      new WorkflowPlanner(), new Replanner(), new ToolSelector(), new HumanApprovalGate(), store,
      { toolDispatcher: failingDispatcher, requireRealToolDispatcher: true, monitor },
    );
    const wf = engine.start({
      workflowId: "wf-observe-fail", requestId: "req", tenantId: "tenant", userId: "user",
      traceId: "trace-fail", roles: ["agent"],
    }, "fail");

    await engine.runNext(wf.context.workflowId, "tenant");

    const payloads = logs.map(parse);
    const failedMetric = payloads.find((p) =>
      p.type === "metric" &&
      p.name === "workflow_step_failed_total" &&
      (p.labels as Record<string, string>).outcome === "replan"
    );
    const workflowTrace = payloads.find((p) => p.type === "trace" && p.spanName === "workflow.run_step");

    expect(failedMetric).toBeDefined();
    expect(workflowTrace?.status).toBe("error");
    expect((workflowTrace?.extra as Record<string, unknown>).outcome).toBe("replan");
  });

  it("delegator deduplicates duplicate runNext jobs for the same workflow", () => {
    const store = new WorkflowStateStore();
    const engine = new AgentWorkflowEngine(
      new WorkflowPlanner(), new Replanner(), new ToolSelector(), new HumanApprovalGate(), store,
    );
    const wf = engine.start({
      workflowId: "wf-dedupe", requestId: "r", tenantId: "t", userId: "u", traceId: "tr",
    }, "dedupe");
    const delegator = new WorkflowDelegator(engine, { scheduler: new JobScheduler() });

    const first = delegator.delegateRunNext(wf.context);
    const second = delegator.delegateRunNext(wf.context);

    expect(second.jobId).toBe(first.jobId);
    expect(delegator.getScheduler().list("t", "queued")).toHaveLength(1);
  });
});
