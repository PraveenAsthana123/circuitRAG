"""Prior-fix retrieval — Tier 2 #2.6.

Per CLAUDE.md §50 + §55. Reads `.loop/hitl_scores.jsonl` (HITL
preference dataset; the verdict='approve' and verdict='edit' rows
are operator-labeled positive examples). Builds a lightweight BM25
index over the issue messages + rule codes. AUTHOR's prompt gets
the top-N most-similar past accepted fixes as few-shot examples.

WHY BM25, NOT VECTOR EMBEDDINGS
================================

  - Zero new dependency (pure-Python tokenization + BM25)
  - Code-fix queries are short + keyword-heavy (rule codes match
    exactly; rule messages have stable phrasing) — BM25 wins on
    keyword match without an embedding model in the loop
  - Embeddings can replace BM25 in v2 once we have ≥1000 preference
    rows; today we have <100 expected and BM25 is sufficient

ZERO-DATA BEHAVIOR
==================

When `.loop/hitl_scores.jsonl` doesn't exist OR has zero
verdict='approve' / verdict='edit' rows, query_similar_fixes()
returns []. AUTHOR's prompt still works without RAG context — the
prior-fix section is OMITTED rather than empty-bloated.

SECURITY GATE
=============

Per §50.5.3 + §54: rows with verdict='reject' are NEVER returned
as positive examples. Rejected outputs are anti-examples, not
patterns to repeat.

USAGE
=====

  from prior_fix_rag import query_similar_fixes
  similar = query_similar_fixes(
      query=issue['message'],
      rule_code=issue['code'],
      limit=3,
  )
  # → list[dict] with keys: chosen_text, summary, score
  # → empty list when no preference data yet

Drilled by mcp/tests/drill_prior_fix_rag.py.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

REPO = Path(__file__).resolve().parent.parent
HITL_LOG = REPO / ".loop" / "hitl_scores.jsonl"


# Verdicts that count as positive examples (operator approves OR
# operator preferred their own edit; rejected = anti-example, skipped).
POSITIVE_VERDICTS: tuple[str, ...] = ("approve", "edit")

# BM25 hyperparameters (industry standard).
BM25_K1: float = 1.5
BM25_B: float = 0.75


@dataclass(frozen=True)
class FixExample:
    """One operator-approved fix from HITL log, ready for few-shot."""

    issue_id: str
    rule_code: str
    chosen_text: str       # the operator's preferred output (or model's accepted)
    note: str              # operator's reason note
    score: float           # BM25 relevance to current query

    model_config: ClassVar[dict] = {"frozen": True}


def _tokenize(text: str) -> list[str]:
    """Lowercase + alpha-num tokens. Code-fix queries have stable
    phrasing; this is sufficient without stemming."""
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _load_positive_rows() -> list[dict]:
    """Load HITL rows where verdict is positive AND chosen_text exists."""
    if not HITL_LOG.exists():
        return []
    out: list[dict] = []
    for line in HITL_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("verdict") not in POSITIVE_VERDICTS:
            continue
        # `chosen_text` may be None for verdict='approve' (operator
        # approved without editing); fall back to the row's note OR
        # rule_code-summary so the few-shot still has substance.
        if row.get("chosen_text") is None and not row.get("note"):
            continue
        out.append(row)
    return out


def _bm25_score(query_tokens: list[str], doc_tokens: list[str], avgdl: float, df: Counter, n_docs: int) -> float:
    """BM25 relevance score for one document given the query."""
    if not doc_tokens:
        return 0.0
    doc_tf = Counter(doc_tokens)
    score = 0.0
    dl = len(doc_tokens)
    for term in query_tokens:
        df_t = df.get(term, 0)
        if df_t == 0:
            continue
        idf = math.log(1 + (n_docs - df_t + 0.5) / (df_t + 0.5))
        tf = doc_tf[term]
        norm = tf * (BM25_K1 + 1) / (tf + BM25_K1 * (1 - BM25_B + BM25_B * dl / max(avgdl, 1)))
        score += idf * norm
    return score


def _build_corpus(rows: list[dict]) -> tuple[list[list[str]], Counter, float]:
    """Tokenize each row into a doc; compute df + avgdl for BM25."""
    docs = []
    df: Counter = Counter()
    total_len = 0
    for row in rows:
        # Doc text: rule code + issue message + chosen text + note
        # Rule code repeated 3x as a soft boost (exact-match weight).
        text = " ".join([
            (row.get("rule_code") or "") * 3,
            row.get("issue_id") or "",
            row.get("chosen_text") or "",
            row.get("note") or "",
        ])
        tokens = _tokenize(text)
        docs.append(tokens)
        for t in set(tokens):
            df[t] += 1
        total_len += len(tokens)
    avgdl = total_len / max(len(docs), 1)
    return docs, df, avgdl


def query_similar_fixes(
    *,
    query: str,
    rule_code: str | None = None,
    limit: int = 3,
    min_score: float = 0.5,
) -> list[FixExample]:
    """Return top-N most-similar prior accepted fixes.

    Returns [] when:
      - HITL log doesn't exist
      - No positive (verdict='approve' or 'edit') rows present
      - No row matches above min_score
    """
    rows = _load_positive_rows()
    if not rows:
        return []
    docs, df, avgdl = _build_corpus(rows)
    n = len(rows)
    query_text = (query or "")
    if rule_code:
        # Rule code is a strong signal; repeat 3× same as docs.
        query_text += f" {rule_code} {rule_code} {rule_code}"
    query_tokens = _tokenize(query_text)
    if not query_tokens:
        return []

    scored: list[tuple[float, dict]] = []
    for row, doc_tokens in zip(rows, docs, strict=True):
        score = _bm25_score(query_tokens, doc_tokens, avgdl, df, n)
        if score >= min_score:
            scored.append((score, row))
    scored.sort(key=lambda x: -x[0])
    out = []
    for score, row in scored[:limit]:
        out.append(FixExample(
            issue_id=row.get("issue_id", ""),
            rule_code=row.get("rule_code") or "",
            chosen_text=row.get("chosen_text") or row.get("note") or "",
            note=row.get("note") or "",
            score=round(score, 4),
        ))
    return out


def render_few_shot(examples: list[FixExample]) -> str:
    """Render top examples into a prompt-embeddable few-shot section.

    Returns "" when the example list is empty (no bloat in prompt).
    """
    if not examples:
        return ""
    lines = ["", "<prior_fixes>",
             "Past operator-accepted fixes for similar issues:"]
    for i, ex in enumerate(examples, 1):
        lines.append(f"  {i}. [rule={ex.rule_code} score={ex.score}] {ex.note[:120]}")
        if ex.chosen_text:
            preview = ex.chosen_text[:300].replace("\n", " ⏎ ")
            lines.append(f"     accepted: {preview}")
    lines.append("</prior_fixes>")
    return "\n".join(lines) + "\n"


def main() -> int:
    """CLI: query the index for ad-hoc inspection."""
    import argparse
    parser = argparse.ArgumentParser(prog="prior_fix_rag.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_q = sub.add_parser("query", help="search the prior-fix index")
    p_q.add_argument("--query", required=True)
    p_q.add_argument("--rule-code", default=None)
    p_q.add_argument("--limit", type=int, default=3)
    p_q.set_defaults(func=lambda a: cmd_query(a))
    p_s = sub.add_parser("stats", help="report index size + verdict distribution")
    p_s.set_defaults(func=lambda a: cmd_stats(a))
    args = parser.parse_args()
    return args.func(args)


def cmd_query(args) -> int:  # noqa: ANN001
    examples = query_similar_fixes(
        query=args.query, rule_code=args.rule_code, limit=args.limit,
    )
    if not examples:
        print("(no similar fixes found in HITL log)")
        return 0
    for ex in examples:
        print(f"  rule={ex.rule_code} score={ex.score}  issue={ex.issue_id}")
        print(f"    note: {ex.note[:80]}")
    return 0


def cmd_stats(_args) -> int:  # noqa: ANN001
    if not HITL_LOG.exists():
        print(f"(HITL log not found: {HITL_LOG.relative_to(REPO)})")
        return 0
    by_verdict: Counter = Counter()
    total = 0
    for line in HITL_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        total += 1
        by_verdict[row.get("verdict", "?")] += 1
    print(f"HITL log: {total} rows")
    for v, n in by_verdict.most_common():
        marker = " ✓" if v in POSITIVE_VERDICTS else ""
        print(f"  {v:<10} {n}{marker}")
    print(f"\nIndexable (positive-verdict + chosen_text/note present): {len(_load_positive_rows())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
