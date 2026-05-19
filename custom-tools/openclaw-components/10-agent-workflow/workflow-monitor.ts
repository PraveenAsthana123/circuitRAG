import { Tracer } from "../06-observability/tracer";
import { MetricsRecorder } from "../06-observability/metrics";
import { WorkflowContext, WorkflowStep } from "./types";

export interface WorkflowStepTraceHandle {
  end(status: "ok" | "error", extra?: Record<string, unknown>): void;
}

export interface WorkflowMonitor {
  workflowStarted(context: WorkflowContext, stepCount: number): void;
  stepStarted(context: WorkflowContext, step: WorkflowStep, toolName: string): WorkflowStepTraceHandle;
  stepSucceeded(
    context: WorkflowContext,
    step: WorkflowStep,
    toolName: string,
    durationMs: number,
    outputSizeBytes: number,
  ): void;
  stepFailed(
    context: WorkflowContext,
    step: WorkflowStep,
    toolName: string,
    durationMs: number,
    retryable: boolean,
    outcome: "retry" | "replan" | "abandon",
  ): void;
  workflowDelegated(context: WorkflowContext, jobId: string): void;
}

export class NoopWorkflowMonitor implements WorkflowMonitor {
  workflowStarted(): void {}
  stepStarted(): WorkflowStepTraceHandle { return { end: () => undefined }; }
  stepSucceeded(): void {}
  stepFailed(): void {}
  workflowDelegated(): void {}
}

export class ObservedWorkflowMonitor implements WorkflowMonitor {
  constructor(
    private readonly metrics: MetricsRecorder = new MetricsRecorder(),
    private readonly tracer: Tracer = new Tracer(),
  ) {}

  workflowStarted(context: WorkflowContext, stepCount: number): void {
    this.metrics.counter("workflow_started_total", 1, {
      component: "agent_workflow",
      tenantId: context.tenantId,
    });
    this.metrics.histogram("workflow_planned_steps", stepCount, {
      component: "agent_workflow",
      tenantId: context.tenantId,
    });
  }

  stepStarted(context: WorkflowContext, step: WorkflowStep, toolName: string): WorkflowStepTraceHandle {
    this.metrics.counter("workflow_step_started_total", 1, {
      component: "agent_workflow",
      stepName: step.name,
      toolName,
      tenantId: context.tenantId,
    });
    return this.tracer.startSpan("workflow.run_step", {
      requestId: context.requestId,
      sessionId: context.sessionId ?? context.workflowId,
      userId: context.userId,
      tenantId: context.tenantId,
      traceId: context.traceId,
      workflowId: context.workflowId,
      stepId: step.stepId,
      stepName: step.name,
      toolName,
      component: "agent_workflow",
    });
  }

  stepSucceeded(
    context: WorkflowContext,
    step: WorkflowStep,
    toolName: string,
    durationMs: number,
    outputSizeBytes: number,
  ): void {
    this.metrics.counter("workflow_step_completed_total", 1, {
      component: "agent_workflow",
      stepName: step.name,
      toolName,
      tenantId: context.tenantId,
    });
    this.metrics.histogram("workflow_step_duration_ms", durationMs, {
      component: "agent_workflow",
      stepName: step.name,
      toolName,
      tenantId: context.tenantId,
    });
    this.metrics.histogram("workflow_step_output_bytes", outputSizeBytes, {
      component: "agent_workflow",
      stepName: step.name,
      toolName,
      tenantId: context.tenantId,
    });
  }

  stepFailed(
    context: WorkflowContext,
    step: WorkflowStep,
    toolName: string,
    durationMs: number,
    retryable: boolean,
    outcome: "retry" | "replan" | "abandon",
  ): void {
    this.metrics.counter("workflow_step_failed_total", 1, {
      component: "agent_workflow",
      stepName: step.name,
      toolName,
      tenantId: context.tenantId,
      retryable: String(retryable),
      outcome,
    });
    this.metrics.histogram("workflow_step_duration_ms", durationMs, {
      component: "agent_workflow",
      stepName: step.name,
      toolName,
      tenantId: context.tenantId,
    });
  }

  workflowDelegated(context: WorkflowContext, jobId: string): void {
    this.metrics.counter("workflow_delegated_total", 1, {
      component: "agent_workflow",
      tenantId: context.tenantId,
    });
    const span = this.tracer.startSpan("workflow.delegated", {
      requestId: context.requestId,
      sessionId: context.sessionId ?? context.workflowId,
      userId: context.userId,
      tenantId: context.tenantId,
      traceId: context.traceId,
      workflowId: context.workflowId,
      jobId,
      component: "agent_workflow",
    });
    span.end("ok");
  }
}
