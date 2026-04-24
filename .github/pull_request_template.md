## Summary
<!-- What does this PR do? 1-3 bullets. Cite the design area if relevant (e.g. "Area 18 — saga recovery"). -->

## Test plan
<!-- How did you verify? -->
- [ ] Unit tests added / updated
- [ ] Integration test exercised (or explicit note why not)
- [ ] `make lint` passes
- [ ] `make test` passes
- [ ] Manual smoke against a local stack (`docker compose up` + `make run-*`)

## Checklist (global CLAUDE.md)
- [ ] No secrets committed
- [ ] Pydantic schemas on every new request/response
- [ ] Error handling on every new async operation (no bare `except`)
- [ ] Tests added / updated
- [ ] `.env.template` updated if new env vars
- [ ] CHANGELOG entry added under `## [Unreleased]`
- [ ] Docs updated (design-area table row if new area, README if new feature)

## Design-area alignment (pick any that apply)
- [ ] Tenant isolation preserved (RLS + payload filter + key namespace)
- [ ] New external dep wrapped in a CircuitBreaker
- [ ] Token budget pre-flight on any new LLM call
- [ ] Prompt version recorded in response
- [ ] Guardrails (CCB + post-hoc) on new inference path
- [ ] New event type has JSON Schema in `schemas/events/`
- [ ] New migration has a `down.sql`
- [ ] New endpoint is paginated (if list) and has idempotency-key support (if write)

## Risk + rollback
<!-- What can go wrong? How to roll back? -->

## Linked issue
<!-- Fixes # -->
