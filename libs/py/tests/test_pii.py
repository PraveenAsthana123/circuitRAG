"""
Tests for documind_core.pii — multi-pattern PII scanner.

Covers:
- Each default pattern detects its category
- Email + phone + SSN + IPv4 + AWS key + RSA private key + API key
- Credit-card patterns: real Luhn-valid card detected; random
  16-digit string filtered out (Luhn negative)
- redact() replaces with mask, preserves other text
- redact_with_labels() formats with category
- Empty input, no-PII input
- has_pii() short-circuits
- Custom patterns
- Negative: validate_credit_cards=False bypasses the Luhn check
- luhn_check edge cases (empty, non-digit, too short)
"""

from __future__ import annotations

import pytest

from documind_core.pii import (
    DEFAULT_PATTERNS,
    PIIScanner,
    luhn_check,
)


class TestLuhn:
    def test_valid_visa(self) -> None:
        # Real-format Visa number passing Luhn (test number from
        # Luhn standard).
        assert luhn_check("4532015112830366")

    def test_invalid_random_digits(self) -> None:
        assert not luhn_check("1234567890123456")

    def test_too_short(self) -> None:
        assert not luhn_check("123")

    def test_empty(self) -> None:
        assert not luhn_check("")

    def test_strips_non_digits(self) -> None:
        # Spaces / dashes are common in card formats.
        assert luhn_check("4532-0151-1283-0366")
        assert luhn_check("4532 0151 1283 0366")

    def test_non_digit_only_returns_false(self) -> None:
        assert not luhn_check("abcd-efgh")


class TestEmailPattern:
    def test_simple_email(self) -> None:
        scanner = PIIScanner()
        matches = scanner.scan("contact us at jane@example.com today")
        assert len(matches) == 1
        assert matches[0].label == "email"
        assert matches[0].text == "jane@example.com"

    def test_subaddress_form(self) -> None:
        matches = PIIScanner().scan("user+filter@example.co.uk")
        assert any(m.label == "email" for m in matches)


class TestSSNPattern:
    def test_valid_ssn(self) -> None:
        matches = PIIScanner().scan("SSN: 123-45-6789 on file")
        assert any(m.label == "ssn_us" for m in matches)

    def test_rejects_invalid_area_codes(self) -> None:
        # Per SSA: area 000 and 666 are never assigned.
        matches = PIIScanner().scan("000-12-3456 666-12-3456")
        assert all(m.label != "ssn_us" for m in matches)


class TestPhonePattern:
    def test_us_formats_detected(self) -> None:
        scanner = PIIScanner()
        for phone in ("(555) 123-4567", "555-123-4567", "+1 555 123 4567"):
            matches = scanner.scan(f"call {phone}")
            assert any(m.label == "phone_us" for m in matches), phone


class TestCreditCardPattern:
    def test_luhn_valid_card_detected(self) -> None:
        # Real Visa test number, passes Luhn.
        matches = PIIScanner().scan("Card: 4532015112830366")
        assert any(m.label == "credit_card" for m in matches)

    def test_luhn_invalid_filtered_out(self) -> None:
        # Looks like a card but fails Luhn — must NOT flag.
        # This is the false-positive-reduction guarantee.
        matches = PIIScanner().scan("Order: 4111111111111112")  # last digit broken
        assert all(m.label != "credit_card" for m in matches)

    def test_disable_luhn_check(self) -> None:
        # Operators may disable Luhn for a higher-recall posture
        # (banking-grade PII detection over-flags by design).
        scanner = PIIScanner(validate_credit_cards=False)
        matches = scanner.scan("4111111111111112")
        assert any(m.label == "credit_card" for m in matches)


class TestSecretsPatterns:
    def test_aws_access_key(self) -> None:
        matches = PIIScanner().scan("AKIAIOSFODNN7EXAMPLE in env")
        assert any(m.label == "aws_access_key" for m in matches)

    def test_rsa_private_key_header(self) -> None:
        matches = PIIScanner().scan("-----BEGIN RSA PRIVATE KEY-----\n...")
        assert any(m.label == "rsa_private_key" for m in matches)

    def test_api_key_token(self) -> None:
        matches = PIIScanner().scan("api_key=sk_live_abcdefghijklmnopqrstuv")
        assert any(m.label == "api_key_token" for m in matches)


class TestIPv4:
    def test_ipv4_detected(self) -> None:
        matches = PIIScanner().scan("server at 192.168.1.100 is down")
        assert any(m.label == "ipv4" for m in matches)


class TestRedact:
    def test_redact_replaces_pii(self) -> None:
        scanner = PIIScanner()
        out = scanner.redact("Email: jane@example.com, phone: 555-123-4567.")
        assert "jane@example.com" not in out
        assert "555-123-4567" not in out
        assert "[REDACTED]" in out

    def test_redact_preserves_non_pii(self) -> None:
        scanner = PIIScanner()
        out = scanner.redact("Hello jane@example.com world")
        assert out.startswith("Hello ")
        assert out.endswith(" world")

    def test_redact_no_pii_returns_unchanged(self) -> None:
        scanner = PIIScanner()
        text = "no sensitive data here"
        assert scanner.redact(text) is text or scanner.redact(text) == text

    def test_redact_with_labels(self) -> None:
        scanner = PIIScanner()
        out = scanner.redact_with_labels("ping 192.168.1.1 and jane@example.com")
        assert "[REDACTED:ipv4]" in out
        assert "[REDACTED:email]" in out


class TestHelpers:
    def test_has_pii_short_circuits(self) -> None:
        # has_pii returns True on first match — should not depend
        # on a full scan.
        assert PIIScanner().has_pii("contact jane@example.com")
        assert not PIIScanner().has_pii("clean text")

    def test_empty_input(self) -> None:
        scanner = PIIScanner()
        assert scanner.scan("") == []
        assert scanner.redact("") == ""
        assert not scanner.has_pii("")

    def test_default_patterns_locked(self) -> None:
        # Regression-lock the default category set. If a future
        # change drops a category by mistake, this test catches it.
        labels = {label for label, _p in DEFAULT_PATTERNS}
        required = {
            "email",
            "ssn_us",
            "phone_us",
            "credit_card",
            "ipv4",
            "aws_access_key",
            "rsa_private_key",
            "api_key_token",
        }
        assert required.issubset(labels)


class TestCustomPatterns:
    def test_custom_pattern_detected(self) -> None:
        # Tenants in regulated tiers add their own patterns
        # (e.g. internal employee IDs).
        scanner = PIIScanner(patterns=[("emp_id", r"\bEMP-[0-9]{6}\b")])
        matches = scanner.scan("EMP-123456 was active")
        assert len(matches) == 1
        assert matches[0].label == "emp_id"

    def test_pii_match_is_frozen(self) -> None:
        scanner = PIIScanner()
        m = scanner.scan("jane@example.com")[0]
        with pytest.raises((AttributeError, Exception)):
            m.label = "x"  # type: ignore[misc]


class TestPIIMatchSpan:
    def test_offsets_correct(self) -> None:
        # The start/end offsets must point to the PII span — used
        # by callers building citation maps + diff views.
        text = "ping 192.168.1.100 today"
        matches = PIIScanner().scan(text)
        ipv4 = next(m for m in matches if m.label == "ipv4")
        assert text[ipv4.start : ipv4.end] == "192.168.1.100"
        assert len(ipv4) == len("192.168.1.100")
