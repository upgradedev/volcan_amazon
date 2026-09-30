"""Fresh-process Playwright runner: the model-coverage display.

The server in CI has no model credentials, so no press can produce a
bedrock-shaped answer here. Instead the runner hands the page's own render
function a bedrock-shaped and a heuristic-shaped response and reads back the
DOM it builds: the coverage sentence, the full-answer disclosure, and their
absence on the heuristic path.
"""
import sys

from playwright.sync_api import expect, sync_playwright

BEDROCK = {
    "voice_summary": "In src/auth/permissions.py, an authorization comparison was inverted.",
    "synthesis_mode": "bedrock",
    "model_prose_full": "Complete model prose retained at adapter boundary.",
    "model_input_chars_sent": 3000,
    "model_input_chars_total": 4107,
}

HEURISTIC = {
    "voice_summary": "In src/auth/permissions.py, an authorization comparison was inverted.",
    "synthesis_mode": "heuristic-local",
    "model_prose_full": None,
    "model_input_chars_sent": None,
    "model_input_chars_total": None,
}


def main(base_url: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(base_url, wait_until="networkidle")
        page.evaluate(
            "(digest) => renderSpoken(digest, 12.5, 'Level 0 executive digest')", BEDROCK
        )
        expect(page.locator("#modelCoverage")).to_have_text(
            "The model read the first 3000 of 4107 patch characters; "
            "the local rules still read the whole patch."
        )
        expect(page.locator("#modelProseWrap")).to_be_visible()
        expect(page.locator("#modelProse")).to_have_text(
            "Complete model prose retained at adapter boundary."
        )
        page.evaluate(
            "(digest) => renderSpoken(digest, 3.1, 'Level 0 executive digest')", HEURISTIC
        )
        expect(page.locator("#modelCoverage")).to_have_text("")
        expect(page.locator("#modelProseWrap")).to_be_hidden()
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1])
