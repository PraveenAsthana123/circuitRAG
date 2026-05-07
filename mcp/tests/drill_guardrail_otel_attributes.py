# RESOURCES: none
"""
Drill: GuardrailChecker.check() emits OTel span attributes + a
matching structured log line, so operators can filter Jaeger by
guardrail.passed / guardrail.violations.count without parsing logs.

Closes the inference-svc OTel scorecard row "tool-decision and
answer-quality spans" — see
docs/architecture/otel-tool-level-coverage-scorecard-and-tracker.md.

Verification strategy: span attributes ride to OTLP and aren't
cheaply assertable from outside. The structured log line carries
the SAME data on the same code path (one source of truth: the
GuardrailResult). The drill verifies via the log; the span
attribute set is wired off the same path.

Negative-assertion §43-style:
 1. Successful check (passed=True) → log line carries
    passed=True, confidence>0, violations=- (sentinel for empty).
    NEGATIVE: a regression that emitted violations="" or "[]"
    (truthy in some greps) would silently let alerts fire.
 2. Failing check (PII + missing citation) → log line carries
    passed=False, violations contains both kinds. NEGATIVE: a
    regression that joined violations differently (newline,
    bracket-delimited) would break grep-based alerts that match
    "violations=...,...".
 3. confidence is bounded [0, 1] in the log line. NEGATIVE: a
    regression that doubled the formula or didn't clamp would
    show confidence=1.5 — operationally meaningless.
 4. found_labels + top_score sub-signals surface in the log.
    NEGATIVE: dropping these would require operators to derive
    answer quality from violations alone — less useful for
    triaging "low-quality but passed" cases.
 5. Calling check() multiple times produces ONE log line per
    call. NEGATIVE: double-emission would double-count alerting
    rates.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_guardrail_otel_attributes.py
"""
from __future__ import annotations

import logging
import re
import sys
from io import StringIO
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "services" / "inference-svc"))

from app.services.guardrails import GuardrailChecker  # type: ignore  # noqa: E402

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


# Capture the guardrail logger output so we can assert on the
# `guardrail_check_completed` line shape.
class _LogCapture:
    def __init__(self) -> None:
        self.buf = StringIO()
        self.handler = logging.StreamHandler(self.buf)
        self.handler.setLevel(logging.INFO)

    def __enter__(self) -> _LogCapture:
        logger = logging.getLogger("app.services.guardrails")
        logger.setLevel(logging.INFO)
        logger.addHandler(self.handler)
        return self

    def __exit__(self, *exc) -> None:
        logging.getLogger("app.services.guardrails").removeHandler(self.handler)

    def lines(self) -> list[str]:
        return [ln for ln in self.buf.getvalue().splitlines() if ln.strip()]

    def completed_lines(self) -> list[str]:
        return [
            ln for ln in self.lines()
            if "guardrail_check_completed" in ln
        ]


_LINE_RE = re.compile(
    r"guardrail_check_completed "
    r"passed=(?P<passed>\S+) "
    r"confidence=(?P<conf>\S+) "
    r"violations=(?P<viol>\S+) "
    r"found_labels=(?P<fl>\S+) "
    r"top_score=(?P<ts>\S+)"
)


def _parse(line: str) -> dict[str, str]:
    m = _LINE_RE.search(line)
    if not m:
        fail(f"log line doesn't match expected shape: {line!r}")
    return m.groupdict()


def main() -> None:
    g = GuardrailChecker()

    step("1. successful check → passed=True, violations=-")
    with _LogCapture() as cap:
        r = g.check(
            answer="The leave policy says 1.5 days/month [Source: hr.pdf, Page 3]",
            citation_map=[{"label": "[Source: hr.pdf, Page 3]"}],
            retrieval_scores=[0.92],
        )
    if not r.passed:
        fail(f"expected passed=True; got {r}")
    completed = cap.completed_lines()
    if len(completed) != 1:
        fail(f"expected 1 completed log line, got {len(completed)}")
    parts = _parse(completed[0])
    if parts["passed"] != "True":
        fail(f"log passed != True: {parts}")
    if parts["viol"] != "-":
        fail(
            f"empty-violations sentinel must be literal '-', got "
            f"{parts['viol']!r}. Empty list rendered as '' or '[]' "
            f"would break grep-based alerts that match presence."
        )
    if float(parts["conf"]) <= 0:
        fail(f"confidence not positive: {parts}")
    ok(f"passed=True confidence={parts['conf']} violations=-")

    step("2. failing check (PII + no citation) → both violations in log")
    with _LogCapture() as cap:
        r = g.check(
            answer="Contact alice@example.com for details",
            citation_map=[{"label": "[Source: hr.pdf, Page 3]"}],
            retrieval_scores=[0.40],
        )
    if r.passed:
        fail(f"expected passed=False; got {r}")
    completed = cap.completed_lines()
    if len(completed) != 1:
        fail(f"expected 1 completed log line, got {len(completed)}")
    parts = _parse(completed[0])
    if parts["passed"] != "False":
        fail(f"log passed != False: {parts}")
    if "no_citation" not in parts["viol"]:
        fail(f"no_citation missing from log: {parts['viol']!r}")
    if "pii_detected:email" not in parts["viol"]:
        fail(
            f"pii_detected:email missing from log: {parts['viol']!r}. "
            f"A regression that joined violations differently would "
            f"land here."
        )
    ok(f"passed=False violations={parts['viol']}")

    step("3. confidence bounded [0, 1]")
    with _LogCapture() as cap:
        # Even with very high retrieval score, confidence formula
        # is 0.4*1 + 0.6*min(score, 1.0) = max 1.0.
        r = g.check(
            answer="x" * 100 + " [Source: doc.pdf, Page 1]",
            citation_map=[{"label": "[Source: doc.pdf, Page 1]"}],
            retrieval_scores=[10.0],  # absurdly high
        )
    parts = _parse(cap.completed_lines()[0])
    conf = float(parts["conf"])
    if conf < 0 or conf > 1.0:
        fail(
            f"confidence out of [0, 1] bounds: {conf}. The formula "
            f"clamps via min(top_score, 1.0); a regression that "
            f"removed the clamp would surface scores > 1."
        )
    ok(f"confidence={conf} within [0, 1]")

    step("4. found_labels + top_score sub-signals surface")
    with _LogCapture() as cap:
        g.check(
            answer="See [Source: a.pdf, Page 1] and [Source: b.pdf, Page 2]",
            citation_map=[
                {"label": "[Source: a.pdf, Page 1]"},
                {"label": "[Source: b.pdf, Page 2]"},
            ],
            retrieval_scores=[0.7, 0.5],
        )
    parts = _parse(cap.completed_lines()[0])
    if int(parts["fl"]) != 2:
        fail(f"found_labels expected 2, got {parts['fl']}")
    if abs(float(parts["ts"]) - 0.7) > 0.01:
        fail(f"top_score expected ~0.7, got {parts['ts']}")
    ok(f"found_labels={parts['fl']} top_score={parts['ts']}")

    step("5. one log line per check call (no double-emission)")
    with _LogCapture() as cap:
        for _ in range(5):
            g.check(
                answer="ok [Source: doc.pdf, Page 1]",
                citation_map=[{"label": "[Source: doc.pdf, Page 1]"}],
                retrieval_scores=[0.5],
            )
    completed = cap.completed_lines()
    if len(completed) != 5:
        fail(
            f"expected 5 completed log lines for 5 calls, got "
            f"{len(completed)}. Double-emission would double "
            f"alert-rate counters."
        )
    ok("5 calls → 5 log lines (no double-emission)")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 GUARDRAIL-OTEL-ATTR STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    main()
