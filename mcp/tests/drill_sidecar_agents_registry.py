#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Sidecar Advisor agents registry — one file per role.

Locks the contract that:

  services/sidecar-advisor/agents/
    base.py             - CoderAgent dataclass
    code_reviewer.py    - exports AGENT (role=author)
    security_auditor.py - exports AGENT (role=author)
    test_advisor.py     - exports AGENT (role=author)
    consistency_check.py- exports AGENT (role=reviewer)
    chair.py            - exports AGENT (role=advisor)
    policy_approver.py  - exports AGENT (role=approver)
    __init__.py         - registry: ALL_AGENTS, by_role, by_name

Eight steps. Five negative assertions.

  1. ALL_AGENTS contains exactly 6 entries with stable ordering.
  2. by_role("author") returns 3 agents (code/security/test).
  3. by_role("reviewer") + by_role("advisor") + by_role("approver")
     each return 1.
  4. NEGATIVE: every agent has a UNIQUE prompt_template (no
     accidental copy-paste collapsing role specialisation).
  5. NEGATIVE: every agent has a UNIQUE name (registry can't have
     two "code_reviewer" entries).
  6. NEGATIVE: by_name("nonexistent") returns None (not raises).
  7. NEGATIVE: CoderAgent rejects role="bogus" with ValueError
     (the role enum is enforced at construction).
  8. NEGATIVE: CoderAgent is frozen — runtime mutation raises
     FrozenInstanceError. Hot-swapping a model needs a code change
     + drill re-validation, not a runtime mutation.

Tag: readonly. Pure-Python -- runs in tier 1.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg):
    print(f"  {GREEN}{msg}{NC}")


def fail(msg):
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title):
    print(f"\n{BOLD}-- {title} --{NC}")


# Load the agents package directly via importlib so we don't need
# documind_core / app.services on the path.
def _load_registry():
    agents_dir = REPO / "services" / "sidecar-advisor" / "agents"
    init_path = agents_dir / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        "sidecar_agents_registry",
        init_path,
        submodule_search_locations=[str(agents_dir)],
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sidecar_agents_registry"] = mod
    spec.loader.exec_module(mod)
    return mod


reg = _load_registry()
CoderAgent = reg.CoderAgent
ALL_AGENTS = reg.ALL_AGENTS
by_role = reg.by_role
by_name = reg.by_name


def main():
    # Step 1: registry has 6 entries, stable order
    step("1. ALL_AGENTS has exactly 6 entries with stable ordering")
    if len(ALL_AGENTS) != 6:
        fail(f"expected 6 agents, got {len(ALL_AGENTS)}: {[a.name for a in ALL_AGENTS]}")
    expected_order = [
        "code_reviewer", "security_auditor", "test_advisor",
        "consistency_check", "chair", "policy_approver",
    ]
    actual_order = [a.name for a in ALL_AGENTS]
    if actual_order != expected_order:
        fail(
            f"registry ordering changed:\n"
            f"  expected: {expected_order}\n"
            f"  got:      {actual_order}\n"
            f"Reordering breaks downstream consumers that index by position."
        )
    ok(f"6 agents in stable order: {actual_order}")

    # Step 2: 3 authors
    step("2. by_role('author') returns 3 agents (code/security/test)")
    authors = by_role("author")
    if len(authors) != 3:
        fail(f"expected 3 authors, got {len(authors)}")
    author_names = sorted(a.name for a in authors)
    if author_names != sorted(["code_reviewer", "security_auditor", "test_advisor"]):
        fail(f"wrong authors: {author_names}")
    ok(f"3 authors: {author_names}")

    # Step 3: 1 each of reviewer, advisor, approver
    step("3. by_role('reviewer'/'advisor'/'approver') each returns 1")
    for role, expected_name in [
        ("reviewer", "consistency_check"),
        ("advisor", "chair"),
        ("approver", "policy_approver"),
    ]:
        rs = by_role(role)
        if len(rs) != 1:
            fail(f"role {role!r}: expected 1, got {len(rs)}")
        if rs[0].name != expected_name:
            fail(f"role {role!r}: expected {expected_name}, got {rs[0].name}")
    ok("1 reviewer (consistency_check) + 1 advisor (chair) + 1 approver (policy_approver)")

    # Step 4: NEGATIVE - prompt templates unique
    step("4. NEGATIVE: every agent has a UNIQUE prompt_template")
    seen_prompts = {}
    for a in ALL_AGENTS:
        if a.prompt_template in seen_prompts:
            fail(
                f"prompt collision: {a.name} and "
                f"{seen_prompts[a.prompt_template]} share a prompt template. "
                f"Role specialisation collapses if prompts duplicate."
            )
        seen_prompts[a.prompt_template] = a.name
    ok("all 6 prompts distinct (no copy-paste role collapse)")

    # Step 5: NEGATIVE - names unique
    step("5. NEGATIVE: every agent name is UNIQUE in the registry")
    seen_names = set()
    for a in ALL_AGENTS:
        if a.name in seen_names:
            fail(f"duplicate name in registry: {a.name}")
        seen_names.add(a.name)
    ok("all 6 names distinct")

    # Step 6: NEGATIVE - by_name returns None for unknown
    step("6. NEGATIVE: by_name('nonexistent') returns None (no raise)")
    if by_name("nonexistent_agent_xyz") is not None:
        fail("by_name should return None for unknown")
    if by_name("code_reviewer") is None:
        fail("by_name should find existing")
    ok("by_name('nonexistent') -> None; by_name('code_reviewer') -> found")

    # Step 7: NEGATIVE - role enum enforced at construction
    step("7. NEGATIVE: CoderAgent rejects role='bogus' with ValueError")
    try:
        CoderAgent(
            name="x", role="bogus", model="m", description="d",
            prompt_template="t",
        )
        fail("CoderAgent accepted bogus role - validation missing")
    except ValueError as exc:
        if "role" not in str(exc).lower():
            fail(f"ValueError message doesn't mention role: {exc}")
    ok("CoderAgent rejects unknown role at construction")

    # Step 8: NEGATIVE - frozen dataclass
    step("8. NEGATIVE: CoderAgent is frozen (no runtime model swap)")
    a = ALL_AGENTS[0]
    try:
        a.model = "different-model"
        fail(
            "CoderAgent allowed runtime mutation. Hot-swapping a model "
            "would skip the drill re-validation; needs to be a code "
            "change, not a runtime assignment."
        )
    except dataclasses.FrozenInstanceError:
        pass
    except AttributeError:
        # Python's frozen-dataclass impl raises FrozenInstanceError
        # which is a subclass of AttributeError
        pass
    ok("CoderAgent frozen — model assignment raises (registry immutable)")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 AGENTS-REGISTRY STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (5 negative assertions: 4, 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    main()
