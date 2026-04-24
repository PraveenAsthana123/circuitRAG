// Minimal runtime error tracker (global CLAUDE.md §26).
// Captures window errors + unhandled rejections; exposes a summary you can
// hit via F12: `window.__errors.getSummary()`.

class ErrorTracker {
  constructor() {
    this.errors = [];
    this.warnings = [];
  }

  init() {
    window.addEventListener('error', (e) => {
      this.errors.push({
        type: 'window.error',
        message: e.message,
        source: e.filename,
        line: e.lineno,
        at: new Date().toISOString(),
      });
    });
    window.addEventListener('unhandledrejection', (e) => {
      this.errors.push({
        type: 'unhandled_rejection',
        message: String(e.reason),
        at: new Date().toISOString(),
      });
    });
  }

  getErrors() {
    return this.errors;
  }

  getWarnings() {
    return this.warnings;
  }

  getSummary() {
    return { errors: this.errors.length, warnings: this.warnings.length };
  }

  getReport() {
    return {
      summary: this.getSummary(),
      errors: this.errors,
      warnings: this.warnings,
    };
  }

  clear() {
    this.errors = [];
    this.warnings = [];
  }
}

export const errorTracker = new ErrorTracker();
