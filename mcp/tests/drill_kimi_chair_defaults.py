#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Kimi chair defaults stay wired in the repo.

Locks the contract that:

  * sidecar-advisor chair agent defaults to `kimi-k2:1t-cloud`
  * agent-orchestrator config defaults advisor model to the same tag
  * agent-orchestrator registry/service defaults match the same tag

Five steps. Four negative assertions.

  1. POSITIVE: locate sidecar-advisor chair agent + agent-orchestrator
     config + registry + service files on disk.
  2. NEGATIVE: chair-agent module's model literal equals KIMI_MODEL.
     Prevents a silent revert to deepseek/llama on a future edit.
  3. NEGATIVE: agent-orchestrator config default advisor model
     literal equals KIMI_MODEL. Config drift would let new pods
     silently fall back to a non-cloud model on rollout.
  4. NEGATIVE: agent-orchestrator registry advisor role default
     equals KIMI_MODEL. Registry drift would let agents resolve
     to a stale chair tag at runtime.
  5. NEGATIVE: service constructor default advisor_model equals
     KIMI_MODEL. Constructor drift would let new instances run
     under a different chair than declared.

This is a readonly structural drill only. It does not verify live
Ollama Cloud access; that remains an environment-gated runtime check.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
KIMI_MODEL = "kimi-k2:1t-cloud"

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


def parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def find_class_assignment(path: Path, class_name: str, attr_name: str) -> str:
    tree = parse(path)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id == attr_name:
                    return ast.literal_eval(stmt.value)
    fail(f"{path}: could not find {class_name}.{attr_name}")


def find_keyword_value_in_call(path: Path, call_name: str, keyword_name: str) -> str:
    tree = parse(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == call_name:
            for kw in node.keywords:
                if kw.arg == keyword_name:
                    return ast.literal_eval(kw.value)
    fail(f"{path}: could not find {call_name}(..., {keyword_name}=...)")


def find_default_agent_role_model(path: Path, role_id: str) -> str:
    tree = parse(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "AgentRoleSpec":
            role_value = None
            model_value = None
            for kw in node.keywords:
                if kw.arg == "role_id":
                    role_value = ast.literal_eval(kw.value)
                if kw.arg == "model":
                    model_value = ast.literal_eval(kw.value)
            if role_value == role_id:
                return model_value
    fail(f"{path}: could not find AgentRoleSpec for role_id={role_id!r}")


def find_function_default(path: Path, function_name: str, arg_name: str) -> str:
    tree = parse(path)
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if isinstance(stmt, ast.FunctionDef) and stmt.name == function_name:
                    args = stmt.args.args
                    defaults = stmt.args.defaults
                    default_offset = len(args) - len(defaults)
                    for index, arg in enumerate(args):
                        if arg.arg == arg_name:
                            if index < default_offset:
                                fail(f"{path}: {function_name}.{arg_name} has no default")
                            return ast.literal_eval(defaults[index - default_offset])
                    for kwarg, default in zip(stmt.args.kwonlyargs, stmt.args.kw_defaults, strict=False):
                        if kwarg.arg == arg_name:
                            if default is None:
                                fail(f"{path}: {function_name}.{arg_name} has no default")
                            return ast.literal_eval(default)
    fail(f"{path}: could not find default for {function_name}(..., {arg_name}=...)")


def find_module_constant(path: Path, constant_name: str) -> str:
    tree = parse(path)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == constant_name:
                    return ast.literal_eval(node.value)
    fail(f"{path}: could not find constant {constant_name}")


def assert_getenv_default(path: Path, env_var: str, default_name: str) -> None:
    tree = parse(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "os" and node.func.attr == "getenv":
                if len(node.args) >= 2:
                    env_arg = node.args[0]
                    default_arg = node.args[1]
                    if (
                        isinstance(env_arg, ast.Constant)
                        and env_arg.value == env_var
                        and isinstance(default_arg, ast.Name)
                        and default_arg.id == default_name
                    ):
                        return
    fail(f"{path}: expected os.getenv({env_var!r}, {default_name})")


def main() -> None:
    chair_path = REPO / "services" / "sidecar-advisor" / "agents" / "chair.py"
    config_path = REPO / "services" / "agent-orchestrator-svc" / "app" / "core" / "config.py"
    registry_path = REPO / "services" / "agent-orchestrator-svc" / "app" / "agent_registry.py"
    service_path = REPO / "services" / "agent-orchestrator-svc" / "app" / "service.py"

    step("1. Sidecar chair default constant stays on Kimi cloud")
    chair_model = find_module_constant(chair_path, "DEFAULT_CHAIR_MODEL")
    if chair_model != KIMI_MODEL:
        fail(f"chair model drifted: expected {KIMI_MODEL!r}, got {chair_model!r}")
    ok(f"DEFAULT_CHAIR_MODEL = {chair_model}")

    step("2. Sidecar chair supports env override for local fallback")
    assert_getenv_default(chair_path, "SIDECAR_CHAIR_MODEL", "DEFAULT_CHAIR_MODEL")
    ok("SIDECAR_CHAIR_MODEL override is wired")

    step("3. Orchestrator settings default advisor model matches chair")
    config_model = find_class_assignment(config_path, "AgentOrchestratorSettings", "agent_advisor_model")
    if config_model != KIMI_MODEL:
        fail(f"settings advisor model drifted: expected {KIMI_MODEL!r}, got {config_model!r}")
    ok(f"settings.agent_advisor_model = {config_model}")

    step("4. Agent registry advisor role default matches chair")
    registry_model = find_default_agent_role_model(registry_path, "advisor")
    if registry_model != KIMI_MODEL:
        fail(f"registry advisor model drifted: expected {KIMI_MODEL!r}, got {registry_model!r}")
    ok(f"registry advisor model = {registry_model}")

    step("5. Service constructor default advisor model matches chair")
    service_model = find_function_default(service_path, "__init__", "advisor_model")
    if service_model != KIMI_MODEL:
        fail(f"service advisor model drifted: expected {KIMI_MODEL!r}, got {service_model!r}")
    ok(f"service advisor_model default = {service_model}")

    print(f"\n{BOLD}{GREEN}{'=' * 52}{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 KIMI-CHAIR-DEFAULT STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (4 negative assertions: 2, 3, 4, 5){NC}")
    print(f"{BOLD}{GREEN}  live cloud verification remains env-gated{NC}")
    print(f"{BOLD}{GREEN}{'=' * 52}{NC}")


if __name__ == "__main__":
    main()
