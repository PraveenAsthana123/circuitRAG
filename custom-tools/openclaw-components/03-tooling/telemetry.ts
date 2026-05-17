export class Telemetry {
  startSpan(name: string, attributes: Record<string, unknown>) {
    const startTime = Date.now();

    return {
      end: (extra: Record<string, unknown> = {}) => {
        const durationMs = Date.now() - startTime;

        console.log(JSON.stringify({
          type: "trace",
          span: name,
          durationMs,
          timestamp: new Date().toISOString(),
          attributes,
          extra,
        }));
      },
    };
  }

  recordMetric(name: string, value: number, tags: Record<string, string>) {
    console.log(JSON.stringify({
      type: "metric",
      name,
      value,
      tags,
      timestamp: new Date().toISOString(),
    }));
  }
}
