"""Fresh-process Playwright runner, isolated from pytest's Windows event loop."""
import sys

from playwright.sync_api import expect, sync_playwright


def main(base_url: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(base_url, wait_until="networkidle")
        expect(page.locator("#connLabel")).to_contain_text("Server reached")
        page.locator("#runReview").click()
        expect(page.locator("#spokenPane")).not_to_contain_text("Nothing spoken yet")
        expect(page.locator("#meterChange")).to_contain_text("file")
        expect(page.locator("#earconCaption")).not_to_contain_text("Nothing played yet")
        expect(page.locator("#brailleOutput")).not_to_have_text("")
        expect(page.locator("#runStatus")).to_contain_text("Round trip")
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1])
