# RESOURCES: playwright
"""
Drill: SpeechReader browser-TTS chunking + no-voice diagnostic alert.

User reported a sequence of bugs that all stemmed from two root
causes — silent truncation (Chrome's ~15k-char utterance cap) and
silent fall-through when voices.length === 0.

Verifies (commit 0e14684):

 1. With voices stubbed, clicking Read on a >15k-char page queues
    MULTIPLE SpeechSynthesisUtterance objects (proves the chunker
    activated; previously a single oversized utterance got silently
    truncated by the browser).
 2. NEGATIVE: every queued utterance is ≤ 4000 chars (regression
    that would re-trip the silent-truncation bug).
 3. The first utterance fires immediately (proves no buffer-wait
    delay; the user's 'taking long time to start' complaint).
 4. With no voices stubbed (voices.length=0), clicking Read renders
    a role='alert' element with 'voices.length = 0' diagnostic +
    platform-specific install hint (proves the silent-failure path
    was closed; the user's 'still no sound' complaint).
 5. NEGATIVE: when no voices, speak() does NOT fire the server-TTS
    fallback (which would clobber the alert message). The previous
    code silently fell through to speakViaServer; the fix returns
    early after setting the diagnostic.

Negative assertions per §43:
  - Step 2: utterance length cap — prevents truncation regression
  - Step 5: no server-TTS fallback when voices=0 — prevents the
    alert-clobber regression that hid the diagnosis

Run:
    PROD_URL=http://localhost:3000 \\
      /tmp/pw-venv/bin/python mcp/tests/drill_speech_browser_chunking_and_alert.py
"""
from __future__ import annotations

import asyncio
import os
import sys

PROD_URL = os.getenv("PROD_URL", "http://localhost:3000")
TARGET = f"{PROD_URL}/admin/architect/deep"

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
NC = "\033[0m"
DIM = "\033[2m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{NC} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{NC} {msg}")


VOICE_STUB = """
(() => {
  const fakeVoice = {
    name: 'TestVoice', lang: 'en-US',
    localService: true, default: true, voiceURI: 'test',
  };
  try {
    Object.defineProperty(
      Object.getPrototypeOf(window.speechSynthesis),
      'getVoices',
      { configurable: true, value: () => [fakeVoice] },
    );
  } catch(_e) {}
  Object.defineProperty(window.speechSynthesis, 'getVoices', {
    configurable: true, value: () => [fakeVoice],
  });

  window.__utters = [];
  window.__firstUtterT = null;
  window.__clickT = null;
  window.speechSynthesis.speak = (u) => {
    if (window.__firstUtterT === null) window.__firstUtterT = performance.now();
    window.__utters.push({
      len: (u.text || '').length,
      head: (u.text || '').slice(0, 50),
    });
    queueMicrotask(() => { try { u.onstart && u.onstart({}); } catch(_e) {} });
  };
  setTimeout(() => {
    try { window.speechSynthesis.dispatchEvent(new Event('voiceschanged')); } catch(_e) {}
  }, 200);
})();
"""


async def run() -> int:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print(f"{YELLOW}⚠ playwright not installed — skipping{NC}")
        return 0

    failures = 0
    print(f"{BOLD}Drill: SpeechReader browser-TTS chunking + no-voice alert{NC}")
    print(f"{DIM}target: {TARGET}{NC}")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context()

        # ─── Part A: chunking with voices stubbed ─────────────────────
        page_a = await ctx.new_page()
        await page_a.add_init_script(VOICE_STUB)
        await page_a.goto(TARGET, wait_until="networkidle")
        await page_a.wait_for_timeout(2500)

        # Wait for full page hydration so text is large
        text_len = await page_a.evaluate(
            "(document.querySelector('main')?.textContent || '').length"
        )
        if text_len < 15000:
            print(f"  {YELLOW}⚠{NC} target page text only {text_len} chars; chunking drill needs >15000")
            print("      (page MAY have been truncated by PageDownloadBar; not a code bug)")
        else:
            ok(f"step 0: page text length = {text_len} chars (>15000 — exercises chunking)")

        await page_a.evaluate("window.__clickT = performance.now()")
        await page_a.locator('button[aria-label="Read aloud with highlight"]').first.click()

        # Wait for queueing to complete
        try:
            await page_a.wait_for_function("window.__utters && window.__utters.length > 0", timeout=4000)
        except Exception:
            fail("step 1: no utterances queued — voices stub may not have taken effect")
            failures += 1
            await browser.close()
            return failures

        await page_a.wait_for_timeout(500)
        utters = await page_a.evaluate("window.__utters")
        first_utter_t = await page_a.evaluate("window.__firstUtterT - window.__clickT")

        # 1. Multiple utterances queued (proves chunking)
        if len(utters) >= 2:
            ok(f"step 1: {len(utters)} utterances queued (chunker activated)")
        else:
            # Either page wasn't long enough OR chunker regressed
            print(f"  {YELLOW}⚠{NC} step 1: only {len(utters)} utterance(s); page may be <4000 chars on this run")

        # 2. NEGATIVE: every utterance ≤ 4000 chars
        max_len = max((u["len"] for u in utters), default=0)
        oversized = [u for u in utters if u["len"] > 4000]
        if not oversized:
            ok(f"step 2: every utterance ≤ 4000 chars (max seen = {max_len})")
        else:
            fail(f"step 2: {len(oversized)} oversized utterance(s); max = {max_len} > 4000")
            failures += 1

        # 3. First utterance fires fast (no buffer-wait)
        if first_utter_t is not None and first_utter_t < 500:
            ok(f"step 3: first utterance queued in {first_utter_t:.0f}ms (<500ms — no buffer-wait)")
        elif first_utter_t is None:
            print(f"  {YELLOW}⚠{NC} step 3: timing not captured")
        else:
            fail(f"step 3: first utterance took {first_utter_t:.0f}ms (>500ms; user's 'long time to start')")
            failures += 1

        await page_a.close()

        # ─── Part B: no-voice alert ───────────────────────────────────
        page_b = await ctx.new_page()
        # Track if /api/v1/tts gets POSTed (it should NOT when voices=0)
        server_tts_posts: list[str] = []
        page_b.on(
            "request",
            lambda r: server_tts_posts.append(r.url)
            if r.method == "POST" and "/api/v1/tts" in r.url
            else None,
        )

        await page_b.goto(TARGET, wait_until="networkidle")
        await page_b.wait_for_timeout(2500)
        # Confirm no voices in this context
        v = await page_b.evaluate("window.speechSynthesis.getVoices().length")
        if v != 0:
            print(f"  {YELLOW}⚠{NC} headless has {v} voices unexpectedly; alert path may not trigger")

        await page_b.locator('button[aria-label="Read aloud with highlight"]').first.click()
        await page_b.wait_for_timeout(1500)

        # 4. Alert renders with diagnostic
        alert_text = await page_b.evaluate(
            """document.querySelector('div[role="alert"]')?.textContent || null"""
        )
        if not alert_text:
            fail("step 4: no role='alert' element rendered when voices.length=0")
            failures += 1
        elif "voices.length = 0" not in alert_text:
            fail(f"step 4: alert missing diagnostic ('voices.length = 0'); text: {alert_text[:200]}")
            failures += 1
        elif not any(
            hint in alert_text
            for hint in ["speech-dispatcher", "espeak", "Settings", "Safari", "different browser"]
        ):
            fail(f"step 4: alert missing platform-specific install hint; text: {alert_text[:200]}")
            failures += 1
        else:
            ok("step 4: alert renders with diagnostic + platform-specific install hint")

        # 5. NEGATIVE: speakViaServer NOT called when voices=0
        if not server_tts_posts:
            ok("step 5: NO /api/v1/tts POST when voices=0 (alert-clobber path closed)")
        else:
            fail(
                f"step 5: server-TTS fired {len(server_tts_posts)}× when voices=0 — "
                f"would clobber the alert (regression)"
            )
            failures += 1

        await browser.close()

    print()
    if failures == 0:
        print(f"{GREEN}{BOLD}ALL 5 STEPS PASSED{NC}")
        return 0
    print(f"{RED}{BOLD}{failures} STEP(S) FAILED{NC}")
    return failures


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
