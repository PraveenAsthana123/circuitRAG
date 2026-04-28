'use client';

/**
 * Code quality (deep dive).
 *
 * Two topics: linting strategy (3-tier enforcement: IDE +
 * pre-commit + CI; Ruff/ESLint/Prettier/Mypy) + PEP 8 + auto-
 * formatting discipline (Black/Ruff/isort + composition with
 * Mypy strict + Bandit).
 *
 * Composes with /admin/principles/deep (SOLID + 17-factor) and
 * /admin/cicd/deep (CI gate runs lint at PR time).
 */

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  // ═══════════════════════════════════════════════════════════════
  // TOPIC 1 — Linting strategy (3-tier enforcement)
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'linting-strategy-three-tier',
    title: '1. Linting strategy — IDE + pre-commit + CI (the three-tier enforcement model)',
    status: 'shipped',
    coreConcept:
      "Linting is enforcement, not opinion. Three tiers: (1) IDE — same config as the repo, devs see red squiggles in real time, fast feedback before commit; (2) pre-commit hooks — run automatically on git commit, block bad code before it leaves the developer's machine; (3) CI — the source of truth; build fails if any check fails. Each tier compounds the previous: IDE catches 80%, pre-commit catches another 15%, CI catches the last 5%. Together they remove style debates from code review entirely.",
    oneLiner: 'IDE catches 80% live. Pre-commit catches 15% on push. CI catches the 5% that snuck through. Reviews focus on logic.',
    businessContext:
      'A team without lint discipline burns 30% of code-review time arguing trailing commas + import ordering + max line length. Reviewer fatigue → real bugs slip through because the cognitive budget went to whitespace. Three-tier linting cuts the style review to zero — humans review architecture + correctness + risk, machines enforce style.',
    fiveW: {
      what: 'Three layers of automated style + correctness checking. Same config across all three so contributors see one rule set everywhere.',
      why: 'Manual style review is the lowest-value, highest-frequency code review activity. Automate it; reclaim review attention for logic.',
      where: 'Every repo. Tier 1 in IDE/editor settings; tier 2 in `.pre-commit-config.yaml`; tier 3 in `.github/workflows/ci.yml`.',
      when: 'Day-1 of any new project. Retrofitting on existing projects: ratchet — only enforce on changed files until the legacy debt is paid down.',
      who: 'Engineer (tier 1 + 2); platform team owns tier 3 + ratchets.',
    },
    interview30s:
      'I run linting at three levels: IDE for real-time feedback, pre-commit hooks to block bad code on commit, CI as the source of truth. Same config for all three. I auto-format aggressively (Black, Prettier) so style is a non-decision. Treat warnings as errors. Include security linting (Bandit, ESLint security plugins). Enforce complexity caps (cyclomatic ≤ 10). Use a ratchet for legacy code: only enforce on changed files until debt is paid down.',
    hld: `flowchart LR
  Code[Developer types code] --> IDE[Tier 1: IDE squiggles]
  IDE -- pass --> Commit[git commit]
  Commit --> Pre[Tier 2: pre-commit hooks]
  Pre -- pass --> Push[git push]
  Push --> CI[Tier 3: CI gate]
  CI -- pass --> Merge[Merge approved]
  IDE -- fail --> Fix1[Fix in IDE]
  Pre -- fail --> Fix2[Fix; commit blocked]
  CI -- fail --> Fix3[PR fails build]
  Fix1 --> IDE
  Fix2 --> Commit
  Fix3 --> Code`,
    flowchart: `flowchart TD
  Start[Lint config drift] --> Q{Same config every tier?}
  Q -- no --> Drift[Diverging tiers - dev frustration]
  Q -- yes --> Auto{Auto-formatter active?}
  Auto -- no --> Debate[Style debates in review - bad]
  Auto -- yes --> Severity{Warnings as errors?}
  Severity -- no --> Tech_debt[Warnings accumulate forever]
  Severity -- yes --> Sec{Security plugin enabled?}
  Sec -- no --> Risk[Bandit/ESLint security skipped]
  Sec -- yes --> Cx{Complexity cap set?}
  Cx -- no --> God[God functions land]
  Cx -- yes --> Done[Healthy 3-tier lint]`,
    sequence: `sequenceDiagram
  participant Dev
  participant IDE
  participant Hook as Pre-commit
  participant CI
  Dev->>IDE: type code
  IDE-->>Dev: red squiggle (live)
  Dev->>Hook: git commit
  Hook->>Hook: ruff + black + mypy
  Hook-->>Dev: pass / block
  Dev->>CI: git push
  CI->>CI: same checks + coverage + security
  CI-->>Dev: build pass / fail`,
    coreLayers: [
      { layer: 'IDE', responsibility: 'Live feedback. Same config as the repo. Fast — every keystroke.' },
      { layer: 'Pre-commit', responsibility: 'Hard gate before code leaves the dev machine. Auto-fix where possible.' },
      { layer: 'CI', responsibility: 'Source of truth. Build fails if any check fails. No manual override.' },
      { layer: 'Auto-formatter', responsibility: 'Black / Prettier / gofmt. Non-decision — code is reformatted automatically.' },
      { layer: 'Security plugin', responsibility: 'Bandit / ESLint security / Brakeman. Catch unsafe patterns at lint time.' },
      { layer: 'Complexity cap', responsibility: 'Cyclomatic ≤ 10, function length ≤ 50, file length ≤ 500.' },
    ],
    lld: `classDiagram
  class LintTier {
    <<abstract>>
    +run() Result
  }
  class IDETier {
    +on_keystroke()
    +severity: live
  }
  class PreCommitTier {
    +on_commit()
    +autofix: bool
    +blocks: True
  }
  class CITier {
    +on_pr()
    +blocks_merge: True
    +source_of_truth
  }
  LintTier <|-- IDETier
  LintTier <|-- PreCommitTier
  LintTier <|-- CITier`,
    coreBuildingBlocks: [
      'Single config file (pyproject.toml / .eslintrc / .prettierrc) consumed by all 3 tiers',
      'Auto-formatter (Black, Prettier, gofmt) — non-decision',
      'Linter (Ruff, ESLint, golangci-lint) with security plugin',
      'Type checker (Mypy strict, TypeScript strict)',
      'Pre-commit framework (.pre-commit-config.yaml)',
      'CI workflow step that runs the SAME tools as pre-commit',
      'Complexity cap (Ruff C90, ESLint complexity, golangci-lint gocyclo)',
      'Ratchet strategy for legacy code (changed-files-only enforcement)',
    ],
    architectureRelevance: {
      backend: 'Python: Ruff + Black + Mypy. Go: gofmt + golangci-lint.',
      rag: 'Same as backend; AI-feature code goes through identical gates.',
      ai: 'Linter catches LLM-prompt typos via custom rules + dictionary checks.',
      microservices: 'Per-service config inherits from a shared `pyproject.toml` template; service chassis ships with linting on day 1.',
    },
    problem:
      'Code review attention burned on style. Bugs slip through because reviewers spent the cognitive budget on whitespace. PRs blocked for hours over import ordering arguments.',
    whyThisApproach:
      'Removing style from review = reclaiming the highest-leverage human attention for logic / risk / architecture. Auto-format + machine-enforced rules = no debate.',
    whenToUse: [
      'Every project, day 1',
      'Retrofitting an existing project (use ratchet)',
      'Multi-language repos (each tier has language-specific tools)',
    ],
    whenNotToUse: [
      'Disposable scripts',
      'Throwaway prototypes (the lint setup time exceeds the project lifetime)',
    ],
    input: 'Repo + chosen lint stack + .pre-commit-config.yaml + CI workflow.',
    process: [
      'Pick the canonical lint stack for each language (Ruff/Black/Mypy for Python, ESLint/Prettier for JS/TS, golangci-lint for Go).',
      'Centralize config (`pyproject.toml` / `.eslintrc.js`).',
      'Install pre-commit hooks; commit `.pre-commit-config.yaml` so contributors `pre-commit install` once.',
      'Mirror the same checks in CI; CI is the source of truth — pre-commit can be bypassed, CI cannot.',
      'For legacy debt, use ratchet: only enforce on changed files until the codebase is clean. Then drop the ratchet.',
      'Treat warnings as errors. Period. Suppress specific rules with explicit `# noqa: <code>` + a justification comment.',
    ],
    output: 'Zero-style-debate code review + auto-formatted codebase + CI-enforced complexity caps.',
    implementationSteps: [
      { step: 'pyproject.toml [tool.ruff] + [tool.black] + [tool.mypy]', logic: 'Single source of truth for Python lint config.' },
      { step: 'pre-commit hooks: ruff (fix), ruff-format, mypy', logic: 'Block bad code on commit; auto-fix where possible.' },
      { step: 'CI: ruff check + ruff format --check + mypy', logic: 'Source of truth. Identical commands to pre-commit.' },
      { step: 'Treat warnings as errors', logic: '`--max-warnings=0` for ESLint / `error` rule severity for Ruff. Warnings accumulate; treat them as fatal.' },
      { step: 'Security plugin', logic: 'Bandit (Python) + eslint-plugin-security (JS) + Brakeman (Ruby). Catches unsafe patterns at lint time.' },
      { step: 'Complexity cap', logic: 'Ruff C90 max-complexity = 10; ESLint complexity = 10. Forces functions to split before they become god-classes.' },
      { step: 'Ratchet for legacy', logic: '`pre-commit run --files <changed-only>`. Or `ruff check --files-only-changed` via git diff. Pay debt down on touch.' },
    ],
    codeExample: {
      language: 'toml',
      code: `# pyproject.toml — single source of truth for Python lint
[tool.ruff]
line-length = 88
target-version = "py311"

[tool.ruff.lint]
select = [
  "E",   # pycodestyle errors
  "F",   # pyflakes
  "I",   # import sorting (replaces isort)
  "N",   # pep8-naming
  "B",   # flake8-bugbear (likely bugs)
  "S",   # flake8-bandit (security)
  "C90", # mccabe complexity
  "UP",  # pyupgrade
  "SIM", # simplify
]
ignore = ["E501"]  # line-length handled by ruff format

[tool.ruff.lint.mccabe]
max-complexity = 10

[tool.mypy]
python_version = "3.11"
strict = true
warn_unused_ignores = true
warn_return_any = true
disallow_untyped_defs = true

# .pre-commit-config.yaml — tier 2
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.5.0
    hooks:
      - id: ruff
        args: ["--fix"]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies: [pydantic, fastapi]

# .github/workflows/ci.yml — tier 3 (excerpt)
- name: Lint + format check
  run: |
    ruff check .
    ruff format --check .
- name: Type check
  run: mypy .`,
    },
    realUseCase:
      'A 50-engineer Python team retrofitted Ruff + Black + Mypy strict over a quarter. Code review time per PR dropped from ~45 min to ~22 min — entire reduction was style + naming + import-order arguments going away. Bug-escape rate to production dropped 18% the same quarter (reviewer attention reallocated to real logic).',
    prosCons: {
      pros: [
        'Removes style from code review (massive cognitive save)',
        'Auto-format kills the import-order debate forever',
        'Security plugin catches unsafe patterns pre-PR',
        'Same config across IDE / pre-commit / CI = no divergence',
        'Bug-escape rate drops as reviewer attention reallocates',
      ],
      cons: [
        'Initial setup cost (~1 day for a typical repo)',
        'Legacy retrofitting needs a ratchet strategy',
        'Some auto-formatting is opinionated (Black) — debate gets pushed up to "should we use Black"',
      ],
    },
    limitations: [
      "Can't catch logic bugs; only style + likely-bug patterns + complexity.",
      'Cross-language repos need per-language stacks.',
      'Pre-commit can be bypassed (`--no-verify`); CI is the source of truth.',
    ],
    comparison: {
      left: 'Manual style review',
      right: 'Three-tier auto-lint',
      rows: [
        { aspect: 'Review time per PR', left: '~45 min', right: '~22 min' },
        { aspect: 'Style debates', left: 'Frequent', right: 'Zero' },
        { aspect: 'Style consistency', left: 'Drift', right: 'Locked' },
        { aspect: 'Security pattern catch', left: 'Random', right: 'Every commit' },
        { aspect: 'Reviewer fatigue', left: 'High', right: 'Lower' },
      ],
    },
    challenges: [
      'Auto-formatter choice — Black is opinionated, some teams resist.',
      'Pre-commit performance — slow hooks (Mypy on large codebase) frustrate devs.',
      'Legacy debt — retrofitting clean-slate enforcement breaks every PR.',
      'Cross-language repo coordination — each language tier needs its own setup.',
      'Suppressing rules requires justification — culture, not just config.',
    ],
    edgeCases: [
      { case: 'Pre-commit slow on large diffs', solution: 'Run only on changed files (default), cache pip wheels, run mypy in CI not pre-commit if it dominates' },
      { case: 'Auto-format conflicts with Git LFS or generated files', solution: '.gitignore the generated path; exclude from formatter via `[tool.black] extend-exclude`' },
      { case: 'Legacy file fails 200 rules on first run', solution: 'Ratchet: enforce only on changed files until the file is touched; then full enforcement on next change' },
      { case: 'Engineer bypasses pre-commit with --no-verify', solution: 'CI catches it; PR fails. Pre-commit is convenience; CI is the gate' },
      { case: 'Security plugin generates false-positive', solution: 'Suppress with `# noqa: S608` + a comment justifying. Reviewer gates the suppression' },
    ],
    solutions: [
      { problem: 'Code review burns on style', solution: '3-tier auto-lint removes style entirely from human attention' },
      { problem: 'Engineers ignore warnings', solution: 'Treat warnings as errors; CI fails on any' },
      { problem: 'Style drift across the codebase', solution: 'Auto-formatter (Black/Prettier) reformats on commit' },
      { problem: 'Legacy code is unfixable', solution: 'Ratchet on changed files only; debt pays down on touch' },
      { problem: 'God functions land', solution: 'Complexity cap (cyclomatic ≤ 10) — forces split before merge' },
    ],
    bestPractices: {
      do: [
        'Same config across all 3 tiers',
        'Auto-format on commit',
        'Treat warnings as errors',
        'Include security plugin (Bandit / eslint-plugin-security)',
        'Cap complexity (≤ 10)',
        'Ratchet strategy for legacy debt',
        'Justify every suppression',
      ],
      avoid: [
        'Different config per tier (drift)',
        'Manual style enforcement in code review',
        'Letting warnings accumulate',
        'Bypassing pre-commit without CI catching it',
        'Blanket suppressions without justification',
      ],
      optimize: [
        'Cache pip + npm + cargo in CI',
        'Run heavy tools (Mypy) in CI only, not pre-commit',
        'Pre-commit on changed files only',
      ],
    },
    antiPatterns: [
      'Manual style enforcement in PR comments',
      'Different lint configs in IDE vs CI',
      'Suppressing rules without justification',
      'Letting CI lint warnings drift to thousands',
      'Auto-format off + manual style review on',
    ],
    testing: ['Drill: same config produces same diagnostics in IDE / pre-commit / CI', 'Drill: pre-commit blocks a known-bad commit', 'Drill: CI fails on warnings'],
    testTypes: ['Tier consistency drill', 'Warning-as-error drill', 'Ratchet drill (legacy untouched, changed clean)'],
    testScenarios: [
      { scenario: 'Engineer commits code with `# fmt: off` block', expected: 'Pre-commit accepts; reviewer reviews the suppression' },
      { scenario: 'Warning lands on a changed file', expected: 'CI fails (warnings as errors)' },
      { scenario: 'Pre-commit bypassed via --no-verify', expected: 'CI catches; PR fails' },
      { scenario: 'Cyclomatic complexity 11 introduced', expected: 'Ruff C90 fails; refactor required' },
    ],
    testData: [
      { type: 'Real PRs', example: 'Sample 20 recent PRs; verify zero style comments from human reviewers' },
      { type: 'Lint output', example: '`ruff check .` exit 0 on main; non-zero blocks merge' },
    ],
    debuggingChecklist: [
      'Same lint version across IDE + pre-commit + CI?',
      'Auto-format running on commit?',
      'Security plugin enabled?',
      'Complexity cap configured?',
      'Warnings treated as errors?',
      'Ratchet applied if retrofitting?',
    ],
    productionIssues: [
      { issue: 'Drift between IDE + CI', rootCause: 'Different config sources; centralize in `pyproject.toml`' },
      { issue: 'Pre-commit too slow', rootCause: 'Mypy runs on whole codebase; move to CI; in pre-commit run only changed-files' },
      { issue: 'Legacy unfixable', rootCause: 'Apply ratchet on changed-files; build down debt on touch' },
    ],
    security: ['Bandit / eslint-plugin-security at every tier', 'Block hardcoded secrets via detect-secrets pre-commit hook', 'Audit + sign suppressions'],
    performance: [
      'IDE feedback < 200ms per file',
      'Pre-commit < 10s per commit (changed files only)',
      'CI lint < 2 min total',
    ],
    costConsiderations: ['Tooling: free (open-source)', 'Setup: ~1 day per repo', 'Saves: 20 min review time × N PRs/day'],
    scaling: ['Centralized config inherited by services', 'Per-language stacks', 'Service chassis ships with linting on day 1'],
    observability: ['CI lint pass-rate dashboard', 'Suppression count over time (target: declining)', 'Style debate count in PR comments (target: 0)'],
    metrics: [
      { name: 'lint_warnings_count', example: '0 (warnings as errors)' },
      { name: 'review_minutes_per_pr_p50', example: '22' },
      { name: 'style_pr_comments_per_week', example: '0' },
      { name: 'noqa_suppressions_count', example: '47 (each justified)' },
    ],
    failureModes: [
      { mode: 'Drift between tiers', detect: 'IDE shows different errors than CI', recover: 'Centralize config, same versions everywhere' },
      { mode: 'Slow pre-commit', detect: 'Devs complain', recover: 'Move heavy tools to CI; pre-commit runs only changed files' },
      { mode: 'Legacy debt', detect: 'CI fails on every change', recover: 'Apply ratchet (`--diff-against=main`); pay debt down on touch' },
    ],
    tradeoffs: [
      { decision: 'Auto-format aggressive (Black)', tradeoff: 'No debate; some teams resist Black\'s opinions' },
      { decision: 'Pre-commit blocks', tradeoff: 'Slows commit; saves PR rejection later' },
      { decision: 'Warnings as errors', tradeoff: 'Initial pain; cleanest signal long-term' },
    ],
    decisionMatrix: [
      { option: 'No lint', whenToUse: 'Throwaway scripts only' },
      { option: 'IDE-only lint', whenToUse: 'Solo project' },
      { option: 'Pre-commit + CI', whenToUse: 'Most teams; balance speed + enforcement' },
      { option: 'Three-tier (IDE + pre-commit + CI)', whenToUse: 'Production codebases (recommended)' },
    ],
    starStory: {
      situation: '50-engineer Python team. Code review averaged 45 min/PR; 30% on style.',
      task: 'Cut review time without sacrificing quality.',
      action: 'Rolled out Ruff + Black + Mypy strict at IDE + pre-commit + CI. Same `pyproject.toml` everywhere. Ratchet on legacy. Trained team on ratchet workflow.',
      result: 'Review time dropped 45 → 22 min. Bug-escape rate dropped 18% (reviewer attention reallocated). Style PR comments = 0. Engineers report more focus on logic.',
    },
    interviewTraps: [
      'Mention "we have linting" without specifying tiers',
      'No mention of auto-formatter (style still in review)',
      'No security plugin',
      'No complexity cap',
      'Pre-commit only, no CI source-of-truth',
    ],
    finalScript:
      'Three-tier enforcement: IDE + pre-commit + CI, same config everywhere. Auto-format aggressively (Black, Prettier). Treat warnings as errors. Include security plugin (Bandit) + complexity cap (≤10). Ratchet on legacy. Result: zero style debate in review; reviewer attention on logic; bug-escape rate drops.',
    alternatives: [
      { name: 'IDE-only', tradeoff: 'Fast feedback; no enforcement' },
      { name: 'Pre-commit only', tradeoff: 'Caught locally; bypassable via --no-verify' },
      { name: 'CI only', tradeoff: 'Caught at PR; slow feedback loop' },
      { name: 'All three (this)', tradeoff: 'Initial setup; sustainable enforcement' },
    ],
    monitoring: ['Lint pass-rate trend', 'Suppression count', 'Style PR comments', 'Review time per PR'],
    maturity: {
      mvp: 'Pre-commit + CI',
      production: 'Three tiers + auto-format + complexity cap + security plugin',
      enterprise: 'Three tiers + ratchet + per-service config inheritance + suppression audit',
    },
    projectFit: ['Every production codebase', 'Multi-team repos', 'Polyglot stacks'],
    interviewLine: 'Three tiers, same config. Auto-format. Warnings as errors. Complexity cap. Ratchet for legacy.',
  },

  // ═══════════════════════════════════════════════════════════════
  // TOPIC 2 — PEP 8 + auto-formatting (Python)
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'pep8-auto-formatting-python',
    title: '2. PEP 8 + auto-formatting — Black / Ruff / Mypy strict (Python tech-lead playbook)',
    status: 'shipped',
    coreConcept:
      "PEP 8 isn't a debate; it's a baseline. Tech leads enforce it via auto-formatter + linter — never manually in code review. The 2026 stack: Ruff (lint, replaces flake8 + isort + pyupgrade + bugbear + bandit) + Black (auto-format, opinionated, kills the comma debate) + Mypy strict (type safety, catches bugs before runtime). Pragmatic deviation from spec: 88-char lines (Black's default, fewer wraps than 79). Naming conventions are non-negotiable: snake_case / PascalCase / ALL_CAPS / leading underscore for private. AI-generated code goes through identical gates.",
    oneLiner: 'Ruff + Black + Mypy strict. 88 chars. snake_case / PascalCase / ALL_CAPS. Auto-format. Strict typing. Never debate style.',
    businessContext:
      'AI coding assistants (Copilot, Claude Code, Cursor) generate fast code that doesn\'t respect house style. Without auto-format + Mypy strict, every AI-generated PR triggers a "fix the style" review pass. With them, AI code lands at the same quality bar as human code — review focuses on whether the LOGIC is right, not whether the imports are sorted.',
    fiveW: {
      what: 'PEP 8 baseline + auto-formatter + linter + type checker stack for Python.',
      why: 'AI-assisted dev makes consistent code MORE important, not less. Style drift compounds across LLM-generated PRs.',
      where: 'Every Python repo. Per-service `pyproject.toml`.',
      when: 'Day 1. Ratchet for legacy.',
      who: 'Engineer (config + suppress); tech lead (enforce + audit suppressions).',
    },
    interview30s:
      "I don't enforce PEP 8 manually. I configure Ruff + Black + Mypy strict in `pyproject.toml`, wire them into pre-commit + CI, and let the tools enforce. Black handles formatting (88 chars, opinionated, kills the comma debate). Ruff handles lint (replaces flake8 + isort + pyupgrade + bandit). Mypy strict catches bugs before runtime. Naming conventions enforced via Ruff N rules. AI-generated code goes through the same gates. Result: code style is a non-decision; reviewer attention reallocates to logic.",
    hld: `flowchart LR
  Code[Python code] --> Ruff[Ruff: lint + import sort + bandit]
  Code --> Black[Black: auto-format 88 char]
  Code --> Mypy[Mypy strict: type check]
  Ruff --> Hook[pre-commit + CI]
  Black --> Hook
  Mypy --> Hook
  Hook --> Pass{All green?}
  Pass -- yes --> Merge[Merge approved]
  Pass -- no --> Fix[Auto-fix or block]`,
    flowchart: `flowchart TD
  Q1{Is style enforced manually?} -- yes --> Bad[Anti-pattern: human burns review on style]
  Q1 -- no --> Q2{Auto-formatter?}
  Q2 -- no --> Drift[Style drift across PRs]
  Q2 -- yes --> Q3{Mypy strict?}
  Q3 -- no --> Type_bugs[Type bugs reach runtime]
  Q3 -- yes --> Q4{Naming rules?}
  Q4 -- no --> Drift2[Mixed snake_case + camelCase]
  Q4 -- yes --> Done[PEP 8 enforced; review focuses on logic]`,
    sequence: `sequenceDiagram
  participant Dev
  participant IDE
  participant Pre as pre-commit
  participant CI
  Dev->>IDE: writes Python
  IDE->>IDE: ruff + black-format auto-fix on save
  Dev->>Pre: git commit
  Pre->>Pre: ruff check + ruff-format check + mypy
  Pre-->>Dev: pass / blocked + suggested fix
  Dev->>CI: git push
  CI->>CI: same checks
  CI-->>Dev: green / red`,
    coreLayers: [
      { layer: 'Ruff', responsibility: 'Lint + import sort + pyupgrade + bandit + complexity. Replaces 6+ tools.' },
      { layer: 'Black / Ruff format', responsibility: 'Opinionated auto-format. 88 chars (default). Kills comma + line-break debates.' },
      { layer: 'Mypy strict', responsibility: 'Type check; --strict flag enables most warnings. Catches type bugs before runtime.' },
      { layer: 'Naming rules', responsibility: 'Ruff N category enforces snake_case / PascalCase / ALL_CAPS automatically.' },
      { layer: 'Suppressions', responsibility: '`# noqa: S608  # justification` — every suppression has an audit comment.' },
    ],
    lld: `classDiagram
  class PythonLintStack {
    +ruff: lint
    +black: format
    +mypy: type
  }
  class Suppression {
    +rule_code
    +justification
    +reviewer_approved
  }
  PythonLintStack --> Suppression`,
    coreBuildingBlocks: [
      'pyproject.toml [tool.ruff] section — single config',
      '88-char line length (pragmatic deviation from PEP 8 79)',
      'Ruff selects: E F I N B S C90 UP SIM',
      'Mypy strict: warn_return_any = true, disallow_untyped_defs = true',
      'Auto-format on save (IDE) + pre-commit ruff-format hook',
      'Type hints required on every public function (PEP 484)',
      'Docstrings required (PEP 257) — first line single-sentence summary',
      'Ratchet via pre-commit on changed files only',
    ],
    architectureRelevance: {
      backend: 'Universal — every Python service uses this stack.',
      rag: 'Same; AI feature code goes through identical gates.',
      ai: 'AI-generated code (Copilot, Claude Code, Cursor) gets the same check; reviewer focuses on logic, not style.',
      microservices: 'Service chassis ships with `pyproject.toml` + `.pre-commit-config.yaml` on day 1.',
    },
    problem:
      "AI-generated Python code doesn't naturally respect house style — different naming, different import order, different line lengths per session. Without strict auto-format + lint, every AI-PR becomes a style-fix review. Mypy issues compound when types are loose.",
    whyThisApproach:
      "Ruff is fast (~10-100x flake8 + isort combined), Black is opinionated (kills debate), Mypy strict catches type bugs that 80% of unit tests miss. Three tools, one config, zero style debates.",
    whenToUse: [
      'Every Python project',
      'Especially: AI-assisted dev (Copilot, Cursor, Claude Code)',
      'Greenfield + retrofitted (use ratchet)',
    ],
    whenNotToUse: [
      'Throwaway scripts',
      'Single-file experiments',
    ],
    input: 'Python codebase + `pyproject.toml` + pre-commit + CI.',
    process: [
      'Configure `[tool.ruff]` + `[tool.black]` (or use ruff format) + `[tool.mypy]` in `pyproject.toml`.',
      'Install pre-commit; commit `.pre-commit-config.yaml`.',
      'CI runs the same commands.',
      'Engineers `pre-commit install` once.',
      'AI-generated code is auto-formatted on commit; lint catches deviations.',
      'Type hints required on every public function; gradually backfill private functions.',
      'Suppressions require justification comments; audit periodically.',
    ],
    output: 'Auto-formatted, type-checked, security-linted Python codebase. Zero style PR comments. Type bugs caught at lint time.',
    implementationSteps: [
      { step: '[tool.ruff] line-length = 88', logic: 'Pragmatic deviation from PEP 8 79; Black default; fewer wraps.' },
      { step: '[tool.ruff.lint] select all categories', logic: 'E F I N B S C90 UP SIM — broad coverage; suppress specific rules with justification.' },
      { step: '[tool.ruff.lint.mccabe] max-complexity = 10', logic: 'Cyclomatic cap; god functions blocked at lint time.' },
      { step: '[tool.mypy] strict = true', logic: 'Enables warn_return_any + warn_unused_ignores + disallow_untyped_defs + more.' },
      { step: '[tool.mypy] python_version = "3.11"', logic: 'Match runtime; catches version-specific issues (e.g. `dict[str, int]` vs `Dict[str, int]`).' },
      { step: 'Pre-commit: ruff (--fix), ruff-format, mypy', logic: 'Auto-fix where possible; block on type errors.' },
      { step: 'CI: same commands', logic: 'Source of truth.' },
      { step: 'Type-hint every public function', logic: 'Mypy strict requires; gradual backfill on private.' },
    ],
    codeExample: {
      language: 'python',
      code: `# Good — modern Python with type hints + docstring
def calculate_discount(price: float, percent: int) -> float:
    """Apply percentage discount to price.

    Raises ValueError if percent < 0 or > 100.
    """
    if not 0 <= percent <= 100:
        raise ValueError(f"percent must be 0-100, got \${percent}")
    return price * (1 - percent / 100)


# Naming conventions (Ruff N rules enforce automatically)
class UserProfile:                   # PascalCase for classes
    MAX_RETRIES = 5                  # ALL_CAPS for class constants

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id        # snake_case for instance vars
        self._cache: dict[str, str] = {}   # leading underscore = private
        self.__secret: str = ""       # double underscore = name-mangled


# Anti-patterns auto-flagged by Ruff:
# bad_func() means E501 if > 88 chars; N802 if Pascal_Case
# x == None  means E711; should be 'x is None'
# if x == True:  means E712; should be 'if x:'
# except:  means E722 bare except
# x = []
# x.append(1)  means could be x = [1]; SIM rules`,
    },
    realUseCase:
      'A team adopted the Ruff + Black + Mypy strict stack mid-project. PR style comments dropped from ~5 per PR to 0. Mypy strict caught a Optional[str] / str confusion that had been generating intermittent NoneType errors in production for 6 months. After full type-hint backfill (~2 weeks), runtime type errors went to zero.',
    prosCons: {
      pros: [
        'Ruff is fast (~10-100x flake8 + isort combined)',
        'Black kills the formatting debate',
        'Mypy strict catches type bugs before runtime',
        'AI-generated code goes through same gates as human code',
        'Replaces 6+ tools (flake8 + isort + pyupgrade + bandit + bugbear + ...) with one',
      ],
      cons: [
        'Black is opinionated; some teams resist',
        'Mypy strict requires type-hint backfill on legacy',
        'Initial setup ~1 day; backfill ~weeks',
      ],
    },
    limitations: [
      'Cannot catch logic bugs',
      'Some patterns require runtime type checks (Pydantic) instead of static',
      'Type stubs needed for untyped third-party libraries',
    ],
    comparison: {
      left: 'PEP 8 manual',
      right: 'Ruff + Black + Mypy strict',
      rows: [
        { aspect: 'Setup time', left: 'Hours', right: '~1 day' },
        { aspect: 'Style debates', left: 'Frequent', right: 'Zero' },
        { aspect: 'Type safety', left: 'Optional', right: 'Enforced' },
        { aspect: 'Speed', left: 'Slow (flake8)', right: 'Fast (Ruff)' },
        { aspect: 'AI-PR quality', left: 'Variable', right: 'Consistent' },
      ],
    },
    challenges: [
      'Black opinionated formatting (some teams resist)',
      'Mypy strict on legacy = many false positives initially',
      'Type stubs needed for untyped libraries',
      'AI assistants may regenerate code that fails lint; CI catches',
      'Pre-commit slow on big diffs (mitigation: changed-files only)',
    ],
    edgeCases: [
      { case: 'Untyped third-party lib', solution: '`# type: ignore[import]` + comment + plan to add stubs' },
      { case: 'Generated code fails lint', solution: 'Add path to `[tool.black] extend-exclude`; document the exclusion' },
      { case: 'Mypy false positive', solution: '`# type: ignore[<error-code>]` + justification; reviewer audits' },
      { case: 'Large dict literal needs special formatting', solution: '`# fmt: off / fmt: on` block; reviewer audits' },
    ],
    solutions: [
      { problem: 'AI code style drift', solution: 'Ruff + Black + Mypy enforce on every commit' },
      { problem: 'Type bugs in production', solution: 'Mypy strict catches at lint time' },
      { problem: 'Slow flake8', solution: 'Ruff replaces it (~10-100x faster)' },
      { problem: 'Legacy untyped code', solution: 'Ratchet: enforce on changed files only; backfill on touch' },
    ],
    bestPractices: {
      do: [
        '88-char lines (Black default)',
        'Type hints on every public function',
        'Docstring first line = single sentence',
        '`is None` not `== None`',
        'Specific exception types, not bare `except:`',
        'Trailing commas in multi-line collections',
        'Justify every `# noqa:` + `# type: ignore`',
      ],
      avoid: [
        'Bare `except:`',
        '`x == None` or `x == True`',
        'Mixed naming (snake_case + camelCase)',
        'Untyped public functions',
        'Manual style enforcement in code review',
      ],
      optimize: [
        'Ruff replaces multiple tools (faster)',
        'Pre-commit on changed files only',
        'Mypy in CI only if it dominates pre-commit',
      ],
    },
    antiPatterns: [
      'Manual PEP 8 enforcement in PR review',
      'Different lint config per service',
      'Mypy not strict (loose mode = vague signals)',
      'Suppressions without justification',
      'Letting Mypy errors accumulate',
    ],
    testing: ['Drill: pre-commit blocks bad code', 'Drill: Mypy strict catches Optional/None confusion', 'Drill: Ruff catches `except:` and `== None`'],
    testTypes: ['Style drill', 'Type drill', 'Naming drill'],
    testScenarios: [
      { scenario: '`def f(x):` (no type hints)', expected: 'Mypy strict fails: missing type annotation' },
      { scenario: '`if x == None:`', expected: 'Ruff E711 fails: use `is None`' },
      { scenario: '`def Bad_Func():`', expected: 'Ruff N802 fails: function should be snake_case' },
      { scenario: 'Function with cyclomatic 11', expected: 'Ruff C90 fails: complexity exceeds 10' },
    ],
    testData: [
      { type: 'Real AI-PR', example: '50 LLM-generated PRs; verify zero style comments needed from human reviewers' },
      { type: 'Mypy errors', example: 'Run `mypy --strict .`; expect 0 errors on main' },
    ],
    debuggingChecklist: [
      '`pyproject.toml` has [tool.ruff] + [tool.mypy]?',
      'Pre-commit installed?',
      'CI runs same commands?',
      'Mypy strict = true?',
      'Naming rules selected (N)?',
      'Type hints on every public function?',
    ],
    productionIssues: [
      { issue: 'Optional/None confusion in prod', rootCause: 'Mypy not strict; enable it' },
      { issue: 'Style drift across services', rootCause: 'Per-service config; centralize in shared template' },
      { issue: 'Pre-commit too slow', rootCause: 'Mypy on full codebase; restrict to changed files in pre-commit, full check in CI' },
    ],
    security: ['Bandit included via Ruff S category', 'Detect-secrets pre-commit hook', 'Audit `# noqa: S*` (security suppressions)'],
    performance: [
      'Ruff: ~10-100x flake8 (Rust-based)',
      'Mypy: O(N) on type graph; cache aggressively',
      'Pre-commit: < 10s on changed files',
    ],
    costConsiderations: ['Tools: free', 'Setup: ~1 day', 'Type-hint backfill: ~weeks for legacy'],
    scaling: ['Centralized `pyproject.toml` template', 'Per-service inheritance', 'Service chassis ships with linting'],
    observability: ['Mypy error count over time', 'Ruff suppression count', 'Type coverage %'],
    metrics: [
      { name: 'mypy_errors_count', example: '0' },
      { name: 'ruff_suppressions_count', example: '47' },
      { name: 'type_coverage_percent', example: '94' },
      { name: 'lint_time_seconds_p95', example: '8' },
    ],
    failureModes: [
      { mode: 'Mypy strict floods on retrofit', detect: '500+ errors on first run', recover: 'Apply ratchet; enforce on changed files only' },
      { mode: 'Black + Ruff conflict', detect: 'Pre-commit alternates fixes', recover: 'Use ruff format (single tool)' },
      { mode: 'Type stub missing', detect: 'Mypy `import-not-found`', recover: 'Add `# type: ignore[import]` + justification + plan' },
    ],
    tradeoffs: [
      { decision: 'Black opinionated', tradeoff: 'No debate; some teams resist' },
      { decision: 'Mypy strict', tradeoff: 'Initial pain; long-term safety' },
      { decision: 'Ruff replaces 6 tools', tradeoff: 'Single config; faster; slightly different rule selection vs flake8' },
    ],
    decisionMatrix: [
      { option: 'Manual PEP 8', whenToUse: 'Throwaway scripts only' },
      { option: 'Flake8 + Black + Mypy', whenToUse: 'Legacy migration' },
      { option: 'Ruff + Black + Mypy strict (this)', whenToUse: 'Production codebases (recommended)' },
      { option: 'Ruff format + Ruff lint + Mypy strict', whenToUse: 'Single-tool simplification' },
    ],
    starStory: {
      situation: 'Production NoneType error firing intermittently for 6 months; root cause unknown.',
      task: 'Find + fix.',
      action: 'Enabled Mypy strict; ran on the codebase. Surfaced an `Optional[str]` returned but used as `str` without check. 1-line fix; tests added. Backfilled type hints across the package over 2 weeks.',
      result: 'NoneType errors went to zero. Subsequent type bugs caught at lint time. PR review focuses on logic.',
    },
    interviewTraps: [
      'Citing flake8 (slow; Ruff replaces)',
      'Mypy not strict (loose signals)',
      'Manual style enforcement in PR comments',
      'Different lint config per service',
    ],
    finalScript:
      'Ruff + Black (or Ruff format) + Mypy strict. 88 chars. Type hints on every public function. Naming rules via Ruff N. Auto-format on commit. Mypy in CI. Same config across services. AI-generated code goes through the same gates. Result: PR style comments = 0; reviewer attention on logic.',
    alternatives: [
      { name: 'Flake8 + Black + Mypy', tradeoff: 'Slower; works' },
      { name: 'Pylint', tradeoff: 'Comprehensive; very slow; opinionated' },
      { name: 'Ruff + Ruff format + Mypy', tradeoff: 'Single tool; less debate; recommended for new projects' },
      { name: 'Ruff + Black + Mypy strict (this)', tradeoff: 'Best practice; battle-tested' },
    ],
    monitoring: ['Mypy error trend', 'Ruff suppression count', 'Type coverage %'],
    maturity: {
      mvp: 'Ruff + Black + pre-commit',
      production: '+ Mypy strict + CI gate + type hints on public functions',
      enterprise: '+ Per-service config inheritance + suppression audit + type stub maintenance',
    },
    projectFit: ['Every Python production codebase', 'AI-assisted dev', 'Polyglot repos with Python service'],
    interviewLine: 'Ruff + Black + Mypy strict. 88 chars. Type hints on public. Auto-format. Zero PR style comments.',
  },
];

export default function CodeQualityDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">Code quality (deep dive)</h1>
        <p className="design-areas-sub">
          Linting strategy as three-tier enforcement (IDE + pre-commit + CI)
          + the Python-specific Ruff + Black + Mypy strict playbook for the
          AI-assisted-dev era. AI-generated code gets the same gates as human
          code; reviewer attention reallocates from style to logic.
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
      <DeepDiveCrossRefs
        refs={[
          { href: '/admin/principles/deep', label: 'Principles — SOLID + 17-factor', why: 'principles define WHAT; this page covers HOW the linter enforces (cyclomatic cap on SRP violation, type hints on DIP boundary)' },
          { href: '/admin/cicd/deep#cicd-master-pipeline', label: 'CI/CD — pipeline gate', why: 'tier 3 of the linting stack runs at PR time as part of the CI pipeline; same commands as pre-commit' },
          { href: '/admin/checklist/deep#lifecycle-checklist', label: 'Checklist §4 Coding', why: 'Linter zero warnings + type hints + no catch-all are direct checklist rows' },
          { href: '/admin/security/deep#devsecops-pipeline', label: 'Security — Bandit + secret-scan', why: 'security plugins (Bandit / detect-secrets) are part of the lint stack; not a separate scan' },
          { href: '/admin/python/deep', label: 'Python — runtime patterns', why: 'this page covers static; python/deep covers async + immutability + validation patterns the linter cannot enforce' },
        ]}
      />
    </div>
  );
}
