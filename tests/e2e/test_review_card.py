"""The review card on the companion page: how the page hosts it, and a real run.

The static tests read docs/index.html and hold the page to the host rules it
states: the card runs in an iframe sandboxed to scripts only, the page answers
only its own iframe, and the card's Confirm and Cancel run through the same
function the page's own buttons call. The browser test drives Chromium once
against a server whose GitHub is scripted (tests/fixtures/fake_github_server.py).
"""
import re
import sys

from tests.e2e.test_html_structure import parsed, read_html, script_body
from tests.fixtures.live_server import run_script, running_server

#: The child server is cut off from AWS and from a real GitHub token, so no
#: billed or outside call can start from it (see test_durable_server_journey.py).
ISOLATED_ENV = {
    "AWS_EC2_METADATA_DISABLED": "true",
    "AWS_CONFIG_FILE": "nonexistent-aws-config",
    "AWS_SHARED_CREDENTIALS_FILE": "nonexistent-aws-credentials",
    "AWS_ACCESS_KEY_ID": "",
    "AWS_SECRET_ACCESS_KEY": "",
    "AWS_SESSION_TOKEN": "",
    "AWS_PROFILE": "",
    "AWS_DEFAULT_PROFILE": "",
    "GITHUB_TOKEN": "",
    "VOLCAN_GITHUB_WRITE": "",
}


def test_the_card_frame_is_sandboxed_to_scripts_and_named():
    frames = parsed().of("iframe")
    assert len(frames) == 1
    frame = frames[0]
    assert frame["id"] == "reviewCardFrame"
    assert frame["sandbox"] == "allow-scripts", "no allow-same-origin: the card's origin stays opaque"
    assert "ui://volcan/review-card" in frame["title"]
    assert "src" not in frame, "the card arrives by resources/read, never by a URL"


def test_the_card_is_labelled_as_drawn_by_this_page():
    html = read_html()
    note = re.search(r'<p id="showCardNote">(.*?)</p>', html, flags=re.S).group(1)
    assert "Drawn by this page" in note
    assert "No Echo Show and no Alexa+" in note
    assert "resources/read" in note and "structuredContent" in note
    assert "Amazon" not in note.replace("Alexa+", ""), "no Amazon mark beyond naming what did not render it"


def test_the_page_answers_only_its_own_card_and_only_confirm_or_cancel():
    script = script_body()
    assert "event.source !== frame.contentWindow" in script
    assert 'transcript !== "confirm" && transcript !== "cancel"' in script
    assert 'params.name !== "review_dialogue_turn"' in script
    # The card's confirm is the page's confirm: the same function, so the
    # stored grant and the credential header apply, and its arguments are ignored.
    assert 'await sendTranscript(transcript, "card")' in script
    assert "params.arguments.approval_grant" not in script


def test_the_card_gets_the_restrictive_policy_and_the_extension_lifecycle():
    script = script_body()
    assert "connect-src 'none'" in script and "default-src 'none'" in script
    assert 'method: "resources/read", params: { uri: REVIEW_CARD_URI }' in script
    for method in ("ui/notifications/tool-input", "ui/notifications/tool-result",
                   "ui/notifications/size-changed", "ui/notifications/initialized"):
        assert method in script, method
    assert 'MCP_APPS_VERSION = "2026-01-26"' in script


def test_the_keyboard_map_states_what_works_inside_the_card():
    html = read_html()
    assert "Inside the review card" in html
    assert '"notifications/volcan/interrupt"' in script_body(), "Escape in the card still interrupts"


def test_a_real_browser_reaches_and_presses_the_card_controls_by_keyboard():
    launcher = [sys.executable, "tests/fixtures/fake_github_server.py"]
    with running_server(ISOLATED_ENV, launcher=launcher) as base_url:
        run = run_script("tests/e2e/review_card_runner.py", base_url, timeout=90)
        assert run.returncode == 0, run.stdout + run.stderr
