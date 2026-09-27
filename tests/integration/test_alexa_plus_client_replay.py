"""Amazon's documented Alexa+ MCP client requests, replayed against Volcan.

Built and tested locally, not certified or deployed; needs the owner's Amazon
developer account. Alexa+ has never called this server. The bodies come from
Amazon's "Alexa+ MCP Client and App Lifecycle" page (see
``tests/fixtures/alexa_plus_envelopes.py`` for the URL and date). That page
shows bodies without headers, so both header cases are pinned here: with the
``MCP-Protocol-Version`` header the documented session works end to end, and
without it Volcan refuses every request after initialize. The second outcome is
an open integration risk recorded in docs/EVIDENCE.md, not a behaviour this
test endorses.
"""
import json
import os

import pytest
from fastapi.testclient import TestClient

from scripts.replay_alexa_plus_envelopes import EXPECTED_FINDING, replay
from scripts.validate_alexa_addon import DEFAULT_PATH, validate
from src.interfaces.mcp_server import app
from tests.fixtures import alexa_plus_envelopes as envelopes

client = TestClient(app)


def _post(payload, headers):
    response = client.post("/mcp", json=payload, headers=headers)
    body = response.json() if response.content else ""
    return response.status_code, {k.lower(): v for k, v in response.headers.items()}, body


@pytest.mark.parametrize("version", envelopes.DOCUMENTED_VERSIONS)
def test_a_spec_following_client_completes_the_documented_session_and_hears_the_finding(version):
    """Whichever documented revision it asks for, it is answered 2025-11-25,
    adopts it, sends that revision's header, and the digest names the finding."""
    run = replay(_post, version, client="spec")
    assert run["negotiated"] == "2025-11-25"
    assert run["version_header_sent"]
    assert [step["ok"] for step in run["steps"]] == [True, True, True, True]
    listed = run["steps"][2]["body"]["result"]["tools"]
    assert "digest_semantic_diff" in {tool["name"] for tool in listed}
    assert run["finding_in_spoken_text"], run["steps"][3]["summary"]


@pytest.mark.parametrize("version", envelopes.DOCUMENTED_VERSIONS)
def test_a_client_that_declares_the_revision_it_asked_for_completes_the_session(version):
    """The third shape: it ignores the answer and sends the revision it asked
    for as its header. For 2025-03-26 this was served before 2026-09-27,
    refused by 76f017c, and is served again."""
    run = replay(_post, version, client="own")
    assert run["negotiated"] == "2025-11-25"
    assert run["version_header"] == version
    assert [step["ok"] for step in run["steps"]] == [True, True, True, True]
    assert run["finding_in_spoken_text"], run["steps"][3]["summary"]


@pytest.mark.parametrize("version", envelopes.DOCUMENTED_VERSIONS)
def test_a_client_that_never_sends_the_version_header_is_refused_after_initialize(version):
    """Recorded, not endorsed: a client that only knows 2025-03-26 never sends it."""
    run = replay(_post, version, client="never")
    assert not run["version_header_sent"]
    assert run["steps"][0]["ok"]
    for step in run["steps"][1:]:
        assert not step["ok"]
        assert "Missing MCP-Protocol-Version header" in step["summary"]


def test_the_documented_initialize_is_copied_from_amazon_unchanged():
    body = envelopes.DOCUMENTED_INITIALIZE
    assert body["id"] == "4e3bdaee-0"
    assert body["params"]["protocolVersion"] == "2025-03-26"
    assert body["params"]["clientInfo"] == {"name": "Alexa+ MCP Client", "version": "1.0.0"}
    assert envelopes.DOCUMENTED_TOOL_CALL["params"]["name"] == "search_hotels"


def test_the_expected_finding_is_the_one_the_page_shows():
    assert EXPECTED_FINDING == "an authorization comparison was inverted"


# --- the add-on package ------------------------------------------------------

def _manifest():
    with open(DEFAULT_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def test_the_committed_addon_package_passes_the_documented_schema():
    problems, placeholders = validate(_manifest())
    assert problems == []
    # The owner's own privacy page, terms page, six icons and one carousel image.
    assert len(placeholders) == 9
    assert all(".invalid/" in item for item in placeholders)


def test_the_package_points_at_an_mcp_endpoint_over_https():
    integration = _manifest()["integrations"][0]
    assert integration["type"] == "MCP"
    uri = integration["config"]["endpoints"]["default"]["uri"]
    assert uri.startswith("https://") and uri.endswith("/mcp")


@pytest.mark.parametrize("mutate, message", [
    (lambda m: m["storeListing"]["locales"]["en-US"]["name"].update(value="V" * 31), "name.value"),
    (lambda m: m["storeListing"]["locales"]["en-US"].update(shortDescription="x" * 124), "shortDescription"),
    (lambda m: m["storeListing"]["locales"]["en-US"].update(examplePhrases=["one", "two"]), "examplePhrases"),
    (lambda m: m["storeListing"]["locales"]["en-US"]["mediaAssets"]["icons"]["light"].pop(), "six sizes"),
    (lambda m: m["integrations"][0]["config"]["endpoints"]["default"].update(uri="http://x.example/mcp"), "HTTPS"),
    (lambda m: m["integrations"][0].update(type="LAMBDA"), "\"MCP\""),
    (lambda m: m.update(manifestVersion="2.0"), "manifestVersion"),
])
def test_each_documented_constraint_is_enforced(mutate, message):
    manifest = _manifest()
    mutate(manifest)
    problems, _ = validate(manifest)
    assert any(message in problem for problem in problems), problems


def test_the_package_lives_where_the_cli_scaffold_puts_it():
    assert DEFAULT_PATH.replace(os.sep, "/").endswith("alexa_plus/addon-package/addon.json")
