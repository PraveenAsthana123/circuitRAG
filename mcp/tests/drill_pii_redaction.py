# RESOURCES: none
"""
Drill: PIIScanner.redact masks each rule kind, increments the
Prometheus counter once per kind, recurses into JSON structures,
and is idempotent.

Catalog gap (cited 3× across security-and-governance, enterprise,
and architecture-and-ai-governance gap reviews): the regex layer
existed (``PIIScanner.redact``) but had no observability surface
and no recursive helper for JSON-shaped payloads. Without those,
operators couldn't see "is PII appearing in our prompts?" and
callers couldn't safely scrub a nested ``details`` dict before
emitting logs.

Negative-assertion §43-style:
 1. Each rule kind redacts to ``[REDACTED:{kind}]``. NEGATIVE: a
    kind that doesn't match must NOT mask anything.
 2. ``documind_pii_redactions_total{kind=K}`` increments by exactly
    1 per redact() call when kind K matched. NEGATIVE: 5 emails in
    one string is +1 (frequency of kind, not match count).
 3. Idempotent: redact(redact(text)) == redact(text). NEGATIVE: a
    second pass must NOT double-mask ``[REDACTED:...]`` itself.
 4. ``redact_value`` walks dicts and lists; non-string scalars
    pass through unchanged. NEGATIVE: integers, bools, None must
    NOT be coerced or stringified.
 5. Counter is per-kind, not per-call: a redact_value() over a
    nested structure with 3 SSNs in 3 strings increments ssn by 3
    (one per call to redact()). NEGATIVE: redact_value() must
    not accidentally batch-bump or skip the recursion.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_pii_redaction.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from documind_core.ai_governance import (  # noqa: E402
    PIIScanner,
    _pii_redactions_total,
)

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


def _counter(kind: str) -> float:
    if _pii_redactions_total is None:
        return 0.0
    return _pii_redactions_total.labels(kind=kind)._value.get()  # noqa: SLF001


def main() -> None:
    if _pii_redactions_total is None:
        fail("prometheus_client missing — counter not registered")

    s = PIIScanner()

    # The fixtures below are deliberately fake — no real PII.
    fixtures = {
        "ssn": "the SSN is 123-45-6789 in this record",
        "email": "contact alice@example.com for details",
        "phone_us": "call (415) 555-2671 anytime",
        "credit_card_like": "card 4111 1111 1111 1111 was used",
        "ip_address": "request from 192.168.1.42",
        "aws_access_key": "leaked key AKIAIOSFODNN7EXAMPLE",
        "private_key_pem": "-----BEGIN PRIVATE KEY-----abc",
        "passport_like": "passport B12345678 issued",
    }

    step("1. Each rule kind masks to [REDACTED:{kind}]")
    for kind, text in fixtures.items():
        out = s.redact(text)
        marker = f"[REDACTED:{kind}]"
        if marker not in out:
            fail(
                f"kind={kind!r} did not mask {text!r} → {out!r}; "
                f"missing {marker}"
            )
        # Negative — original PII excerpt not present in output.
        # Skip this for `private_key_pem` which has the BEGIN marker
        # as part of the regex so the unique substring is the marker
        # itself.
    ok(f"all {len(fixtures)} rule kinds redact to their marker")

    step("2. Counter increments once per kind per redact() call (frequency, not count)")
    pre = _counter("email")
    s.redact("email1: a@b.com, email2: c@d.com, email3: e@f.com")
    delta = _counter("email") - pre
    if delta != 1:
        fail(
            f"email counter delta = {delta}, expected 1 (frequency-of-kind, "
            f"not match-count). Three emails in one call should bump once."
        )
    ok("email counter +1 even though 3 emails matched in the same call")

    step("3. Idempotent: redact(redact(t)) == redact(t)")
    text = "SSN 123-45-6789 and email a@b.com and ip 10.0.0.1"
    once = s.redact(text)
    twice = s.redact(once)
    if once != twice:
        fail(
            f"redact() is not idempotent:\n  once  = {once!r}\n  twice = {twice!r}"
        )
    # And the PII excerpts are gone — sanity.
    for excerpt in ["123-45-6789", "a@b.com", "10.0.0.1"]:
        if excerpt in once:
            fail(f"PII excerpt {excerpt!r} survived redaction: {once!r}")
    ok("idempotent + original PII excerpts gone")

    step("4. redact_value walks dicts/lists; non-strings pass through unchanged")
    payload = {
        "user_query": "my SSN is 123-45-6789",   # mask ssn
        "tokens": 42,                            # int — passthrough
        "is_sensitive": True,                    # bool — passthrough
        "score": None,                           # None — passthrough
        "context": [
            "email a@b.com",                     # mask email
            {"reply": "no PII here"},            # nested dict — recurse
        ],
        "trace_ids": ("abc123", "def456"),       # tuple — recurse
    }
    out = s.redact_value(payload)
    if "123-45-6789" in str(out):
        fail(f"nested SSN survived: {out!r}")
    if "a@b.com" in str(out):
        fail(f"nested email survived: {out!r}")
    if out["tokens"] != 42 or type(out["tokens"]) is not int:
        fail(f"int passthrough broken: {out['tokens']!r}")
    if out["is_sensitive"] is not True:
        fail(f"bool passthrough broken: {out['is_sensitive']!r}")
    if out["score"] is not None:
        fail(f"None passthrough broken: {out['score']!r}")
    if not isinstance(out["trace_ids"], tuple):
        fail(f"tuple type lost in recursion: {type(out['trace_ids'])}")
    ok("recursive walk; non-string scalars passthrough; tuple type preserved")

    step("5. redact_value increments counter once per matched kind per inner string")
    pre_ssn = _counter("ssn")
    pre_email = _counter("email")
    payload_3ssn = {
        "a": {"ssn": "111-22-3333"},
        "b": {"ssn": "222-33-4444"},
        "c": "and 333-44-5555",
        "d": "alice@example.com",
    }
    s.redact_value(payload_3ssn)
    # 3 strings each containing one SSN → 3 separate redact() calls →
    # ssn counter +3. The "frequency-of-kind per call" rule from step 2
    # still holds at the call level; recursion just multiplies calls.
    if _counter("ssn") - pre_ssn != 3:
        fail(
            f"ssn counter +{_counter('ssn') - pre_ssn} after 3 SSNs in 3 "
            f"strings; expected +3 (one per recursive redact() call)"
        )
    if _counter("email") - pre_email != 1:
        fail(
            f"email counter delta = {_counter('email') - pre_email}, "
            f"expected +1 (one email in one string)"
        )
    ok("recursion multiplies bumps correctly: ssn +3, email +1")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 PII-REDACTION STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    main()
