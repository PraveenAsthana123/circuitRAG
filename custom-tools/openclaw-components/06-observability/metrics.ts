export class MetricsRecorder {
  counter(name: string, value: number, labels: Record<string, string>): void {
    console.log(JSON.stringify({
      type: "metric",
      metricType: "counter",
      name,
      value,
      labels,
      timestamp: new Date().toISOString(),
    }));
  }

  histogram(name: string, value: number, labels: Record<string, string>): void {
    console.log(JSON.stringify({
      type: "metric",
      metricType: "histogram",
      name,
      value,
      labels,
      timestamp: new Date().toISOString(),
    }));
  }
}
