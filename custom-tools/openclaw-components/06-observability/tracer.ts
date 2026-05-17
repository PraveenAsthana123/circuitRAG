export class Tracer {
  startSpan(name: string, attributes: Record<string, unknown>) {
    const startedAt = Date.now();

    return {
      end: (status: "ok" | "error", extra: Record<string, unknown> = {}) => {
        console.log(JSON.stringify({
          type: "trace",
          spanName: name,
          status,
          durationMs: Date.now() - startedAt,
          attributes,
          extra,
          timestamp: new Date().toISOString(),
        }));
      },
    };
  }
}
