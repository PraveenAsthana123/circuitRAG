#!/usr/bin/env python3
"""Advanced offline-safe status for RAGAS, Giskard, and DeepEval.

The goal is operator signal without surprise LLM/API calls:
  - package import/version status for each engine
  - env-gated readiness for real judge/scanner paths
  - deterministic local RAG quality gate for smoke/regression checks
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
DEFAULT_REPORT = REPO / ".loop" / "eval_quality_report.json"
DEFAULT_AUDIT = REPO / ".loop" / "eval_quality_audit.jsonl"

SAMPLE = {
    "id": "sample-neo4j",
    "question": "What database stores graph relationships in DocuMind?",
    "answer": "Neo4j stores graph relationships for DocuMind.",
    "contexts": [
        "DocuMind uses Neo4j for graph relationships and Cypher traversal.",
        "Qdrant stores dense vectors for semantic retrieval.",
    ],
    "ground_truth": "Neo4j stores graph relationships.",
}


def _pkg_status(pkg: str, module: str | None = None) -> dict[str, Any]:
    module = module or pkg
    try:
        mod = import_module(module)
        try:
            ver = version(pkg)
        except PackageNotFoundError:
            ver = getattr(mod, "__version__", "unknown")
        return {"installed": True, "importable": True, "version": ver, "error": ""}
    except Exception as exc:  # noqa: BLE001
        ver = None
        try:
            ver = version(pkg)
        except PackageNotFoundError:
            pass
        return {
            "installed": ver is not None,
            "importable": False,
            "version": ver,
            "error": f"{type(exc).__name__}: {str(exc)[:240]}",
        }


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def _overlap(a: str, b: str) -> float:
    aa = _tokens(a)
    bb = _tokens(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa)


def deterministic_rag_gate(
    *,
    question: str,
    answer: str,
    contexts: list[str],
    ground_truth: str | None = None,
) -> dict[str, Any]:
    context_blob = " ".join(contexts)
    scores = {
        "answer_groundedness": _overlap(answer, context_blob),
        "context_relevance": _overlap(question, context_blob),
        "answer_correctness": _overlap(ground_truth or answer, answer),
    }
    thresholds = {
        "answer_groundedness": float(os.getenv("EVAL_GATE_GROUNDEDNESS_THRESHOLD", "0.55")),
        "context_relevance": float(os.getenv("EVAL_GATE_CONTEXT_RELEVANCE_THRESHOLD", "0.35")),
        "answer_correctness": float(os.getenv("EVAL_GATE_CORRECTNESS_THRESHOLD", "0.60")),
    }
    passes = {name: scores[name] >= thresholds[name] for name in scores}
    return {
        "scores": scores,
        "thresholds": thresholds,
        "passes": passes,
        "overall_pass": all(passes.values()),
        "engine": "deterministic_offline_gate",
        "note": "Fast lexical smoke gate; use RAGAS/DeepEval for judge-grade evaluation when enabled.",
    }


def deterministic_risk_scan(*, question: str, answer: str, contexts: list[str]) -> dict[str, Any]:
    text = "\n".join([question, answer, *contexts]).lower()
    patterns = {
        "prompt_injection": [
            "ignore previous instructions",
            "system prompt",
            "developer message",
            "jailbreak",
            "act as",
        ],
        "pii_like": [
            r"\b\d{3}-\d{2}-\d{4}\b",
            r"\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b",
        ],
        "secret_like": [
            "api_key",
            "secret_key",
            "password=",
            "bearer ",
        ],
    }
    findings: list[dict[str, str]] = []
    for category, needles in patterns.items():
        for needle in needles:
            matched = bool(re.search(needle, text)) if needle.startswith("\\b") else needle in text
            if matched:
                findings.append({"category": category, "pattern": needle})
    return {
        "engine": "deterministic_risk_scan",
        "issue_count": len(findings),
        "issues": findings[:20],
        "passed": not findings,
    }


def _load_records(path: str | None) -> list[dict[str, Any]]:
    if path is None:
        return [dict(SAMPLE)]
    raw = Path(path).read_text(encoding="utf-8")
    if path.endswith(".jsonl"):
        return [json.loads(line) for line in raw.splitlines() if line.strip()]
    loaded = json.loads(raw)
    if isinstance(loaded, dict) and "records" in loaded:
        loaded = loaded["records"]
    if not isinstance(loaded, list):
        raise ValueError("eval input must be a JSON list, JSON object with records, or JSONL")
    return loaded


def _normalise_record(record: dict[str, Any], index: int) -> dict[str, Any]:
    contexts = record.get("contexts", record.get("retrieved_contexts", []))
    if isinstance(contexts, str):
        contexts = [contexts]
    return {
        "id": str(record.get("id") or record.get("case_id") or f"case-{index + 1}"),
        "question": str(record.get("question", "")),
        "answer": str(record.get("answer", record.get("predicted_answer", ""))),
        "contexts": [str(c) for c in contexts],
        "ground_truth": record.get("ground_truth", record.get("ground_truth_answer")),
        "metadata": dict(record.get("metadata", {})),
    }


def _harness_scores(case: dict[str, Any]) -> dict[str, Any]:
    service_path = REPO / "services" / "evaluation-svc"
    if str(service_path) not in sys.path:
        sys.path.insert(0, str(service_path))
    try:
        from app.eval_harness import DeepEvalEngine, GiskardEngine, RagasEngine

        ragas = RagasEngine().evaluate(
            question=case["question"],
            answer=case["answer"],
            contexts=case["contexts"],
            ground_truth=case["ground_truth"],
        )
        deepeval = DeepEvalEngine().evaluate(
            question=case["question"],
            answer=case["answer"],
            contexts=case["contexts"],
        )
        giskard = GiskardEngine().scan(model_callable=lambda _prompt: case["answer"])
        return {"ragas": ragas, "deepeval": deepeval, "giskard": giskard}
    except Exception as exc:  # noqa: BLE001
        return {
            "ragas": {"available": False, "error": str(exc)[:200], "stub": True},
            "deepeval": {"available": False, "error": str(exc)[:200], "stub": True},
            "giskard": {"available": False, "error": str(exc)[:200], "stub": True},
        }


def evaluate_record(record: dict[str, Any], *, index: int = 0, include_harness: bool = True) -> dict[str, Any]:
    case = _normalise_record(record, index)
    gate = deterministic_rag_gate(
        question=case["question"],
        answer=case["answer"],
        contexts=case["contexts"],
        ground_truth=case["ground_truth"],
    )
    risk = deterministic_risk_scan(
        question=case["question"],
        answer=case["answer"],
        contexts=case["contexts"],
    )
    result = {
        "id": case["id"],
        "metadata": case["metadata"],
        "offline_gate": gate,
        "risk_scan": risk,
        "overall_pass": bool(gate["overall_pass"] and risk["passed"]),
    }
    if include_harness:
        result["engines"] = _harness_scores(case)
    return result


def run_batch(
    records: list[dict[str, Any]],
    *,
    include_harness: bool = True,
    audit_path: Path | None = None,
) -> dict[str, Any]:
    started = time.time()
    results = [
        evaluate_record(record, index=index, include_harness=include_harness)
        for index, record in enumerate(records)
    ]
    if audit_path is not None:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8") as fh:
            for result in results:
                fh.write(json.dumps({"ts": started, **result}, sort_keys=True) + "\n")
    n = len(results)
    passed = sum(1 for result in results if result["overall_pass"])
    metric_names = ("answer_groundedness", "context_relevance", "answer_correctness")
    means = {
        name: (sum(result["offline_gate"]["scores"][name] for result in results) / n if n else 0.0)
        for name in metric_names
    }
    return {
        "generated_at_unix": started,
        "n": n,
        "passed": passed,
        "failed": n - passed,
        "pass_rate": passed / n if n else 0.0,
        "mean_scores": means,
        "results": results,
        "status": "PASS" if passed == n else "FAIL",
    }


def status() -> dict[str, Any]:
    ragas = _pkg_status("ragas")
    giskard = _pkg_status("giskard")
    deepeval = _pkg_status("deepeval")
    return {
        "ragas": {
            **ragas,
            "enabled_env": os.getenv("RAGAS_EVAL_ENABLED", "").strip() == "1",
            "ready_for_real_eval": bool(ragas["importable"] and os.getenv("RAGAS_EVAL_ENABLED", "").strip() == "1"),
            "role": "RAG faithfulness/relevance/context judge",
        },
        "giskard": {
            **giskard,
            "enabled_env": os.getenv("GISKARD_SCAN_ENABLED", "").strip() == "1",
            "ready_for_real_scan": bool(giskard["importable"] and os.getenv("GISKARD_SCAN_ENABLED", "").strip() == "1"),
            "role": "LLM red-team and bias scanner",
        },
        "deepeval": {
            **deepeval,
            "enabled_env": os.getenv("DEEPEVAL_ENABLED", "").strip() == "1",
            "ready_for_real_eval": bool(deepeval["importable"] and os.getenv("DEEPEVAL_ENABLED", "").strip() == "1"),
            "role": "Alternative RAG/task eval triangulation",
        },
        "offline_gate": deterministic_rag_gate(
            question=SAMPLE["question"],
            answer=SAMPLE["answer"],
            contexts=SAMPLE["contexts"],
            ground_truth=SAMPLE["ground_truth"],
        ),
        "risk_scan": deterministic_risk_scan(
            question=SAMPLE["question"],
            answer=SAMPLE["answer"],
            contexts=SAMPLE["contexts"],
        ),
        "recommendation": (
            "Use deterministic gate on every CI run, RAGAS on sampled RAG answers, "
            "Giskard on scheduled red-team scans, and DeepEval only after its import "
            "stack is compatible with this Python runtime."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--input", help="JSON/JSONL eval records. Defaults to built-in smoke sample.")
    parser.add_argument("--output", default=str(DEFAULT_REPORT), help="write batch report JSON here")
    parser.add_argument("--audit", default=str(DEFAULT_AUDIT), help="append per-record audit JSONL here")
    parser.add_argument("--no-harness", action="store_true", help="skip env-gated RAGAS/Giskard/DeepEval harness calls")
    parser.add_argument("--fail-on-gate", action="store_true", help="exit non-zero when any record fails the offline gate")
    args = parser.parse_args()
    if args.input or args.fail_on_gate:
        records = _load_records(args.input)
        payload = run_batch(
            records,
            include_harness=not args.no_harness,
            audit_path=Path(args.audit) if args.audit else None,
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"Eval batch {payload['status']}: {payload['passed']}/{payload['n']} passed")
            print(f"Wrote: {output}")
        return 1 if args.fail_on_gate and payload["status"] != "PASS" else 0

    payload = status()
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"RAGAS importable={payload['ragas']['importable']} enabled={payload['ragas']['enabled_env']}")
        print(f"Giskard importable={payload['giskard']['importable']} enabled={payload['giskard']['enabled_env']}")
        print(f"DeepEval importable={payload['deepeval']['importable']} enabled={payload['deepeval']['enabled_env']}")
        print(f"Offline gate pass={payload['offline_gate']['overall_pass']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
