#!/usr/bin/env python3
"""Deep RAG end-to-end test.

Workflow:
  1. Slice 30 BBC tech articles from the Kaggle dataset
  2. Upload each through ingestion-svc (sync=true so we wait for embedding)
  3. Issue retrieval queries against retrieval-svc
  4. Issue full RAG queries against inference-svc /api/v1/ask
  5. Score: retrieval@k accuracy, citation presence, latency
"""
from __future__ import annotations

import csv
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

DATASET = Path("/tmp/rag-deep-test/bbc-news-data.csv")
TENANT_ID = str(uuid.uuid4())  # ingestion-svc validates UUID format
INGEST_BASE = "http://localhost:8082"
RETRIEVE_BASE = "http://localhost:8083"
INFERENCE_BASE = "http://localhost:8084"
N_DOCS = 10  # rate-limit: ingestion-svc allows 10 uploads per tenant per window
CATEGORY = "tech"

# Ground-truth Q&A — questions where the answer should appear in the
# corpus. Each Q has expected substring(s) to find in the response.
QA_PAIRS = [
    # tech-category questions, answers grounded in BBC tech articles
    ("What is Half-Life 2 known for?", ["Half-Life", "game"]),
    ("What did Apple announce about iPod?", ["iPod"]),
    ("What is Microsoft doing about spyware?", ["Microsoft", "spyware"]),
    ("What are mobile phone trends?", ["mobile", "phone"]),
    ("What is Wi-Fi or wireless internet?", ["wireless", "Wi-Fi"]),
]


def load_articles(category: str, n: int) -> list[dict]:
    with DATASET.open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f, delimiter="\t") if r["category"] == category]
    return rows[:n]


def upload_doc(client: httpx.Client, doc: dict, idx: int) -> dict:
    """POST a single article as a multipart upload."""
    body = f"# {doc['title']}\n\n{doc['content']}"
    files = {"file": (f"{doc['filename']}.md", body.encode("utf-8"), "text/markdown")}
    data = {"sync": "true"}
    headers = {"X-Tenant-ID": TENANT_ID}
    r = client.post(
        f"{INGEST_BASE}/api/v1/documents/upload",
        files=files, data=data, headers=headers,
        timeout=60.0,
    )
    return {"idx": idx, "title": doc["title"], "status": r.status_code,
            "body": r.json() if r.status_code < 500 else r.text[:200]}


def query_retrieve(client: httpx.Client, q: str, k: int = 5) -> dict:
    headers = {"X-Tenant-ID": TENANT_ID, "Content-Type": "application/json"}
    payload = {"query": q, "top_k": k}
    t0 = time.time()
    r = client.post(f"{RETRIEVE_BASE}/api/v1/retrieve",
                    json=payload, headers=headers, timeout=30.0)
    elapsed = time.time() - t0
    return {"q": q, "status": r.status_code, "latency_ms": int(elapsed * 1000),
            "body": r.json() if r.status_code < 500 else r.text[:300]}


def query_ask(client: httpx.Client, q: str) -> dict:
    headers = {"X-Tenant-ID": TENANT_ID, "Content-Type": "application/json"}
    payload = {"query": q}
    t0 = time.time()
    r = client.post(f"{INFERENCE_BASE}/api/v1/ask",
                    json=payload, headers=headers, timeout=120.0)
    elapsed = time.time() - t0
    return {"q": q, "status": r.status_code, "latency_ms": int(elapsed * 1000),
            "body": r.json() if r.status_code < 500 else r.text[:300]}


def main() -> int:
    print(f"=== DEEP RAG TEST ===")
    print(f"tenant_id: {TENANT_ID}")
    print(f"corpus:    BBC News tech category, {N_DOCS} docs")
    print()

    articles = load_articles(CATEGORY, N_DOCS)
    print(f"  loaded {len(articles)} articles "
          f"(total chars: {sum(len(a['content']) for a in articles):,})")
    print()

    with httpx.Client() as client:
        # ---- INGEST ----
        print(f"=== STAGE 1: INGEST {N_DOCS} docs (sync mode — waits for embedding) ===")
        ingest_results = []
        ingest_t0 = time.time()
        for i, doc in enumerate(articles):
            res = upload_doc(client, doc, i)
            ingest_results.append(res)
            elapsed = time.time() - ingest_t0
            ok_marker = "✓" if res["status"] in (200, 201, 202) else f"✗{res['status']}"
            print(f"  [{i+1}/{N_DOCS}] {ok_marker} {elapsed:.1f}s   '{res['title'][:55]}'")
            time.sleep(2.0)  # spread under rate limit (10/window per tenant)
        ingest_elapsed = time.time() - ingest_t0
        ok_count = sum(1 for r in ingest_results if r["status"] in (200, 201, 202))
        print(f"  ingest: {ok_count}/{N_DOCS} ok in {ingest_elapsed:.1f}s")
        print()

        # ---- RETRIEVE ----
        print(f"=== STAGE 2: RETRIEVAL — {len(QA_PAIRS)} queries ===")
        retrieve_results = []
        for q, expected in QA_PAIRS:
            res = query_retrieve(client, q, k=5)
            res["expected"] = expected
            retrieve_results.append(res)
            print(f"  Q: {q[:60]}")
            print(f"  → {res['status']}  {res['latency_ms']}ms")
            if res["status"] == 200:
                hits = res["body"].get("data", {}).get("hits", []) or res["body"].get("hits", [])
                print(f"     {len(hits)} hits returned")
                for h in hits[:2]:
                    snippet = (h.get("text") or h.get("content") or "")[:100]
                    score = h.get("score") or h.get("similarity")
                    print(f"       score={score}  text={snippet}...")
            else:
                print(f"     ERROR: {str(res['body'])[:200]}")
            print()

        # ---- ASK (full RAG) ----
        print(f"=== STAGE 3: FULL RAG (/api/v1/ask) — {len(QA_PAIRS)} queries ===")
        ask_results = []
        for q, expected in QA_PAIRS:
            res = query_ask(client, q)
            res["expected"] = expected
            ask_results.append(res)
            print(f"  Q: {q[:60]}")
            print(f"  → {res['status']}  {res['latency_ms']}ms")
            if res["status"] == 200:
                ans = res["body"].get("data", {}).get("answer") or res["body"].get("answer", "")
                cits = res["body"].get("data", {}).get("citations") or res["body"].get("citations", [])
                print(f"     answer: {str(ans)[:200]}...")
                print(f"     citations: {len(cits)} returned")
            else:
                print(f"     ERROR: {str(res['body'])[:200]}")
            print()

    # ---- REPORT ----
    print(f"=== SUMMARY ===")
    print(f"INGEST: {ok_count}/{N_DOCS} ok  (avg {ingest_elapsed/max(N_DOCS,1):.2f}s/doc)")
    retrieve_ok = sum(1 for r in retrieve_results if r["status"] == 200)
    retrieve_p95 = sorted([r["latency_ms"] for r in retrieve_results])[int(len(retrieve_results) * 0.95)] if retrieve_results else 0
    print(f"RETRIEVE: {retrieve_ok}/{len(retrieve_results)} 200-status   p95 {retrieve_p95}ms")
    ask_ok = sum(1 for r in ask_results if r["status"] == 200)
    ask_p95 = sorted([r["latency_ms"] for r in ask_results])[int(len(ask_results) * 0.95)] if ask_results else 0
    print(f"ASK:      {ask_ok}/{len(ask_results)} 200-status   p95 {ask_p95}ms")

    # Citation accuracy: did the answer mention any expected substring?
    matched = 0
    for r in ask_results:
        if r["status"] != 200:
            continue
        ans = r["body"].get("data", {}).get("answer") or r["body"].get("answer", "")
        ans_lower = str(ans).lower()
        if any(e.lower() in ans_lower for e in r["expected"]):
            matched += 1
    print(f"GROUND-TRUTH MATCH: {matched}/{len(ask_results)} answers contained expected substring")

    out_path = Path("/tmp/rag-deep-test/results.json")
    out_path.write_text(json.dumps({
        "tenant_id": TENANT_ID,
        "ingest": {"ok": ok_count, "total": N_DOCS, "elapsed_s": ingest_elapsed,
                   "samples": ingest_results[:3]},
        "retrieve": {"ok": retrieve_ok, "total": len(retrieve_results),
                     "p95_ms": retrieve_p95, "results": retrieve_results},
        "ask": {"ok": ask_ok, "total": len(ask_results),
                "p95_ms": ask_p95, "ground_truth_match": matched,
                "results": ask_results},
    }, indent=2, default=str))
    print(f"\nFull results: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
