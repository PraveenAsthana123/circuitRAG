import { describe, expect, it } from "vitest";
import {
  PIIDetection,
  PIIDetector,
  PIIProvider,
  RegexPIIProvider,
} from "./pii-detector";

class StubPIIProvider implements PIIProvider {
  constructor(private readonly results: PIIDetection[]) {}

  detect(_text: string): PIIDetection[] {
    return this.results;
  }
}

describe("PIIDetector provider seam", () => {
  it("maps injected provider positives into guardrail findings", () => {
    const detector = new PIIDetector(new StubPIIProvider([
      {
        detected: true,
        ruleId: "PII_LIBRARY_NATIONAL_ID",
        severity: "critical",
        message: "Library detected national identifier",
      },
    ]));

    expect(detector.detect("id payload")).toEqual([
      {
        ruleId: "PII_LIBRARY_NATIONAL_ID",
        severity: "critical",
        message: "Library detected national identifier",
      },
    ]);
  });

  it("filters non-detected provider results", () => {
    const detector = new PIIDetector(new StubPIIProvider([
      { detected: false, message: "benign token" },
      { detected: true, message: "possible pii" },
    ]));

    expect(detector.detect("mixed result")).toEqual([
      {
        ruleId: "PII",
        severity: "medium",
        message: "possible pii",
      },
    ]);
  });

  it("default regex provider preserves existing email detection", () => {
    const detector = new PIIDetector();

    expect(detector.detect("alice@example.com")[0]).toMatchObject({
      ruleId: "PII_EMAIL",
      severity: "medium",
    });
  });

  it("regex provider remains directly injectable", () => {
    const detector = new PIIDetector(new RegexPIIProvider());

    expect(detector.detect("SSN 123-45-6789")[0]).toMatchObject({
      ruleId: "PII_SSN",
      severity: "critical",
    });
  });
});
