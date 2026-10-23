"""Fresh-process Playwright runner for the review card on the companion page.

It opens the scripted pull request, stages a review, reaches the card's
Confirm and Cancel with real Tab presses, reads their accessible names by
role, and presses Enter on Confirm. The server is
tests/fixtures/fake_github_server.py, so the pull request is the scripted one
and the outcome is the dry-run default.
"""
import sys

from playwright.sync_api import expect, sync_playwright

PR_URL = "https://github.com/octo/demo/pull/7"
CONFIRM_NAME = "Confirm the request changes review"
CANCEL_NAME = "Cancel the staged review"


def focused_in_card(frame) -> str:
    return frame.evaluate("document.activeElement ? document.activeElement.id : ''")


def main(base_url: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.emulate_media(reduced_motion="reduce")
        page.goto(base_url, wait_until="networkidle")
        expect(page.locator("#connLabel")).to_contain_text("Server reached")
        expect(page.locator("#showCardNote")).to_contain_text("No Echo Show and no Alexa+")
        assert page.locator("#reviewCardFrame").is_hidden(), "no card before the first turn"

        page.locator("#prUrl").fill(PR_URL)
        page.locator("#openReview").click()
        expect(page.locator("#reviewCardFrame")).to_be_visible(timeout=20_000)
        assert page.locator("#reviewCardFrame").get_attribute("sandbox") == "allow-scripts"
        card = page.frame_locator("#reviewCardFrame")
        expect(card.locator("#cardFile")).to_contain_text("src/auth/permissions.py", timeout=10_000)
        expect(card.locator("#cardFinding")).to_contain_text("authorization comparison was inverted")
        expect(card.locator("ol.lines li")).to_have_count(2)
        expect(card.get_by_role("img", name="The same line in eight-dot code Braille").first).to_be_visible()
        expect(card.get_by_role("button", name=CONFIRM_NAME)).to_have_count(0)

        page.locator("#reviewComment").fill("Restore the equality check")
        page.locator("#cmdRequestChanges").click()
        confirm = card.get_by_role("button", name=CONFIRM_NAME)
        cancel = card.get_by_role("button", name=CANCEL_NAME)
        expect(confirm).to_be_visible(timeout=15_000)
        expect(cancel).to_be_visible()
        expect(card.get_by_role("group", name="Confirm or cancel the staged review")).to_be_visible()

        # Keyboard only from here: the control before the card, then Tab.
        frame = page.locator("#reviewCardFrame").element_handle().content_frame()
        page.locator("#keymapOpenReview").focus()
        reached = []
        for _ in range(12):
            page.keyboard.press("Tab")
            current = focused_in_card(frame)
            reached.append(current)
            if current == "cardConfirm":
                break
        assert "cardConfirm" in reached, f"Tab never reached Confirm inside the card: {reached}"
        page.keyboard.press("Tab")
        assert focused_in_card(frame) == "cardCancel", "Cancel follows Confirm in the tab order"
        page.keyboard.press("Shift+Tab")
        assert focused_in_card(frame) == "cardConfirm"
        # A failed host call must expose the error and retain the staged
        # context/keyboard controls. The next press retries through the host.
        def reject_confirmation(route):
            route.fulfill(status=500, json={"detail": "Scripted temporary host failure"})

        page.route("**/api/review/turn", reject_confirmation)
        page.keyboard.press("Enter")
        expect(card.locator("#cardError")).to_contain_text("The host did not run confirm")
        expect(page.locator("#reviewStatus")).to_contain_text("Scripted temporary host failure")
        assert focused_in_card(frame) == "cardError"
        expect(confirm).to_be_visible()
        expect(cancel).to_be_visible()
        page.unroute("**/api/review/turn", reject_confirmation)
        confirm.focus()
        page.keyboard.press("Enter")

        expect(page.locator("#dialogueLog")).to_contain_text("Pressed in the review card: confirm", timeout=15_000)
        expect(page.locator("#dialogueLog")).to_contain_text("Dry run. Nothing was sent to GitHub.")
        expect(page.locator("#dialogueState")).to_have_text("RECORDED, NOT SENT")
        outcome = card.locator("#cardOutcome")
        expect(outcome).to_contain_text("Dry run")
        assert outcome.get_attribute("data-kind") == "recorded"
        assert focused_in_card(frame) == "cardOutcome", "focus follows the answer"
        expect(confirm).to_have_count(0)
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1])
