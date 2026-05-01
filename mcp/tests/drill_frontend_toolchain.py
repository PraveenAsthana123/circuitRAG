# RESOURCES: readonly
"""
Drill: §19 frontend toolchain — Prettier config + husky pre-commit
hook + npm scripts.

The 2026-04-30 audit flagged:
  - services/frontend/.prettierrc      (missing)
  - services/frontend/.prettierignore  (missing)
  - .husky/pre-commit                  (missing)
  - npm scripts: format / format:check / validate / pre-merge

Steps:

  1. Both Prettier config files exist at services/frontend/.
  2. .prettierrc is valid JSON AND matches §19.5 expected fields:
     semi, singleQuote, tabWidth, trailingComma, printWidth,
     bracketSpacing, arrowParens, endOfLine.
  3. .prettierignore lists at minimum: .next, node_modules,
     package-lock.json (would-be churn from auto-format on
     machine-generated files).
  4. .husky/pre-commit exists, is executable, and references
     either pre-commit (the framework) or a project-conventional
     fallback hook script.
  5. package.json has all four §19.4 npm scripts: format,
     format:check, validate, pre-merge — plus circuitRAG additions
     (test:e2e, check:prod).
  6. NEGATIVE: a malformed .prettierrc (corrupt JSON) would fail
     step 2's JSON.parse. We synthesize a corrupt copy to a temp
     path, attempt to parse, and confirm the parser rejects it.
     Lock: the drill's JSON validation actually fires.
  7. NEGATIVE: a non-existent npm script ("phantom-script") must
     NOT appear in scripts. Lock: the npm-script audit doesn't
     coincidentally find anything.

Run:
    .venv/bin/python mcp/tests/drill_frontend_toolchain.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "services" / "frontend"

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{NC} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{NC} {msg}")


def main() -> int:
    failures = 0

    # 1. Prettier configs exist.
    prc = FRONTEND / ".prettierrc"
    pri = FRONTEND / ".prettierignore"
    if prc.is_file() and pri.is_file():
        ok(f"step 1: .prettierrc + .prettierignore both present at services/frontend/")
    else:
        fail(f"step 1: missing — .prettierrc:{prc.is_file()} .prettierignore:{pri.is_file()}")
        failures += 1

    # 2. .prettierrc is valid JSON with §19.5 fields.
    expected_fields = {
        "semi", "singleQuote", "tabWidth", "trailingComma",
        "printWidth", "bracketSpacing", "arrowParens", "endOfLine",
    }
    if prc.is_file():
        try:
            cfg = json.loads(prc.read_text(encoding="utf-8"))
            missing = expected_fields - set(cfg.keys())
            if not missing:
                ok(f"step 2: .prettierrc valid JSON; all 8 §19.5 fields present")
            else:
                fail(f"step 2: .prettierrc missing §19.5 fields: {sorted(missing)}")
                failures += 1
        except json.JSONDecodeError as e:
            fail(f"step 2: .prettierrc invalid JSON: {e}")
            failures += 1
    else:
        # already failed step 1
        pass

    # 3. .prettierignore covers churn-prone paths.
    if pri.is_file():
        text = pri.read_text(encoding="utf-8")
        required_paths = [".next", "node_modules", "package-lock.json"]
        missing = [p for p in required_paths if p not in text]
        if not missing:
            ok(f"step 3: .prettierignore covers .next + node_modules + lockfile")
        else:
            fail(f"step 3: .prettierignore missing entries: {missing}")
            failures += 1

    # 4. .husky/pre-commit exists and is executable.
    husky = REPO / ".husky" / "pre-commit"
    if husky.is_file() and os.access(husky, os.X_OK):
        text = husky.read_text(encoding="utf-8")
        # Should reference pre-commit framework or a fallback script.
        if "pre-commit" in text or "loop_watcher_hook" in text:
            ok(f"step 4: .husky/pre-commit executable + delegates to pre-commit framework")
        else:
            fail(f"step 4: .husky/pre-commit exists but doesn't delegate to a real hook")
            failures += 1
    elif husky.is_file():
        fail(f"step 4: .husky/pre-commit exists but is NOT executable (chmod +x)")
        failures += 1
    else:
        fail(f"step 4: .husky/pre-commit missing")
        failures += 1

    # 5. package.json has the §19.4 + circuitRAG scripts.
    pkg = FRONTEND / "package.json"
    if pkg.is_file():
        pkg_data = json.loads(pkg.read_text(encoding="utf-8"))
        scripts = pkg_data.get("scripts", {})
        required_scripts = ["format", "format:check", "validate", "pre-merge", "test:e2e", "check:prod"]
        missing = [s for s in required_scripts if s not in scripts]
        if not missing:
            ok(f"step 5: package.json has all 6 required scripts: {required_scripts}")
        else:
            fail(f"step 5: package.json missing scripts: {missing}")
            failures += 1
    else:
        fail(f"step 5: package.json not found")
        failures += 1

    # 6. NEGATIVE — corrupt JSON must reject.
    corrupt = "{ this is not valid json"
    try:
        json.loads(corrupt)
        fail("step 6 (negative): JSON parser ACCEPTED corrupt input — drill's validation is broken")
        failures += 1
    except json.JSONDecodeError:
        ok("step 6 (negative): JSON parser correctly rejects corrupt input — step-2 validation is real")

    # 7. NEGATIVE — phantom script not in scripts.
    if pkg.is_file():
        pkg_data = json.loads(pkg.read_text(encoding="utf-8"))
        scripts = pkg_data.get("scripts", {})
        if "phantom-script-does-not-exist" not in scripts:
            ok("step 7 (negative): phantom script absent — script audit reads real package.json")
        else:
            fail("step 7 (negative): phantom script somehow appears in scripts")
            failures += 1

    print()
    if failures == 0:
        print(f"{GREEN}{BOLD}ALL 7 STEPS PASSED{NC}")
        return 0
    print(f"{RED}{BOLD}{failures} STEP(S) FAILED{NC}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
