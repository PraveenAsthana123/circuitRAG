export class Logger {
  info(message: string, meta: Record<string, unknown> = {}) {
    console.log(JSON.stringify({
      level: "INFO",
      message,
      timestamp: new Date().toISOString(),
      ...meta,
    }));
  }

  warn(message: string, meta: Record<string, unknown> = {}) {
    console.warn(JSON.stringify({
      level: "WARN",
      message,
      timestamp: new Date().toISOString(),
      ...meta,
    }));
  }

  error(message: string, meta: Record<string, unknown> = {}) {
    console.error(JSON.stringify({
      level: "ERROR",
      message,
      timestamp: new Date().toISOString(),
      ...meta,
    }));
  }
}
