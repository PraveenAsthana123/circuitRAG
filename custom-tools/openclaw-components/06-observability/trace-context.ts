import { randomBytes } from "node:crypto";

export interface TraceContext {
  readonly version: "00";
  readonly traceId: string;
  readonly spanId: string;
  readonly parentSpanId?: string;
  readonly sampled: boolean;
}

const TRACE_ID_RE = /^[0-9a-f]{32}$/;
const SPAN_ID_RE = /^[0-9a-f]{16}$/;

function randomHex(bytes: number): string {
  return randomBytes(bytes).toString("hex");
}

function nonZeroTraceId(): string {
  let value = randomHex(16);
  while (value === "00000000000000000000000000000000") value = randomHex(16);
  return value;
}

function nonZeroSpanId(): string {
  let value = randomHex(8);
  while (value === "0000000000000000") value = randomHex(8);
  return value;
}

export function parseTraceparent(traceparent: string): TraceContext | undefined {
  const parts = traceparent.trim().split("-");
  if (parts.length !== 4) return undefined;
  const [version, traceId, spanId, flags] = parts;
  if (version !== "00") return undefined;
  if (!TRACE_ID_RE.test(traceId) || traceId === "00000000000000000000000000000000") return undefined;
  if (!SPAN_ID_RE.test(spanId) || spanId === "0000000000000000") return undefined;
  if (!/^[0-9a-f]{2}$/.test(flags)) return undefined;
  return {
    version,
    traceId,
    spanId,
    sampled: (Number.parseInt(flags, 16) & 0x01) === 1,
  };
}

export function formatTraceparent(context: TraceContext): string {
  const flags = context.sampled ? "01" : "00";
  return `${context.version}-${context.traceId}-${context.spanId}-${flags}`;
}

export function createTraceContext(options: {
  readonly sampled: boolean;
  readonly parentTraceparent?: string;
}): TraceContext {
  const parent = options.parentTraceparent
    ? parseTraceparent(options.parentTraceparent)
    : undefined;
  return {
    version: "00",
    traceId: parent?.traceId ?? nonZeroTraceId(),
    spanId: nonZeroSpanId(),
    parentSpanId: parent?.spanId,
    sampled: options.sampled,
  };
}
