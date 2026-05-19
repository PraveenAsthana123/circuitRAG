import { describe, expect, it, vi } from "vitest";
import { InMemoryToolTelemetrySink, Telemetry, ToolTelemetrySink } from "./telemetry";

class SpySink implements ToolTelemetrySink {
  readonly records: Record<string, unknown>[] = [];
  emit(record: Record<string, unknown>): void {
    this.records.push(record);
  }
}

describe("Component 3 Telemetry sink injection", () => {
  it("BACKDOOR: injected sink receives span payload without console.log", () => {
    const sink = new SpySink();
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new Telemetry(sink).startSpan("tool.dispatch", { requestId: "r" }).end({ ok: true });

      expect(log).not.toHaveBeenCalled();
      expect(sink.records).toHaveLength(1);
      expect(sink.records[0]).toMatchObject({
        type: "trace",
        span: "tool.dispatch",
        attributes: { requestId: "r" },
        extra: { ok: true },
      });
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: injected sink receives metric payload without console.log", () => {
    const sink = new SpySink();
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new Telemetry(sink).recordMetric("tool_success_total", 1, { toolName: "calculator" });

      expect(log).not.toHaveBeenCalled();
      expect(sink.records).toEqual([
        expect.objectContaining({
          type: "metric",
          name: "tool_success_total",
          value: 1,
          tags: { toolName: "calculator" },
        }),
      ]);
    } finally {
      log.mockRestore();
    }
  });

  it("default sink preserves console JSON contract", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new Telemetry().recordMetric("m", 0, {});

      expect(log).toHaveBeenCalledTimes(1);
      expect(JSON.parse(log.mock.calls[0][0] as string)).toMatchObject({
        type: "metric",
        name: "m",
        value: 0,
        tags: {},
      });
    } finally {
      log.mockRestore();
    }
  });

  it("in-memory sink is bounded and defensively copies records", () => {
    const sink = new InMemoryToolTelemetrySink(2);
    const telemetry = new Telemetry(sink);

    telemetry.recordMetric("a", 1, {});
    telemetry.recordMetric("b", 2, {});
    telemetry.recordMetric("c", 3, {});

    const listed = sink.list();
    expect(listed.map((record) => record.name)).toEqual(["b", "c"]);
    listed[0].name = "mutated";
    expect(sink.list()[0].name).toBe("b");
  });

  it("in-memory sink rejects non-positive bounds", () => {
    expect(() => new InMemoryToolTelemetrySink(0)).toThrow("maxRecords must be >= 1");
  });
});
