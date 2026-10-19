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
import sys

from playwright.sync_api import expect, sync_playwright

FILE = "src/auth/permissions.py"
LOCAL = "Inspecting src/auth/permissions.py: security sensitive, critical significance."
PROSE = "Inverted admin check. Non-admins can now delete workspaces. Revert the comparison."


def answered(model_id, words):
    said = f"{LOCAL} {words} on Amazon Bedrock says: Inverted admin check."
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
    return {
        "spoken_text": LOCAL,
        "spoken_text_for_speech": LOCAL,
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
            + FILE + "'s part of the patch. The local rules read the whole patch."
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
            + FILE + "'s part of the patch. The local rules read the whole patch."
        )

        # 4. Every branch where no model answered says so, with its reason.
        for reason in (REFUSAL, TIMEOUT, NO_CREDENTIALS):
            seen = press(not_answered(reason))
            print(json.dumps({"not_answered": seen}, indent=1))
            assert seen["engine"] == "local rules, no model answered", seen
            assert "No model answered, because: " + reason + "." in seen["note"], seen
            assert seen["coverage"] == "", seen
            assert "Amazon Bedrock" not in seen["engine"], seen
            assert "local rules" in seen["caption"], seen
            expect(page.locator("#modelProseWrap")).to_be_hidden()
            expect(page.locator("#spokenPane")).not_to_contain_text("Amazon Bedrock says")

        # 5. The server's own answer, unmodified: CI has no model, so the
        #    local rules answered and the page says why.
        seen = press(None)
        assert seen["engine"] == "local rules, no model answered", seen
        assert "No model answered, because: " in seen["note"], seen

        assert "local AST" not in page.locator("body").inner_text()
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1])
