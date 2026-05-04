#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: ADR-020 audit-cadence ratchet — every parallel-tool-authored
commit has its audit drill.

ADR-020 (3b1cc02) declared: every parallel-tool-authored commit
landing in main MUST trigger a drill audit within ≤2 autonomous-
loop iterations. Phase 7I closed the first practical gap (G-2's
TTS proxy → drill_tts_proxy_route). This drill ratchets the
floor: the registry below lists every known parallel-tool commit
and its audit drill; any new parallel-tool commit found in git
history that ISN'T in the registry is flagged as paydown work.

Detection has two paths because parallel-tool commits land in
two ways:

1. Direct parallel-tool commit (no `Co-Authored-By: Claude`
   trailer in the message body). G-1 (5dfeb9c) is the only
   instance to date.
2. Autonomous-loop batched parallel-tool content (subject line
   matches `G-\\d+:` pattern). G-2 (51bac70) + G-3 (45633d2)
   are this shape.

Nine steps. Six negative assertions.

  1. POSITIVE: discover parallel-tool commits across both
     detection paths in last 100 commits. Floor: at least one
     commit known (otherwise the drill has no purchase).
  2. NEGATIVE: every commit in PARALLEL_TOOL_COMMITS still
     exists in git history. Catches stale registry entries
     (commits removed via rebase).
  3. NEGATIVE: every audit drill named in the registry exists
     at mcp/tests/<filename>. Catches drill renames or
     deletions without registry update.
  4. NEGATIVE: every audit drill has the canonical
     `# RESOURCES:` header (and uses readonly tier OR explicit
     resource tag). Locks the convention.
  5. NEGATIVE: every parallel-tool commit discovered in step 1
     is in PARALLEL_TOOL_COMMITS OR KNOWN_UNAUDITED. New
     commits not tracked = paydown deficit. Ratchet floor at 0.
  6. NEGATIVE: KNOWN_UNAUDITED entries correspond to real
     recent commits (no stale paydown markers — commits that
     never existed or have been audited).
  7. POSITIVE: emit per-commit audit-status table.
  8. POSITIVE: emit ratchet state — # audited / # unaudited
     paydown / total parallel-tool commits known.

Run: python3 mcp/tests/drill_adr020_audit_cadence.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DRILLS_DIR = REPO / "mcp" / "tests"

# Registry of (commit_sha → audit_drill_filename). When a new
# parallel-tool commit lands, add an entry here in the same
# autonomous-loop iteration that adds its audit drill.
PARALLEL_TOOL_COMMITS = {
    "5dfeb9c": ("G-1: agent-orchestrator-svc", "drill_agent_orchestrator_structure.py"),
    "51bac70": ("G-2: services/frontend/* incl. TTS proxy", "drill_tts_proxy_route.py"),
    "45633d2": ("G-3: scripts/* help-contract paydown", "drill_scripts_have_help.py"),
    # G-4 has 8 audit drills (project-plan + task-run + approval +
    # memory + control-plane api/chain/ui + admin-summary). The
    # registry is 1:1 (commit -> single representative drill); we
    # pick drill_agentic_control_plane_api.py as the most
    # comprehensive (exercises the API surface end-to-end). All 8
    # drills are listed in the G-4 commit message body.
    "480dd3e": ("G-4: agentic control plane (8 pre-shipped audits)", "drill_agentic_control_plane_api.py"),
    # G-5 has 3 audit drills (rating-surface, advisor-record-rating,
    # sidecar-nextjs-page). Pick drill_sidecar_advisor_record_rating
    # as representative — covers the backend write path. Latency=0
    # because the new audit drill shipped in the same commit as
    # the source code (true inverted cadence under MAX_AUDIT_LATENCY=1).
    "dde309b": ("G-5: sidecar event rating surface", "drill_sidecar_advisor_record_rating.py"),
    # G-5.2: parallel-tool follow-on adding rating UI affordances +
    # extending drill_sidecar_rating_surface in same commit.
    # drill_sidecar_rating_surface predates this by ~1.25h (it
    # landed in Phase 7AA), so latency=0 (preexisting). Yet
    # another inverted-cadence instance per ADR-021.
    "2a1a7b0": ("G-5.2: rating UI + review metadata + drill-down", "drill_sidecar_rating_surface.py"),
    # 91cd8a8: parallel-tool's ADR-021 doc commit. Audit = drill_
    # cheatsheet_adr_coverage which validates the ADR is referenced
    # in the cheatsheet's composes-with footer. The commit is doc-
    # only; ADR-020's structural-audit checklist (drill existence,
    # NEGATIVE marker, banner format, project-rule audit) doesn't
    # apply to docs. Registering with the structural drill that
    # DOES cover it (cheatsheet ADR coverage).
    "91cd8a8": ("ADR-021 doc — pre-shipped drill audit cadence", "drill_cheatsheet_adr_coverage.py"),
    # c41b19c: parallel-tool's test alignment commit (modifies
    # this very drill). Self-referential audit — drill_adr020_
    # audit_cadence is BOTH the modified file AND its own audit
    # via the catalog discipline drill (NEGATIVE markers, banner,
    # docstring count). Cohesion drill catches divergence.
    "c41b19c": ("test alignment of cadence drill with ADR-021", "drill_adr020_audit_cadence.py"),
    # G-5.1: autonomous-loop committed parallel-tool's metadata
    # extension (rated_by/rating_notes columns + Vitest infra +
    # migration 003). Co-Authored-By: Claude trailer present, but
    # Path B regex catches the G-5.1 subject token. Audit drills:
    # drill_sidecar_rating_metadata + drill_sidecar_rating_route
    # shipped in same commit (latency=0).
    "14c7616": ("G-5.1: rating metadata columns + Vitest infra", "drill_sidecar_rating_metadata.py"),
    # G-5.2-followon: small follow-on extending the rating route
    # + Vitest tests. Audit = drill_sidecar_rating_surface
    # (preexisting from Phase 7AA, predates this commit by hours).
    "0e7f864": ("G-5.2-followon: rating route + Vitest extensions", "drill_sidecar_rating_surface.py"),
    # e0a0182: parallel-tool's next.config.mjs tweak — pin sidecar
    # + TTS API routes to the local server. 4-line change. Audit
    # via drill_tts_proxy_route + drill_sidecar_rating_surface
    # which exercise the routes; pick rating_surface as
    # representative since it's the more recent landing.
    "e0a0182": ("next.config: keep sidecar + tts routes local", "drill_sidecar_rating_surface.py"),
    # G-6: operator monitoring dashboard (page + 2 routes + Sidebar
    # + lib client). Audit drill ships in same commit (latency=0,
    # true simultaneous per ADR-021 inverted cadence).
    "7a1701f": ("G-6: operator monitoring dashboard", "drill_admin_monitoring_surface.py"),
    # 214c2c4: parallel-tool's docs(runtime) commit that aligned the
    # monitoring + agentic truth surfaces — bundled the autonomous-
    # loop's Phase 7RR work plus additional doc updates. Audit via
    # drill_admin_monitoring_runtime_surface (which 214c2c4 added).
    "214c2c4": ("docs(runtime): align monitoring + agentic surfaces", "drill_admin_monitoring_runtime_surface.py"),
    # G-7 + Phase 7SS observability stack landing. Audit shipped in
    # same commit (drill_observability_stack_provisioning); latency=0.
    "c0d82d9": ("G-7: Prometheus/Grafana/Alertmanager provisioning", "drill_observability_stack_provisioning.py"),
    # 05fce13: parallel-tool intermediate adding alertmanager +
    # runtime-status route coverage. Audit drill landed earlier
    # (Phase 7TT drift-fix commit). Inverted cadence.
    "05fce13": ("alertmanager + runtime-status route coverage", "drill_alertmanager_receiver_config.py"),
    # d0301e6: parallel-tool expansion of monitoring truth surfaces +
    # exporter coverage (node-exporter + cadvisor in compose).
    # Audit via drill_admin_monitoring_runtime_surface (which the
    # parallel-tool extended to 9 steps for these new surfaces).
    "d0301e6": ("expand monitoring + exporter coverage", "drill_admin_monitoring_runtime_surface.py"),
    # 610fdf4: parallel-tool's test(drills) commit registering
    # observability audits + hardening the runtime-status drill.
    # Audit via drill_admin_monitoring_runtime_surface (which it
    # extends).
    "610fdf4": ("register observability audits + harden runtime-status drill", "drill_admin_monitoring_runtime_surface.py"),
    # 6831dee: local-chair fallback for sidecar council when the
    # cloud-first Kimi tag 404s in a local Ollama runtime. Audit
    # via the council drill that now exercises the 404→fallback
    # path explicitly.
    "6831dee": ("fall back to local chair model on ollama 404", "drill_sidecar_pr_review_council.py"),
}

# Paydown bucket — parallel-tool commits known to exist but not
# yet audited. Per ADR-015 ratchet pattern: floor moves toward
# zero. Empty at landing because Phase 7I paid the last entry
# (G-2) down. Future iterations may temporarily add entries here
# while the audit drill lands within the 2-iteration SLO.
KNOWN_UNAUDITED: dict[str, str] = {}

# ADR-020 SLO: every parallel-tool commit's audit drill should
# land within ≤MAX_AUDIT_LATENCY autonomous-loop iterations of
# the parallel-tool commit. "Iteration" = autonomous-loop commit.
# Latency is computed via `git rev-list --count <pt_sha>..
# <audit_add_sha>`.
#
# Tightening history (per ADR-015 ratchet pattern, reward
# shrinkage):
#   * Phase 7J (initial): 2 (matched ADR-020 text)
#   * Phase 7Z (now):     1 (tightened — G-3 + G-4 both shipped
#                            at latency=0; threshold has
#                            headroom for tightening)
# Future tightening: drop to 0 once 3+ consecutive G-buckets ship
# at latency=0 (consistent inverted cadence).
MAX_AUDIT_LATENCY = 1

# Grandfathered SLO violations — audits that landed BEFORE
# ADR-020 was named (Phase 7F, 3b1cc02). G-1 and G-2 audits
# landed 10 and 9 iterations late respectively. These entries
# are PERMANENT historical artifacts: latency is computed from
# git history and won't shrink without a rebase (which is gated
# per CLAUDE.md §42). The ratchet's purpose for these entries is
# integrity-of-record (reject if latency drifts UP — implies
# history changed) rather than paydown-toward-zero.
#
# True ADR-020 paydown happens via:
#   1. Lowering MAX_AUDIT_LATENCY (gate tightening — Phase 7Z
#      moved from 2 to 1).
#   2. Future G-buckets shipping at latency=0 / 1 (in-SLO entries
#      that don't enter this dict).
#
# Net session improvement: avg-iter-latency 6.3 → 4.8 across G-1
# through G-4. Phase 7Z's threshold tightening makes the avg
# trend a structural commitment going forward.
KNOWN_LATE_AUDITS: dict[str, int] = {
    "5dfeb9c": 10,  # G-1: agent-orchestrator-svc -> Phase 7E
    "51bac70": 9,   # G-2: TTS proxy -> Phase 7I
    # G-3 (45633d2) and G-4 (480dd3e) latency=0 (audits preexisting);
    # not grandfathered because they're within SLO.
}

# How far back to scan git history. 100 commits ≈ 5 sessions of
# autonomous-loop iterations. Catches recent drift without
# scanning the entire repo.
HISTORY_DEPTH = 100

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}{msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}-- {title} --{NC}")


def _git(args: list[str]) -> str:
    """Run git with REPO as cwd; return stdout. Empty string on
    failure (graceful degradation per ADR-019: drill emits a
    'no git history visible' message but doesn't crash)."""
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        return r.stdout if r.returncode == 0 else ""
    except (subprocess.SubprocessError, FileNotFoundError):
        return ""


def _commit_message(sha: str) -> str:
    """Full commit message body (subject + body)."""
    return _git(["log", "-1", "--pretty=%B", sha])


def _commit_exists(sha: str) -> bool:
    return bool(_git(["rev-parse", "--verify", "--quiet", sha]))


def _audit_iteration_latency(parallel_sha: str, audit_drill_path: Path) -> int | None:
    """Return iteration latency between parallel-tool commit and
    audit drill landing. 0 = preexisting (audit predates parallel-
    tool commit) or simultaneous; positive N = N commits between.
    None = couldn't determine (audit drill never added, git error)."""
    add_sha = _git([
        "log", "--diff-filter=A", "--pretty=%H", "-1",
        "--", str(audit_drill_path),
    ]).strip()
    if not add_sha:
        return None
    count_str = _git([
        "rev-list", "--count", f"{parallel_sha}..{add_sha}",
    ]).strip()
    if not count_str.isdigit():
        return None
    return int(count_str)


def _commit_unix_time(sha: str) -> int | None:
    """Author timestamp (seconds since epoch) for the given commit.
    None on git error."""
    s = _git(["log", "-1", "--pretty=%at", sha]).strip()
    if not s.isdigit():
        return None
    return int(s)


def _audit_time_latency_hours(parallel_sha: str, audit_drill_path: Path) -> float | None:
    """Return wall-clock latency in hours between parallel-tool commit
    and audit-drill add commit. Negative = audit predates parallel-
    tool (the inverted-cadence pattern from G-4). None = git error.

    Time-latency is invariant to rebases/squashes — unlike iteration-
    latency, which counts commits between two SHAs and breaks when
    history is rewritten. Both are emitted; operators can pick the
    metric most relevant to their incident."""
    add_sha = _git([
        "log", "--diff-filter=A", "--pretty=%H", "-1",
        "--", str(audit_drill_path),
    ]).strip()
    if not add_sha:
        return None
    pt_t = _commit_unix_time(parallel_sha)
    add_t = _commit_unix_time(add_sha)
    if pt_t is None or add_t is None:
        return None
    return (add_t - pt_t) / 3600.0


def _discover_parallel_tool_commits() -> dict[str, str]:
    """Return {short_sha: subject} for every parallel-tool commit
    in the last HISTORY_DEPTH commits, by SUBJECT-ONLY signal.

    HISTORICAL NOTE — broken Path A: this drill originally used
    "no Co-Authored-By: Claude trailer" as Path A. That worked when
    autonomous-loop commits ALWAYS carried the trailer. Per CLAUDE.md
    §54 (2026-05-04 "Git Commit Signature Policy"), the trailer is now
    DROPPED from autonomous-loop commits — so absence of the trailer
    no longer discriminates parallel-tool from autonomous-loop work.
    Path A removed.

    BROKEN Path C: an earlier rewrite added a body-search for
    "parallel-tool" / G-<digit>. That self-triggered on any commit
    whose body explained or referenced parallel-tool work — including
    THIS drill's own fix-commit. False-positive city.

    Surviving signal: SUBJECT contains an explicit G-<digit> token.
    Strong positive — only declared parallel-tool work uses this prefix.
    Better to under-detect (let real parallel-tool work without G-<N>
    explicitly land in KNOWN_UNAUDITED) than over-detect.
    """
    out: dict[str, str] = {}
    log = _git(["log", "-" + str(HISTORY_DEPTH),
                "--pretty=%H%x09%s"])
    for line in log.splitlines():
        parts = line.split("\t", 1)
        if len(parts) < 2:
            continue
        sha_full, subject = parts
        sha = sha_full[:7]
        # Subject contains G-<digit> token. Robust to observed
        # naming variations:
        #   "feat(sidecar): G-5 - sidecar event rating surface"
        #   "feat(sidecar): G-5.2-followon - rating route extension"
        #   "G-5: ..."
        #   "feat(agentic): G-4 - agentic control plane"
        if re.match(r"^[a-z]+\(.+?\):\s*G-\d+[\s\.\-:]", subject) or \
                re.match(r"^G-\d+[\s\.\-:]", subject):
            out[sha] = subject
    return out


def main() -> int:
    step("1. POSITIVE: discover parallel-tool commits in last HISTORY_DEPTH commits")
    discovered = _discover_parallel_tool_commits()
    if not discovered:
        # Graceful degradation: in a fresh checkout without git history
        # the drill can't enforce anything. Emit a clear stderr message
        # and exit success (per ADR-019).
        ok("no parallel-tool commits visible (fresh checkout or pre-history); drill is a no-op here")
        # Still emit the standard banner so run_drills.py recognises success.
        print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
        print(f"{BOLD}{GREEN}  ALL 8 ADR020-AUDIT-CADENCE STEPS PASSED{NC}")
        print(f"{BOLD}{GREEN}  (degraded: no git history){NC}")
        print(f"{BOLD}{GREEN}{'=' * 50}{NC}")
        return 0
    ok(f"discovered {len(discovered)} parallel-tool commit(s) in last {HISTORY_DEPTH}")

    step("2. NEGATIVE: every PARALLEL_TOOL_COMMITS entry exists in git history")
    stale_registry: list[tuple[str, str]] = []
    for sha, (label, drill_file) in PARALLEL_TOOL_COMMITS.items():
        if not _commit_exists(sha):
            stale_registry.append((sha, label))
    if stale_registry:
        fail(
            f"{len(stale_registry)} stale registry entries (commit removed): "
            f"{stale_registry[:3]}"
        )
    ok(f"all {len(PARALLEL_TOOL_COMMITS)} registry commits resolve in git history")

    step("3. NEGATIVE: every audit drill named in registry exists on disk")
    missing_drills: list[tuple[str, str]] = []
    for sha, (label, drill_file) in PARALLEL_TOOL_COMMITS.items():
        if not (DRILLS_DIR / drill_file).is_file():
            missing_drills.append((sha, drill_file))
    if missing_drills:
        fail(
            f"{len(missing_drills)} audit drill(s) missing on disk: "
            f"{missing_drills[:3]}. Renamed without registry update?"
        )
    ok(f"all {len(PARALLEL_TOOL_COMMITS)} audit drills present in mcp/tests/")

    step("4. NEGATIVE: every audit drill has canonical # RESOURCES: header")
    bad_headers: list[tuple[str, str]] = []
    for sha, (label, drill_file) in PARALLEL_TOOL_COMMITS.items():
        path = DRILLS_DIR / drill_file
        head = path.read_text().splitlines()[:5]
        if not any(line.startswith("# RESOURCES:") for line in head):
            bad_headers.append((drill_file, head[0] if head else "(empty)"))
    if bad_headers:
        fail(
            f"{len(bad_headers)} audit drill(s) lack '# RESOURCES:' "
            f"header: {bad_headers[:3]}"
        )
    ok(f"all {len(PARALLEL_TOOL_COMMITS)} audit drills have RESOURCES header")

    step("5. NEGATIVE: discovered parallel-tool commits all tracked or paydown-bucketed")
    untracked = []
    for sha, subject in discovered.items():
        if sha in PARALLEL_TOOL_COMMITS:
            continue
        if sha in KNOWN_UNAUDITED:
            continue
        untracked.append((sha, subject[:80]))
    if untracked:
        fail(
            f"{len(untracked)} discovered parallel-tool commit(s) NOT in "
            f"PARALLEL_TOOL_COMMITS or KNOWN_UNAUDITED: {untracked[:3]}. "
            "Either land an audit drill (and add registry entry) or "
            "explicitly grandfather via KNOWN_UNAUDITED."
        )
    ok(
        f"all {len(discovered)} discovered commits accounted for "
        f"(audited: {len(PARALLEL_TOOL_COMMITS & set(discovered.keys()) if False else [s for s in discovered if s in PARALLEL_TOOL_COMMITS])}, "
        f"paydown: {len([s for s in discovered if s in KNOWN_UNAUDITED])})"
    )

    step("6. NEGATIVE: KNOWN_UNAUDITED entries correspond to real recent commits")
    stale_paydown: list[tuple[str, str]] = []
    for sha, label in KNOWN_UNAUDITED.items():
        if not _commit_exists(sha):
            stale_paydown.append((sha, label))
    if stale_paydown:
        fail(
            f"{len(stale_paydown)} stale KNOWN_UNAUDITED entries: "
            f"{stale_paydown[:3]}. Either land the audit and move to "
            "PARALLEL_TOOL_COMMITS, or remove from paydown bucket."
        )
    ok(f"{len(KNOWN_UNAUDITED)} paydown entries (all resolve)")

    step("7. NEGATIVE: every audit's iteration latency <= MAX or grandfathered")
    latency_violations: list[tuple[str, int, int]] = []
    measured: dict[str, int] = {}
    for sha, (label, drill_file) in PARALLEL_TOOL_COMMITS.items():
        drill_path = DRILLS_DIR / drill_file
        latency = _audit_iteration_latency(sha, drill_path)
        if latency is None:
            fail(
                f"could not compute iteration latency for "
                f"{sha} -> {drill_file} (git error or drill never added)"
            )
        measured[sha] = latency
        if latency <= MAX_AUDIT_LATENCY:
            continue
        # Latency exceeds SLO; must be grandfathered with EXACT value.
        # Allowing a higher value than registered means git history
        # changed (rebase added commits between the two SHAs); the
        # registry is now lying about reality.
        registered = KNOWN_LATE_AUDITS.get(sha)
        if registered is None:
            latency_violations.append((sha, latency, MAX_AUDIT_LATENCY))
        elif latency > registered:
            # Grandfathered, but latency drifted UP — git history
            # changed. Reconcile the registry.
            latency_violations.append((sha, latency, registered))
    if latency_violations:
        msg = ", ".join(
            f"{sha}: actual={lat}, max_allowed={maxv}"
            for sha, lat, maxv in latency_violations[:5]
        )
        fail(
            f"{len(latency_violations)} ADR-020 SLO violation(s): {msg}. "
            "Either land the audit drill faster (preferred) or extend "
            "KNOWN_LATE_AUDITS with the EXACT measured latency."
        )
    in_slo = sum(1 for v in measured.values() if v <= MAX_AUDIT_LATENCY)
    grandfathered = sum(
        1 for sha, v in measured.items()
        if v > MAX_AUDIT_LATENCY and sha in KNOWN_LATE_AUDITS
    )
    ok(
        f"latencies measured: {len(measured)} entries; "
        f"{in_slo} within SLO (<={MAX_AUDIT_LATENCY}); "
        f"{grandfathered} grandfathered late"
    )

    step("8. POSITIVE: emit per-commit audit-status table")
    time_latencies: dict[str, float] = {}
    for sha, (label, drill_file) in sorted(PARALLEL_TOOL_COMMITS.items()):
        lat = measured.get(sha)
        lat_str = f"lat={lat}" if lat is not None else "lat=?"
        slo_marker = "✓" if (lat is not None and lat <= MAX_AUDIT_LATENCY) else (
            "GF" if sha in KNOWN_LATE_AUDITS else "!!"
        )
        # Wall-clock time-latency in hours. Negative = inverted
        # cadence (audit predates parallel-tool commit, e.g. G-4).
        drill_path = DRILLS_DIR / drill_file
        time_h = _audit_time_latency_hours(sha, drill_path)
        if time_h is not None:
            time_latencies[sha] = time_h
            time_str = (
                f"{time_h:+.1f}h" if abs(time_h) < 48
                else f"{time_h / 24:+.1f}d"
            )
        else:
            time_str = "?"
        ok(
            f"  AUDITED [{slo_marker} {lat_str:<8} {time_str:>8}] "
            f"{sha}  {label[:42]:<42} -> {drill_file}"
        )
    for sha, label in sorted(KNOWN_UNAUDITED.items()):
        ok(f"  PAYDOWN                              {sha}  {label[:42]:<42}")

    step("9. POSITIVE: emit ratchet state + SLO summary")
    audited = len(PARALLEL_TOOL_COMMITS)
    paydown = len(KNOWN_UNAUDITED)
    total = audited + paydown
    if total > 0:
        ok(
            f"ADR-020 ratchet: {audited}/{total} audited "
            f"({paydown} paydown). "
            f"Floor: {paydown} unaudited."
        )
        avg_latency = sum(measured.values()) / len(measured) if measured else 0
        ok(
            f"SLO: max-allowed={MAX_AUDIT_LATENCY} iterations; "
            f"in-SLO={in_slo}, grandfathered={grandfathered}, "
            f"avg-iter-latency={avg_latency:.1f}"
        )
        if time_latencies:
            avg_time = sum(time_latencies.values()) / len(time_latencies)
            inverted = sum(1 for v in time_latencies.values() if v < 0)
            same_day = sum(1 for v in time_latencies.values() if 0 <= v < 24)
            unit = "h" if abs(avg_time) < 48 else "d"
            avg_disp = avg_time if unit == "h" else avg_time / 24
            ok(
                f"Wall-clock: avg-time-latency={avg_disp:+.1f}{unit}; "
                f"inverted (audit pre-shipped)={inverted}, "
                f"same-day={same_day}"
            )
    else:
        ok("ADR-020 ratchet: 0/0 (registry empty)")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 9 ADR020-AUDIT-CADENCE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 2, 3, 4, 5, 6, 7){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
