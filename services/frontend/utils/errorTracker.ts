/**
 * §26 ErrorTracker — F12-introspectable runtime diagnostic surface.
 *
 * Sibling to <ClientErrorReporter />, NOT a replacement. The reporter
 * POSTs errors to /api/v1/admin/client-errors (server-side aggregation).
 * The tracker keeps an in-memory ring buffer the developer can query
 * from the browser console:
 *
 *   window.__errors.getSummary()  // counts by category
 *   window.__errors.getReport()   // full structured report
 *   window.__errors.getErrors()   // captured error events
 *   window.__errors.getWarnings() // captured warnings
 *   window.__errors.clear()       // reset
 *
 * Init is gated on `process.env.NODE_ENV === 'development'`. In prod the
 * tracker is a noop — diagnostic noise is for the developer, not the
 * end-user.
 *
 * What gets captured (per §26.2):
 *   - console.error / console.warn (intercepted via wrapping)
 *   - window.error  / unhandledrejection
 *   - PerformanceObserver: long tasks (> 100ms) per §30.1
 *   - PerformanceObserver: layout shifts (CLS) per §30.1
 *   - On-demand DOM scan via getReport(): missing alt, empty links,
 *     duplicate IDs, missing viewport/charset
 *
 * What we explicitly do NOT do:
 *   - Re-wrap fetch — ClientErrorReporter already does this. Double
 *     wrapping breaks the "wrapped" guard and causes fetch loops.
 *   - Capture DOM content. Privacy by default.
 *   - Replace ErrorBoundary or the global reporter. We compose.
 */

export type TrackerEntryKind =
  | 'console_error'
  | 'console_warn'
  | 'window_error'
  | 'unhandled_rejection'
  | 'long_task'
  | 'layout_shift';

export interface TrackerEntry {
  kind: TrackerEntryKind;
  message: string;
  at: number;
  route: string;
  extra?: Record<string, unknown>;
}

export interface TrackerSummary {
  errors: number;
  warnings: number;
  longTasks: number;
  layoutShifts: number;
  totalCLS: number;
  domIssues: number;
  enabled: boolean;
  startedAt: number | null;
}

export interface TrackerReport {
  summary: TrackerSummary;
  errors: TrackerEntry[];
  warnings: TrackerEntry[];
  longTasks: TrackerEntry[];
  layoutShifts: TrackerEntry[];
  domIssues: DomIssue[];
}

export interface DomIssue {
  kind:
    | 'missing_alt'
    | 'empty_link'
    | 'duplicate_id'
    | 'missing_viewport'
    | 'missing_charset'
    | 'unlabeled_input';
  message: string;
  selector?: string;
}

const MAX_ENTRIES = 500;

class ErrorTracker {
  private errors: TrackerEntry[] = [];
  private warnings: TrackerEntry[] = [];
  private longTasks: TrackerEntry[] = [];
  private layoutShifts: TrackerEntry[] = [];
  private totalCLS = 0;
  private startedAt: number | null = null;
  private installed = false;
  private originalConsoleError: typeof console.error | null = null;
  private originalConsoleWarn: typeof console.warn | null = null;
  private observer: PerformanceObserver | null = null;
  private clsObserver: PerformanceObserver | null = null;

  init(): void {
    if (typeof window === 'undefined') return;
    if (this.installed) return;
    this.installed = true;
    this.startedAt = Date.now();

    this.originalConsoleError = console.error;
    this.originalConsoleWarn = console.warn;

    console.error = (...args: unknown[]) => {
      this.push('errors', {
        kind: 'console_error',
        message: this.argsToMessage(args),
        at: Date.now(),
        route: this.currentRoute(),
        extra: { argCount: args.length },
      });
      this.originalConsoleError?.apply(console, args);
    };

    console.warn = (...args: unknown[]) => {
      this.push('warnings', {
        kind: 'console_warn',
        message: this.argsToMessage(args),
        at: Date.now(),
        route: this.currentRoute(),
        extra: { argCount: args.length },
      });
      this.originalConsoleWarn?.apply(console, args);
    };

    window.addEventListener('error', (ev: ErrorEvent) => {
      this.push('errors', {
        kind: 'window_error',
        message: ev.message || 'unknown',
        at: Date.now(),
        route: this.currentRoute(),
        extra: {
          filename: ev.filename ?? null,
          lineno: ev.lineno ?? null,
          colno: ev.colno ?? null,
        },
      });
    });

    window.addEventListener('unhandledrejection', (ev: PromiseRejectionEvent) => {
      const reason = ev.reason;
      const message =
        reason instanceof Error
          ? reason.message
          : typeof reason === 'string'
            ? reason
            : 'unhandled promise rejection';
      this.push('errors', {
        kind: 'unhandled_rejection',
        message,
        at: Date.now(),
        route: this.currentRoute(),
      });
    });

    this.installPerformanceObservers();
  }

  private installPerformanceObservers(): void {
    if (typeof PerformanceObserver === 'undefined') return;

    try {
      this.observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (entry.duration > 100) {
            this.push('longTasks', {
              kind: 'long_task',
              message: `Long task: ${Math.round(entry.duration)}ms`,
              at: Date.now(),
              route: this.currentRoute(),
              extra: {
                durationMs: Math.round(entry.duration),
                name: entry.name,
              },
            });
          }
        }
      });
      this.observer.observe({ entryTypes: ['longtask'] });
    } catch {
      // longtask not supported (some browsers); ignore.
    }

    try {
      this.clsObserver = new PerformanceObserver((list) => {
        for (const raw of list.getEntries()) {
          const entry = raw as PerformanceEntry & {
            value?: number;
            hadRecentInput?: boolean;
          };
          if (entry.hadRecentInput) continue;
          const value = entry.value ?? 0;
          if (value <= 0) continue;
          this.totalCLS += value;
          if (value > 0.1) {
            this.push('layoutShifts', {
              kind: 'layout_shift',
              message: `Layout shift value=${value.toFixed(3)}`,
              at: Date.now(),
              route: this.currentRoute(),
              extra: { value, totalCLS: this.totalCLS },
            });
          }
        }
      });
      this.clsObserver.observe({ entryTypes: ['layout-shift'] });
    } catch {
      // layout-shift not supported; ignore.
    }
  }

  private push(
    bucket: 'errors' | 'warnings' | 'longTasks' | 'layoutShifts',
    entry: TrackerEntry,
  ): void {
    const arr = this[bucket];
    arr.push(entry);
    if (arr.length > MAX_ENTRIES) {
      arr.shift();
    }
  }

  private argsToMessage(args: unknown[]): string {
    return args
      .map((a) => {
        if (a instanceof Error) return a.message;
        if (typeof a === 'string') return a;
        try {
          return JSON.stringify(a);
        } catch {
          return String(a);
        }
      })
      .join(' ')
      .slice(0, 1000);
  }

  private currentRoute(): string {
    return typeof window !== 'undefined' ? window.location.pathname : '';
  }

  private scanDom(): DomIssue[] {
    if (typeof document === 'undefined') return [];
    const issues: DomIssue[] = [];

    document.querySelectorAll('img').forEach((img) => {
      if (!img.hasAttribute('alt')) {
        issues.push({
          kind: 'missing_alt',
          message: `<img> without alt: ${img.src.slice(0, 100)}`,
          selector: this.selectorFor(img),
        });
      }
    });

    document.querySelectorAll('a').forEach((a) => {
      const text = (a.textContent || '').trim();
      const ariaLabel = a.getAttribute('aria-label');
      if (!text && !ariaLabel) {
        issues.push({
          kind: 'empty_link',
          message: `<a> with no text or aria-label: href=${a.getAttribute('href') ?? ''}`,
          selector: this.selectorFor(a),
        });
      }
    });

    const idMap = new Map<string, number>();
    document.querySelectorAll('[id]').forEach((el) => {
      const id = el.id;
      idMap.set(id, (idMap.get(id) ?? 0) + 1);
    });
    idMap.forEach((count, id) => {
      if (count > 1) {
        issues.push({
          kind: 'duplicate_id',
          message: `Duplicate id="${id}" appears ${count} times`,
        });
      }
    });

    if (!document.querySelector('meta[name="viewport"]')) {
      issues.push({
        kind: 'missing_viewport',
        message: '<meta name="viewport"> missing — mobile rendering will be broken',
      });
    }
    if (!document.querySelector('meta[charset]')) {
      issues.push({
        kind: 'missing_charset',
        message: '<meta charset="..."> missing',
      });
    }

    document.querySelectorAll('input, select, textarea').forEach((el) => {
      const id = el.getAttribute('id');
      const ariaLabel = el.getAttribute('aria-label');
      const ariaLabelledby = el.getAttribute('aria-labelledby');
      const labelFor = id ? document.querySelector(`label[for="${id}"]`) : null;
      if (!ariaLabel && !ariaLabelledby && !labelFor) {
        const tag = el.tagName.toLowerCase();
        const type = el.getAttribute('type');
        if (tag === 'input' && (type === 'hidden' || type === 'submit' || type === 'button')) {
          return;
        }
        issues.push({
          kind: 'unlabeled_input',
          message: `<${tag}${type ? ` type=${type}` : ''}> without label/aria`,
          selector: this.selectorFor(el),
        });
      }
    });

    return issues;
  }

  private selectorFor(el: Element): string {
    if (el.id) return `#${el.id}`;
    const cls = el.className && typeof el.className === 'string' ? el.className.split(/\s+/)[0] : '';
    const tag = el.tagName.toLowerCase();
    return cls ? `${tag}.${cls}` : tag;
  }

  getSummary(): TrackerSummary {
    const domIssues = this.scanDom();
    return {
      errors: this.errors.length,
      warnings: this.warnings.length,
      longTasks: this.longTasks.length,
      layoutShifts: this.layoutShifts.length,
      totalCLS: Number(this.totalCLS.toFixed(4)),
      domIssues: domIssues.length,
      enabled: this.installed,
      startedAt: this.startedAt,
    };
  }

  getReport(): TrackerReport {
    return {
      summary: this.getSummary(),
      errors: [...this.errors],
      warnings: [...this.warnings],
      longTasks: [...this.longTasks],
      layoutShifts: [...this.layoutShifts],
      domIssues: this.scanDom(),
    };
  }

  getErrors(): TrackerEntry[] {
    return [...this.errors];
  }

  getWarnings(): TrackerEntry[] {
    return [...this.warnings];
  }

  clear(): void {
    this.errors = [];
    this.warnings = [];
    this.longTasks = [];
    this.layoutShifts = [];
    this.totalCLS = 0;
  }
}

export const errorTracker = new ErrorTracker();

declare global {
  interface Window {
    __errors?: ErrorTracker;
    __documindErrorTrackerInstalled?: boolean;
  }
}
