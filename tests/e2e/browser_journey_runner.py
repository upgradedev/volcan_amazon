"""Fresh-process Playwright runner, isolated from pytest's Windows event loop."""
import sys

from playwright.sync_api import expect, sync_playwright


def main(base_url: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(base_url, wait_until="networkidle")
        expect(page.locator("#connLabel")).to_contain_text("Server reached")
        hero_box = page.locator("#runReview").bounding_box()
        assert hero_box is not None and hero_box["y"] + hero_box["height"] <= 720, (
            f"primary action is below the desktop fold: {hero_box}"
        )
        page.locator("#runMcp").click()
        expect(page.locator("#mcpStatus")).to_contain_text("Handshake complete", timeout=15_000)
        expect(page.locator("#mcpCount")).to_have_text("12")
        # The stage shows a silent preview on load; the live pane stays empty
        # until the press, so "not empty" is only true once the press answered.
        assert page.locator("#spokenPane").inner_text().strip() == ""
        page.locator("#runReview").click()
        expect(page.locator("#spokenPane")).to_contain_text("src/auth/permissions.py", timeout=30_000)
        expect(page.locator("#meterChange")).to_contain_text("file")
        expect(page.locator("#earconCaption")).not_to_contain_text("Nothing played yet")
        expect(page.locator("#brailleOutput")).not_to_have_text("")
        expect(page.locator("#runStatus")).to_contain_text("Round trip")

        phone = browser.new_page(viewport={"width": 375, "height": 720})
        phone.goto(base_url, wait_until="networkidle")
        phone_box = phone.locator("#runReview").bounding_box()
        assert phone_box is not None and phone_box["y"] + phone_box["height"] <= 720, (
            f"primary action is below the phone fold: {phone_box}"
        )
        phone.close()
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1])
