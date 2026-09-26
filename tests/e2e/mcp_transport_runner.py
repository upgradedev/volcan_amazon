"""Fresh-process Playwright runner: the page's MCP handshake in one transport mode.

Usage: python tests/e2e/mcp_transport_runner.py <base_url> <stateful|stateless>

Every /mcp request the page sends is recorded with its headers. In stateless
mode the server issues no Mcp-Session-Id, so no request may carry one: a header
built from an id the server never returned is answered 404 and the handshake
report would then be false. The notification must be answered 202 and the page
must say so, and "End the MCP session" must describe the transport truthfully.
"""
import sys

from playwright.sync_api import expect, sync_playwright


def main(base_url: str, mode: str) -> None:
    assert mode in {"stateful", "stateless"}, mode
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        # (method, Mcp-Session-Id header or None, HTTP status) per /mcp exchange.
        sent: list[tuple[str, str | None, int]] = []

        def on_response(response):
            if response.url.endswith("/mcp"):
                request = response.request
                sent.append((request.method, request.headers.get("mcp-session-id"), response.status))

        page.on("response", on_response)
        page.goto(base_url, wait_until="networkidle")
        expect(page.locator("#connLabel")).to_contain_text("Server reached")

        page.locator("#runMcp").click()
        expect(page.locator("#mcpStatus")).to_contain_text("Handshake complete", timeout=15_000)
        caption = page.locator("#mcpPane .caption").inner_text()
        assert "notifications/initialized answered HTTP 202" in caption, caption
        page.wait_for_load_state("networkidle")

        posts = [entry for entry in sent if entry[0] == "POST"]
        assert len(posts) == 3, f"expected initialize, notification and tools/list: {sent}"
        statuses = [entry[2] for entry in posts]
        assert statuses == [200, 202, 200], f"/mcp answered {statuses}"
        session_text = page.locator("#mcpSession").inner_text()
        if mode == "stateless":
            carried = [entry[1] for entry in sent if entry[1] is not None]
            assert not carried, f"stateless transport, but the page sent Mcp-Session-Id {carried}"
            assert "none" in session_text and "stateless" in session_text, session_text
        else:
            issued = posts[1][1]
            assert issued and len(issued) >= 32, f"no session id on the notification: {sent}"
            assert all(entry[1] == issued for entry in posts[1:]), sent
            assert session_text.endswith("..."), session_text

        page.locator("#endMcp").click()
        if mode == "stateless":
            expect(page.locator("#mcpStatus")).to_contain_text("stateless")
            assert not [entry for entry in sent if entry[0] == "DELETE"], sent
        else:
            expect(page.locator("#mcpStatus")).to_contain_text("DELETE /mcp answered HTTP 204")
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
