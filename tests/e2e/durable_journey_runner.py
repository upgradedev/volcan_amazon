"""Fresh-process Playwright runner: the anonymous judge journey on a durable server.

Usage: python tests/e2e/durable_journey_runner.py <base_url>

The server runs the Phase 2 configuration (DynamoDB state, a Secrets Manager
approval secret, the stateless MCP transport) against in-memory fakes. A
visitor with no credential presses what a judge presses: the handshake, the
spoken review, then Stage, Approve and the audit trail that follows.
"""
import sys

from playwright.sync_api import expect, sync_playwright


def main(base_url: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        errors: list[str] = []
        failed: list[str] = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.on("response", lambda r: failed.append(f"{r.status} {r.url}") if r.status >= 400 else None)
        page.goto(base_url, wait_until="networkidle")
        expect(page.locator("#connLabel")).to_contain_text("Server reached")
        expect(page.locator("#stateDurability")).to_contain_text("shared table")

        page.locator("#runMcp").click()
        expect(page.locator("#mcpStatus")).to_contain_text("Handshake complete", timeout=15_000)
        assert "answered HTTP 202" in page.locator("#mcpPane .caption").inner_text()

        page.locator("#runReview").click()
        expect(page.locator("#spokenPane")).to_contain_text("src/auth/permissions.py", timeout=30_000)

        page.locator("#tabGov").click()
        page.locator("#stageBtn").click()
        expect(page.locator("#leaseTag")).to_contain_text("LEASE ACTIVE", timeout=15_000)
        page.locator("#approveBtn").click()
        expect(page.locator("#leaseTag")).to_have_text("GRANT ACCEPTED", timeout=15_000)
        vault = page.locator("#auditVault")
        expect(vault).to_contain_text("git diff HEAD", timeout=15_000)
        expect(vault).to_contain_text("released to you, nothing run")
        expect(vault).not_to_contain_text("could not be read")
        expect(page.locator("#auditNote")).to_be_visible()
        expect(page.locator("#auditNote")).to_contain_text("public demo chain")

        assert not failed, f"requests answered with an error status: {failed}"
        assert not errors, f"console errors: {errors}"
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1])
