export interface ObservabilityContext {
  requestId: string;
  sessionId: string;
  userId: string;
  tenantId: string;
  traceId: string;
  component: string;
}

export interface AIOpsEvent {
  eventId: string;
  severity: "info" | "warning" | "error" | "critical";
  category: "latency" | "quality" | "security" | "cost" | "runtime";
  message: string;
  context: ObservabilityContext;
  timestamp: string;
}
