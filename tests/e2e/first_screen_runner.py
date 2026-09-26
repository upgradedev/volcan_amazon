"""Fresh-process Playwright checks of the first screen, isolated from pytest's event loop.

    python tests/e2e/first_screen_runner.py offline <base_url>
    python tests/e2e/first_screen_runner.py silent <base_url>

offline: every request not addressed to the local server is aborted. The page
must still load both typefaces from its own bytes and log no console error, and
it must not even try to reach another origin.

silent: on load the stage draws the server's real answer, and nothing is spoken,
played or announced until the primary action is pressed.
"""
import json
import sys

from playwright.sync_api import expect, sync_playwright

FACES = (
    ("Atkinson Hyperlegible", "400"),
    ("Atkinson Hyperlegible", "700"),
    ("JetBrains Mono", "400"),
    ("JetBrains Mono", "600"),
)

FONTS_JS = """async (faces) => {
  const out = [];
  for (const [family, weight] of faces) {
    const spec = weight + ' 16px "' + family + '"';
    const loaded = await document.fonts.load(spec);
    out.push({
      spec: spec,
      loadedFaces: loaded.length,
      check: document.fonts.check(spec),
      registered: Array.from(document.fonts)
        .filter((f) => f.family.replace(/"/g, '') === family)
        .map((f) => ({ weight: f.weight, status: f.status }))
    });
  }
  return out;
}"""

# Installed before any page script runs: counts every attempt to make a sound
# and every change inside a live region, from the first byte of the document.
PROBE_JS = """
(() => {
  window.__probe = { speak: 0, play: 0, live: [] };
  if (window.speechSynthesis) {
    const original = window.speechSynthesis.speak.bind(window.speechSynthesis);
    window.speechSynthesis.speak = (u) => { window.__probe.speak += 1; return original(u); };
  }
  const play = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function () { window.__probe.play += 1; return play.apply(this, arguments); };
  const LIVE = '[aria-live]:not([aria-live="off"]), [role="status"], [role="alert"], [role="log"], [role="marquee"], [role="timer"]';
  const observer = new MutationObserver((records) => {
    for (const r of records) {
      const node = r.target.nodeType === 1 ? r.target : r.target.parentElement;
      const region = node && node.closest(LIVE);
      if (region) { window.__probe.live.push((region.id || region.tagName) + ':' + r.type); }
    }
  });
  const start = () => observer.observe(document.documentElement,
    { subtree: true, childList: true, characterData: true });
  if (document.documentElement) { start(); } else { document.addEventListener('readystatechange', start, { once: true }); }
})();
"""


def offline(base_url: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        refused: list[str] = []

        def gate(route):
            if route.request.url.startswith(base_url):
                route.continue_()
            else:
                refused.append(route.request.url)
                route.abort()

        context.route("**/*", gate)
        page = context.new_page()
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base_url, wait_until="networkidle")
        faces = page.evaluate(FONTS_JS, [list(f) for f in FACES])
        page.wait_for_timeout(500)
        print(json.dumps({"faces": faces, "refused": refused, "errors": errors}, indent=1))
        for face in faces:
            assert face["loadedFaces"] >= 1 and face["check"], f"typeface not loaded: {face}"
            assert face["registered"] and all(f["status"] == "loaded" for f in face["registered"]), face
        assert refused == [], f"the page tried to reach another origin: {refused}"
        assert errors == [], f"console errors: {errors}"
        browser.close()


def silent(base_url: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        context.add_init_script(PROBE_JS)
        page = context.new_page()
        page.goto(base_url, wait_until="networkidle")
        expect(page.locator("#stage")).to_have_attribute("data-preview", "ready", timeout=20_000)
        page.wait_for_timeout(1500)
        before = page.evaluate("window.__probe")
        snapshot = page.locator("#stage").aria_snapshot()
        print(json.dumps({"before_press": before}, indent=1))
        print(snapshot)

        assert before["speak"] == 0, f"speech started before the press: {before}"
        assert before["play"] == 0, f"audio played before the press: {before}"
        assert before["live"] == [], f"a live region changed before the press: {before['live']}"
        # The live panes stay empty until the user acts; the preview lives beside them.
        assert page.locator("#spokenPane").inner_text().strip() == ""
        assert page.locator("#runStatus").inner_text().strip() == ""
        assert page.locator("#securityAlert").inner_text().strip() == ""
        # What is on screen is the server's answer, labelled as not yet played.
        expect(page.locator("#previewState")).to_contain_text("not played yet")
        expect(page.locator("#spokenPreview")).to_contain_text("src/auth/permissions.py")
        assert page.locator("#brailleCells .bcell").count() > 0
        assert page.locator("#brailleOutput .row").count() > 0
        assert "not played yet" in (page.locator("#earconWave").get_attribute("aria-label") or "")
        assert "Security-sensitive changes" in snapshot
        assert "not played yet" in snapshot

        page.locator('[data-testid="primary-hero-action"]').click()
        expect(page.locator("#spokenPane")).to_contain_text("src/auth/permissions.py", timeout=30_000)
        expect(page.locator("#runStatus")).to_contain_text("Round trip")
        page.wait_for_timeout(3500)
        after = page.evaluate("window.__probe")
        print(json.dumps({"after_press": {"speak": after["speak"], "play": after["play"],
                                          "live_changes": len(after["live"])}}, indent=1))
        assert after["play"] >= 1, "pressing the primary must play the cue"
        assert after["speak"] >= 1, "pressing the primary must speak the digest"
        assert after["live"], "the answer must be announced once the user asked for it"
        browser.close()


if __name__ == "__main__":
    {"offline": offline, "silent": silent}[sys.argv[1]](sys.argv[2].rstrip("/"))
