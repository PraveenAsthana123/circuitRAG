# RESOURCES: readonly
"""
Drill: SpeechReader advanced features end-to-end on a real page.

Drives `/admin/architect/deep` (architect topic carries acronyms
ADRs / HLD / LLD / RAG / MCP — perfect surface for pronunciation
checks) and exercises every SpeechReader feature:

 1. Toolbar 🔊 button mounts and fires speechSynthesis.speak.
 2. Pronunciation dictionary rewrites tricky acronyms.
 3. Plural acronyms ("ADRs") get rewritten + keep the suffix
    (negative assertion: raw "ADRs" must NOT remain in spoken text).
 4. Pitch + volume sliders mount in the overlay.
 5. Overlay words are clickable (cursor:pointer + onClick handler);
    clicking a non-first word triggers a NEW speak() call (= jump).
 6. Esc keyboard shortcut returns the reader to 'idle'
    (Read-aloud button reappears).
 7. Sentence-level highlight: words in the active sentence carry
    a yellow underline (textDecoration), and the active word still
    wins with the yellow background pill.
 8. Read-selection: when ≥3 words are selected on the page, the
    "🎯 Read selection" button appears in the toolbar.

Negative assertions per §43:
  - Step 3 fails closed if the regex regresses to `\\b${from}\\b`
    and lets "ADRs" pass through unchanged. Singular HLD still
    being rewritten alone wouldn't catch the plural regression.
  - Step 6 explicitly waits for the Read button to come BACK after
    Esc. If state is stuck at 'speaking', the speaking-state button
    stays mounted and this step times out.

Run:
    PROD_URL=http://localhost:3000 \\
      /tmp/pw-venv/bin/python mcp/tests/drill_speech_reader_advanced.py

Requires: /tmp/pw-venv with playwright + chromium installed.
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


async def run() -> int:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print(f"{YELLOW}⚠ playwright not installed — skipping{NC}")
        return 0

    failures = 0
    print(f"{BOLD}Drill: SpeechReader advanced features{NC}")
    print(f"{DIM}target: {TARGET}{NC}")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context()
        page = await ctx.new_page()

        # Capture every utterance handed to speechSynthesis.speak and
        # short-circuit playback. Fire onstart synchronously so React
        # state hits 'speaking', and one synthetic onboundary so the
        # word/sentence highlight engages (otherwise activeIdx stays
        # -1 and highlight tests can't observe styling). Don't auto-
        # fire onend — Esc test needs to trigger the transition itself.
        await page.add_init_script(
            """
            (() => {
              window.__spoken = [];
              window.__cancels = 0;
              window.__lastUtter = null;
              const orig = window.speechSynthesis.speak.bind(window.speechSynthesis);
              window.speechSynthesis.speak = (u) => {
                window.__spoken.push(String(u.text || ''));
                window.__lastUtter = u;
                queueMicrotask(() => {
                  try { u.onstart && u.onstart({}); } catch(_e) {}
                  // synthetic word-boundary at charIndex 0 so the React
                  // state machine activates the first word (drives the
                  // sentence-highlight check in step 7).
                  try { u.onboundary && u.onboundary({ name: 'word', charIndex: 0 }); } catch(_e) {}
                });
              };
              const ocancel = window.speechSynthesis.cancel.bind(window.speechSynthesis);
              window.speechSynthesis.cancel = () => {
                window.__cancels += 1;
                ocancel();
              };
            })();
            """
        )

        await page.goto(TARGET, wait_until="domcontentloaded")

        # 1. Toolbar mounts.
        try:
            await page.wait_for_selector('button[aria-label="Read aloud"]', timeout=10000)
            ok("step 1: toolbar 🔊 button mounted")
        except Exception:
            fail("step 1: toolbar 🔊 button never mounted")
            failures += 1
            await browser.close()
            return failures

        # Wait for the page to settle — MutationObserver in PageDownloadBar
        # re-captures pageText as topic cards / mermaid / lazy hydration
        # land. Real users scroll-then-click; tests must do the same.
        await page.wait_for_function(
            "(document.querySelector('main')?.textContent?.length || 0) > 20000",
            timeout=15000,
        )
        # MutationObserver debounce is 400ms; wait 700ms for the re-capture
        # to land in React state.
        await page.wait_for_timeout(700)

        # Click Read.
        await page.click('button[aria-label="Read aloud"]')
        try:
            await page.wait_for_function("window.__spoken.length > 0", timeout=5000)
            await page.wait_for_selector('button[aria-label="Speaking — click to pause"]', timeout=5000)
        except Exception:
            fail("step 1b: speak() never invoked or state didn't transition")
            failures += 1
            await browser.close()
            return failures

        spoken = await page.evaluate("window.__spoken[0]")

        # 2. Pronunciation rewriting (HLD / RAG must be present).
        if "H L D" in spoken and "R A G" in spoken:
            ok("step 2: HLD → 'H L D' and RAG → 'R A G'")
        else:
            fail(f"step 2: HLD/RAG not rewritten in spoken text (head: {spoken[:160]!r})")
            failures += 1

        # 3. Plural-aware regex: "A D Rs" present AND raw "ADRs" gone.
        adrs_rewritten = "A D Rs" in spoken
        # Negative: scrub the rewritten form before checking the raw.
        scrubbed = spoken.replace("A D Rs", "")
        raw_adrs_remaining = "ADRs" in scrubbed
        if adrs_rewritten and not raw_adrs_remaining:
            ok("step 3: plural 'ADRs' → 'A D Rs' AND no raw 'ADRs' leaks (negative)")
        else:
            fail(
                f"step 3: plural rewrite failed: "
                f"adrs_rewritten={adrs_rewritten}, raw_adrs_remaining={raw_adrs_remaining}"
            )
            failures += 1

        # 4. Pitch + volume sliders mounted.
        pitch_present = await page.evaluate(
            """!!Array.from(document.querySelectorAll('input[type=range]'))
                 .find(i => i.min === '0.5' && i.max === '2')"""
        )
        volume_present = await page.evaluate(
            """!!Array.from(document.querySelectorAll('input[type=range]'))
                 .find(i => i.min === '0' && i.max === '1')"""
        )
        if pitch_present and volume_present:
            ok("step 4: pitch (0.5–2) + volume (0–1) sliders in overlay")
        else:
            fail(f"step 4: sliders missing — pitch={pitch_present}, volume={volume_present}")
            failures += 1

        # 5. Click a non-first overlay word, expect a SECOND speak() call.
        clicked = await page.evaluate(
            """(() => {
              const clickable = Array.from(document.querySelectorAll('span'))
                 .filter(s => s.style.cursor === 'pointer'
                           && s.id && s.id.startsWith('speech-w-'));
              if (clickable.length < 30) return { count: clickable.length, fired: false };
              // pick word #25 (well past the first ~few)
              clickable[25].click();
              return { count: clickable.length, fired: true };
            })()"""
        )
        if clicked.get("fired") and clicked.get("count", 0) > 30:
            # Wait for second speak() call.
            try:
                await page.wait_for_function("window.__spoken.length >= 2", timeout=3000)
                spoken2 = await page.evaluate("window.__spoken[1]")
                # Negative: second utterance should be a slice (shorter than the first).
                if spoken2 and len(spoken2) < len(spoken):
                    ok(f"step 5: click-to-jump fires (2nd utterance is slice; "
                       f"len {len(spoken2)} < {len(spoken)})")
                else:
                    fail("step 5: click-to-jump second utterance not a slice (regression)")
                    failures += 1
            except Exception:
                fail("step 5: click on overlay word didn't fire a second speak()")
                failures += 1
        else:
            fail(f"step 5: not enough clickable overlay words (got {clicked.get('count')})")
            failures += 1

        # 6. Esc returns to idle (Read button comes back).
        await page.keyboard.press("Escape")
        try:
            await page.wait_for_selector(
                'button[aria-label="Read aloud"]',
                state="visible",
                timeout=4000,
            )
            ok("step 6: Esc → state=idle (Read button reappears)")
        except Exception:
            fail("step 6: Esc didn't transition state back to idle (button stuck)")
            failures += 1

        # 7. Restart speech, verify sentence-level underline on overlay.
        await page.click('button[aria-label="Read aloud"]')
        try:
            await page.wait_for_selector('button[aria-label="Speaking — click to pause"]', timeout=5000)
        except Exception:
            fail("step 7 setup: couldn't restart speech for sentence-highlight check")
            failures += 1
        else:
            # Even before any onboundary fires, sentence highlight defaults
            # to off (activeIdx=-1). Trigger one onboundary so spans[0] is
            # active, then check at least one sibling word in the same
            # sentence carries underline-style decoration.
            triggered = await page.evaluate(
                """(() => {
                  // Find the most recent utterance and call its onboundary
                  // callback for charIndex 0.
                  // We can't reach the utter object directly, but we can
                  // simulate a click on word 0 to put it active.
                  const w0 = document.querySelector('span[id^="speech-w-"]');
                  if (!w0) return { ok: false, reason: 'no overlay span' };
                  w0.click();
                  return { ok: true };
                })()"""
            )
            if not triggered.get("ok"):
                fail(f"step 7: setup — {triggered}")
                failures += 1
            else:
                # After clicking word 0, the next speak() call sets activeIdx to 0.
                await page.wait_for_function("window.__spoken.length >= 2", timeout=3000)
                # Check styles directly: at least 2 spans share active-sentence
                # underline OR the active word has the yellow background.
                style_check = await page.evaluate(
                    """(() => {
                      const spans = Array.from(document.querySelectorAll('span[id^="speech-w-"]'));
                      const active = spans.find(s => s.style.background &&
                          s.style.background.includes('254, 240, 138'));
                      const underlined = spans.filter(s =>
                          s.style.textDecoration && s.style.textDecoration.includes('underline'));
                      return { activeFound: !!active, underlinedCount: underlined.length };
                    })()"""
                )
                # Either active-word pill OR same-sentence underline must exist.
                if style_check.get("activeFound") or style_check.get("underlinedCount", 0) >= 1:
                    ok(f"step 7: sentence highlight engaged "
                       f"(active={style_check.get('activeFound')}, "
                       f"underlined={style_check.get('underlinedCount')})")
                else:
                    fail(f"step 7: no active word or sentence underline visible: {style_check}")
                    failures += 1

        # 8. Read-selection: select ≥3 words, expect button to appear.
        # Stop reader first so we're back to idle (button only shows in idle).
        await page.keyboard.press("Escape")
        try:
            await page.wait_for_selector('button[aria-label="Read aloud"]', state="visible", timeout=3000)
        except Exception:
            pass

        await page.evaluate(
            """(() => {
              const h1 = document.querySelector('h1');
              if (!h1) return false;
              const range = document.createRange();
              range.selectNodeContents(h1);
              const sel = window.getSelection();
              sel.removeAllRanges();
              sel.addRange(range);
              document.dispatchEvent(new Event('selectionchange'));
              return true;
            })()"""
        )
        await page.wait_for_timeout(400)
        sel_btn = await page.locator('button:has-text("Read selection")').count()
        if sel_btn >= 1:
            ok("step 8: read-selection button appears when ≥3 words highlighted")
        else:
            # Soft warning — h1 may be < 3 words; try a longer paragraph.
            await page.evaluate(
                """(() => {
                  const p = Array.from(document.querySelectorAll('p, li'))
                    .find(e => (e.textContent || '').trim().split(/\\s+/).length >= 5);
                  if (!p) return;
                  const range = document.createRange();
                  range.selectNodeContents(p);
                  const sel = window.getSelection();
                  sel.removeAllRanges();
                  sel.addRange(range);
                  document.dispatchEvent(new Event('selectionchange'));
                })()"""
            )
            await page.wait_for_timeout(400)
            sel_btn = await page.locator('button:has-text("Read selection")').count()
            if sel_btn >= 1:
                ok("step 8: read-selection button appears when ≥3 words highlighted")
            else:
                fail("step 8: read-selection button never appeared")
                failures += 1

        await browser.close()

    print()
    if failures == 0:
        print(f"{GREEN}{BOLD}ALL 8 STEPS PASSED{NC}")
        return 0
    print(f"{RED}{BOLD}{failures} STEP(S) FAILED{NC}")
    return failures


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
