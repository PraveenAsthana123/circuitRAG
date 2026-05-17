// ✅ P1 IMPROVED (Iter 31, 2026-05-17): broader pattern set with
//     severity tiers + Luhn-validated cards. Same logic family as
//     Component 4's PIIMasker (iter 25) but applied to the
//     guardrail-eval surface so the decision engine can route
//     PII-containing inputs to higher-severity buckets.
//
//     Severity is policy-tuned:
//       - critical: SSN, credit card (Luhn-validated), IBAN
//       - high:     IPv4 (often leaks infrastructure topology)
//       - medium:   email, phone
//     Critical findings are the policy engine's signal to BLOCK,
//     not just review.
//
//     Real production needs validator.js + libphonenumber + a real
//     PII classifier (Presidio / Lakera). This is still heuristic.

import { GuardrailFinding } from "./types";

const EMAIL_RE = /\b[\p{L}\p{N}._%+-]+@[\p{L}\p{N}.-]+\.[\p{L}]{2,}\b/giu;
const US_PHONE_RE = /(?<!\d)(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)/g;
const INTL_PHONE_RE = /\+\d{1,3}(?:[\s.-]?\d){7,14}\b/g;
const CARD_RE = /\b(?:\d[ -]?){12,18}\d\b/g;
const SSN_RE = /\b\d{3}-\d{2}-\d{4}\b/g;
const IPV4_RE = /\b(?:\d{1,3}\.){3}\d{1,3}\b/g;
const IBAN_RE = /\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b/g;

function luhnValid(digits: string): boolean {
  let sum = 0;
  let alt = false;
  for (let i = digits.length - 1; i >= 0; i--) {
    let n = digits.charCodeAt(i) - 48;
    if (alt) {
      n *= 2;
      if (n > 9) n -= 9;
    }
    sum += n;
    alt = !alt;
  }
  return sum % 10 === 0;
}

export class PIIDetector {
  detect(text: string): GuardrailFinding[] {
    const findings: GuardrailFinding[] = [];

    if (EMAIL_RE.test(text)) {
      findings.push({
        ruleId: "PII_EMAIL",
        severity: "medium",
        message: "Input contains an email address",
      });
    }

    if (US_PHONE_RE.test(text) || INTL_PHONE_RE.test(text)) {
      findings.push({
        ruleId: "PII_PHONE",
        severity: "medium",
        message: "Input contains a phone number",
      });
    }

    if (SSN_RE.test(text)) {
      findings.push({
        ruleId: "PII_SSN",
        severity: "critical",
        message: "Input contains an SSN-like sequence",
      });
    }

    // Card with Luhn validation — rejects random 16-digit IDs.
    for (const match of text.matchAll(CARD_RE)) {
      const digits = match[0].replace(/[\s-]/g, "");
      if (digits.length >= 13 && digits.length <= 19 && luhnValid(digits)) {
        findings.push({
          ruleId: "PII_CARD",
          severity: "critical",
          message: "Input contains a Luhn-valid card number",
        });
        break; // one finding suffices to drive the decision
      }
    }

    if (IBAN_RE.test(text)) {
      findings.push({
        ruleId: "PII_IBAN",
        severity: "critical",
        message: "Input contains an IBAN",
      });
    }

    if (IPV4_RE.test(text)) {
      findings.push({
        ruleId: "PII_IP",
        severity: "high",
        message: "Input contains an IPv4 address",
      });
    }

    return findings;
  }
}
