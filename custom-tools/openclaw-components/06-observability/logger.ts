export class StructuredLogger {
  log(
    level: "info" | "warn" | "error",
    message: string,
    meta: Record<string, unknown>
  ): void {
    console.log(JSON.stringify({
      level,
      message,
      timestamp: new Date().toISOString(),
      ...meta,
    }));
  }
}
