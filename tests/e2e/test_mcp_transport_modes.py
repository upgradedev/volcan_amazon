"""Both MCP transport modes, driven the way a judge drives them.

The public Lambda runs ``VOLCAN_MCP_SESSION_MODE=stateless``; a local run is
stateful by default. Each mode gets a real server, the terminal conformance
script (told which mode to expect, so a server in the wrong mode fails) and a
real Chromium pressing the page's handshake button.
"""
import pytest

from tests.fixtures.live_server import run_script, running_server


@pytest.mark.parametrize("mode", ["stateless", "stateful"])
def test_script_and_page_handshake_agree_with_the_transport_mode(mode):
    with running_server({"VOLCAN_MCP_SESSION_MODE": mode}) as base_url:
        report = run_script("scripts/mcp_conformance.py", f"{base_url}/mcp", "--expect-mode", mode)
        assert report.returncode == 0, report.stdout + report.stderr
        assert "0 failed" in report.stdout, report.stdout
        wording = "stateless, no id issued" if mode == "stateless" else "stateful, "
        assert wording in report.stdout, report.stdout

        journey = run_script("tests/e2e/mcp_transport_runner.py", base_url, mode)
        assert journey.returncode == 0, journey.stdout + journey.stderr


def test_the_conformance_script_fails_a_server_in_the_wrong_mode():
    with running_server({"VOLCAN_MCP_SESSION_MODE": "stateful"}) as base_url:
        report = run_script(
            "scripts/mcp_conformance.py", f"{base_url}/mcp", "--expect-mode", "stateless",
        )
    assert report.returncode == 1, report.stdout + report.stderr
    assert "[FAIL] transport declares" in report.stdout, report.stdout
