// Negative drills for Iter 25 (2026-05-17): PIIMasker broader
// coverage + credit-card Luhn validation.

import { describe, it, expect } from "vitest";
import { PIIMasker } from "./pii-masker";

const m = new PIIMasker();

describe("PIIMasker — coverage (P1)", () => {
  it("masks ASCII email (compat with original)", () => {
    expect(m.mask("contact me at alice@example.com")).toContain("[EMAIL]");
  });

  it("BACKDOOR CHECK: masks international TLDs (.io, .co.uk, etc)", () => {
    // Pre-fix's ASCII regex would still catch these (lowercase letters
    // OK), but the new \p{L} version covers IDN labels too. This
    // test asserts the original ASCII case is preserved.
    const out = m.mask("send to foo@bar.co.uk and baz@quux.io");
    expect(out).toBe("send to [EMAIL] and [EMAIL]");
  });

  it("masks US phone variants", () => {
    expect(m.mask("call 415-555-1234")).toBe("call [PHONE]");
    expect(m.mask("call (415) 555-1234")).toBe("call [PHONE]");
    expect(m.mask("call 4155551234")).toBe("call [PHONE]");
    expect(m.mask("call +1 415 555 1234")).toBe("call [PHONE]");
  });

  it("masks international phone with country code", () => {
    expect(m.mask("ring +44 20 7946 0958")).toBe("ring [PHONE]");
    expect(m.mask("ring +91-98765-43210")).toBe("ring [PHONE]");
  });

  it("masks a valid Luhn card number (Visa test card)", () => {
    expect(m.mask("card 4242 4242 4242 4242")).toBe("card [CARD]");
    expect(m.mask("card 4111111111111111")).toBe("card [CARD]");
  });

  it("BACKDOOR CHECK: does NOT mask invalid-Luhn 16-digit strings", () => {
    // 1234567890123456 fails Luhn — must NOT be masked as [CARD]
    // (otherwise tracking numbers, order IDs leak through).
    const out = m.mask("tracking 1234567890123456");
    expect(out).not.toContain("[CARD]");
    expect(out).toContain("1234567890123456");
  });

  it("masks SSN-like patterns", () => {
    expect(m.mask("SSN 123-45-6789")).toBe("SSN [SSN]");
  });

  it("masks IPv4", () => {
    expect(m.mask("server at 10.0.0.5 then 192.168.1.100"))
      .toBe("server at [IP] then [IP]");
  });

  it("masks IBAN", () => {
    expect(m.mask("IBAN GB82WEST12345698765432"))
      .toBe("IBAN [IBAN]");
  });

  it("masks multiple PII types in one string", () => {
    const input =
      "Contact alice@example.com or +1-555-1234567, card 4242424242424242";
    const out = m.mask(input);
    expect(out).toContain("[EMAIL]");
    expect(out).toContain("[PHONE]");
    expect(out).toContain("[CARD]");
    expect(out).not.toContain("alice@example.com");
    expect(out).not.toContain("4242424242424242");
  });

  it("does NOT mask plain text without PII (false-positive check)", () => {
    const benign = "The order ID is 12345 and the price was $19.99.";
    expect(m.mask(benign)).toBe(benign);
  });
});
