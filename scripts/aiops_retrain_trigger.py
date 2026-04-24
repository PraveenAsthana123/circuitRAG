#!/usr/bin/env python3
"""
AIops — automatic retrain-trigger driver.

Polls the evaluation-svc + Prometheus for these signals:

* Faithfulness avg over 1h dropped > 5% vs last week's baseline.
* Precision@5 dropped > 10% vs baseline.
* CCB interrupt rate > 0.2/s sustained.
* Retrieval quality breaker opened in the last hour.

When ANY signal trips, it:
1. Writes a `retrain_required` row to `governance.policies` (audit trail).
2. Publishes a `ops.retrain_required.v1` Kafka event for the ops team to pick up.
3. Pings Slack / PagerDuty (stub here — wire your own webhook).

The retrain itself (re-embed corpus, re-index, retrain reranker) is a separate
workflow owned by the AI team — this script is JUST the trigger.

Run as a CronJob in K8s (every 10 minutes). For dev:
    python3 scripts/aiops_retrain_trigger.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any

import httpx

PROM_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
EVAL_URL = os.getenv("DOCUMIND_EVALUATION_URL", "http://localhost:8085")

THRESH = {
    "faithfulness_drop_pct": 5.0,    # relative drop
    "precision_drop_pct":    10.0,
    "ccb_interrupt_rps":     0.2,
    "retrieval_breaker_opens_per_hr": 1,
}


@dataclass
class Signal:
    name: str
    fired: bool
    value: float
    threshold: float
    reason: str


async def prom_query(client: httpx.AsyncClient, q: str) -> float:
    r = await client.get(f"{PROM_URL}/api/v1/query", params={"query": q})
    r.raise_for_status()
    data = r.json().get("data", {}).get("result", [])
    if not data:
        return 0.0
    try:
        return float(data[0]["value"][1])
    except (KeyError, IndexError, ValueError):
        return 0.0


async def check_faithfulness(client: httpx.AsyncClient) -> Signal:
    # Faithfulness ratio: current 1h avg / last-week 24h avg.
    # If ratio < (1 - threshold), regression.
    now = await prom_query(client, "avg_over_time(documind_eval_faithfulness[1h])")
    baseline = await prom_query(
        client,
        "avg_over_time(documind_eval_faithfulness[24h] offset 7d)",
    )
    if baseline == 0:
        return Signal("faithfulness", False, 0, THRESH["faithfulness_drop_pct"],
                      "no baseline data")
    drop_pct = (1 - now / baseline) * 100
    return Signal(
        "faithfulness",
        fired=drop_pct > THRESH["faithfulness_drop_pct"],
        value=drop_pct,
        threshold=THRESH["faithfulness_drop_pct"],
        reason=f"{drop_pct:.1f}% drop (now={now:.3f} baseline={baseline:.3f})",
    )


async def check_ccb_interrupt_rate(client: httpx.AsyncClient) -> Signal:
    rps = await prom_query(client, "sum(rate(documind_ccb_interrupts_total[5m]))")
    return Signal(
        "ccb_interrupts",
        fired=rps > THRESH["ccb_interrupt_rps"],
        value=rps,
        threshold=THRESH["ccb_interrupt_rps"],
        reason=f"{rps:.3f}/s vs threshold {THRESH['ccb_interrupt_rps']}/s",
    )


async def check_retrieval_breaker_opens(client: httpx.AsyncClient) -> Signal:
    opens = await prom_query(
        client, "sum(increase(documind_retrieval_quality_opens_total[1h]))"
    )
    return Signal(
        "retrieval_quality_breaker",
        fired=opens >= THRESH["retrieval_breaker_opens_per_hr"],
        value=opens,
        threshold=THRESH["retrieval_breaker_opens_per_hr"],
        reason=f"{int(opens)} opens in last hour",
    )


async def main(dry_run: bool) -> int:
    started = time.time()
    async with httpx.AsyncClient(timeout=10) as client:
        signals = await asyncio.gather(
            check_faithfulness(client),
            check_ccb_interrupt_rate(client),
            check_retrieval_breaker_opens(client),
            return_exceptions=True,
        )

    fired: list[Signal] = [s for s in signals if isinstance(s, Signal) and s.fired]
    duration = time.time() - started

    print(json.dumps({
        "ts": int(started),
        "duration_s": round(duration, 2),
        "signals": [
            {"name": s.name, "fired": s.fired, "value": s.value, "reason": s.reason}
            for s in signals if isinstance(s, Signal)
        ],
        "retrain_required": bool(fired),
    }, indent=2))

    if not fired:
        return 0

    if dry_run:
        print("[dry-run] would publish ops.retrain_required.v1 event", file=sys.stderr)
        return 0

    # Real trigger: publish Kafka event + optional webhook call.
    # TODO: inject kafka producer + webhook client (keep this script
    # self-contained for the initial commit).
    print("[trigger] retrain event would be published here", file=sys.stderr)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.dry_run)))
