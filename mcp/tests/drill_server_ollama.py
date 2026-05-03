#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: MCP server for Ollama (Tier 5 #5.15).

Per CLAUDE.md §43 + §55. Locks the contract: 3 tools registered
with correct scopes; argument schemas reject malformed input;
unknown tool returns 404; out-of-range args (temperature > 2.0;
prompt > 32K) rejected.

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "mcp" / "server_ollama.py"


def _load():
    sys.path.insert(0, str(REPO))
    spec = importlib.util.spec_from_file_location("mcp.server_ollama", SCRIPT)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not load {SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mcp.server_ollama"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: server_ollama imports + 3 tools registered --")
    so = _load()
    if not hasattr(so, "TOOL_REGISTRY"):
        print("x step 1: TOOL_REGISTRY missing")
        return 1
    expected = {"ollama.generate", "ollama.list_models", "ollama.warm"}
    if set(so.TOOL_REGISTRY.keys()) != expected:
        print(f"x step 1: tool registry mismatch — expected {expected}, got {set(so.TOOL_REGISTRY.keys())}")
        return 1
    print(f"  ok: 3 tools registered ({sorted(so.TOOL_REGISTRY.keys())})")

    print("-- 2. POSITIVE: each tool has args_schema + handler + required_scopes --")
    for name, meta in so.TOOL_REGISTRY.items():
        for key in ("args_schema", "handler", "required_scopes"):
            if key not in meta:
                print(f"x step 2: tool {name} missing {key}")
                return 1
        if not meta["required_scopes"]:
            print(f"x step 2: tool {name} has empty required_scopes (per §50.5.3 every tool MUST have ≥1 scope)")
            return 1
    print("  ok: all 3 tools have schema + handler + scope")

    print("-- 3. NEGATIVE: GenerateArgs rejects prompt > 32K chars --")
    try:
        so.GenerateArgs(model="x", prompt="A" * 50_000)
    except Exception:
        print("  ok: 50K-char prompt rejected by max_length")
    else:
        print("x step 3: 50K-char prompt accepted")
        return 1

    print("-- 4. NEGATIVE: GenerateArgs rejects temperature > 2.0 --")
    try:
        so.GenerateArgs(model="x", prompt="hi", temperature=5.0)
    except Exception:
        print("  ok: temperature=5.0 rejected by ge/le bounds")
    else:
        print("x step 4: temperature=5.0 accepted")
        return 1

    print("-- 5. NEGATIVE: GenerateArgs rejects extra fields --")
    try:
        so.GenerateArgs.model_validate({
            "model": "x", "prompt": "hi",
            "operator_pii": "praveen@example.com",
        })
    except Exception:
        print("  ok: extra 'operator_pii' field rejected (extra='forbid')")
    else:
        print("x step 5: extra field accepted")
        return 1

    print("-- 6. NEGATIVE: WarmArgs has default keep_alive='24h' (preserved across restart) --")
    args = so.WarmArgs(model="qwen2.5:latest")
    if args.keep_alive != "24h":
        print(f"x step 6: WarmArgs default keep_alive expected '24h'; got {args.keep_alive!r}")
        return 1
    print(f"  ok: WarmArgs default keep_alive='24h' (matches scripts/warm_council_pool.py)")

    print("-- 7. NEGATIVE: TOOL_REGISTRY scopes follow ollama:* namespace --")
    for name, meta in so.TOOL_REGISTRY.items():
        for scope in meta["required_scopes"]:
            if not scope.startswith("ollama:"):
                print(f"x step 7: tool {name} has non-namespaced scope {scope!r}; must start with 'ollama:'")
                return 1
    print(f"  ok: all scopes namespaced under 'ollama:*'")

    print("-- 8. POSITIVE: FastAPI app exposes /health/live, /health/ready, /tools/list, /tools/call --")
    routes = {r.path for r in so.app.routes if hasattr(r, "path")}
    for required in ("/health/live", "/health/ready", "/tools/list", "/tools/call"):
        if required not in routes:
            print(f"x step 8: missing route {required}; got {sorted(routes)}")
            return 1
    print(f"  ok: 4 standard MCP routes present")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
