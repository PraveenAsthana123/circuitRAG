import { GuardrailFinding } from "./types";

export class PIIDetector {
  detect(text: string): GuardrailFinding[] {
    const findings: GuardrailFinding[] = [];

    if (/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi.test(text)) {
      findings.push({
        ruleId: "PII_EMAIL",
        severity: "medium",
        message: "Input contains an email address",
      });
    }

    if (/\b\d{3}[-.]?\d{3}[-.]?\d{4}\b/g.test(text)) {
      findings.push({
        ruleId: "PII_PHONE",
        severity: "medium",
        message: "Input contains a phone number",
      });
    }

    return findings;
  }
}
