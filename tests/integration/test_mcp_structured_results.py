"""Structured results and the ui:// review card, over the MCP endpoint.

MCP revision 2025-11-25 (server/tools, "Output Schema"): when a tool publishes
an ``outputSchema``, the server MUST return structured results that conform to
it, and a tool that returns ``structuredContent`` SHOULD also return the same
JSON in a text block. These tests validate every structured result against
the published schema with a JSON Schema 2020-12 validator, the dialect the
specification defaults to, across the dialogue states a client can reach.

The resource half follows server/resources of the same revision and the MCP
Apps extension (SEP-1865, stable 2026-01-26): the card is listed, read as
``text/html;profile=mcp-app`` and linked from the tool through
``_meta.ui.resourceUri``.

No call leaves the process. GitHub is ``httpx.MockTransport`` and the model
adapter is told no credentials resolved, so every digest is the local engine.
"""
import json
import re

import httpx
import jsonschema
import pytest
from fastapi.testclient import TestClient

from src.interfaces.composition import bedrock_adapter, github_adapter
from src.interfaces.mcp_protocol import (
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    PROTOCOL_VERSION,
    RESOURCE_NOT_FOUND,
)
from src.interfaces.mcp_server import app
from src.interfaces.review_card_view import REVIEW_CARD_HTML
from tests.fixtures.fake_github import DIFF, PR_URL, FakeGitHub

client = TestClient(app)

STRUCTURED_TOOLS = ("digest_semantic_diff", "drill_down_section", "review_dialogue_turn")
CARD_URI = "ui://volcan/review-card"
CARD_MIME = "text/html;profile=mcp-app"

CLEAN_DIFF = (
    "diff --git a/src/utils/parser.py b/src/utils/parser.py\n"
    "--- a/src/utils/parser.py\n"
    "+++ b/src/utils/parser.py\n"
    "@@ -4,1 +4,3 @@ def normalise(data):\n"
    "-    return data.strip()\n"
    "+    if not data:\n"
    "+        return \"\"\n"
    "+    return data.strip()\n"
)


@pytest.fixture(autouse=True)
def local_only(monkeypatch):
    """No model call and no GitHub request can leave this process."""
    monkeypatch.setattr(bedrock_adapter, "credentials_present", lambda refresh=False: False)
    fake = FakeGitHub()
    saved = (github_adapter.transport, github_adapter.token, github_adapter.write_enabled)
    github_adapter.transport = httpx.MockTransport(fake)
    github_adapter.token = None
    github_adapter.write_enabled = False
    try:
        yield fake
    finally:
        github_adapter.transport, github_adapter.token, github_adapter.write_enabled = saved


def rpc(method: str, params: dict | None = None, request_id: int = 7) -> dict:
    response = client.post(
        "/mcp", headers={"MCP-Protocol-Version": PROTOCOL_VERSION},
        json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}},
    )
    assert response.status_code == 200, response.text
    return response.json()


def catalog() -> dict[str, dict]:
    return {tool["name"]: tool for tool in rpc("tools/list")["result"]["tools"]}


def call(name: str, arguments: dict) -> dict:
    body = rpc("tools/call", {"name": name, "arguments": arguments})
    assert "error" not in body, body
    result = body["result"]
    assert result["isError"] is False, result
    return result


def assert_conforms(name: str, result: dict, tools: dict[str, dict]) -> dict:
    """The result's structuredContent validates against the published schema."""
    assert "structuredContent" in result, f"{name} declares outputSchema but returned none"
    structured = result["structuredContent"]
    jsonschema.validate(structured, tools[name]["outputSchema"], cls=jsonschema.Draft202012Validator)
    # The serialized JSON in a text block, for clients that predate the field.
    assert json.loads(result["content"][-1]["text"]) == structured
    # Speech first: the first block is the sentence a listener hears.
    assert result["content"][0]["type"] == "text"
    assert not result["content"][0]["text"].lstrip().startswith("{")
    return structured


# --- the published schemas ---------------------------------------------------

def test_three_tools_publish_a_valid_strict_output_schema():
    tools = catalog()
    for name in STRUCTURED_TOOLS:
        schema = tools[name]["outputSchema"]
        jsonschema.Draft202012Validator.check_schema(schema)
        assert schema["type"] == "object"
        assert "title" not in schema, "the top-level title is dropped as it is for inputSchema"
        assert schema["additionalProperties"] is False, f"{name} must name every key it returns"
        assert schema["required"], f"{name} requires nothing"


def test_tools_without_structured_results_publish_no_output_schema():
    """A schema the tool never meets would make SDK clients reject its results."""
    for name, tool in catalog().items():
        if name not in STRUCTURED_TOOLS:
            assert "outputSchema" not in tool, name


# --- every structured result conforms -----------------------------------------

def test_the_digest_conforms_with_a_finding_and_with_no_rule_matched():
    tools = catalog()
    flagged = assert_conforms("digest_semantic_diff", call("digest_semantic_diff", {"raw_diff": DIFF}), tools)
    assert flagged["critical_findings"], "the inverted check must be named"
    assert flagged["synthesis_mode"] == "heuristic-local"
    clean = assert_conforms("digest_semantic_diff", call("digest_semantic_diff", {"raw_diff": CLEAN_DIFF, "level": 1}), tools)
    assert clean["critical_findings"] == []


def test_the_drill_down_conforms_for_a_flagged_and_an_unflagged_section():
    tools = catalog()
    flagged = assert_conforms("drill_down_section", call("drill_down_section", {"raw_diff": DIFF, "section_index": 0}), tools)
    assert flagged["security_findings"]
    plain = assert_conforms("drill_down_section", call("drill_down_section", {"raw_diff": DIFF, "section_index": 1}), tools)
    assert plain["security_flags"] == [] and plain["file_path"] == "src/utils/parser.py"


def review(session: str, transcript: str, tools: dict, **extra) -> dict:
    result = call("review_dialogue_turn", {"session_id": session, "transcript": transcript, **extra})
    return assert_conforms("review_dialogue_turn", result, tools)


def test_every_review_dialogue_state_conforms_and_carries_the_card():
    tools = catalog()
    session = "structured-journey"

    helped = review(session, "help", tools)
    assert helped["review_card"] is None, "no patch is open, so there is nothing to draw"

    opened = review(session, "open the pull request", tools, pr_url=PR_URL)
    card = opened["review_card"]
    assert opened["state"] == "OVERVIEW"
    assert card["resource_uri"] == CARD_URI
    assert card["file_path"] == "src/auth/permissions.py"
    assert "authorization comparison was inverted" in card["finding"]
    assert [line["kind"] for line in card["changed_lines"]] == ["removed", "added"]
    assert card["changed_lines"][1]["number"] == 14
    assert all(set(line["braille"]) <= {chr(c) for c in range(0x2800, 0x2900)} for line in card["changed_lines"])
    assert card["can_submit"] is True and card["awaiting_confirmation"] is False

    moved = review(session, "what changed in parser dot py", tools)
    assert moved["state"] == "FILE"
    assert moved["review_card"]["file_path"] == "src/utils/parser.py"
    assert moved["review_card"]["finding"] is None, "no rule matched in this file"

    lines = review(session, "read the lines", tools)
    assert lines["state"] == "LINES" and lines["line"] is not None

    unknown = review(session, "banana", tools)
    assert unknown["error"] is True, "an unrecognised command is still a conforming result"

    staged = review(session, "request changes: restore the equality check", tools)
    assert staged["state"] == "CONFIRM_REVIEW"
    assert staged["review_card"]["awaiting_confirmation"] is True
    assert staged["approval_grant"] and staged["pending_review"]["head_sha"] == "a" * 40

    done = review(session, "confirm", tools, approval_grant=staged["approval_grant"])
    assert done["state"] == "RECORDED"
    assert done["review_outcome"]["dry_run"] is True and done["review_outcome"]["submitted"] is False
    assert done["review_card"]["awaiting_confirmation"] is False

    again = review(session, "confirm", tools)
    assert again["approval_grant"] is None and again["pending_review"] is None
    assert not (again["review_outcome"] or {}).get("submitted"), "nothing is staged, so nothing is released"


def test_a_cancel_and_a_pasted_patch_conform():
    tools = catalog()
    review("structured-cancel", "open", tools, pr_url=PR_URL)
    review("structured-cancel", "request changes: please look again", tools)
    cancelled = review("structured-cancel", "cancel", tools)
    assert cancelled["awaiting_confirmation"] is False and cancelled["approval_grant"] is None

    pasted = review("structured-pasted", "open", tools, raw_diff=CLEAN_DIFF)
    assert pasted["pull_request"] is None
    assert pasted["review_card"]["can_submit"] is False


def test_a_forged_grant_from_any_surface_is_refused():
    """The card's Confirm is a tools/call like any other: the grant check still decides."""
    tools = catalog()
    review("structured-forged", "open", tools, pr_url=PR_URL)
    review("structured-forged", "request changes: restore the check", tools)
    refused = review("structured-forged", "confirm", tools, approval_grant="v1.forged.forged")
    assert refused["state"] == "REFUSED"
    assert refused["review_outcome"]["submitted"] is False
    assert refused["review_outcome"]["dry_run"] is False


# --- the card as an MCP resource ---------------------------------------------

def test_initialize_advertises_resources_without_subscribe():
    body = rpc("initialize", {
        "protocolVersion": PROTOCOL_VERSION, "capabilities": {},
        "clientInfo": {"name": "structured-test", "version": "1"},
    })
    assert body["result"]["capabilities"]["resources"] == {"listChanged": False}


def test_the_card_is_listed_and_read_as_an_mcp_apps_view():
    listed = rpc("resources/list")["result"]["resources"]
    entry = next(resource for resource in listed if resource["uri"] == CARD_URI)
    assert entry["mimeType"] == CARD_MIME and entry["name"] and entry["description"]

    contents = rpc("resources/read", {"uri": CARD_URI})["result"]["contents"]
    assert len(contents) == 1
    view = contents[0]
    assert view["uri"] == CARD_URI and view["mimeType"] == CARD_MIME
    assert view["text"].lower().startswith("<!doctype html>")
    assert view["_meta"] == {"ui": {"prefersBorder": True}}, "no csp domains: the restrictive default applies"


def test_the_review_tool_links_the_card_it_can_resolve():
    tool = catalog()["review_dialogue_turn"]
    uri = tool["_meta"]["ui"]["resourceUri"]
    assert uri == CARD_URI
    assert "visibility" not in tool["_meta"]["ui"], "the default, model and app, is meant"
    assert rpc("resources/read", {"uri": uri})["result"]["contents"][0]["uri"] == uri


def test_resource_errors_follow_the_specification():
    missing = rpc("resources/read", {"uri": "ui://volcan/no-such-card"})
    assert missing["error"]["code"] == RESOURCE_NOT_FOUND
    assert missing["error"]["data"] == {"uri": "ui://volcan/no-such-card"}
    assert rpc("resources/read", {})["error"]["code"] == INVALID_PARAMS
    assert rpc("resources/templates/list")["result"] == {"resourceTemplates": []}
    assert rpc("resources/subscribe", {"uri": CARD_URI})["error"]["code"] == METHOD_NOT_FOUND


# --- what the card's own code may do ------------------------------------------

def card_script() -> str:
    return "\n".join(re.findall(r"<script\b[^>]*>(.*?)</script>", REVIEW_CARD_HTML, flags=re.S))


def test_the_card_loads_nothing_and_writes_no_markup():
    script = card_script()
    assert not re.search(r"""(?:src|href)\s*=\s*["']https?:""", REVIEW_CARD_HTML)
    for banned in ("fetch(", "XMLHttpRequest", "WebSocket", "innerHTML", "outerHTML",
                   "insertAdjacentHTML", "document.write", "eval(", "localStorage"):
        assert banned not in script, banned


def test_the_card_speaks_the_extension_lifecycle():
    script = card_script()
    assert 'request("ui/initialize"' in script
    assert "appInfo" in script and "appCapabilities" in script and 'PROTOCOL = "2026-01-26"' in script
    assert 'notify("ui/notifications/initialized"' in script
    assert '"ui/notifications/tool-input"' in script and '"ui/notifications/tool-result"' in script
    assert 'notify("ui/notifications/size-changed"' in script
    assert "event.source !== window.parent" in script


def test_the_card_asks_only_for_confirm_or_cancel_and_only_on_a_press():
    script = card_script()
    calls = re.findall(r'request\("tools/call"', script)
    assert len(calls) == 1, "one place sends tools/call"
    assert re.findall(r'choose\("(\w+)"\)', script) == ["confirm", "cancel"]
    # choose() runs only from the two buttons' click handlers.
    assert len(re.findall(r"choose\(", script)) == 3, "the definition and the two click handlers"
    assert 'name: "review_dialogue_turn"' in script


def test_the_card_controls_are_labelled_buttons_and_motion_can_be_reduced():
    script = card_script()
    assert script.count('.type = "button"') == 2
    assert 'setAttribute("aria-label", "Confirm the request changes review")' in script
    assert 'setAttribute("aria-label", "Cancel the staged review")' in script
    assert "@media (prefers-reduced-motion: reduce)" in REVIEW_CARD_HTML
    assert "button:focus-visible" in REVIEW_CARD_HTML
    assert "not that the change is safe" in script, "a quiet file is never called safe"
