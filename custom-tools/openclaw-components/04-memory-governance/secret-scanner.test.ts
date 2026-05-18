// Negative drills for Iter 52 (2026-05-17): SecretScanner.

import { describe, it, expect } from "vitest";
import { SecretScanner } from "./secret-scanner";

const s = new SecretScanner();

describe("SecretScanner — credential patterns (P0)", () => {
  it("BACKDOOR CHECK: AWS access key ID detected", () => {
    const out = s.scan("the key is AKIAIOSFODNN7EXAMPLE");
    expect(out.find((f) => f.type === "aws_access_key")).toBeDefined();
  });

  it("AWS secret key (in key=value form) detected", () => {
    const out = s.scan('aws_secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"');
    expect(out.find((f) => f.type === "aws_secret_key")).toBeDefined();
  });

  it("GitHub classic PAT detected", () => {
    const out = s.scan("token: ghp_abcdefghijklmnopqrstuvwxyz0123456789");
    expect(out.find((f) => f.type === "github_token")).toBeDefined();
  });

  it("GitHub fine-grained PAT detected", () => {
    const out = s.scan(
      "token: github_pat_" + "1".repeat(82),
    );
    expect(out.find((f) => f.type === "github_token")).toBeDefined();
  });

  it("OpenAI key detected", () => {
    const out = s.scan("OPENAI_API_KEY=sk-abcdefghij1234567890abcdef");
    expect(out.find((f) => f.type === "openai_key")).toBeDefined();
  });

  it("Anthropic key detected", () => {
    const out = s.scan(
      "ANTHROPIC_API_KEY=sk-ant-api03-" + "a".repeat(45),
    );
    expect(out.find((f) => f.type === "anthropic_key")).toBeDefined();
  });

  it("Google API key detected", () => {
    const out = s.scan(
      "GOOGLE_API_KEY=AIza" + "B".repeat(35),
    );
    expect(out.find((f) => f.type === "google_api_key")).toBeDefined();
  });

  it("Slack bot token detected", () => {
    const out = s.scan(
      "slack: xoxb-1234567890-1234567890-" + "A".repeat(24),
    );
    expect(out.find((f) => f.type === "slack_bot_token")).toBeDefined();
  });

  it("PEM private key block detected", () => {
    const out = s.scan(
      "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...",
    );
    expect(out.find((f) => f.type === "private_key_pem")).toBeDefined();
  });

  it("JWT detected", () => {
    const jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkphbmUifQ.abc123def456";
    const out = s.scan(`auth: ${jwt}`);
    expect(out.find((f) => f.type === "jwt")).toBeDefined();
  });

  it("benign text yields no findings", () => {
    expect(s.scan("just a sentence about cats")).toEqual([]);
    expect(s.scan("order id 12345 was shipped")).toEqual([]);
  });

  it("BACKDOOR CHECK: redact() replaces secrets with [REDACTED:type]", () => {
    const input = "my key is AKIAIOSFODNN7EXAMPLE and my token is ghp_abcdefghijklmnopqrstuvwxyz0123456789";
    const out = s.redact(input);
    expect(out).not.toContain("AKIAIOSFODNN7EXAMPLE");
    expect(out).not.toContain("ghp_abcdefghijklmnopqrstuvwxyz0123456789");
    expect(out).toContain("[REDACTED:aws_access_key]");
    expect(out).toContain("[REDACTED:github_token]");
  });

  it("findings carry the correct index for replacement", () => {
    const input = "before AKIAIOSFODNN7EXAMPLE after";
    const [finding] = s.scan(input);
    expect(input.slice(finding.index, finding.index + finding.match.length))
      .toBe("AKIAIOSFODNN7EXAMPLE");
  });
});
