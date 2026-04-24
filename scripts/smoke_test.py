#!/usr/bin/env python3
"""
End-to-end smoke test.

Exercises: ingestion → retrieval → inference through the running services.
Assumes all services are up (make data-up + make run-*).

Usage::

    python scripts/smoke_test.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from uuid import UUID

import httpx

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
INGESTION_URL = os.getenv("DOCUMIND_INGESTION_URL", "http://localhost:8082")
INFERENCE_URL = os.getenv("DOCUMIND_INFERENCE_URL", "http://localhost:8084")
RETRIEVAL_URL = os.getenv("DOCUMIND_RETRIEVAL_URL", "http://localhost:8083")


async def main() -> int:
    sample = Path(__file__).resolve().parent.parent / "data" / "samples" / "documind-overview.txt"
    if not sample.exists():
        print(f"Missing sample doc: {sample}. Run scripts/seed_demo.py first.")
        return 1

    async with httpx.AsyncClient(timeout=120) as client:
        # 1. Health checks
        for name, url in [
            ("ingestion", f"{INGESTION_URL}/health"),
            ("retrieval", f"{RETRIEVAL_URL}/health"),
            ("inference", f"{INFERENCE_URL}/health"),
        ]:
            try:
                r = await client.get(url)
                r.raise_for_status()
                print(f"[ok] {name} healthy")
            except Exception as exc:
                print(f"[FAIL] {name} unreachable at {url}: {exc}")
                return 2

        # 2. Upload
        print("\n[upload] POST /api/v1/documents/upload (sync mode)")
        with sample.open("rb") as fh:
            resp = await client.post(
                f"{INGESTION_URL}/api/v1/documents/upload",
                files={"file": (sample.name, fh, "text/plain")},
                data={"sync": "true"},
                headers={"X-Tenant-ID": str(TENANT_ID)},
            )
        resp.raise_for_status()
        doc = resp.json()
        print(f"       → doc_id={doc['document_id']} state={doc['state']}")

        # 3. Ask
        print("\n[ask] POST /api/v1/ask")
        r = await client.post(
            f"{INFERENCE_URL}/api/v1/ask?debug=true",
            json={"query": "What is DocuMind and what stack does it use?", "top_k": 3, "strategy": "hybrid"},
            headers={"X-Tenant-ID": str(TENANT_ID)},
        )
        r.raise_for_status()
        ans = r.json()
        print(f"       confidence={ans['confidence']} tokens={ans['tokens_prompt']}/{ans['tokens_completion']}")
        print(f"       answer: {ans['answer'][:240]}...")
        print(f"       citations: {len(ans['citations'])}")

    print("\n[done] smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
