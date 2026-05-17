// Negative drills for Iter 20 (2026-05-17): AES-256-GCM
// encryption-at-rest for memory values.

import { describe, it, expect } from "vitest";
import {
  ValueEncryptor,
  EncryptionKeyError,
  DecryptionFailedError,
} from "./encryption";
import { MemoryGovernanceService } from "./memory-governance-service";
import { MemoryStore } from "./memory-store";
import { MemoryAuditLog } from "./memory-audit-log";
import { PIIMasker } from "./pii-masker";
import { RetentionPolicy } from "./retention-policy";

describe("ValueEncryptor — primitives (P1)", () => {
  it("round-trip: encrypted value decrypts to original", () => {
    const enc = new ValueEncryptor(ValueEncryptor.generateKey());
    const plain = "User loves TypeScript; email alice@example.com";
    const cipher = enc.encrypt(plain);
    expect(cipher).not.toBe(plain);
    expect(cipher.startsWith("v1.aesgcm:")).toBe(true);
    expect(enc.decrypt(cipher)).toBe(plain);
  });

  it("two encryptions of the same plaintext produce different ciphertexts (random nonce)", () => {
    const enc = new ValueEncryptor(ValueEncryptor.generateKey());
    const c1 = enc.encrypt("same");
    const c2 = enc.encrypt("same");
    expect(c1).not.toBe(c2);
    expect(enc.decrypt(c1)).toBe("same");
    expect(enc.decrypt(c2)).toBe("same");
  });

  it("rejects wrong-length key", () => {
    expect(() => new ValueEncryptor(Buffer.from("too-short")))
      .toThrowError(EncryptionKeyError);
  });

  it("BACKDOOR CHECK: tampered ciphertext throws DecryptionFailedError", () => {
    const enc = new ValueEncryptor(ValueEncryptor.generateKey());
    const cipher = enc.encrypt("secret");
    // Tamper: flip a char in the base64 body.
    const tampered = cipher.slice(0, -3) + "XYZ";
    expect(() => enc.decrypt(tampered)).toThrowError(DecryptionFailedError);
  });

  it("decryption with WRONG key throws", () => {
    const enc1 = new ValueEncryptor(ValueEncryptor.generateKey());
    const enc2 = new ValueEncryptor(ValueEncryptor.generateKey());
    const cipher = enc1.encrypt("secret");
    expect(() => enc2.decrypt(cipher)).toThrowError(DecryptionFailedError);
  });

  it("plaintext without sentinel passes through (migration path)", () => {
    const enc = new ValueEncryptor(ValueEncryptor.generateKey());
    // Existing record from before encryption was enabled.
    expect(enc.decrypt("plain old value")).toBe("plain old value");
  });
});

describe("MemoryGovernanceService — at-rest encryption (P1)", () => {
  it("stored value in MemoryStore is the CIPHERTEXT, not the plaintext", () => {
    const store = new MemoryStore();
    const enc = new ValueEncryptor(ValueEncryptor.generateKey());
    const svc = new MemoryGovernanceService(
      store, new MemoryAuditLog(), new PIIMasker(),
      new RetentionPolicy(), enc,
    );

    svc.save({
      tenantId: "tenant-A", userId: "u", actorUserId: "u",
      key: "pref", value: "I love TypeScript",
      reason: "test",
    });

    const inStore = store.findByKey("tenant-A", "u", "pref");
    expect(inStore).toBeDefined();
    // BACKDOOR CHECK: plaintext must NOT be readable from the store.
    expect(inStore!.value).not.toBe("I love TypeScript");
    expect(inStore!.value.startsWith("v1.aesgcm:")).toBe(true);

    // But read() decrypts.
    const fetched = svc.read("tenant-A", "u", "pref");
    expect(fetched?.value).toBe("I love TypeScript");
  });

  it("without encryptor, behavior is backcompat (plaintext stored)", () => {
    const store = new MemoryStore();
    const svc = new MemoryGovernanceService(
      store, new MemoryAuditLog(), new PIIMasker(),
      new RetentionPolicy(),
      // no encryptor
    );
    svc.save({
      tenantId: "t", userId: "u", actorUserId: "u",
      key: "k", value: "I love TypeScript",
      reason: "test",
    });
    const inStore = store.findByKey("t", "u", "k");
    expect(inStore!.value).toBe("I love TypeScript");
  });
});
