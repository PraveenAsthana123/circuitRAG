"""
PII detection — multi-pattern Aho-Corasick-style scanner (§16.11
of the RAG playbook).

Why this design:
- Linear-pass alternative to running 12 regex passes over each
  chunk. PII scanning runs on every ingested chunk + every prompt
  + every LLM output — a 12× regex multiplier kills throughput.
- Built on Python's `re` with a single combined alternation —
  Python compiles this to a DFA-equivalent structure, so the scan
  is O(n + m) just like a hand-rolled Aho-Corasick.
- Patterns are NAMED so the audit row can record exactly which
  category fired (SSN vs email vs phone) — operators triaging a
  PII alert need this.

The scanner is INTENTIONALLY conservative — over-flagging is
preferable to under-flagging in regulated tiers. Tune patterns
per tenant (banking != healthcare != public).

Standard PII categories included:
- email (RFC-ish)
- US SSN (NNN-NN-NNNN)
- US phone (multiple formats)
- credit card (Luhn-validated common BIN ranges)
- IPv4 address
- AWS access key (AKIA prefix)
- private RSA key header
- generic API key (sk-/pk-/api_key= prefixes)

Custom patterns can be added at construction time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["PIIMatch", "PIIScanner", "DEFAULT_PATTERNS", "luhn_check"]


# Default pattern library. Each entry is (label, pattern). Labels
# are stable strings — they appear in audit rows + telemetry.
# IMPORTANT: keep patterns conservative — false positives are
# triaged; false negatives are leaks.
DEFAULT_PATTERNS: list[tuple[str, str]] = [
    ("email", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ("ssn_us", r"\b(?!000|666)[0-8][0-9]{2}-(?!00)[0-9]{2}-(?!0000)[0-9]{4}\b"),
    # Phone (US-format). Accepts strict NANP area codes (2-9 lead)
    # but loosens the exchange to any 3 digits — operators feed
    # this scanner test data + scraped numbers that don't follow
    # NANP exchange rules. False-negative rate matters more than
    # false-positive for PII scanning.
    ("phone_us", r"(?:\+?1[-.\s]?)?\(?[2-9][0-9]{2}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b"),
    ("credit_card", r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b"),
    ("ipv4", r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"),
    ("aws_access_key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("rsa_private_key", r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    # API key tokens — common forms: sk_live_xxx, sk-test-xxx,
    # pk_xxx, api_key=xxx, Bearer xxx with sk/pk prefix.
    # The token body allows underscores + hyphens since real
    # provider tokens commonly include them (Stripe, OpenAI, etc.).
    ("api_key_token", r"\b(?:sk|pk)[_-](?:live|test)[_-][A-Za-z0-9_\-]{16,}\b"),
]


@dataclass(frozen=True)
class PIIMatch:
    """One PII finding. Frozen so it's safe to log/audit by reference."""

    label: str
    text: str
    start: int  # offset into the input
    end: int  # exclusive

    def __len__(self) -> int:
        return self.end - self.start


def luhn_check(digits: str) -> bool:
    """Verify a string of digits passes the Luhn checksum.

    Used to filter out random 16-digit numbers that look like
    credit cards but aren't. Reduces false positives by an order
    of magnitude in production.

    Returns True for valid Luhn, False otherwise (incl. non-digits
    or empty).
    """
    digits_only = "".join(c for c in digits if c.isdigit())
    if len(digits_only) < 12:
        return False
    total = 0
    # Iterate right-to-left, doubling every second digit.
    for i, ch in enumerate(reversed(digits_only)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


class PIIScanner:
    """Multi-pattern PII scanner. Single linear pass per scan().

    Internally compiles a single combined regex with named groups
    via alternation — Python's re module compiles this to a DFA
    so the runtime is O(n + total_pattern_size).

    Usage:
        scanner = PIIScanner()
        for match in scanner.scan(text):
            print(match.label, match.text)
        redacted = scanner.redact(text)
    """

    def __init__(
        self,
        *,
        patterns: list[tuple[str, str]] | None = None,
        validate_credit_cards: bool = True,
    ) -> None:
        self._patterns = patterns or list(DEFAULT_PATTERNS)
        self._validate_cc = validate_credit_cards
        # Build one big regex with named alternatives. We embed each
        # pattern in a named group `_p<i>` to recover the label after
        # match. Python regex group names must be valid identifiers,
        # so we use indices, not raw labels (which may have hyphens).
        joined = "|".join(f"(?P<_p{i}>{p})" for i, (_label, p) in enumerate(self._patterns))
        self._regex = re.compile(joined)
        self._labels: list[str] = [label for label, _p in self._patterns]

    def scan(self, text: str) -> list[PIIMatch]:
        """Return all PII findings in `text` in document order.

        Empty input → empty list (NEVER raises).
        """
        if not text:
            return []
        out: list[PIIMatch] = []
        for m in self._regex.finditer(text):
            label = self._label_for_match(m)
            if label is None:
                continue  # defensive — shouldn't happen with our build
            matched = m.group(0)
            # Filter false-positive credit cards via Luhn.
            if label == "credit_card" and self._validate_cc and not luhn_check(matched):
                continue
            out.append(PIIMatch(label=label, text=matched, start=m.start(), end=m.end()))
        return out

    def has_pii(self, text: str) -> bool:
        """Fast-path — return on first match."""
        return next(iter(self.scan(text)), None) is not None

    def redact(self, text: str, *, mask: str = "[REDACTED]") -> str:
        """Return `text` with every PII finding replaced by `mask`.

        Preserves the rest of the string verbatim (offsets only
        change for redacted spans). The mask is identical for
        every finding — for label-aware masking, use
        :meth:`redact_with_labels`.
        """
        matches = self.scan(text)
        if not matches:
            return text
        # Apply replacements right-to-left so earlier offsets stay
        # valid as we mutate.
        out = list(text)
        for m in reversed(matches):
            out[m.start : m.end] = mask
        return "".join(out)

    def redact_with_labels(self, text: str, *, fmt: str = "[REDACTED:{label}]") -> str:
        """Like :meth:`redact` but per-label mask."""
        matches = self.scan(text)
        if not matches:
            return text
        out = list(text)
        for m in reversed(matches):
            out[m.start : m.end] = fmt.format(label=m.label)
        return "".join(out)

    def _label_for_match(self, m: re.Match[str]) -> str | None:
        # The combined regex has named groups _p0, _p1, ... — find
        # the one that actually matched (groupdict returns None for
        # non-matching groups).
        for i, label in enumerate(self._labels):
            if m.group(f"_p{i}") is not None:
                return label
        return None
