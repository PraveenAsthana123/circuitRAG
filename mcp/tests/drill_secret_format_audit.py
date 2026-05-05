#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: project-wide audit for secret-shaped string literals.

Phase 7I (drill_tts_proxy_route, 640312f) checked one route for
hardcoded OpenAI keys. This drill generalises across the entire
codebase and across the major secret formats: OpenAI (`sk-...`),
Anthropic (`sk-ant-...`), AWS access key (`AKIA...`), GitHub
tokens (`ghp_...`/`gho_`/`ghu_`/`ghs_`/`ghr_`/`ghs_`), Google API
keys (`AIza...`), Slack tokens (`xoxb-`/`xoxa-`/`xoxp-`/`xoxr-`/
`xoxs-`).

Why this drill matters: a leaked production key in source costs
money (cloud bills), reputation (incident write-up), and
potentially data (downstream services trust the key). CLAUDE.md
§3 names "no secrets in code" as a non-negotiable; this drill
enforces it across 7000+ files.

False positives are handled via KNOWN_TEST_FIXTURES: AWS docs
publish `AKIAIOSFODNN7EXAMPLE` as a canonical fake; the
drill_pii_redaction.py drill uses it. Allowlisted explicitly.

Ten steps. Eight negative assertions.

  1. POSITIVE: discover scannable files (>= 1000 floor — drill
     cannot trivially pass by deleting source).
  2. NEGATIVE: no OpenAI key shape (`sk-[A-Za-z0-9_-]{20,}`,
     excluding sk-ant- prefix which has its own pattern, and
     KNOWN_TEST_FIXTURES). Tightest; sk- prefix is the
     OpenAI-canonical user-key shape.
  3. NEGATIVE: no Anthropic key shape (`sk-ant-...`).
  4. NEGATIVE: no AWS access key shape (`AKIA[A-Z0-9]{16}`,
     excluding KNOWN_TEST_FIXTURES like AKIAIOSFODNN7EXAMPLE).
  5. NEGATIVE: no GitHub token shape (`gh[poursa]_[A-Za-z0-9]{36,}`).
  6. NEGATIVE: no Google API key shape (`AIza[0-9A-Za-z_-]{35}`).
  7. NEGATIVE: no Slack token shape (`xox[baprs]-...`).
  8. NEGATIVE: no Stripe LIVE key shape (`[sp]k_live_...`).
     Test keys (`sk_test_`/`pk_test_`) are publishable by design;
     only live keys are secrets.
  9. NEGATIVE: no JWT-shape token (`eyJ<header>.<payload>.<sig>`).
     A real JWT in source = session/user-token leak.
  10. POSITIVE: emit per-pattern scan summary (file count,
     match count) for operator visibility.

Run: python3 mcp/tests/drill_secret_format_audit.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

EXCLUDE_DIRS = {
    ".git", "node_modules", ".next", ".next-prod", ".venv", "venv",
    ".venv-tts",  # 2026-05-05: TTS-specific venv at /mnt/deepa/rag/.venv-tts
                  # contains litellm test fixtures with sk-* shaped keys
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "data", ".loop", ".runtime", ".playwright-mcp", "htmlcov",
    ".turbo", ".vite", "dist", "build", ".eslintcache",
}
SCANNABLE_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".sh",
    ".yaml", ".yml", ".json", ".md", ".env", ".tf", ".tfvars",
    ".sql", ".toml",
}
# Self-exclusion: this drill's own source contains the regex
# patterns; without exclusion we'd false-positive on ourselves.
SELF_NAME = "drill_secret_format_audit.py"

# Allowlist for known-fake fixtures used in test/example code.
# AWS publishes AKIAIOSFODNN7EXAMPLE in their canonical docs; the
# drill_pii_redaction.py drill uses it deliberately. Keep this
# set small; every entry is one explicit exemption.
KNOWN_TEST_FIXTURES = {
    "AKIAIOSFODNN7EXAMPLE",
}

# Pattern set. Each entry: (kind, regex). The kind labels the
# violation in step output; the regex is anchored with \b so it
# doesn't match inside longer identifiers.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # OpenAI user keys: sk-<>=20 chars, but exclude sk-ant- prefix
    # (Anthropic; pattern 3 catches it specifically).
    ("OpenAI", re.compile(r"\bsk-(?!ant-)[A-Za-z0-9_-]{20,}")),
    ("Anthropic", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("AWS_AccessKey", re.compile(r"\bAKIA[A-Z0-9]{16}\b")),
    # GitHub tokens: ghp_ (PAT), gho_ (OAuth), ghu_ (user-to-svc),
    # ghs_ (server-to-svc), ghr_ (refresh).
    ("GitHub", re.compile(r"\bgh[poursa]_[A-Za-z0-9]{36,}")),
    ("Google", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    # Slack tokens: xoxb (bot), xoxa (workspace), xoxp (user),
    # xoxr (refresh), xoxs (system).
    ("Slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{8,}")),
    # Stripe LIVE keys (sk_live_ secret, pk_live_ publishable but
    # still a secret in the sense that it identifies the
    # production account). Test keys (sk_test_/pk_test_) are
    # publishable by design and intentionally NOT matched.
    ("Stripe_live", re.compile(r"\b[sp]k_live_[A-Za-z0-9]{24,}")),
    # JWT: three base64url-ish segments separated by '.'. The eyJ
    # prefix is the canonical base64 of `{"al`, so it discriminates
    # JWTs from other dotted-tokens.
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
]

# Floor — codebase has thousands of source files; if the drill
# discovers fewer than this, something is wrong with the scan.
MIN_FILES = 1000

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}{msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}-- {title} --{NC}")


def _scannable_files() -> list[Path]:
    files: list[Path] = []
    for path in REPO.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in SCANNABLE_EXTS:
            continue
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        if path.name == SELF_NAME:
            continue
        files.append(path)
    return files


def _match_kind(files: list[Path], kind: str, pattern: re.Pattern[str]) -> list[tuple[str, str]]:
    """Return list of (relative_path, matched_snippet) for the pattern,
    excluding KNOWN_TEST_FIXTURES."""
    hits: list[tuple[str, str]] = []
    for path in files:
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for m in pattern.finditer(text):
            matched = m.group(0)
            if matched in KNOWN_TEST_FIXTURES:
                continue
            # Truncate snippet for output but preserve enough to identify.
            snippet = matched[:24] + ("..." if len(matched) > 24 else "")
            hits.append((str(path.relative_to(REPO)), snippet))
    return hits


def main() -> int:
    step("1. POSITIVE: discover scannable files (>= MIN_FILES floor)")
    files = _scannable_files()
    if len(files) < MIN_FILES:
        fail(
            f"only {len(files)} scannable files; floor is {MIN_FILES}. "
            "Drill cannot trivially pass by deleting source."
        )
    ok(f"discovered {len(files)} scannable files")

    pattern_summary: dict[str, int] = {}

    step("2. NEGATIVE: no OpenAI key shape in any source file")
    hits = _match_kind(files, "OpenAI", PATTERNS[0][1])
    pattern_summary["OpenAI"] = len(hits)
    if hits:
        fail(
            f"{len(hits)} OpenAI key shape(s) found "
            f"(SECURITY REGRESSION): {hits[:3]}"
        )
    ok("no OpenAI key shape (excluding sk-ant-) anywhere in source")

    step("3. NEGATIVE: no Anthropic key shape in any source file")
    hits = _match_kind(files, "Anthropic", PATTERNS[1][1])
    pattern_summary["Anthropic"] = len(hits)
    if hits:
        fail(
            f"{len(hits)} Anthropic key shape(s) found "
            f"(SECURITY REGRESSION): {hits[:3]}"
        )
    ok("no Anthropic key shape (sk-ant-) anywhere in source")

    step("4. NEGATIVE: no AWS access key shape (excluding KNOWN_TEST_FIXTURES)")
    hits = _match_kind(files, "AWS_AccessKey", PATTERNS[2][1])
    pattern_summary["AWS_AccessKey"] = len(hits)
    if hits:
        fail(
            f"{len(hits)} AWS access key shape(s) found "
            f"(SECURITY REGRESSION): {hits[:3]}. If a known test "
            "fixture, add to KNOWN_TEST_FIXTURES."
        )
    ok("no AWS access key shape outside allowlist")

    step("5. NEGATIVE: no GitHub token shape in any source file")
    hits = _match_kind(files, "GitHub", PATTERNS[3][1])
    pattern_summary["GitHub"] = len(hits)
    if hits:
        fail(
            f"{len(hits)} GitHub token shape(s) found "
            f"(SECURITY REGRESSION): {hits[:3]}"
        )
    ok("no GitHub token shape (ghp_/gho_/ghu_/ghs_/ghr_) anywhere")

    step("6. NEGATIVE: no Google API key shape in any source file")
    hits = _match_kind(files, "Google", PATTERNS[4][1])
    pattern_summary["Google"] = len(hits)
    if hits:
        fail(
            f"{len(hits)} Google API key shape(s) found "
            f"(SECURITY REGRESSION): {hits[:3]}"
        )
    ok("no Google API key shape (AIza...) anywhere in source")

    step("7. NEGATIVE: no Slack token shape in any source file")
    hits = _match_kind(files, "Slack", PATTERNS[5][1])
    pattern_summary["Slack"] = len(hits)
    if hits:
        fail(
            f"{len(hits)} Slack token shape(s) found "
            f"(SECURITY REGRESSION): {hits[:3]}"
        )
    ok("no Slack token shape (xox[baprs]-) anywhere in source")

    step("8. NEGATIVE: no Stripe LIVE key shape in any source file")
    hits = _match_kind(files, "Stripe_live", PATTERNS[6][1])
    pattern_summary["Stripe_live"] = len(hits)
    if hits:
        fail(
            f"{len(hits)} Stripe LIVE key shape(s) found "
            f"(SECURITY REGRESSION): {hits[:3]}. Test keys "
            "(sk_test_/pk_test_) are publishable; only live keys flag."
        )
    ok("no Stripe LIVE key shape ([sp]k_live_) anywhere in source")

    step("9. NEGATIVE: no JWT-shape token in any source file")
    hits = _match_kind(files, "JWT", PATTERNS[7][1])
    pattern_summary["JWT"] = len(hits)
    if hits:
        fail(
            f"{len(hits)} JWT-shape token(s) found "
            f"(SECURITY REGRESSION — session/user-token leak): "
            f"{hits[:3]}"
        )
    ok("no JWT-shape token (eyJ<header>.<payload>.<sig>) anywhere in source")

    step("10. POSITIVE: per-pattern scan summary")
    summary = ", ".join(
        f"{k}:{pattern_summary.get(k, 0)}"
        for k in (
            "OpenAI", "Anthropic", "AWS_AccessKey", "GitHub", "Google", "Slack",
            "Stripe_live", "JWT",
        )
    )
    ok(
        f"scanned {len(files)} files across {len(SCANNABLE_EXTS)} extensions; "
        f"matches per pattern: {summary}"
    )
    if KNOWN_TEST_FIXTURES:
        ok(
            f"allowlist active for {len(KNOWN_TEST_FIXTURES)} known test "
            f"fixtures: {sorted(KNOWN_TEST_FIXTURES)}"
        )

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 10 SECRET-FORMAT-AUDIT STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (8 negative assertions: 2, 3, 4, 5, 6, 7, 8, 9){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
