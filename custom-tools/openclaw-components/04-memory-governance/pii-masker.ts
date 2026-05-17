// ✅ P1 IMPROVED (Iter 25, 2026-05-17): broader pattern coverage
//     + credit-card Luhn validation to suppress false positives on
//     arbitrary 16-digit strings (order numbers, tracking IDs).
//
//     Real production needs validator.js + libphonenumber + a real
//     PII classifier (Presidio / Lakera) — see GAPS Component 4
//     row "PII masker ASCII-only regex". This fix substantially
//     improves coverage without those deps.
//
//     What's covered now:
//       - Email: international TLDs, IDN-friendly (no ASCII anchor)
//       - Phone: US/CA, international +CC, common separators
//       - Credit cards: 13-19 digits with separators; Luhn-validated
//         (rejects random-looking 16-digit strings)
//       - SSN-like: ###-##-#### with US-only intent
//       - IPv4: standard dotted quad
//       - IBAN: 2-letter country + 2 check + 11-30 alphanumeric
//
//     Each replacement keeps the same sentinel labels so downstream
//     readers see the same shape as before.

const EMAIL_RE = /\b[\p{L}\p{N}._%+-]+@[\p{L}\p{N}.-]+\.[\p{L}]{2,}\b/giu;

// US/CA: optional +1, area code (with optional parens), 7-digit local.
// Use digit-boundary lookarounds instead of \b so the opening "("
// is consumed when present and excluded from the match otherwise.
const US_PHONE_RE = /(?<!\d)(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)/g;

// International: +CC followed by 7-15 digits with optional separators.
const INTL_PHONE_RE = /\+\d{1,3}(?:[\s.-]?\d){7,14}\b/g;

// 13-19 digits with optional spaces/dashes (matches all major card BINs).
const CARD_RE = /\b(?:\d[ -]?){12,18}\d\b/g;

const SSN_RE = /\b\d{3}-\d{2}-\d{4}\b/g;
const IPV4_RE = /\b(?:\d{1,3}\.){3}\d{1,3}\b/g;
const IBAN_RE = /\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b/g;

/** Luhn-validate stripped digits; returns true if a valid card. */
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

export class PIIMasker {
  mask(text: string): string {
    // Order matters: mask emails/IBAN first (they may otherwise be
    // partially eaten by the more permissive phone/card matchers).
    let out = text.replace(EMAIL_RE, "[EMAIL]");
    out = out.replace(IBAN_RE, "[IBAN]");
    out = out.replace(SSN_RE, "[SSN]");

    // Cards: Luhn-validate so random 16-digit IDs don't get masked.
    out = out.replace(CARD_RE, (match) => {
      const digits = match.replace(/[\s-]/g, "");
      if (digits.length < 13 || digits.length > 19) return match;
      return luhnValid(digits) ? "[CARD]" : match;
    });

    out = out.replace(INTL_PHONE_RE, "[PHONE]");
    out = out.replace(US_PHONE_RE, "[PHONE]");
    out = out.replace(IPV4_RE, "[IP]");
    return out;
  }
}
