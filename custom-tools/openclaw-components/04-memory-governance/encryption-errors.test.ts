// Negative drills for Iter 93 (2026-05-18): Encryption error
// CONTRACT — locks that EncryptionKeyError + DecryptionFailedError
// preserve instanceof/name semantics. The audit + governance
// layers may catch these by class; broken instanceof chains via
// bundler tree-shaking or subclass renames would silently misroute.

import { describe, it, expect } from "vitest";
import {
  EncryptionKeyError,
  DecryptionFailedError,
  ValueEncryptor,
} from "./encryption";
import { randomBytes } from "crypto";

const KEY = randomBytes(32);

describe("Iter 93 — Encryption error contracts (P2)", () => {
  it("BACKDOOR: EncryptionKeyError instanceof works on direct construction", () => {
    const e = new EncryptionKeyError("bad");
    expect(e).toBeInstanceOf(EncryptionKeyError);
    expect(e).toBeInstanceOf(Error);
    expect(e.name).toBe("EncryptionKeyError");
    expect(e.message).toBe("bad");
  });

  it("BACKDOOR: DecryptionFailedError instanceof works on direct construction", () => {
    const e = new DecryptionFailedError("ciphertext bad");
    expect(e).toBeInstanceOf(DecryptionFailedError);
    expect(e).toBeInstanceOf(Error);
    expect(e.name).toBe("DecryptionFailedError");
    expect(e.message).toBe("ciphertext bad");
  });

  it("BACKDOOR: ValueEncryptor constructor throws EncryptionKeyError on wrong-length key", () => {
    try {
      new ValueEncryptor(Buffer.alloc(16));  // 16, not 32
      throw new Error("expected throw");
    } catch (e) {
      expect(e).toBeInstanceOf(EncryptionKeyError);
      expect((e as Error).message).toMatch(/32 bytes/);
    }
  });

  it("BACKDOOR: decrypt of tampered ciphertext throws DecryptionFailedError", () => {
    const enc = new ValueEncryptor(KEY);
    const ciphertext = enc.encrypt("hello");
    // Tamper: flip the last hex character.
    const tampered = ciphertext.slice(0, -1) +
                     (ciphertext.slice(-1) === "a" ? "b" : "a");
    try {
      enc.decrypt(tampered);
      throw new Error("expected throw");
    } catch (e) {
      expect(e).toBeInstanceOf(DecryptionFailedError);
    }
  });

  it("BACKDOOR: decrypt with WRONG key throws DecryptionFailedError (not silent garbage)", () => {
    const a = new ValueEncryptor(KEY);
    const b = new ValueEncryptor(randomBytes(32));
    const ct = a.encrypt("secret");
    expect(() => b.decrypt(ct)).toThrow(DecryptionFailedError);
  });

  it("decrypt of short-ciphertext throws DecryptionFailedError (boundary)", () => {
    const enc = new ValueEncryptor(KEY);
    expect(() => enc.decrypt("v1.aesgcm:abc")).toThrow(DecryptionFailedError);
  });

  it("plaintext without sentinel prefix passes through (migration path, no throw)", () => {
    const enc = new ValueEncryptor(KEY);
    expect(enc.decrypt("not-encrypted-value")).toBe("not-encrypted-value");
  });

  it("DecryptionFailedError NOT instanceof EncryptionKeyError (orthogonal classes)", () => {
    expect(new DecryptionFailedError("x")).not.toBeInstanceOf(EncryptionKeyError);
    expect(new EncryptionKeyError("x")).not.toBeInstanceOf(DecryptionFailedError);
  });

  it("BACKDOOR: round-trip encrypt → decrypt yields original plaintext", () => {
    const enc = new ValueEncryptor(KEY);
    const ct = enc.encrypt("the quick brown fox");
    expect(enc.decrypt(ct)).toBe("the quick brown fox");
  });

  it("encrypt produces output with the version+algo sentinel prefix", () => {
    const enc = new ValueEncryptor(KEY);
    const ct = enc.encrypt("x");
    expect(ct).toMatch(/^v1\.aesgcm:/);
  });

  it("two encrypts of same plaintext produce DIFFERENT ciphertexts (random nonce)", () => {
    const enc = new ValueEncryptor(KEY);
    const a = enc.encrypt("same input");
    const b = enc.encrypt("same input");
    expect(a).not.toBe(b);
    // But both decrypt to the same plaintext.
    expect(enc.decrypt(a)).toBe(enc.decrypt(b));
  });

  it("base64-string key accepted (alternative to Buffer)", () => {
    const keyB64 = KEY.toString("base64");
    const enc = new ValueEncryptor(keyB64);
    const ct = enc.encrypt("hi");
    expect(enc.decrypt(ct)).toBe("hi");
  });

  it("error stack traces preserved (debug visibility)", () => {
    const e = new DecryptionFailedError("trace me");
    expect(e.stack).toBeDefined();
    expect(e.stack).toContain("DecryptionFailedError");
  });
});
