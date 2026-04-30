"""
Tests for documind_core.encryption — Fernet wrapper + sentinel prefix.

Covers:
- Cipher init: empty key, bad key, str key, bytes key
- encrypt/decrypt roundtrip across edge cases (empty, unicode, long)
- decrypt of legacy plaintext (no sentinel) is pass-through
- decrypt of corrupt/wrong-key token returns the failure marker
  (NEVER raises — callers must be able to surface the problem
  without a crash; this is the §38 governance contract)
- generate_key produces a valid, fresh Fernet key per call
"""

from __future__ import annotations

import pytest

from documind_core.encryption import Cipher, generate_key
from documind_core.exceptions import ValidationError

# ── fixtures ──────────────────────────────────────────────────


@pytest.fixture
def key() -> str:
    return generate_key()


@pytest.fixture
def cipher(key: str) -> Cipher:
    return Cipher(key)


# ── Cipher.__init__ ───────────────────────────────────────────


class TestCipherInit:
    def test_empty_string_key_rejected(self) -> None:
        with pytest.raises(ValidationError, match="non-empty encryption key"):
            Cipher("")

    def test_empty_bytes_key_rejected(self) -> None:
        with pytest.raises(ValidationError, match="non-empty encryption key"):
            Cipher(b"")

    def test_invalid_fernet_key_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Invalid Fernet key"):
            Cipher("not-a-real-fernet-key")

    def test_str_key_accepted(self, key: str) -> None:
        Cipher(key)  # no exception

    def test_bytes_key_accepted(self, key: str) -> None:
        Cipher(key.encode())  # no exception


# ── encrypt / decrypt roundtrip ───────────────────────────────


class TestRoundtrip:
    def test_simple_string(self, cipher: Cipher) -> None:
        plaintext = "secret-value-42"
        assert cipher.decrypt(cipher.encrypt(plaintext)) == plaintext

    def test_empty_string(self, cipher: Cipher) -> None:
        assert cipher.decrypt(cipher.encrypt("")) == ""

    def test_unicode(self, cipher: Cipher) -> None:
        plaintext = "ÜñïçødëΣ密码🔐"
        assert cipher.decrypt(cipher.encrypt(plaintext)) == plaintext

    def test_long_payload(self, cipher: Cipher) -> None:
        plaintext = "x" * 10_000
        assert cipher.decrypt(cipher.encrypt(plaintext)) == plaintext

    def test_output_has_sentinel_prefix(self, cipher: Cipher) -> None:
        assert cipher.encrypt("anything").startswith("__ENCRYPTED__:")

    def test_two_encryptions_of_same_input_differ(self, cipher: Cipher) -> None:
        # Fernet stamps a timestamp + IV — same plaintext => different
        # ciphertext. If this ever fails, Fernet semantics changed and
        # the threat model needs review.
        a = cipher.encrypt("same")
        b = cipher.encrypt("same")
        assert a != b
        assert cipher.decrypt(a) == cipher.decrypt(b) == "same"


# ── decrypt edge cases ────────────────────────────────────────


class TestDecryptEdgeCases:
    def test_legacy_plaintext_passes_through(self, cipher: Cipher) -> None:
        # Pre-migration rows have no sentinel — decrypt must NOT touch them.
        assert cipher.decrypt("legacy-cleartext") == "legacy-cleartext"

    def test_empty_string_passes_through(self, cipher: Cipher) -> None:
        assert cipher.decrypt("") == ""

    def test_corrupt_sentinel_payload_returns_marker(self, cipher: Cipher) -> None:
        # The §38 contract: corrupt ciphertext NEVER crashes the caller.
        # It returns a visible marker so admins can spot the bad row.
        assert cipher.decrypt("__ENCRYPTED__:not-a-real-token") == "***DECRYPTION_FAILED***"

    def test_wrong_key_returns_marker(self) -> None:
        # Two ciphers with different keys: anything encrypted by A
        # must NOT decrypt under B — and must NOT raise either.
        cipher_a = Cipher(generate_key())
        cipher_b = Cipher(generate_key())
        encrypted = cipher_a.encrypt("a-secret")
        assert cipher_b.decrypt(encrypted) == "***DECRYPTION_FAILED***"

    def test_partial_sentinel_treated_as_plaintext(self, cipher: Cipher) -> None:
        # "__ENCRYPTED" without the trailing ":" is NOT the sentinel.
        # Must pass through untouched (legacy migration safety).
        assert cipher.decrypt("__ENCRYPTED") == "__ENCRYPTED"


# ── generate_key ──────────────────────────────────────────────


class TestGenerateKey:
    def test_returns_string(self) -> None:
        assert isinstance(generate_key(), str)

    def test_key_is_valid_for_cipher(self) -> None:
        # Generated key must round-trip through Cipher without issues.
        cipher = Cipher(generate_key())
        assert cipher.decrypt(cipher.encrypt("ok")) == "ok"

    def test_two_calls_return_different_keys(self) -> None:
        # Cryptographic-grade randomness; collision probability is
        # negligible. If this ever fails twice in a row, the RNG broke.
        assert generate_key() != generate_key()

    def test_key_length_is_fernet_standard(self) -> None:
        # Fernet keys are 32-byte url-safe base64 (44 chars including padding).
        assert len(generate_key()) == 44
