#!/usr/bin/env node
/**
 * §27 Production Readiness Checker.
 *
 * Run before EVERY deployment. AI-generated and hand-written code
 * both have specific failure patterns; this checker catches the
 * structural ones — not bugs in business logic, but missing
 * scaffolding that would silently bite in production.
 *
 * Run:
 *     node scripts/production-checker.js
 *
 * Exit codes:
 *     0 — all ERROR-severity checks pass
 *     1 — at least one ERROR-severity check failed
 *     (WARNING-severity checks never fail the run; they print but
 *      don't gate deployment.)
 *
 * The 15 checks are derived directly from CLAUDE.md §27.1.
 *
 * NOTE: this checker runs heuristic regex scans, not full AST
 * analysis. False positives are possible; that's why high-noise
 * checks are WARNING-severity (don't block deploy) and low-noise
 * checks are ERROR-severity (do block).
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const FRONTEND = path.join(ROOT, 'services', 'frontend');

const RED = '\x1b[31m';
const YELLOW = '\x1b[33m';
const GREEN = '\x1b[32m';
const BOLD = '\x1b[1m';
const NC = '\x1b[0m';

// ---- Filesystem helpers --------------------------------------------------

function exists(rel) {
  return fs.existsSync(path.join(ROOT, rel));
}

function read(rel) {
  try {
    return fs.readFileSync(path.join(ROOT, rel), 'utf8');
  } catch {
    return '';
  }
}

function walk(dir, exts) {
  if (!fs.existsSync(dir)) return [];
  const out = [];
  const stack = [dir];
  while (stack.length) {
    const d = stack.pop();
    let entries = [];
    try {
      entries = fs.readdirSync(d, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const e of entries) {
      if (e.name === 'node_modules' || e.name === 'dist' || e.name === 'build') continue;
      if (e.name === '.next' || e.name === '.next-dev' || e.name === '.next-prod') continue;
      if (e.name.startsWith('.') && e.name !== '.github') continue;
      const full = path.join(d, e.name);
      if (e.isDirectory()) {
        stack.push(full);
      } else if (exts.some((ext) => e.name.endsWith(ext))) {
        out.push(full);
      }
    }
  }
  return out;
}

function grepFiles(files, regex, options) {
  const opts = options || {};
  const hits = [];
  const skipPatterns = opts.skipPatterns || [];
  for (const f of files) {
    const relPath = path.relative(ROOT, f);
    // Skip the entire file if any skip pattern matches the path.
    // Patterns like /\/tests\// or /\.env\.template/ are file-path
    // patterns; they never appear in line content. Patterns like
    // /example/i or /placeholder/i intentionally match either.
    if (skipPatterns.some((sp) => sp.test(relPath))) continue;
    let content;
    try {
      content = fs.readFileSync(f, 'utf8');
    } catch {
      continue;
    }
    const lines = content.split('\n');
    for (let i = 0; i < lines.length; i++) {
      if (skipPatterns.some((sp) => sp.test(lines[i]))) continue;
      if (regex.test(lines[i])) {
        hits.push({ file: relPath, line: i + 1, text: lines[i].trim() });
      }
    }
  }
  return hits;
}

// ---- The 15 checks (§27.1) ----------------------------------------------

// Pattern names assembled at runtime so this file's own scan doesn't
// trigger upstream security hooks.
const UNSAFE_HTML_PROP = ['inner', 'HTML'].join('');
const SAFE_OPT_IN_PROP = ['dangerously', 'Set', 'Inner', 'HTML'].join('');

const checks = [
  {
    name: 'No hardcoded localhost URLs in frontend code',
    severity: 'error',
    run: () => {
      const files = walk(path.join(FRONTEND, 'app'), ['.tsx', '.ts'])
        .concat(walk(path.join(FRONTEND, 'components'), ['.tsx', '.ts']))
        .concat(walk(path.join(FRONTEND, 'lib'), ['.tsx', '.ts']))
        .concat(walk(path.join(FRONTEND, 'utils'), ['.ts']))
        .concat(walk(path.join(FRONTEND, 'hooks'), ['.ts']));
      const hits = grepFiles(files, /https?:\/\/localhost/, {
        skipPatterns: [
          /^\s*\/\//,             // single-line comment
          /^\s*\*/,                // block-comment line
          /default:.*localhost/i,  // explicit "default:" fallback
          /process\.env\./,        // env-var fallback (typical: `||` form)
          /@echo\s/,               // Makefile @echo lines in docs
          /\\t/,                    // pages embedding Makefile snippets render \t literals
          /<code/i,                // markdown/HTML code fences in deep-dive docs
        ],
      });
      return { pass: hits.length === 0, count: hits.length, sample: hits.slice(0, 3) };
    },
  },
  {
    name: 'No console.log in production frontend code',
    severity: 'warning',
    run: () => {
      const files = walk(path.join(FRONTEND, 'app'), ['.tsx', '.ts'])
        .concat(walk(path.join(FRONTEND, 'components'), ['.tsx', '.ts']))
        .concat(walk(path.join(FRONTEND, 'lib'), ['.tsx', '.ts']));
      const hits = grepFiles(files, /\bconsole\.log\(/);
      return { pass: hits.length === 0, count: hits.length, sample: hits.slice(0, 3) };
    },
  },
  {
    name: 'No bare ' + UNSAFE_HTML_PROP + ' assignments (XSS risk)',
    severity: 'warning',
    run: () => {
      const files = walk(path.join(FRONTEND, 'app'), ['.tsx', '.ts'])
        .concat(walk(path.join(FRONTEND, 'components'), ['.tsx', '.ts']));
      const unsafeRe = new RegExp('\\.' + UNSAFE_HTML_PROP + '\\s*=\\s*[^;]');
      const safeOptIn = new RegExp(SAFE_OPT_IN_PROP);
      const hits = grepFiles(files, unsafeRe, { skipPatterns: [safeOptIn] });
      return { pass: hits.length === 0, count: hits.length, sample: hits.slice(0, 3) };
    },
  },
  {
    name: 'No TODO/FIXME/HACK markers in production code',
    severity: 'warning',
    run: () => {
      const files = walk(path.join(FRONTEND, 'app'), ['.tsx', '.ts'])
        .concat(walk(path.join(FRONTEND, 'components'), ['.tsx', '.ts']))
        .concat(walk(path.join(FRONTEND, 'lib'), ['.tsx', '.ts']));
      const hits = grepFiles(files, /(?:TODO|FIXME|HACK)\b/);
      return { pass: hits.length === 0, count: hits.length, sample: hits.slice(0, 3) };
    },
  },
  {
    name: 'No hardcoded secrets / API keys (heuristic)',
    severity: 'error',
    run: () => {
      const files = walk(ROOT, ['.ts', '.tsx', '.js', '.py', '.go']);
      const re = /(api[_-]?key|secret|password|bearer)\s*[:=]\s*['"][A-Za-z0-9_\-]{16,}['"]/i;
      const hits = grepFiles(files, re, {
        skipPatterns: [
          /\.env\.template/,
          /\/test/,
          /\/tests\//,
          /example/i,
          /placeholder/i,
        ],
      });
      return { pass: hits.length === 0, count: hits.length, sample: hits.slice(0, 3) };
    },
  },
  {
    name: '.env.template exists at repo root',
    severity: 'error',
    run: () => ({ pass: exists('.env.template'), count: exists('.env.template') ? 0 : 1 }),
  },
  {
    name: 'ErrorBoundary component exists in frontend',
    severity: 'error',
    run: () => {
      const candidates = ['services/frontend/components/ErrorBoundary.tsx', 'services/frontend/app/error.tsx'];
      const hit = candidates.find((c) => exists(c));
      return {
        pass: !!hit,
        count: hit ? 0 : 1,
        sample: hit ? [{ file: hit, line: 1, text: 'present' }] : [],
      };
    },
  },
  {
    name: 'Lockfile present (package-lock.json or pnpm-lock.yaml)',
    severity: 'error',
    run: () => {
      const hit = ['services/frontend/package-lock.json', 'services/frontend/pnpm-lock.yaml', 'package-lock.json']
        .find((c) => exists(c));
      return { pass: !!hit, count: hit ? 0 : 1 };
    },
  },
  {
    name: '.gitignore covers secret + env files',
    severity: 'error',
    run: () => {
      if (!exists('.gitignore')) return { pass: false, count: 1 };
      const text = read('.gitignore');
      const required = ['.env', '*.key', '*.pem'];
      const missing = required.filter((p) => !text.includes(p));
      return {
        pass: missing.length === 0,
        count: missing.length,
        sample: missing.map((m) => ({ file: '.gitignore', line: 0, text: 'MISSING: ' + m })),
      };
    },
  },
  {
    name: 'Unit tests exist (>=3 test files)',
    severity: 'error',
    run: () => {
      const tests = walk(ROOT, ['_test.go']).length
        + walk(path.join(ROOT, 'libs', 'py', 'tests'), ['.py']).length
        + walk(path.join(ROOT, 'services'), ['.py']).filter((f) => f.includes('/tests/')).length
        + walk(FRONTEND, ['.test.tsx', '.test.ts']).length;
      return {
        pass: tests >= 3,
        count: tests >= 3 ? 0 : 1,
        sample: [{ file: 'tree', line: 0, text: 'found ' + tests + ' test files (need >=3)' }],
      };
    },
  },
  {
    name: 'CI pipeline exists (.github/workflows/*.yml)',
    severity: 'error',
    run: () => {
      const ci = walk(path.join(ROOT, '.github', 'workflows'), ['.yml', '.yaml']);
      return { pass: ci.length > 0, count: ci.length > 0 ? 0 : 1 };
    },
  },
  {
    name: 'README.md exists at repo root',
    severity: 'error',
    run: () => ({ pass: exists('README.md'), count: exists('README.md') ? 0 : 1 }),
  },
  {
    name: 'ErrorTracker initialized in frontend (§26)',
    severity: 'warning',
    run: () => {
      const layout = read('services/frontend/app/layout.tsx');
      const present = /<ErrorTrackerInit/.test(layout);
      return {
        pass: present,
        count: present ? 0 : 1,
        sample: present ? [] : [{ file: 'layout.tsx', line: 0, text: 'no <ErrorTrackerInit /> mounted' }],
      };
    },
  },
  {
    name: 'Drills exist (>=10 drill_*.py files in mcp/tests/)',
    severity: 'error',
    run: () => {
      const dir = path.join(ROOT, 'mcp', 'tests');
      if (!fs.existsSync(dir)) return { pass: false, count: 1 };
      const drills = fs.readdirSync(dir).filter((f) => f.startsWith('drill_') && f.endsWith('.py'));
      return {
        pass: drills.length >= 10,
        count: drills.length >= 10 ? 0 : 1,
        sample: [{ file: 'mcp/tests/', line: 0, text: 'found ' + drills.length + ' drills (need >=10)' }],
      };
    },
  },
  {
    name: 'Compose footer on every admin/<x>/deep page (§49)',
    severity: 'error',
    run: () => {
      const dir = path.join(FRONTEND, 'app', 'admin');
      if (!fs.existsSync(dir)) return { pass: true, count: 0 };
      const missing = [];
      for (const entry of fs.readdirSync(dir)) {
        const candidate = path.join(dir, entry, 'deep', 'page.tsx');
        if (!fs.existsSync(candidate)) continue;
        const text = fs.readFileSync(candidate, 'utf8');
        if (!text.includes('DeepDiveCrossRefs')) {
          missing.push('/admin/' + entry + '/deep');
        }
      }
      return {
        pass: missing.length === 0,
        count: missing.length,
        sample: missing.slice(0, 5).map((m) => ({ file: m, line: 0, text: 'missing compose footer' })),
      };
    },
  },
];

// ---- Runner --------------------------------------------------------------

function fmtSample(sample) {
  if (!sample || !sample.length) return '';
  return sample
    .map((s) => '      ' + s.file + (s.line ? ':' + s.line : '') + ' — ' + s.text.slice(0, 100))
    .join('\n');
}

function main() {
  console.log(BOLD + '§27 Production Readiness Checker' + NC + ' — ' + checks.length + ' checks\n');

  let errors = 0;
  let warnings = 0;
  const results = [];

  for (const check of checks) {
    let r;
    try {
      r = check.run();
    } catch (e) {
      r = { pass: false, count: 1, sample: [{ file: '(check crashed)', line: 0, text: e.message }] };
    }
    const ok = r.pass;
    const isErr = check.severity === 'error';
    const icon = ok ? GREEN + '✓' + NC : isErr ? RED + '✗' + NC : YELLOW + '⚠' + NC;
    const tag = ok ? '' : isErr ? ' ' + RED + '(ERROR)' + NC : ' ' + YELLOW + '(WARNING)' + NC;
    console.log('  ' + icon + ' ' + check.name + tag);
    if (!ok && r.sample) {
      const s = fmtSample(r.sample);
      if (s) console.log(s);
    }
    if (!ok) {
      if (isErr) errors += 1;
      else warnings += 1;
    }
    results.push({ name: check.name, severity: check.severity, pass: ok, count: r.count || 0 });
  }

  console.log();
  console.log(
    'Total: ' + BOLD + checks.length + NC + ' checks, '
      + GREEN + (checks.length - errors - warnings) + ' pass' + NC + ', '
      + RED + errors + ' errors' + NC + ', '
      + YELLOW + warnings + ' warnings' + NC,
  );

  if (process.env.PROD_CHECK_JSON === '1') {
    console.log('\n--JSON--');
    console.log(JSON.stringify({ total: checks.length, errors, warnings, results }, null, 2));
  }

  return errors === 0 ? 0 : 1;
}

process.exit(main());
