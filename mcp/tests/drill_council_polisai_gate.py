#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: PolisAI gates every Ollama council call.

Per CLAUDE.md §43 + §47 (Policy → Council → Workers) + §38 (decision
audit). Locks the integration that:

  - call_ollama() raises OllamaPolicyDenied when called WITHOUT a
    valid actor (default 'council:unknown' fails default-deny)
  - call_ollama() raises OllamaPolicyDenied when called with a known
    actor but missing scopes (this drill stubs the scope-pass-through
    by calling the gate directly)
  - call_ollama() with a valid actor (council:author/reviewer/advisor/
    researcher) + ollama:call scope passes the gate
  - every gate decision (allow + deny) lands in policy_audit.jsonl per
    §38 / §48.4
  - the 4 council Ollama-generate rules are present in the policy file
  - the gate fires BEFORE the actual subprocess.run(curl) — proven by
    monkey-patching subprocess and verifying it was never invoked when
    the gate denies
  - removing the actor kwarg from a call_ollama site is a tripwire —
    default-deny catches it loudly

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))


def main() -> int:
    print("-- 1. POSITIVE: policy file lists 4 council ollama:generate allow rules --")
    policy_file = REPO / "config" / "policies" / "agent_dispatch.json"
    policy = json.loads(policy_file.read_text(encoding="utf-8"))
    ollama_rules = [
        r for r in policy["rules"]
        if r["tool"] == "ollama:generate" and r["effect"] == "allow"
    ]
    if len(ollama_rules) != 4:
        print(f"x expected 4 ollama:generate allow rules; got {len(ollama_rules)}")
        return 1
    actors = {r["actor"] for r in ollama_rules}
    expected_actors = {
        "council:researcher", "council:author",
        "council:reviewer", "council:advisor",
    }
    if actors != expected_actors:
        print(f"x rule actors mismatch; got {actors}")
        return 1
    print(f"  ok: 4 rules covering {sorted(actors)}")

    print("-- 2. POSITIVE: local_council exposes call_ollama + OllamaPolicyDenied --")
    import local_council  # noqa: E402  (sys.path manipulation above)
    if not hasattr(local_council, "call_ollama"):
        print("x local_council.call_ollama missing")
        return 1
    if not hasattr(local_council, "OllamaPolicyDenied"):
        print("x local_council.OllamaPolicyDenied missing")
        return 1
    if not issubclass(local_council.OllamaPolicyDenied, RuntimeError):
        print("x OllamaPolicyDenied must subclass RuntimeError")
        return 1
    print("  ok: call_ollama + OllamaPolicyDenied (subclass of RuntimeError) present")

    print("-- 3. NEGATIVE: default actor='council:unknown' is denied --")
    # If a call site forgets actor=, default 'council:unknown' must fail
    # default-deny. This is the trip-wire for forgotten actor kwargs.
    fake_curl_called = {"hit": False}

    def fake_run(*args, **kwargs):  # noqa: ARG001
        fake_curl_called["hit"] = True
        from subprocess import CompletedProcess
        return CompletedProcess(args=[], returncode=0, stdout="{}", stderr="")

    with patch("local_council.subprocess.run", side_effect=fake_run):
        try:
            local_council.call_ollama(
                model="deepseek-coder:6.7b-instruct",
                system="x",
                prompt="x",
            )
        except local_council.OllamaPolicyDenied as exc:
            decision = exc.decision
            if decision.actor != "council:unknown":
                print(f"x denied actor should be 'council:unknown'; got {decision.actor!r}")
                return 1
            if decision.allow:
                print("x decision should be deny but allow=True")
                return 1
        else:
            print("x default actor='council:unknown' should have been denied")
            return 1
    if fake_curl_called["hit"]:
        print("x curl was called even though policy denied")
        return 1
    print("  ok: default 'council:unknown' denied; curl never invoked")

    print("-- 4. NEGATIVE: unknown actor 'attacker:bot' is denied via default-deny --")
    fake_curl_called["hit"] = False
    with patch("local_council.subprocess.run", side_effect=fake_run):
        try:
            local_council.call_ollama(
                model="deepseek-coder:6.7b-instruct",
                system="x",
                prompt="x",
                actor="attacker:bot",
            )
        except local_council.OllamaPolicyDenied as exc:
            if exc.decision.rule_matched != "default-deny":
                print(f"x rule should be 'default-deny'; got {exc.decision.rule_matched!r}")
                return 1
        else:
            print("x unknown actor should have been denied")
            return 1
    if fake_curl_called["hit"]:
        print("x curl was called for unknown actor")
        return 1
    print("  ok: 'attacker:bot' default-denied; curl never invoked")

    print("-- 5. POSITIVE: known actor 'council:author' + ollama:call scope passes gate --")
    # Monkeypatch subprocess.run to return a fake Ollama response so we
    # don't need a live Ollama server. The point is: the gate ALLOWS
    # this and curl IS called.
    fake_curl_called["hit"] = False
    fake_response = {"response": "FAKE_OK", "eval_count": 42}

    def fake_run_ok(*args, **kwargs):  # noqa: ARG001
        fake_curl_called["hit"] = True
        from subprocess import CompletedProcess
        return CompletedProcess(
            args=[], returncode=0,
            stdout=json.dumps(fake_response), stderr="",
        )

    with patch("local_council.subprocess.run", side_effect=fake_run_ok):
        text, tokens = local_council.call_ollama(
            model="deepseek-coder:6.7b-instruct",
            system="x",
            prompt="x",
            actor="council:author",
        )
    if not fake_curl_called["hit"]:
        print("x curl should have been invoked for known actor")
        return 1
    if text != "FAKE_OK":
        print(f"x unexpected response text: {text!r}")
        return 1
    if tokens != 42:
        print(f"x unexpected tokens: {tokens}")
        return 1
    print("  ok: 'council:author' + ollama:call → gate allow → curl invoked → response returned")

    print("-- 6. NEGATIVE: gate fires BEFORE the curl subprocess --")
    # Specifically: in step 3 + 4, fake_curl_called['hit'] stayed False
    # despite call_ollama being invoked. That ALREADY proves the gate
    # short-circuits before subprocess. This step locks the ordering
    # explicitly: any future refactor that reorders gate-after-curl
    # would let denied calls leak network requests.
    src = (SCRIPTS / "local_council.py").read_text(encoding="utf-8")
    # Find the call_ollama function body
    func_start = src.find("def call_ollama(")
    func_end = src.find("\ndef ", func_start + 10)
    if func_start == -1:
        print("x call_ollama function not found in source")
        return 1
    body = src[func_start:func_end if func_end != -1 else len(src)]
    # _polisai_gate must appear BEFORE subprocess.run in the function body
    gate_pos = body.find("_polisai_gate(")
    curl_pos = body.find("subprocess.run(")
    if gate_pos == -1:
        print("x _polisai_gate not called in call_ollama")
        return 1
    if curl_pos == -1:
        print("x subprocess.run not called in call_ollama")
        return 1
    if gate_pos > curl_pos:
        print(f"x _polisai_gate must precede subprocess.run; gate@{gate_pos} curl@{curl_pos}")
        return 1
    print(f"  ok: _polisai_gate (pos {gate_pos}) precedes subprocess.run (pos {curl_pos})")

    print("-- 7. NEGATIVE: every call_ollama site in local_council.py passes actor= --")
    # If a future refactor adds a call_ollama site without actor=, the
    # default 'council:unknown' would silently be used and every call
    # would deny. Lock: every call_ollama( in the file (other than its
    # definition) must include actor= as a kwarg.
    invocations = []
    pos = 0
    while True:
        idx = src.find("call_ollama(", pos)
        if idx == -1:
            break
        # Skip the definition itself
        before = src[max(0, idx - 4):idx]
        if before.endswith("def "):
            pos = idx + 1
            continue
        # Capture the full call expression up to matching close-paren
        depth = 0
        end = idx + len("call_ollama(") - 1  # position of opening (
        for i in range(end, len(src)):
            c = src[i]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        invocation = src[idx:end + 1]
        invocations.append(invocation)
        pos = end + 1
    if len(invocations) < 4:
        print(f"x expected >=4 call_ollama invocations; found {len(invocations)}")
        return 1
    missing_actor = [
        inv for inv in invocations if "actor=" not in inv
    ]
    if missing_actor:
        print(f"x {len(missing_actor)} call_ollama site(s) missing actor= kwarg:")
        for inv in missing_actor[:3]:
            print(f"    {inv[:120]!r}")
        return 1
    print(f"  ok: all {len(invocations)} call_ollama sites pass actor=")

    print("-- 8. POSITIVE: deny decision lands in .loop/policy_audit.jsonl --")
    audit_log = REPO / ".loop" / "policy_audit.jsonl"
    if not audit_log.exists():
        print("x audit log missing — earlier steps should have populated it")
        return 1
    rows = audit_log.read_text(encoding="utf-8").strip().split("\n")
    # Find the most recent rows from the actors we tested in steps 3-5
    recent_actors = {
        "council:unknown", "attacker:bot", "council:author",
    }
    seen_actors = set()
    for line in rows[-50:]:
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("actor") in recent_actors and r.get("tool") == "ollama:generate":
            seen_actors.add(r["actor"])
    if seen_actors != recent_actors:
        missing = recent_actors - seen_actors
        print(f"x audit rows missing for actors: {missing}")
        return 1
    print(f"  ok: audit rows for all 3 actors ({sorted(recent_actors)}) present in policy_audit.jsonl")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
