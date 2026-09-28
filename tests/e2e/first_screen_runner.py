"""Fresh-process Playwright checks of the first screen, isolated from pytest's event loop.

    python tests/e2e/first_screen_runner.py offline <base_url>
    python tests/e2e/first_screen_runner.py silent <base_url>

offline: every request not addressed to the local server is aborted. The page
must still load both typefaces from its own bytes and log no console error, and
it must not even try to reach another origin.

silent: on load the stage draws the server's real answer, and nothing is spoken,
played or announced until the primary action is pressed. After the press the
answer reaches a listener through one channel: one status line, one utterance.

handshake: the Evidence panel's MCP handshake succeeds against the server that
served the page, and a refused handshake prints the server's own reason.

skip: the skip link moves focus into main, not back to the document body.

voice: one voice per answer in the review dialogue, plus a short handover in
the status line that never repeats the answer; and "My screen reader speaks
the answers" hands every answer to the status line with the page's own voice
silent, on the stage and in the dialogue alike.

stale: a patch changed after a press never sits beside the previous patch's
answer. The stage returns to the new patch's silent answer, and the old
answer is neither shown nor spoken.
"""
import json
import re
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
        digests: list[dict] = []
        page.on("request", lambda r: digests.append(json.loads(r.post_data or "{}"))
                if r.url.endswith("/api/digest_semantic_diff") else None)
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
        # A page view never asks for a model: every digest before the press
        # names the local engine.
        assert digests and all(d.get("engine") == "local" for d in digests), digests
        seen_before_press = len(digests)
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
        # The server's answer now opens with the finding itself, so the
        # sentence on the first screen is the inverted comparison.
        assert "an authorization comparison was inverted" in snapshot
        expect(page.locator("#spokenPreview")).to_contain_text("user.role != 'admin'")
        assert "not played yet" in snapshot
        # The preview is the verdict sentence alone, and says so: the rest of
        # the answer is the change counts, spoken and printed by the press.
        expect(page.locator("#previewState")).to_contain_text("first sentence")
        assert "Modified" not in page.locator("#spokenPreview").inner_text()
        page.locator("#previewEngine").click()
        expect(page.locator("#previewEngineWhy")).to_contain_text("local heuristic")
        expect(page.locator("#previewEngineWhy")).to_contain_text("synthesis_mode: heuristic-local")
        assert page.evaluate("window.__probe.live") == [], "opening a disclosure is not an announcement"

        page.locator('[data-testid="primary-hero-action"]').click()
        expect(page.locator("#spokenPane")).to_contain_text("src/auth/permissions.py", timeout=30_000)
        expect(page.locator("#runStatus")).to_contain_text("Round trip")
        page.wait_for_timeout(3500)
        after = page.evaluate("window.__probe")
        # One channel: every live-region change the press caused is the status
        # line, and it names the round trip and hands over to the speech engine
        # rather than reading the answer over it a second time.
        regions = sorted({entry.split(":", 1)[0] for entry in after["live"]})
        print(json.dumps({"live_regions_written_by_the_press": regions,
                          "status": page.locator("#runStatus").inner_text()}, indent=1))
        assert regions == ["runStatus"], f"the press wrote to more than one live region: {regions}"
        status = page.locator("#runStatus").inner_text()
        assert "Speaking it now." in status, status
        assert "authorization comparison" not in status, "the status line must not repeat the spoken answer"
        assert after["speak"] == 1, f"the answer must be spoken exactly once: {after['speak']}"
        expect(page.locator("#spokenPane")).to_contain_text("an authorization comparison was inverted")
        print(json.dumps({"after_press": {"speak": after["speak"], "play": after["play"],
                                          "live_changes": len(after["live"])}}, indent=1))
        assert len(digests) == seen_before_press + 1
        assert "engine" not in digests[-1], "the press asks the server's default engine"
        assert after["play"] >= 1, "pressing the primary must play the cue"
        assert after["speak"] >= 1, "pressing the primary must speak the digest"
        assert after["live"], "the answer must be announced once the user asked for it"
        assert not page.locator("#previewState").is_visible(), "a played answer is no longer 'not played yet'"
        assert page.locator("#spokenPreview").inner_text().strip() == ""
        browser.close()


def handshake(base_url: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(base_url, wait_until="networkidle")
        expect(page.locator("#connPillText")).to_have_text("Online", timeout=20_000)
        page.locator("#runMcp").evaluate("button => button.click()")
        expect(page.locator("#mcpVersion")).to_have_text("2025-11-25", timeout=20_000)
        expect(page.locator("#mcpCount")).to_have_text(re.compile(r"^\d+$"), timeout=20_000)
        count = page.locator("#mcpCount").inner_text()
        print(json.dumps({"tools": count, "errors": errors}))
        assert int(count) > 0
        assert errors == [], errors

        # A refusal keeps its reason. The body is the server's own 403 shape.
        refusal = {"error": "origin_not_allowed",
                   "detail": "Origin 'http://example.test' is not permitted. Set VOLCAN_ALLOWED_ORIGINS to allow it."}
        page.route("**/mcp", lambda route: route.fulfill(
            status=403, content_type="application/json", body=json.dumps(refusal)))
        page.locator("#runMcp").evaluate("button => button.click()")
        expect(page.locator("#mcpPane")).to_contain_text("HTTP 403", timeout=20_000)
        expect(page.locator("#mcpPane")).to_contain_text("Set VOLCAN_ALLOWED_ORIGINS to allow it.")
        assert "The handshake failed: ." not in page.locator("#mcpPane").inner_text()
        browser.close()


def skip(base_url: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(base_url, wait_until="networkidle")
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.className") == "skip-link"
        page.keyboard.press("Enter")
        focused = page.evaluate("document.activeElement.id")
        print(json.dumps({"focused_after_skip": focused}))
        assert focused == "main", f"the skip link left focus on {focused or 'BODY'}"
        page.keyboard.press("Tab")
        inside = page.evaluate("!!document.activeElement.closest('main')")
        assert inside, "the next Tab after skipping must land inside main"
        browser.close()


def voice(base_url: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        context.add_init_script(PROBE_JS)
        page = context.new_page()
        page.goto(base_url, wait_until="networkidle")
        expect(page.locator("#stage")).to_have_attribute("data-preview", "ready", timeout=20_000)

        # The page's voice, the default: a dialogue turn is spoken and no live
        # region reads it a second time.
        page.locator("#openReview").click()
        expect(page.locator("#dialogueState")).to_have_text("OVERVIEW", timeout=20_000)
        page.wait_for_timeout(2000)
        page.evaluate("window.__probe.live = []; window.__probe.speak = 0")
        page.locator("#cmdSummary").click()
        expect(page.locator("#dialogueLog")).to_contain_text("an authorization comparison was inverted",
                                                             timeout=20_000)
        page.wait_for_timeout(2000)
        expect(page.locator("#reviewStatus")).to_have_text("Answered. Speaking it now.",
                                                            timeout=20_000)
        page_voice = page.evaluate("window.__probe")
        print(json.dumps({"page_voice": page_voice}, indent=1))
        assert page_voice["speak"] >= 1, "the page's voice did not speak the turn"
        regions = sorted({entry.split(":", 1)[0] for entry in page_voice["live"]})
        assert regions == ["reviewStatus"], (
            f"the turn must hand over to the status line only: {regions}")
        handover = page.locator("#reviewStatus").inner_text()
        assert "authorization comparison" not in handover, (
            "the handover must not repeat the spoken answer")

        # The listener's screen reader: nothing is spoken by the page, and the
        # whole turn is in the one status line.
        page.locator("#voiceMode").click()
        expect(page.locator("#voiceMode")).to_have_attribute("aria-pressed", "true")
        page.evaluate("window.__probe.live = []; window.__probe.speak = 0")
        page.locator("#cmdSummary").click()
        expect(page.locator("#reviewStatus")).to_contain_text("an authorization comparison was inverted",
                                                              timeout=20_000)
        page.wait_for_timeout(2000)
        reader = page.evaluate("window.__probe")
        regions = sorted({entry.split(":", 1)[0] for entry in reader["live"]})
        print(json.dumps({"reader_dialogue": {"speak": reader["speak"], "regions": regions}}, indent=1))
        assert reader["speak"] == 0, "the page spoke although the screen reader is the voice"
        assert regions == ["reviewStatus"], regions
        # The listener's screen reader gets the spoken form: operators named.
        status = page.locator("#reviewStatus").inner_text()
        assert "not equals" in status and "!=" not in status, status

        page.evaluate("window.__probe.live = []; window.__probe.speak = 0")
        page.locator('[data-testid="primary-hero-action"]').click()
        expect(page.locator("#runStatus")).to_contain_text("an authorization comparison was inverted",
                                                           timeout=20_000)
        page.wait_for_timeout(2500)
        hero = page.evaluate("window.__probe")
        regions = sorted({entry.split(":", 1)[0] for entry in hero["live"]})
        print(json.dumps({"reader_hero": {"speak": hero["speak"], "regions": regions}}, indent=1))
        assert hero["speak"] == 0 and regions == ["runStatus"], hero
        status = page.locator("#runStatus").inner_text()
        assert "not equals" in status and "!=" not in status, status

        # Remembered in this browser, and nothing is announced when restored.
        page.reload(wait_until="networkidle")
        expect(page.locator("#voiceMode")).to_have_attribute("aria-pressed", "true")
        assert page.evaluate("window.__probe.live") == []
        browser.close()


def stale(base_url: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        context.add_init_script(PROBE_JS)
        page = context.new_page()
        page.goto(base_url, wait_until="networkidle")
        expect(page.locator("#stage")).to_have_attribute("data-preview", "ready", timeout=20_000)
        page.locator('[data-testid="primary-hero-action"]').click()
        expect(page.locator("#spokenPane")).to_contain_text("an authorization comparison was inverted",
                                                            timeout=30_000)
        expect(page.locator("#securityAlert")).not_to_be_empty()
        # Switch the patch at once, before the cue has ended and the answer
        # has been spoken: the queued sentence belongs to the old patch.
        spoken_before = page.evaluate("window.__probe.speak")
        page.locator("#preset4").click()
        expect(page.locator("#patchFile")).to_have_text("src/utils/parser.py")
        expect(page.locator("#stage")).to_have_attribute("data-preview", "ready", timeout=20_000)
        expect(page.locator("#earconContour")).to_contain_text("Rising", timeout=20_000)
        page.wait_for_timeout(2500)
        state = {
            "spokenPane": page.locator("#spokenPane").inner_text().strip(),
            "securityAlert": page.locator("#securityAlert").inner_text().strip(),
            "preview": page.locator("#spokenPreview").inner_text().strip(),
            "meters_hidden": page.locator("#meters").is_hidden(),
            "earconPlayer": page.locator("#earconPlayer").inner_text().strip(),
            "speak_after_switch": page.evaluate("window.__probe.speak") - spoken_before,
        }
        print(json.dumps(state, indent=1))
        assert state["spokenPane"] == "", "the previous patch's answer is still on the stage"
        assert state["securityAlert"] == "", "the previous patch's finding is still on the stage"
        assert "permissions.py" not in state["preview"], state["preview"]
        assert state["meters_hidden"], "the meters still describe the previous patch"
        assert state["earconPlayer"] == "", "the replay button would play the previous patch's cue"
        assert state["speak_after_switch"] == 0, "the previous patch's answer was spoken after the switch"
        expect(page.locator("#previewState")).to_contain_text("not played yet")
        browser.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    modes = {"offline": offline, "silent": silent, "handshake": handshake, "skip": skip,
             "stale": stale, "voice": voice}
    modes[sys.argv[1]](sys.argv[2].rstrip("/"))
