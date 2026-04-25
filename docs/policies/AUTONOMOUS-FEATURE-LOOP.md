# Autonomous Feature Loop — DocuMind

**Status:** Opt-in per session.
**Activation:** user says "enter the loop" / "continuous mode" /
"make next automated" / "keep going until I stop."
**Scope:** Repository-level loop behavior. Apply this together with any
user- or tool-level local automation policy active in your
environment.

> When active, the agent picks the next feature without waiting for a
> "next" prompt. Each iteration ends with a commit hash + one-line
> insight. Loop stops only on explicit user signal, gated operation,
> drill failure, environmental flake, or empty menu.

---

## Per-iteration checklist (DocuMind-specific)

Each loop iteration must:

1. **Pick** from:
   - Follow-up notes in the most-recent DEMO-*.md files.
   - Bug notes in recent commit messages (search `git log --grep="follow-up"`).
   - Composition bugs — look for "feature X and feature Y don't
     intersect correctly" after multi-capability commits.
   - Refactor debt — when the same pattern appears in 3+ files.

2. **Build** real code — MCP servers, inference-svc routes, core lib,
   whichever the feature demands. No mocks in drills.

3. **Drill** under `mcp/tests/drill_*.py` with:
   - `# RESOURCES: <tokens>` tag on line 1.
   - `✓` / `✗` markers per step.
   - `ALL N STEPS PASSED` banner on success.
   - At least one NEGATIVE assertion (something that should NOT
     happen, proven not-happening).

4. **Doc** under `docs/DEMO-*.md` (if feature warrants) OR inline in
   commit message for small fixes.

5. **Commit** with message that includes:
   - Rationale (why).
   - What the drill proves (both positive AND negative).
   - Any composition-of-features note.

6. **Verify** runner still green:
   ```bash
   scripts/run_drills.py --parallel 4 --only <related-terms>
   ```

7. **Report** in one-sentence insight format:

   ```
   ★ Insight ─────────────────────────────────────
   - [The concrete lesson.]
   ─────────────────────────────────────────────────

   Commit `<hash>`. N/N drill steps green. Loop continues.
   ```

8. **Loop** — next iteration, no "next" prompt needed.

## DocuMind-specific stop conditions

Beyond the global stop conditions, stop when:

- **MCP HR or ITSM or drill server has been restarted 5+ times in a row** —
  suggests persistent port conflict or OTel collector down.
- **Postgres migration drift** — schema changed since last loop start;
  re-run migrations + verify before continuing.
- **Golden demo fails** — whatever we're iterating on broke the
  end-to-end flow. Fix golden demo before the next iteration.

## Menu-inference helpers

When the loop needs a candidate, it searches:

- Recent `DEMO-*.md` files for "follow-up" / "open" / "next" /
  "TODO" sections.
- Recent commit bodies for "documented as gap" / "small bug" /
  "left behind."
- `mcp/tests/drill_*.py` for flakes (any drill with a sleep that
  could be replaced by a poll).
- `services/*/app/` for TODO comments.

## Example iteration shapes

Representative loop candidates in this repository:

- Composition bug after a multi-server routing change.
- Follow-up fix when worker behavior diverges from API behavior.
- Refactor once the same coordination pattern appears in 3+ files.

Keep examples generic here. Put time estimates, commit hashes, and
session-specific outcomes in demo docs or commit history rather than in
the standing policy.
