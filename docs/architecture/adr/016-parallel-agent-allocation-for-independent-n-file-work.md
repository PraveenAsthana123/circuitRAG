# ADR-016: Parallel-agent allocation for independent N-file work

## Status

Accepted — landed across four demonstrations in the autonomous-loop
session: Phase 5S (`d06fe59`), Phase 6C (`c4e65ad`), Phase 6J
(`8e5f1d1`), Phase 6K + 6L (`45c5ad5` + `887fa9a`).

## Context

The autonomous loop runs as a sequential rhythm: pick → build →
drill → doc → commit → loop. Most iterations decompose cleanly
into single-thread work. But four iterations in this session
showed a different shape: the work was N independent file edits
plus one cross-cutting drill that locks contracts. Those
iterations benefited from parallel-agent allocation.

The pattern was undocumented up to ADR-016. Operators reading
the session's verdict log can see "agent" mentioned in commit
messages but can't tell when a parallel split is appropriate vs
when single-thread is faster. ADR-016 names the pattern and its
preconditions.

The four demonstrations:

| Phase | What was parallelized | Outcome |
|---|---|---|
| 5S | 1 agent writing a 247-line Server Component while I wrote the structural drill | Saved ~50% wall time vs serial; drill passed agent output first try |
| 6C | 3 agents tagging 23 drill files with `# RESOURCES:` tokens in chunks of 8/7/8 | Wall ~30s vs ~5 min serial; agents hit rate limit AFTER artifacts landed (reports lost; artifacts intact) |
| 6J | The parallel content stream shipped 2 paired scripts; my single drill locked both contracts via integration assertion | Cooperation across 2 sessions instead of duplicate work |
| 6K + 6L | 50-file integration commit (drill docstring uplift) + 27-file integration commit (docs + tooling) — work originated in parallel session, merged via single commit | Two streams' work landed coherently |

## Decision

**Use parallel-agent allocation when ALL of these hold; otherwise
stay single-threaded:**

1. **Independent files**. Each agent's work touches a disjoint
   file set. Two agents writing the same file produce merge
   conflicts that cost more than serial wall time.

2. **Spec is concrete enough that an agent can't drift**. The
   instruction must specify: exact file path, exact required
   shape (line count target, assertion list, naming convention),
   exact decisions to make autonomously vs report back.

3. **Drill exists or is being written in parallel**. Agents can
   misinterpret. The drill is the contract that locks the agent's
   output to the design intent. Without a drill, "the agent
   completed it" is unverifiable.

4. **The work is large enough to amortize the agent overhead**.
   Briefing an agent costs ~2 paragraphs of prompt + ~30s of
   round-trip. For work under ~100 lines or ~3 files, single-
   thread is faster. For work over ~5 files OR ~250 lines, the
   parallel split wins.

5. **Each agent's output can be verified independently**. The
   drill should be able to assert each agent's contribution
   without needing all of them to complete first. Coupling
   between agents' outputs makes failure recovery harder.

### Allocation patterns

**A. One agent + one foreground drill (5S, 6J shape)**:
operator (or me) writes the drill in the foreground while ONE
agent writes the substantive feature in the background. Drill
finishes first, runs against agent output when ready.

**B. N agents on chunked work + foreground integration (6C
shape)**: split work into N independent chunks of ~8 files each;
run agents concurrently with `run_in_background: true`; merge
afterward. Drill (run synchronously after merge) verifies the
combined state.

**C. Two parallel streams converging (6K + 6L shape)**: the
parallel content-stream produced N changes; my session integrated
them via single commits split by scope. The drill state at merge
time confirmed both streams' work composed cleanly.

### What NOT to parallelize

- **Serial bug-fix iterations**. Each iteration depends on the
  previous commit; running them in parallel produces merge chaos.
- **Drill-then-feature work**. The drill must precede the feature
  it locks; an agent writing the feature without seeing the drill
  is more likely to drift.
- **Doc updates that span related sections**. The cheatsheet,
  council-telemetry runbook, and ADR-015 were updated together
  by the parallel content-stream — but they shipped as one logical
  doc commit (6L), not three parallel ones.

## Consequences

### Positive

* **Wall-time reduction proportional to agent count**. 6C took
  ~30s for 23 files vs ~5 min single-thread. Same shape applied to
  larger refactors would scale similarly.
* **Cooperation across multiple AI sessions becomes structured**.
  6K and 6L committed work originated in a parallel session
  without forcing one to subsume the other. Each session can
  iterate at its own cadence.
* **The drill becomes the synchronization point**. Agents finish
  at different times; the drill (or full readonly sweep) is the
  single mechanism that asserts the combined state is correct.
  No need for inter-agent coordination protocols.

### Negative

* **Rate-limit surprises**. Phase 6C's three agents all hit a
  rate limit AFTER completing their core file edits but before
  writing summary reports. The artifacts landed correctly; the
  reports were truncated. Verifying via the drill (not the agent
  reports) was what saved the iteration.
* **Briefing cost is non-trivial**. Each agent gets ~2 paragraphs
  of prompt context. Three agents = 6 paragraphs. Below the
  amortization threshold (~5 files), serial is faster.
* **Coupling between agents** is a hidden cost. If agent A and
  agent B both edit imports of the same module, their outputs
  may be syntactically valid but semantically inconsistent.
  Independence-by-file-set is the cheapest discriminator.

### Risks accepted

* **One agent goes off-spec while others succeed**. The drill
  catches it (the agent's file fails the assertion), but only
  AFTER all agents return. Worst-case wall time = slowest agent
  + drill + recovery commit.
* **Cross-session coordination drift**. The parallel content-
  stream and this session occasionally commit conflicting
  changes (e.g. interpreter path migrations vs PY_BIN priority
  flip). The verdict log surfaces conflicts; humans (operators,
  not agents) reconcile.

## Alternatives considered

### A. Serial (the default — when to NOT use parallel)

Pros: simplest mental model; no coordination cost; small commits.
Cons: wall-time linear in work size; under-utilizes available
agent parallelism.

The decision favors parallel WHEN the four preconditions hold;
serial otherwise. Mixed pattern is normal.

### B. One agent doing all the work in one shot

Pros: zero coordination cost; one prompt, one output.
Cons: large diffs are hard to review; an agent making 50 file
edits in one shot is more likely to drift on later files than
an agent making 8 edits with a clear chunked spec; recovery
from partial failure requires re-running the whole agent.

Discarded for chunked work where independence is clear.

### C. Inter-agent coordination protocol (e.g. shared scratch file)

Pros: agents can synchronize on intermediate state.
Cons: adds a coordination surface that itself can drift;
introduces ordering dependencies that defeat parallelism;
in practice, the drill is the only synchronization point that
matters and the file system is the only shared state needed.

Discarded as YAGNI.

### D. Run agents serially but with separate sub-conversations

Pros: get each agent's full report; cleaner audit trail.
Cons: wall time same as no-parallelism; no actual speedup.

Discarded as offering no advantage over single-thread.

## References

| Phase | Commit | Pattern | Files affected |
|---|---|---|---|
| 5S | `d06fe59` | A — 1 agent + foreground drill | 1 page (247 lines) + drill |
| 6C | `c4e65ad` | B — 3 agents chunked + foreground integration | 23 drill files in chunks of 8/7/8 |
| 6J | `8e5f1d1` | A — 1 drill locking 2 paired scripts (parallel-stream + this session) | 2 scripts + 1 drill |
| 6K | `45c5ad5` | C — parallel-stream's 50-file delivery + this session's commit | 50 drill files + meta-drill |
| 6L | `887fa9a` | C — parallel-stream's 27-file delivery integrated | 27 docs + tooling files |

Composes with: ADR-014 (the autonomous-loop architecture this
allocation lives within), ADR-015 (the ratchet pattern that often
needs parallel cleanup — 6C cleaned `KNOWN_MISSING` via 3 agents),
~/.claude/policies/autonomous-feature-loop.md §44.2 ("each iteration
is ONE thing" — the parallel-agent pattern is ONE iteration with
N concurrent threads, not N iterations).
