# AI Coding Governance Policy

Status: active

Scope: all human and AI coding agents that create, modify, test, review, deploy, or monitor code in this repository.

Purpose: reduce repeated defects from automated code changes by requiring scoped work, explicit contracts, observable behavior, reproducible verification, and fast failure diagnosis.

## 1. Common AI Coding Failure Modes

AI coding agents in this repository must actively guard against these recurring mistakes:

- Changing too many unrelated files while fixing a narrow issue.
- Guessing API routes, environment variables, model names, CLI flags, database schemas, or package names.
- Passing local smoke checks while skipping integration, contract, or production-build checks.
- Fixing lint by suppressing rules instead of understanding whether the rule protects runtime behavior.
- Adding background workers, self-healing loops, or schedulers without status reporting, backoff, idempotency, and a kill switch.
- Creating tools that lack help text, JSON output, error codes, structured logs, or drill coverage.
- Making frontend changes that pass unit tests but fail `next build`, typed routes, accessibility, or browser console checks.
- Making backend changes without request IDs, typed contracts, health signals, or clear failure classes.
- Writing tests that mock the broken part of the system instead of exercising the contract boundary.
- Updating dependencies without checking audit, lockfile churn, engine compatibility, and downstream package conflicts.
- Leaving generated reports, traces, or runtime artifacts mixed with source changes in commits.
- Failing to state what was fixed, what was tested, what remains blocked, and what needs operator action.

## 2. Work Intake Rules

Before editing code, an agent must identify:

- The user-visible failure or missing capability.
- The owning service, module, script, or policy boundary.
- The expected contract: API shape, CLI flags, event schema, DB schema, UI route, MCP tool surface, or background job behavior.
- The smallest file set needed to complete the task.
- The verification commands that prove the fix.
- Any external dependency that cannot be resolved locally, such as Kubernetes, Snyk token, cloud credentials, or remote MCP services.

If the contract is unclear and the change creates a new public surface, write or update an ADR before implementation.

## 3. Change Control Rules

Every AI code change must follow these controls:

- Keep edits scoped to the task. Do not reformat or refactor unrelated files.
- Do not revert user or monitor changes unless explicitly instructed.
- Prefer existing local patterns over new abstractions.
- Do not invent configuration. Read existing docs, schemas, route definitions, package files, and scripts first.
- Make risky write operations approval-gated.
- Make background work idempotent and resumable.
- Add `--help`, `--status`, and machine-readable `--json` output to operational CLIs when practical.
- Use stable error codes or failure classes for expected failures.
- Include rollback or disable guidance for schedulers, workers, and self-healing loops.

## 4. Required Verification Matrix

Agents must choose the smallest sufficient set from this matrix and report exactly what ran.

| Change type | Required checks |
|---|---|
| Python service | `ruff`, focused `pytest`, relevant smoke or drill |
| FastAPI/API route | focused route tests, OpenAPI/contract check if present, service health check |
| Frontend route/component | lint, TypeScript, focused test, production build for Next.js routing changes |
| MCP tool/server | tool list check, per-tool happy path, per-tool failure path, approval gate drill if writes occur |
| Scheduler/worker | one-shot run, status output, idempotency check, retry/backoff behavior |
| Dependency update | lockfile review, audit, build/test, engine compatibility note |
| Security/auth/policy | negative tests, audit/log evidence, fail-closed behavior |
| Observability | logs include correlation IDs, metrics/traces emit, dashboard/report path documented |
| Infrastructure/Kubernetes | manifest validation, dry run when possible, rollback note |

When a check cannot run locally, record the blocker and the exact command the operator must run.

## 5. Test Policy

New or changed behavior must have tests at the right level:

- Unit tests for deterministic pure logic and edge cases.
- Contract tests for API, CLI, MCP, schema, and event boundaries.
- Integration tests for database, queue, cache, model, and service interactions.
- Smoke tests for deployed or locally served workflows.
- Validation tests for bad inputs, permission failures, missing env vars, and timeout behavior.
- Regression tests for every fixed bug when the failure can be reproduced.

Tests should assert observable outcomes, not implementation trivia.

## 6. Self-Healing And Self-Monitoring Policy

Self-healing jobs and autonomous agents must be controlled systems, not silent mutation loops.

Required capabilities:

- A single task board or state file showing `working_now`, `next_up`, `fixed`, and `blocked`.
- `--once` mode for controlled execution.
- `--status` and `--status --json` for operators and dashboards.
- Bounded retries with exponential backoff.
- Idempotency keys or durable state for write actions.
- Approval gate for destructive, security-sensitive, database-write, deployment, and external-ticket actions.
- Clear stuck-task detection and escalation after repeated failures.
- Structured logs with task ID, actor, tool, model, attempt, duration, result, and error class.
- Metrics for attempts, successes, failures, latency, queue depth, blocked tasks, and approval outcomes.
- A kill switch or feature flag.

Self-healing agents must not hide failures. They should repair known safe classes and report unknown failures.

## 7. Observability And Troubleshooting Policy

Every service, tool, and worker should expose enough evidence to answer: what is running, what failed, why, where, and what changed?

Required operational signals:

- Health endpoint or status command.
- Structured logs with request ID or task ID.
- Error classes that separate validation, dependency, timeout, auth, policy, and internal failures.
- Metrics for latency, error rate, throughput, retry count, and queue depth where applicable.
- Trace spans around external calls, model calls, DB calls, cache calls, and tool invocations.
- Report artifacts for long-running drills and autonomous loops.
- Operator command center or runbook entry for common checks.

Troubleshooting output should be copy-paste friendly and include exact commands, paths, and next actions.

## 8. Commit And Report Policy

Before commit, an AI agent must:

- Run `git status --short`.
- Stage only files related to the task.
- Exclude runtime artifacts unless the task explicitly updates reports or golden outputs.
- Run the selected verification matrix.
- Write a commit message that states the behavioral outcome and references the governing ADR or policy when applicable.

Final reports must include:

- What changed.
- What passed.
- What could not be verified.
- Remaining blockers or operator-owned actions.
- Any dependency, engine, credential, or external-resource warning.

## 9. Preventive Controls To Add Over Time

The forward approach is to turn this policy into automated gates:

- Pre-commit checks for lint, formatting, secret scan, and generated artifact drift.
- CI jobs for backend tests, frontend build, MCP drills, and command-center smoke checks.
- Dependency audit gates with explicit allowlists for temporary exceptions.
- Contract snapshots for API routes, MCP tools, CLI flags, and event schemas.
- Required `--status --json` for workers and long-running scripts.
- Dashboard panels for task queue, model health, approval queue, failed drills, and dependency drift.
- Release checklist that blocks deploys without smoke, integration, and rollback evidence.
- Periodic scheduled drills for model availability, MCP tool surfaces, Snyk/k8s readiness, and ingestion approval workflows.

## 10. Minimum Done Definition

A change is not done until:

- The contract is documented or discoverable.
- The code is scoped and reviewed against existing patterns.
- Tests or drills prove the changed behavior.
- Logs/status make failures diagnosable.
- The final report names fixed issues and remaining blockers.
- The commit contains only intended files.
