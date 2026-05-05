#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: empirical-loop end-to-end integration (per ADR-023 + §43).

Locks the FULL chain: synthesized search report → promotion gate →
best_config.json → loader → effective getters. Without this drill,
unit drills could pass while the chain breaks at a seam.

Composes:
  scripts/promote_best_config.py     (gate writes best_config.json)
  scripts/best_config_loader.py      (reader consumes it)
  scripts/best_config_history.py     (audit projection reads append)
  scripts/stage3_earned_check.py     (meta-gate verdict on history)

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"


def _fresh_import(name: str):
    """Re-import a script module from disk so env-flag changes are picked up."""
    if name in sys.modules:
        del sys.modules[name]
    return importlib.import_module(name)


def _make_search_report(top_pass: float, runner_pass: float, *, eval_size: int = 5) -> dict:
    return {
        "ranked_configs": [
            {
                "config": {
                    "chunking_strategy": "recursive_paragraph_sentence",
                    "min_score": 0.5,
                    "rerank_enabled": False,
                    "rerank_top_k": 10,
                    "retrieval_top_k": 10,
                },
                "overall_pass_rate": top_pass,
                "eval_set_size": eval_size,
            },
            {
                "config": {
                    "chunking_strategy": "recursive_paragraph_sentence",
                    "min_score": 0.0,
                    "rerank_enabled": False,
                    "rerank_top_k": 10,
                    "retrieval_top_k": 5,
                },
                "overall_pass_rate": runner_pass,
                "eval_set_size": eval_size,
            },
        ],
        "summary": "e2e-integration-fixture",
    }


def main() -> int:
    sys.path.insert(0, str(SCRIPTS))

    print("-- 1. POSITIVE: all 4 chain modules importable in isolation --")
    for env_flag, mod_name in [
        ("PROMOTION_GATE_ENABLED", "promote_best_config"),
        ("BEST_CONFIG_LOADER_ENABLED", "best_config_loader"),
        ("BEST_CONFIG_HISTORY_ENABLED", "best_config_history"),
        ("STAGE3_EARNED_CHECK_ENABLED", "stage3_earned_check"),
    ]:
        os.environ[env_flag] = "1"
        m = _fresh_import(mod_name)
        if not m.is_available():
            print(f"x {mod_name}.is_available() must be True with env set")
            return 1
    print("  ok: 4 chain modules import + gate on env flag")

    print("-- 2. NEGATIVE: gate REJECTS low pass-rate; chain dead-ends correctly --")
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        report_path = tmp_p / "report.json"
        best_path = tmp_p / "best.json"
        history_path = tmp_p / "history.jsonl"
        report_path.write_text(json.dumps(_make_search_report(0.3, 0.2)))

        os.environ["PROMOTION_MIN_PASS_RATE"] = "0.5"
        gate = _fresh_import("promote_best_config")
        decision = gate.promote(
            report_path=str(report_path),
            best_path=str(best_path),
            history_path=str(history_path),
        )
        if decision.promoted:
            print("x low pass-rate must be REJECTED")
            return 1
        if best_path.exists():
            print("x best_config.json must NOT be written on rejection")
            return 1
        if not history_path.exists():
            print("x history.jsonl MUST be appended even on rejection (audit)")
            return 1
        os.environ.pop("PROMOTION_MIN_PASS_RATE", None)
    print("  ok: rejection chain — no best_config write; history row preserved")

    print("-- 3. POSITIVE: gate PROMOTES high pass-rate; loader picks up the result --")
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        report_path = tmp_p / "report.json"
        best_path = tmp_p / "best.json"
        history_path = tmp_p / "history.jsonl"
        report_path.write_text(json.dumps(_make_search_report(1.0, 0.0)))

        gate = _fresh_import("promote_best_config")
        decision = gate.promote(
            report_path=str(report_path),
            best_path=str(best_path),
            history_path=str(history_path),
        )
        if not decision.promoted:
            print(f"x high pass-rate should promote; got {decision.reason}")
            return 1
        if not best_path.exists():
            print("x best_config.json must be written on promotion")
            return 1

        # Loader reads it
        os.environ["BEST_CONFIG_PATH"] = str(best_path)
        os.environ["BEST_CONFIG_LOADER_ENABLED"] = "1"
        loader = _fresh_import("best_config_loader")
        cfg = loader.load_best_config(force=True)
        if cfg is None:
            print("x loader must read just-written best_config.json")
            return 1
        if cfg.min_score != 0.5:
            print(f"x loader.min_score expected 0.5; got {cfg.min_score}")
            return 1
        if cfg.top_k != 10:
            print(f"x loader.top_k expected 10; got {cfg.top_k}")
            return 1
        # Getters reflect file
        if loader.get_default_min_score() != 0.5:
            print("x get_default_min_score() must reflect promoted config")
            return 1
    print("  ok: promotion → write → loader read; cross-component handoff intact")

    print("-- 4. NEGATIVE: chain SURVIVES disabled loader (legacy fallback) --")
    # When the loader is disabled, the gate's write still produces
    # a file BUT the loader getters return legacy defaults. Drill
    # enforces the legacy-fallback path one more time at the e2e seam.
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        best_path = tmp_p / "best.json"
        # Pre-populate a valid best_config
        best_path.write_text(json.dumps({
            "config": {
                "min_score": 0.99,
                "rerank_enabled": True,
                "retrieval_top_k": 50,
            },
            "pass_rate": 1.0,
        }))
        os.environ["BEST_CONFIG_PATH"] = str(best_path)
        os.environ.pop("BEST_CONFIG_LOADER_ENABLED", None)
        loader = _fresh_import("best_config_loader")
        # Disabled → loader returns LEGACY defaults (0.0, 10, False)
        if loader.get_default_min_score() != 0.0:
            print(f"x disabled loader must return 0.0; got {loader.get_default_min_score()}")
            return 1
        if loader.get_default_top_k() != 10:
            print(f"x disabled loader must return 10; got {loader.get_default_top_k()}")
            return 1
        if loader.get_default_rerank_enabled() is not False:
            print(f"x disabled loader must return False; got {loader.get_default_rerank_enabled()}")
            return 1
    print("  ok: disabled loader → legacy defaults regardless of file content")

    print("-- 5. NEGATIVE: history reader projects rejection rationale unchanged --")
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        history_path = tmp_p / "history.jsonl"
        # Mix: 1 promoted + 2 rejected + 1 skipped
        now = time.time()
        rows = [
            {"promoted": True, "reason": "promoted — all gates passed",
             "decided_at_ts": now,
             "config": {"chunking_strategy": "rps", "min_score": 0.5,
                        "rerank_enabled": False, "retrieval_top_k": 10}},
            {"promoted": False, "reason": "rejected — gates failed: pass_rate=0.3",
             "decided_at_ts": now - 100,
             "gates_failed": ["pass_rate=0.3 < min=0.5"]},
            {"promoted": False, "reason": "rejected — gates failed: margin=0.01",
             "decided_at_ts": now - 200,
             "gates_failed": ["margin=0.01 < min=0.05"]},
            {"promoted": False, "reason": "skipped — disabled",
             "decided_at_ts": now - 300},
        ]
        history_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        os.environ["BEST_CONFIG_HISTORY_PATH"] = str(history_path)
        os.environ["BEST_CONFIG_HISTORY_ENABLED"] = "1"
        reader = _fresh_import("best_config_history")
        loaded = reader.load_history()
        s = reader.summarize(loaded, days=-1)
        if s.promoted != 1 or s.rejected != 2 or s.skipped != 1:
            print(f"x classification wrong: p={s.promoted} r={s.rejected} s={s.skipped}")
            return 1
        # gate-type aggregation
        if s.gates_failed_counts.get("pass_rate") != 1:
            print(f"x pass_rate count expected 1; got {s.gates_failed_counts}")
            return 1
        if s.gates_failed_counts.get("margin") != 1:
            print(f"x margin count expected 1; got {s.gates_failed_counts}")
            return 1
    print("  ok: history projection preserves classification + gate-type counts")

    print("-- 6. NEGATIVE: stage3 meta-gate REFUSES <min_cycles even on 100% success --")
    # Critical invariant: 1 cycle at 100% success != "earned" — that's
    # speculation. Drill enforces the §56.3 contract at the e2e seam.
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        history_path = tmp_p / "history.jsonl"
        history_path.write_text(json.dumps({
            "promoted": True,
            "reason": "promoted",
            "decided_at_ts": time.time(),
            "config": {"chunking_strategy": "rps", "min_score": 0.5,
                       "rerank_enabled": False, "retrieval_top_k": 10},
        }) + "\n")
        os.environ["BEST_CONFIG_HISTORY_PATH"] = str(history_path)
        os.environ["STAGE3_EARNED_CHECK_ENABLED"] = "1"
        check = _fresh_import("stage3_earned_check")
        verdict = check.check(
            history_path=str(history_path),
            min_cycles=10,
            min_success_ratio=0.8,
        )
        if verdict.verdict == "earned":
            print(f"x 1 cycle at 100% must NOT be earned; got {verdict.verdict}")
            return 1
        if verdict.verdict != "not_earned":
            print(f"x expected not_earned; got {verdict.verdict}")
            return 1
    print("  ok: meta-gate refuses speculation at e2e seam (§56.3)")

    print("-- 7. NEGATIVE: chain survives MALFORMED best_config.json (§47 fail-safe) --")
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        bad = tmp_p / "best.json"
        bad.write_text("not-json-{{{ malformed")
        os.environ["BEST_CONFIG_PATH"] = str(bad)
        os.environ["BEST_CONFIG_LOADER_ENABLED"] = "1"
        loader = _fresh_import("best_config_loader")
        # Must NOT raise
        try:
            cfg = loader.load_best_config(force=True)
        except Exception as exc:
            print(f"x malformed file must not raise; got {exc}")
            return 1
        if cfg is not None:
            print("x malformed file must yield None")
            return 1
        # Getters fall back to legacy
        if loader.get_default_min_score() != 0.0:
            print("x getters must fall back to legacy on malformed file")
            return 1
    print("  ok: malformed file → defaults; chain doesn't break")

    print("-- 8. POSITIVE: handoff order — gate writes BEFORE loader reads --")
    # Catches a hypothetical refactor that splits gate-write and
    # loader-read into different processes without proper sync.
    # We can't really test process ordering in a drill, but we CAN
    # assert that the gate writes the file with all fields the loader
    # needs. If the gate ever drops a field the loader requires,
    # this step catches it.
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        report_path = tmp_p / "report.json"
        best_path = tmp_p / "best.json"
        history_path = tmp_p / "history.jsonl"
        report_path.write_text(json.dumps(_make_search_report(1.0, 0.0)))
        gate = _fresh_import("promote_best_config")
        gate.promote(
            report_path=str(report_path),
            best_path=str(best_path),
            history_path=str(history_path),
        )
        # The loader requires `config` block. Verify gate wrote it.
        written = json.loads(best_path.read_text())
        if "config" not in written:
            print("x gate output must have 'config' top-level key (loader requires)")
            return 1
        cfg = written["config"]
        for required in ("min_score", "rerank_enabled"):
            if required not in cfg:
                print(f"x gate output config must have {required}")
                return 1
        # Round-trip verify: load via loader from same file
        os.environ["BEST_CONFIG_PATH"] = str(best_path)
        os.environ["BEST_CONFIG_LOADER_ENABLED"] = "1"
        loader = _fresh_import("best_config_loader")
        loaded = loader.load_best_config(force=True)
        if loaded is None:
            print("x loader must successfully read what gate wrote")
            return 1
    print("  ok: gate output → loader read round-trip preserves required fields")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
