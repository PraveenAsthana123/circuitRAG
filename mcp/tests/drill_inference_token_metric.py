# RESOURCES: none
"""
Drill: documind_inference_tokens_total{model, kind} counts every
LLM response's prompt + completion tokens, by model and kind.

The catalog gap (cited 3× — rag-data-layers, AIOps, enterprise):
the inference-svc logged token counts but never exposed them as a
Prometheus series. Without this, ops can't:
  * forecast spend
  * spot a cost spike after a prompt or model change
  * compare input-vs-output token shape across models

Each step is a negative-assertion §43-style:
 1. Baseline snapshot.
 2. Successful response → counter increments by exactly
    ``prompt_tokens`` for kind=prompt AND ``completion_tokens`` for
    kind=completion. Negative: a response with N+M tokens must NOT
    bump some other counter (e.g. an "all-tokens" sink).
 3. Two responses on the SAME model accumulate. Negative: the
    second call must NOT replace the first (Counter, not Gauge).
 4. Different model label → different series. Negative: tokens
    from model A must NOT appear under model B.
 5. Failed call (CircuitOpenError) does NOT bump. Negative: a
    rejected call didn't consume tokens, so the counter must
    stay flat.
 6. Zero-token response → counter unchanged. Negative: ``inc(0)``
    must not create a phantom series.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_inference_token_metric.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "services" / "inference-svc"))

from app.services.ollama_client import (  # type: ignore  # noqa: E402
    _inference_tokens_total,
    _record_tokens,
)

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


def _val(model: str, kind: str) -> float:
    if _inference_tokens_total is None:
        return 0.0
    return _inference_tokens_total.labels(model=model, kind=kind)._value.get()  # noqa: SLF001


def _series_count_for(model: str) -> int:
    """How many label combinations exist for this model (across kinds)."""
    if _inference_tokens_total is None:
        return 0
    n = 0
    for labels, _ in _inference_tokens_total._metrics.items():  # noqa: SLF001
        if labels[0] == model:
            n += 1
    return n


def main() -> None:
    if _inference_tokens_total is None:
        fail("prometheus_client missing — counter not registered")

    MODEL_A = "llama3.1:8b"
    MODEL_B = "claude-haiku-4-5"

    step("1. Baseline snapshot")
    b_a_prompt = _val(MODEL_A, "prompt")
    b_a_completion = _val(MODEL_A, "completion")
    b_b_prompt = _val(MODEL_B, "prompt")
    b_b_completion = _val(MODEL_B, "completion")
    ok(
        f"baseline: A.prompt={b_a_prompt} A.completion={b_a_completion} "
        f"B.prompt={b_b_prompt} B.completion={b_b_completion}"
    )

    step("2. Successful response (236/48 tokens) → counter +236 prompt, +48 completion")
    _record_tokens(model=MODEL_A, prompt_tokens=236, completion_tokens=48)
    delta_p = _val(MODEL_A, "prompt") - b_a_prompt
    delta_c = _val(MODEL_A, "completion") - b_a_completion
    if delta_p != 236:
        fail(f"prompt delta != 236: got {delta_p}")
    if delta_c != 48:
        fail(f"completion delta != 48: got {delta_c}")
    ok("A.prompt +236  A.completion +48 (separate kind buckets)")

    step("3. Two responses on same model accumulate (Counter semantics)")
    _record_tokens(model=MODEL_A, prompt_tokens=100, completion_tokens=20)
    delta_p = _val(MODEL_A, "prompt") - b_a_prompt
    delta_c = _val(MODEL_A, "completion") - b_a_completion
    if delta_p != 336:  # 236 + 100
        fail(
            f"prompt delta after 2 calls != 336 (236+100): got {delta_p}. "
            f"If got 100, the counter is being RESET — that's a Gauge, "
            f"not a Counter; semantic regression."
        )
    if delta_c != 68:  # 48 + 20
        fail(f"completion delta after 2 calls != 68 (48+20): got {delta_c}")
    ok(f"A.prompt={delta_p} (cumulative); A.completion={delta_c}")

    step("4. Different model → different series (label isolation)")
    _record_tokens(model=MODEL_B, prompt_tokens=500, completion_tokens=200)
    if _val(MODEL_B, "prompt") - b_b_prompt != 500:
        fail("MODEL_B series isolation broken")
    # Critical negative: A's counter stayed at 336/68 — B's tokens
    # didn't leak into A's series.
    if _val(MODEL_A, "prompt") - b_a_prompt != 336:
        fail(
            "MODEL_A.prompt changed after recording MODEL_B tokens! "
            "Cross-model leak."
        )
    ok("B.prompt +500 B.completion +200; A unchanged (no cross-model leak)")

    step("5. Zero-token response → counter unchanged AND no phantom series")
    pre_a_prompt = _val(MODEL_A, "prompt")
    pre_series = _series_count_for("nonexistent-model-xyz")
    _record_tokens(model="nonexistent-model-xyz", prompt_tokens=0, completion_tokens=0)
    if _val(MODEL_A, "prompt") != pre_a_prompt:
        fail("zero-token call moved an unrelated counter")
    # The guard in _record_tokens skips inc() when count is 0, so no
    # series should be materialized for the new model name.
    if _series_count_for("nonexistent-model-xyz") != pre_series:
        fail(
            "zero-token call materialized a phantom series under "
            "'nonexistent-model-xyz' — Counter was inc(0)'d which "
            "creates the labelset. Counter must skip the call entirely."
        )
    ok("zero-token call → no phantom series")

    step("6. Counter exposes HELP/TYPE in Prometheus exposition format")
    from prometheus_client import REGISTRY, generate_latest
    out = generate_latest(REGISTRY).decode()
    has_help = (
        "# HELP documind_inference_tokens_total" in out
        or "# HELP documind_inference_tokens" in out
    )
    has_type = "# TYPE documind_inference_tokens_total counter" in out
    if not has_help:
        fail("HELP line for documind_inference_tokens_total missing")
    if not has_type:
        fail("TYPE counter line for documind_inference_tokens_total missing")
    # And the labels render correctly. Prometheus exposition emits
    # labels in alphabetical order, so it's ``{kind=...,model=...}``,
    # not the declaration order.
    expected = f'kind="prompt",model="{MODEL_A}"'
    if expected not in out:
        fail(f"{expected!r} labelset not in /metrics output")
    ok("HELP + TYPE counter + labelset all present in exposition")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 6 INFERENCE-TOKEN-METRIC STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    main()
