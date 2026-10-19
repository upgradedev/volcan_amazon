"""Fresh-process Playwright runner: what the drill-down press shows and says.

The server in CI has no model credentials, so its own drill-down always comes
from the local rules. To see the model branch the runner lets the real request
reach the real server and then rewrites the model fields of the real response
(the earcon and the local sentence stay the server's own), in the shapes
``op_drill_down`` returns. It then presses the real Drill button with the
listener's screen reader as the voice, and reads back the meter label, the
coverage line, the full answer and the status line a screen reader and a
Braille display read.
"""
import json
import os
import sys

from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from src.application.digest_diff_use_case import model_words  # noqa: E402

FILE = "src/auth/permissions.py"
LOCAL = "Inspecting src/auth/permissions.py: security sensitive, critical significance."
PROSE = "Inverted admin check. Non-admins can now delete workspaces. Revert the comparison."


def answered(model_id, words):
    who = f"{words} on Amazon Bedrock" if model_id else "Amazon Bedrock, model not named,"
    said = f"{LOCAL} {who} says: Inverted admin check."
    return {
        "spoken_text": said,
        "spoken_text_for_speech": said,
        "synthesis_mode": "bedrock",
        "synthesis_fallback_reason": None,
        "model_prose_full": PROSE,
        "model_input_truncated": False,
        "model_input_chars_sent": 412,
        "model_input_chars_total": 412,
        "model_answered": model_id,
    }


def not_answered(reason):
    # The shape op_drill_down returns: the local finding, then the reason.
    said = f"{LOCAL} No model answered: {reason}."
    return {
        "spoken_text": said,
        "spoken_text_for_speech": said,
        "synthesis_mode": "heuristic-local",
        "synthesis_fallback_reason": reason,
        "model_prose_full": None,
        "model_input_truncated": False,
        "model_input_chars_sent": None,
        "model_input_chars_total": None,
        "model_answered": None,
    }


REFUSAL = ("The model's safety classifier declined to summarize this patch; "
           "the local deterministic digest answered instead")
TIMEOUT = ("Amazon Bedrock did not answer before the request deadline; "
           "the local deterministic digest answered instead")
NO_CREDENTIALS = "no AWS credentials were resolved by the boto3 credential chain"
MODEL_IDS = (
    "anthropic.claude-sonnet-5",
    "anthropic.claude-haiku-4-5",
    "eu.anthropic.claude-opus-4-8",
    "anthropic.claude-3-5-sonnet-20241022-v2:0",
    "a configured inference profile",
)


def main(base_url: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        # The listener's screen reader is the voice, so the answer goes to the
        # status line whole instead of to the browser's speech engine.
        context.add_init_script("try { localStorage.setItem('volcan.voice', 'reader'); } catch (e) {}")
        page = context.new_page()
        override = {"fields": None}

        def rewrite(route):
            response = route.fetch()
            body = response.json()
            if override["fields"] is not None:
                body.update(override["fields"])
            route.fulfill(response=response, json=body)

        page.route("**/api/drill_down_section", rewrite)
        page.goto(base_url, wait_until="networkidle")
        expect(page.locator("#voiceMode")).to_have_attribute("aria-pressed", "true")

        # 0a. The page names a model by the same rule as the server: run the
        #     page's own modelWords on the ids the Python rule is tested on.
        on_page = page.evaluate("ids => ids.map(id => modelWords(id))", list(MODEL_IDS))
        assert on_page == [model_words(model_id) for model_id in MODEL_IDS], on_page

        # 0b. The main digest, from this server with no model: its caption
        #     says no model answered and why, not "no model called".
        page.locator("#runReview").click()
        expect(page.locator("#spokenCaption")).to_contain_text(
            "returned in", timeout=20_000)
        expect(page.locator("#spokenCaption")).to_contain_text(
            "the local rules, no model answered (heuristic-local), because: " + NO_CREDENTIALS + ".")
        assert "no model called" not in page.locator("#spokenCaption").text_content()

        def press(fields):
            override["fields"] = fields
            page.evaluate("document.getElementById('runStatus').textContent = ''")
            page.locator("#drillDown").click()
            expect(page.locator("#runStatus")).to_contain_text("Drill down on " + FILE, timeout=20_000)
            return {
                "engine": page.evaluate("document.getElementById('meterEngine').firstChild.nodeValue"),
                "note": page.locator("#meterEngineNote").text_content(),
                "coverage": page.locator("#modelCoverage").text_content(),
                "status": page.locator("#runStatus").text_content(),
                "caption": page.locator("#spokenCaption").text_content(),
            }

        # 1. Claude answered: the label comes from model_answered.
        seen = press(answered("anthropic.claude-sonnet-5", "Claude Sonnet 5"))
        print(json.dumps({"answered": seen}, indent=1))
        assert seen["engine"] == "Claude Sonnet 5 on Amazon Bedrock", seen
        assert "model_answered: anthropic.claude-sonnet-5" in seen["note"], seen
        expect(page.locator("#modelCoverage")).to_have_text(
            "Claude Sonnet 5 on Amazon Bedrock read 412 of 412 characters of "
            + FILE + "'s part of the patch. The local rules read all of this file's changes."
        )
        expect(page.locator("#modelProseWrap")).to_be_visible()
        expect(page.locator("#modelProseWrap")).to_have_attribute("open", "")
        expect(page.locator("#modelProse")).to_have_text(PROSE)
        assert "Claude Sonnet 5 on Amazon Bedrock says: Inverted admin check." in seen["status"], seen
        expect(page.locator("#spokenPane")).to_contain_text("Claude Sonnet 5 on Amazon Bedrock says:")
        assert "Claude Sonnet 5 on Amazon Bedrock" in seen["caption"], seen

        # 2. Another model id is named as itself: no constant on the page.
        seen = press(answered("anthropic.claude-haiku-4-5", "Claude Haiku 4.5"))
        assert seen["engine"] == "Claude Haiku 4.5 on Amazon Bedrock", seen
        assert "Claude Sonnet 5" not in seen["coverage"], seen

        # 3. A prefix is reported as a prefix.
        prefix = answered("anthropic.claude-sonnet-5", "Claude Sonnet 5")
        prefix.update({"model_input_truncated": True, "model_input_chars_sent": 3000,
                       "model_input_chars_total": 4107})
        press(prefix)
        expect(page.locator("#modelCoverage")).to_have_text(
            "Claude Sonnet 5 on Amazon Bedrock read the first 3000 of 4107 characters of "
            + FILE + "'s part of the patch. The local rules read all of this file's changes."
        )

        # 3b. A Bedrock answer that names no model is still labelled a model
        #     answer, with no invented name.
        seen = press(answered(None, None))
        assert seen["engine"] == "Amazon Bedrock, model not named", seen
        assert "model_answered: null." in seen["note"], seen
        assert "No model answered" not in seen["note"], seen
        expect(page.locator("#modelCoverage")).to_have_text(
            "The model on Amazon Bedrock read 412 of 412 characters of "
            + FILE + "'s part of the patch. The local rules read all of this file's changes."
        )
        expect(page.locator("#modelProse")).to_have_text(PROSE)

        # 4. Every branch where no model answered says so, with its reason.
        for reason in (REFUSAL, TIMEOUT, NO_CREDENTIALS):
            seen = press(not_answered(reason))
            print(json.dumps({"not_answered": seen}, indent=1))
            assert seen["engine"] == "local rules, no model answered", seen
            assert "No model answered, because: " + reason + "." in seen["note"], seen
            assert seen["coverage"] == "", seen
            assert "Amazon Bedrock" not in seen["engine"], seen
            assert "local rules" in seen["caption"], seen
            # The status line a screen reader and a Braille display read
            # carries the reason, not only the meter.
            assert "No model answered: " + reason + "." in seen["status"], seen
            expect(page.locator("#modelProseWrap")).to_be_hidden()
            expect(page.locator("#spokenPane")).not_to_contain_text("Amazon Bedrock says")

        # 5. The server's own answer, unmodified: CI has no model, so the
        #    local rules answered and the page says why.
        seen = press(None)
        assert seen["engine"] == "local rules, no model answered", seen
        assert "No model answered, because: " + NO_CREDENTIALS + "." in seen["note"], seen
        assert "No model answered: " + NO_CREDENTIALS + "." in seen["status"], seen

        assert "local AST" not in page.locator("body").inner_text()
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1])
