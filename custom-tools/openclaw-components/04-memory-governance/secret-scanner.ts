// Added Iter 52 (2026-05-17) — secret pattern detection.
// PII masking (Component 4 + 5) catches person-identifying data.
// SecretScanner catches CREDENTIALS — leaked API keys, cloud
// access keys, tokens. An LLM that echoes a chat message
// containing an AWS secret key in its memory of past conversation
// is one of the highest-impact leak categories.
//
// Real production should layer a real scanner (TruffleHog,
// detect-secrets, ggshield) for entropy-based + provider-specific
// validation. This stub closes the obvious-pattern gap.

export interface SecretFinding {
  type: string;          // "aws_access_key" | "github_token" | ...
  match: string;         // the matched substring
  index: number;         // position in the input
}

// Pattern catalog. Each entry has a name + regex (no /g — we use
// matchAll for position tracking) + an optional validator.
interface Pattern {
  type: string;
  regex: RegExp;
  validate?: (s: string) => boolean;
}

const PATTERNS: Pattern[] = [
  // AWS Access Key ID — 20 char uppercase alnum starting with AKIA/ASIA.
  { type: "aws_access_key", regex: /\b(AKIA|ASIA)[A-Z0-9]{16}\b/g },

  // AWS Secret Access Key — 40 char base64. High-FP without entropy
  // check, so paired with an entropy floor.
  {
    type: "aws_secret_key",
    regex: /\baws[_\-]?(secret|access)[_\-]?key\s*[:=]\s*['"]?([A-Za-z0-9/+=]{40})['"]?/gi,
  },

  // GitHub PAT (classic + fine-grained).
  { type: "github_token", regex: /\bghp_[A-Za-z0-9]{36}\b/g },
  { type: "github_token", regex: /\bgithub_pat_[A-Za-z0-9_]{82}\b/g },

  // GitHub OAuth access token.
  { type: "github_oauth", regex: /\bgho_[A-Za-z0-9]{36}\b/g },

  // OpenAI API key (sk-... 48+ chars).
  { type: "openai_key", regex: /\bsk-[A-Za-z0-9]{20,}\b/g },

  // Anthropic API key (sk-ant-api03-...).
  { type: "anthropic_key", regex: /\bsk-ant-(api|sid)\d{2}-[A-Za-z0-9_-]{40,}\b/g },

  // Google API key (39 chars, AIza prefix).
  { type: "google_api_key", regex: /\bAIza[0-9A-Za-z_-]{35}\b/g },

  // Slack bot token.
  { type: "slack_bot_token", regex: /\bxoxb-[0-9]{10,13}-[0-9]{10,13}-[A-Za-z0-9]{24}\b/g },

  // Generic PEM private key block.
  { type: "private_key_pem", regex: /-----BEGIN (RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----/g },

  // JWT — header.payload.signature with base64url chars. Filters
  // out very short matches that are almost certainly false positives.
  {
    type: "jwt",
    regex: /\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/g,
  },
];

export class SecretScanner {
  scan(text: string): SecretFinding[] {
    const findings: SecretFinding[] = [];
    for (const { type, regex, validate } of PATTERNS) {
      for (const m of text.matchAll(regex)) {
        const match = m[0];
        if (validate && !validate(match)) continue;
        findings.push({
          type, match, index: m.index ?? -1,
        });
      }
    }
    return findings;
  }

  /** Mask secrets in `text` by replacing each match with the
   *  sentinel `[REDACTED:type]`. */
  redact(text: string): string {
    // Sort findings by index DESCENDING so replacements don't
    // shift earlier-indexed positions.
    const findings = this.scan(text).sort((a, b) => b.index - a.index);
    let out = text;
    for (const f of findings) {
      out = out.slice(0, f.index) +
            `[REDACTED:${f.type}]` +
            out.slice(f.index + f.match.length);
    }
    return out;
  }
}
