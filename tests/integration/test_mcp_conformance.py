"""Conformance tests for the MCP Streamable HTTP server (revision 2025-11-25).

These run the full client handshake through FastAPI's TestClient:

    initialize -> notifications/initialized -> tools/list -> tools/call

and then assert the failure modes that separate a real protocol server from a
JSON endpoint wearing the name: unknown sessions, the protocol version header (resolved when missing,
refused with HTTP 400 when unsupported),
each JSON-RPC error code, notification semantics, tool errors that stay inside
the result, and the Allow header on an unsupported HTTP method.
"""
import base64
import json
import os

import pytest
from fastapi.testclient import TestClient

from src.interfaces.mcp_protocol import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    PROTOCOL_VERSION,
)
from src.interfaces.mcp_server import app

client = TestClient(app)

SAMPLE_DIFF = """diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
@@ -1 +1,2 @@
+    secret_token = os.environ["API_SECRET"]
"""


def initialize() -> tuple[str, dict]:
    """Performs the initialize handshake and returns (session_id, result)."""
    response = client.post("/mcp", json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "volcan-conformance", "version": "1.0"},
        },
    })
    assert response.status_code == 200, response.text
    session_id = response.headers.get("mcp-session-id")
    assert session_id, "initialize must issue an Mcp-Session-Id header"
    return session_id, response.json()["result"]


def headers_for(session_id: str) -> dict[str, str]:
    return {"Mcp-Session-Id": session_id, "MCP-Protocol-Version": PROTOCOL_VERSION}


# --- handshake --------------------------------------------------------------

def test_initialize_returns_protocol_version_capabilities_and_server_info():
    session_id, result = initialize()
    assert result["protocolVersion"] == PROTOCOL_VERSION
    # tools, and resources for the ui:// review card; neither announces changes.
    assert result["capabilities"] == {"tools": {"listChanged": False}, "resources": {"listChanged": False}}
    assert result["serverInfo"]["name"]
    assert result["serverInfo"]["version"]
    assert len(session_id) >= 32, "session id must be cryptographically sized"


REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def _read_repo_file(name: str) -> str:
    with open(os.path.join(REPO_ROOT, name), "r", encoding="utf-8") as handle:
        return handle.read()


def test_initialize_instructions_name_the_same_audience_as_the_readme():
    """G1: the initialize instructions must name the audience the page and the
    README's first sentence name: blind and low-vision developers."""
    _, result = initialize()
    assert "blind and low-vision" in result["instructions"]
    assert "mobility-impaired" not in result["instructions"]
    readme = _read_repo_file("README.md")
    first = next(line for line in readme.splitlines() if "Volcan lets" in line)
    assert "blind and low-vision" in first


def test_two_initializations_issue_different_session_ids():
    first, _ = initialize()
    second, _ = initialize()
    assert first != second


def test_stateless_transport_omits_session_affinity(monkeypatch):
    """Transport requests work without an MCP id; app state is still process-local."""
    monkeypatch.setenv("VOLCAN_MCP_SESSION_MODE", "stateless")
    initialized = client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}},
    })
    assert initialized.status_code == 200
    assert "mcp-session-id" not in initialized.headers

    listed = client.post(
        "/mcp",
        headers={"MCP-Protocol-Version": PROTOCOL_VERSION},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    assert listed.status_code == 200
    assert listed.json()["result"]["tools"]

    deleted = client.delete(
        "/mcp", headers={"MCP-Protocol-Version": PROTOCOL_VERSION},
    )
    assert deleted.status_code == 405
    assert deleted.json()["error"] == "stateless_transport"


def test_initialized_notification_returns_202_with_no_body():
    session_id, _ = initialize()
    response = client.post(
        "/mcp",
        headers=headers_for(session_id),
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )
    assert response.status_code == 202
    assert response.content == b""


def test_protocol_version_header_is_echoed():
    session_id, _ = initialize()
    response = client.post(
        "/mcp", headers=headers_for(session_id),
        json={"jsonrpc": "2.0", "id": 2, "method": "ping"},
    )
    assert response.headers["mcp-protocol-version"] == PROTOCOL_VERSION
    assert response.json()["result"] == {}


def test_full_handshake_then_tools_list_then_tools_call():
    session_id, _ = initialize()

    initialized = client.post(
        "/mcp", headers=headers_for(session_id),
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )
    assert initialized.status_code == 202

    listing = client.post(
        "/mcp", headers=headers_for(session_id),
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    assert listing.status_code == 200
    tools = listing.json()["result"]["tools"]
    assert len(tools) >= 10
    names = {tool["name"] for tool in tools}
    assert {"digest_semantic_diff", "play_earcon", "stage_governed_action"} <= names

    call = client.post("/mcp", headers=headers_for(session_id), json={
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "digest_semantic_diff", "arguments": {"raw_diff": SAMPLE_DIFF, "level": 0}},
    })
    assert call.status_code == 200
    result = call.json()["result"]
    assert result["isError"] is False
    assert result["content"][0]["type"] == "text"
    assert result["content"][1]["type"] == "audio"


# --- tool catalog schemas ---------------------------------------------------

def test_every_tool_advertises_a_json_schema_object():
    session_id, _ = initialize()
    listing = client.post(
        "/mcp", headers=headers_for(session_id),
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    for tool in listing.json()["result"]["tools"]:
        assert tool["name"]
        assert tool["description"]
        schema = tool["inputSchema"]
        assert schema["type"] == "object"
        assert isinstance(schema["properties"], dict)
        assert schema["properties"], f"{tool['name']} advertises no properties"


def test_input_schema_tracks_the_pydantic_model_field_names():
    """Renaming a request-model field must break this test, not drift silently."""
    session_id, _ = initialize()
    listing = client.post(
        "/mcp", headers=headers_for(session_id),
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    by_name = {tool["name"]: tool for tool in listing.json()["result"]["tools"]}

    digest_props = by_name["digest_semantic_diff"]["inputSchema"]["properties"]
    assert set(digest_props) == {"raw_diff", "level"}
    assert by_name["digest_semantic_diff"]["inputSchema"]["required"] == ["raw_diff"]

    stage_props = by_name["stage_governed_action"]["inputSchema"]["properties"]
    assert {"action_id", "action_type", "command", "summary_spoken", "lease_sec"} <= set(stage_props)

    confirm_props = by_name["confirm_governed_action"]["inputSchema"]["properties"]
    assert "approval_grant" in confirm_props


# --- audio content block ----------------------------------------------------

def test_play_earcon_returns_a_playable_audio_content_block():
    session_id, _ = initialize()
    call = client.post("/mcp", headers=headers_for(session_id), json={
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "play_earcon", "arguments": {"earcon_type": "ACTION_COMMITTED"}},
    })
    result = call.json()["result"]
    assert result["isError"] is False
    audio = result["content"][0]
    assert audio["type"] == "audio"
    assert audio["mimeType"] == "audio/wav"
    decoded = base64.b64decode(audio["data"])
    assert decoded.startswith(b"RIFF")
    assert b"WAVE" in decoded[:16]
    assert len(decoded) > 1000


# --- error codes ------------------------------------------------------------

def test_parse_error_minus_32700():
    response = client.post(
        "/mcp",
        headers={"MCP-Protocol-Version": PROTOCOL_VERSION, "Content-Type": "application/json"},
        content=b"{not json",
    )
    assert response.json()["error"]["code"] == PARSE_ERROR


def test_invalid_request_minus_32600_for_wrong_jsonrpc_version():
    response = client.post(
        "/mcp", headers={"MCP-Protocol-Version": PROTOCOL_VERSION},
        json={"jsonrpc": "1.0", "id": 1, "method": "ping"},
    )
    assert response.json()["error"]["code"] == INVALID_REQUEST


def test_invalid_request_minus_32600_for_a_batched_array():
    response = client.post(
        "/mcp", headers={"MCP-Protocol-Version": PROTOCOL_VERSION},
        json=[{"jsonrpc": "2.0", "id": 1, "method": "ping"}],
    )
    assert response.json()["error"]["code"] == INVALID_REQUEST
    assert "batch" in response.json()["error"]["message"].lower()


def test_method_not_found_minus_32601():
    session_id, _ = initialize()
    response = client.post(
        "/mcp", headers=headers_for(session_id),
        json={"jsonrpc": "2.0", "id": 9, "method": "prompts/list"},
    )
    assert response.json()["error"]["code"] == METHOD_NOT_FOUND


def test_invalid_params_minus_32602_for_unknown_tool():
    session_id, _ = initialize()
    response = client.post("/mcp", headers=headers_for(session_id), json={
        "jsonrpc": "2.0", "id": 10, "method": "tools/call",
        "params": {"name": "definitely_not_a_tool", "arguments": {}},
    })
    error = response.json()["error"]
    assert error["code"] == INVALID_PARAMS
    assert "available" in error["data"]


def test_invalid_params_minus_32602_for_arguments_failing_the_schema():
    session_id, _ = initialize()
    response = client.post("/mcp", headers=headers_for(session_id), json={
        "jsonrpc": "2.0", "id": 11, "method": "tools/call",
        "params": {"name": "digest_semantic_diff", "arguments": {"level": "not-an-int"}},
    })
    assert response.json()["error"]["code"] == INVALID_PARAMS


def test_tool_failure_is_reported_as_is_error_not_as_a_transport_error():
    session_id, _ = initialize()
    response = client.post("/mcp", headers=headers_for(session_id), json={
        "jsonrpc": "2.0", "id": 12, "method": "tools/call",
        "params": {"name": "play_earcon", "arguments": {"earcon_type": "NO_SUCH_EARCON"}},
    })
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is True
    assert "failed" in result["content"][0]["text"].lower()


def test_request_without_an_id_that_is_not_a_notification_is_invalid():
    response = client.post(
        "/mcp", headers={"MCP-Protocol-Version": PROTOCOL_VERSION},
        json={"jsonrpc": "2.0", "method": "tools/list"},
    )
    assert response.json()["error"]["code"] == INVALID_REQUEST


# --- session and protocol version rules -------------------------------------

def test_unknown_session_id_is_rejected_with_http_404():
    response = client.post(
        "/mcp",
        headers={"Mcp-Session-Id": "a-session-this-server-never-issued",
                 "MCP-Protocol-Version": PROTOCOL_VERSION},
        json={"jsonrpc": "2.0", "id": 5, "method": "tools/list"},
    )
    assert response.status_code == 404
    assert response.json()["error"] == "unknown_session"


# Changed on 2026-09-27. Until then the tests below asserted that a request
# after initialize without MCP-Protocol-Version was refused with -32600 on POST
# and HTTP 400 on GET and DELETE, which was stricter than the specification.
# The transport specification, revision 2025-11-25, "Protocol Version Header",
# says a server that receives no such header uses the revision it can identify,
# for example the one negotiated during initialization, and otherwise SHOULD
# assume 2025-03-26. It also says an invalid or unsupported header MUST be
# answered with 400 Bad Request, which POST did not do: it answered HTTP 200.
# Both are now pinned here, and a missing header is never refused on its own.

def _initialize_session_at(revision):
    response = client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": revision, "capabilities": {}},
    })
    return response.json()["result"]["protocolVersion"], response.headers["mcp-session-id"]


def test_missing_protocol_version_with_a_session_uses_the_negotiated_revision():
    session_id, _ = initialize()
    response = client.post(
        "/mcp", headers={"Mcp-Session-Id": session_id},
        json={"jsonrpc": "2.0", "id": 6, "method": "tools/list"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "error" not in body, body
    assert len(body["result"]["tools"]) > 0, "a served request must return the real catalog"


def test_a_session_negotiated_at_2025_06_18_is_served_without_the_header():
    negotiated, session_id = _initialize_session_at("2025-06-18")
    assert negotiated == "2025-06-18"
    response = client.post(
        "/mcp", headers={"Mcp-Session-Id": session_id},
        json={"jsonrpc": "2.0", "id": 9, "method": "ping"},
    )
    assert response.status_code == 200
    assert response.json()["result"] == {}


def test_missing_protocol_version_without_a_session_is_served_as_2025_03_26():
    """No header and no session: the specification's SHOULD assume 2025-03-26,
    which this server accepts. A batch is still refused, because this server
    never implemented the 2025-03-26 batching it would otherwise imply."""
    listed = client.post("/mcp", json={"jsonrpc": "2.0", "id": 62, "method": "tools/list"})
    assert listed.status_code == 200
    assert len(listed.json()["result"]["tools"]) > 0
    batch = client.post("/mcp", json=[{"jsonrpc": "2.0", "id": 63, "method": "ping"}])
    assert batch.json()["error"]["code"] == INVALID_REQUEST
    assert "2025-11-25" in batch.json()["error"]["message"]


def test_a_stateless_deployment_serves_a_request_without_the_header(monkeypatch):
    """Stateless mode issues no session id, so there is no negotiated revision
    to look up and the specification's 2025-03-26 default applies."""
    monkeypatch.setenv("VOLCAN_MCP_SESSION_MODE", "stateless")
    initialized = client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {}},
    })
    assert "mcp-session-id" not in initialized.headers
    called = client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "play_earcon", "arguments": {"earcon_type": "TEST_PASSED"}},
    })
    assert called.status_code == 200
    content = called.json()["result"]["content"]
    assert any(block.get("type") == "audio" for block in content)


def test_an_unknown_session_without_the_header_is_still_404_not_the_fallback():
    """The session check runs first: a missing header must not rescue a session
    this server never issued or already terminated."""
    response = client.post(
        "/mcp", headers={"Mcp-Session-Id": "a-session-this-server-never-issued"},
        json={"jsonrpc": "2.0", "id": 64, "method": "tools/list"},
    )
    assert response.status_code == 404
    assert response.json()["error"] == "unknown_session"
    session_id, _ = initialize()
    assert client.delete("/mcp", headers=headers_for(session_id)).status_code == 204
    after = client.post(
        "/mcp", headers={"Mcp-Session-Id": session_id},
        json={"jsonrpc": "2.0", "id": 65, "method": "ping"},
    )
    assert after.status_code == 404


@pytest.mark.parametrize("method", [
    "tools/list",
    "tools/call",
    "ping",
    "resources/list",
    "definitely/not/a/method",
])
def test_without_the_header_every_method_gets_its_own_real_answer(method):
    """A missing header is resolved, not refused, so each method is dispatched
    and answered as it would be with the header: a result for the implemented
    methods and -32601 for the rest. The answer is the same with and without a
    session, because both resolve to a revision this server accepts."""
    session_id, _ = initialize()
    params = {"name": "play_earcon", "arguments": {"earcon_type": "TEST_PASSED"}} if method == "tools/call" else {}
    message = {"jsonrpc": "2.0", "id": 77, "method": method, "params": params}
    with_header = client.post("/mcp", headers=headers_for(session_id), json=message).json()
    with_session = client.post("/mcp", headers={"Mcp-Session-Id": session_id}, json=message)
    without_session = client.post("/mcp", json=message)
    for response in (with_session, without_session):
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == 77
        assert ("result" in body) == ("result" in with_header)
        if "error" in body:
            assert body["error"]["code"] == METHOD_NOT_FOUND
            assert body["error"] == with_header["error"]


def test_the_sse_stream_opens_without_the_protocol_version_header():
    session_id, _ = initialize()
    served = client.get("/mcp", headers={"Mcp-Session-Id": session_id})
    assert served.status_code == 200
    assert "text/event-stream" in served.headers["content-type"]


def test_session_termination_works_without_the_protocol_version_header():
    session_id, _ = initialize()
    assert client.delete("/mcp", headers={"Mcp-Session-Id": session_id}).status_code == 204
    assert client.delete("/mcp", headers=headers_for(session_id)).status_code == 404


def test_an_unsupported_version_is_refused_with_http_400_on_every_verb():
    """The specification: an invalid or unsupported MCP-Protocol-Version MUST
    be answered with 400 Bad Request. POST keeps the JSON-RPC envelope in the
    body so the refusal still names the request id."""
    session_id, _ = initialize()
    stale = {"Mcp-Session-Id": session_id, "MCP-Protocol-Version": "1999-01-01"}
    assert client.get("/mcp", headers=stale).status_code == 400
    assert client.delete("/mcp", headers=stale).status_code == 400
    posted = client.post("/mcp", headers=stale, json={"jsonrpc": "2.0", "id": 8, "method": "ping"})
    assert posted.status_code == 400
    assert posted.json()["error"]["code"] == INVALID_REQUEST
    assert posted.json()["id"] == 8
    # The refused DELETE must not have terminated the session.
    assert client.delete("/mcp", headers=headers_for(session_id)).status_code == 204


def test_unsupported_protocol_version_is_refused_even_without_a_session():
    response = client.post(
        "/mcp",
        headers={"MCP-Protocol-Version": "1999-01-01"},
        json={"jsonrpc": "2.0", "id": 7, "method": "tools/list"},
    )
    assert response.status_code == 400
    assert "result" not in response.json()
    assert response.json()["error"]["code"] == INVALID_REQUEST


def test_initialize_does_not_require_a_protocol_version_header():
    response = client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                   "clientInfo": {"name": "c", "version": "1"}},
    })
    assert response.status_code == 200
    assert "error" not in response.json()


def test_delete_terminates_the_session_and_a_second_delete_is_404():
    session_id, _ = initialize()
    first = client.delete("/mcp", headers=headers_for(session_id))
    assert first.status_code == 204
    second = client.delete("/mcp", headers=headers_for(session_id))
    assert second.status_code == 404


# --- transport --------------------------------------------------------------

def test_get_mcp_opens_a_comment_only_terminating_sse_stream():
    session_id, _ = initialize()
    response = client.get("/mcp", headers=headers_for(session_id))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert body.startswith(": volcan mcp stream open")
    assert "event:" not in body
    assert "data:" not in body
    assert "notifications/message" not in body


@pytest.mark.parametrize("method", ["put", "patch"])
def test_unsupported_http_method_returns_405_with_allow_header(method):
    response = getattr(client, method)("/mcp", json={})
    assert response.status_code == 405
    allow = response.headers.get("allow", "")
    assert "POST" in allow and "GET" in allow


# --- origin validation ------------------------------------------------------

def test_unexpected_browser_origin_is_rejected():
    response = client.post(
        "/mcp", headers={"Origin": "https://evil.example.com"},
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert response.status_code == 403
    assert response.json()["error"] == "origin_not_allowed"


def test_loopback_origin_is_accepted():
    response = client.post(
        "/mcp", headers={"Origin": "http://127.0.0.1:8000"},
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert response.status_code == 200


def test_the_companion_can_initialize_mcp_on_its_configured_origin(monkeypatch):
    """The deployed page and MCP endpoint share one origin.

    A fixed loopback allowlist made the terminal probe pass while the browser
    received 403. The deployment allowlist is the security boundary for this
    case; the request Host is deliberately not trusted.
    """
    monkeypatch.setenv("VOLCAN_ALLOWED_ORIGINS", "https://volcan.example.com")
    response = client.post(
        "/mcp", headers={"Origin": "https://volcan.example.com"},
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert response.status_code == 200
    assert response.json()["result"]["protocolVersion"] == PROTOCOL_VERSION


def test_matching_origin_and_host_are_not_trusted_without_configuration():
    """A rebinding page can control both Origin and Host; neither grants access."""
    response = client.post(
        "/mcp",
        headers={"Origin": "https://rebound.example", "Host": "rebound.example"},
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert response.status_code == 403


def test_absent_origin_is_accepted_for_non_browser_clients():
    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert response.status_code == 200


# --- every advertised tool actually runs ------------------------------------

TOOL_ARGUMENTS: dict[str, dict] = {
    "digest_semantic_diff": {"raw_diff": SAMPLE_DIFF, "level": 1},
    "drill_down_section": {"raw_diff": SAMPLE_DIFF, "section_index": 0},
    "stage_governed_action": {
        "action_id": "mcp-tool-sweep", "action_type": "RUN_TESTS",
        "command": "pytest tests/unit", "summary_spoken": "Run the unit suite",
    },
    "confirm_governed_action": {
        "action_id": "mcp-tool-sweep", "approval_grant": "v1.forged.forged",
        "approver_id": "sweeper",
    },
    "play_earcon": {"earcon_type": "TEST_PASSED"},
    "voice_turn": {
        "session_id": "sweep", "user_id": "sweeper", "repository": "volcan",
        "intent": "summarize_diff", "params": {"raw_diff": SAMPLE_DIFF},
    },
    "translate_text_to_braille": {"text": "review the patch"},
    "braille_diff_digest": {"raw_diff": SAMPLE_DIFF},
    "process_switch_pulse": {"input_type": "SIP_AND_PUFF", "signal_strength": 0.9},
    "get_haptic_profile": {"event_type": "SECURITY_FLAG"},
    "check_ast_completeness": {"source_code": "class A:\n    def b(self):\n        return 1\n"},
    # "help" is the one turn that touches neither GitHub nor a patch, so this
    # sweep proves the tool is callable without a request leaving the process.
    "review_dialogue_turn": {"session_id": "conformance-sweep", "transcript": "help"},
}


def test_every_advertised_tool_can_be_called_and_returns_content_blocks():
    """A catalog entry nobody can call is a lie the catalog tells."""
    session_id, _ = initialize()
    listing = client.post(
        "/mcp", headers=headers_for(session_id),
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    names = [tool["name"] for tool in listing.json()["result"]["tools"]]
    assert set(names) == set(TOOL_ARGUMENTS), (
        "the catalog and this sweep disagree; add arguments for any new tool"
    )

    for index, name in enumerate(names, start=100):
        response = client.post("/mcp", headers=headers_for(session_id), json={
            "jsonrpc": "2.0", "id": index, "method": "tools/call",
            "params": {"name": name, "arguments": TOOL_ARGUMENTS[name]},
        })
        assert response.status_code == 200, f"{name} -> HTTP {response.status_code}"
        body = response.json()
        assert "error" not in body, f"{name} returned a transport error: {body.get('error')}"
        result = body["result"]
        assert result["isError"] is False, f"{name} reported a tool error"
        assert result["content"], f"{name} returned no content blocks"
        for block in result["content"]:
            assert block["type"] in {"text", "audio"}, f"{name} returned {block['type']}"
            if block["type"] == "text":
                assert isinstance(block["text"], str)
            else:
                assert block["mimeType"] == "audio/wav"
                assert base64.b64decode(block["data"]).startswith(b"RIFF")


def test_a_refused_grant_travels_as_content_not_as_an_error():
    """The refusal is the product's answer, so it belongs in the result."""
    session_id, _ = initialize()
    client.post("/mcp", headers=headers_for(session_id), json={
        "jsonrpc": "2.0", "id": 200, "method": "tools/call",
        "params": {"name": "stage_governed_action", "arguments": {
            "action_id": "mcp-refusal", "action_type": "RUN_TESTS",
            "command": "pytest tests/unit", "summary_spoken": "Run the unit suite",
        }},
    })
    response = client.post("/mcp", headers=headers_for(session_id), json={
        "jsonrpc": "2.0", "id": 201, "method": "tools/call",
        "params": {"name": "confirm_governed_action", "arguments": {
            "action_id": "mcp-refusal", "approval_grant": "v1.tampered.tampered",
            "approver_id": "attacker",
        }},
    })
    result = response.json()["result"]
    assert result["isError"] is False
    detail = json.loads(result["content"][-1]["text"])
    assert detail["approved"] is False
    assert detail["refusal_code"] in {"BAD_SIGNATURE", "MALFORMED"}


@pytest.mark.parametrize("requested", ["2025-06-18", "2025-11-25"])
def test_a_supported_requested_revision_is_answered_with_that_same_revision(requested):
    """The lifecycle rule: support the requested revision, answer with it.

    Until 2026-09-27 this server answered 2025-11-25 to every request, even to a
    client that asked for 2025-06-18, which it supports.
    """
    response = client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": requested, "capabilities": {}},
    })
    assert response.json()["result"]["protocolVersion"] == requested
    assert response.headers["mcp-protocol-version"] == requested


def test_an_unsupported_requested_revision_is_answered_with_the_latest():
    response = client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
    })
    assert response.json()["result"]["protocolVersion"] == PROTOCOL_VERSION


def _initialize_asking_for(revision):
    response = client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": revision, "capabilities": {}},
    })
    return response.json()["result"]["protocolVersion"], response.headers["mcp-session-id"]


def test_2025_03_26_is_not_offered_because_this_server_does_not_honour_it():
    """That revision has no version header and requires batch support.

    Amazon documents its Alexa+ MCP client asking for 2025-03-26. The server
    answers with its own revision, and a client on it then sends the header.
    """
    negotiated, _ = _initialize_asking_for("2025-03-26")
    assert negotiated == PROTOCOL_VERSION


def test_a_2025_03_26_header_is_accepted_after_initialize_although_never_negotiated():
    """Changed on 2026-09-27 with the behaviour, after an audit.

    Until then this test asserted that the header was refused. That refusal had
    arrived with the negotiation change of the same day and removed a path that
    worked before it: a client that asks for 2025-03-26 and then declares it.
    Amazon documents no headers for its Alexa+ client, so that shape is served
    again. It is still told 2025-11-25, and a batch is still refused.
    """
    _, session_id = _initialize_asking_for("2025-03-26")
    headers = {"Mcp-Session-Id": session_id, "MCP-Protocol-Version": "2025-03-26"}
    served = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "ping"})
    assert served.status_code == 200
    assert served.json()["result"] == {}
    listed = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    assert "tools" in listed.json()["result"]
    batch = client.post("/mcp", headers=headers, json=[{"jsonrpc": "2.0", "id": 4, "method": "ping"}])
    assert batch.json()["error"]["code"] == INVALID_REQUEST
    assert "2025-11-25" in batch.json()["error"]["message"]


@pytest.mark.parametrize("header", ["2024-11-05", "2025-03-27", "latest", ""])
def test_any_other_version_header_is_still_refused_after_initialize(header):
    _, session_id = _initialize_asking_for(PROTOCOL_VERSION)
    refused = client.post(
        "/mcp", headers={"Mcp-Session-Id": session_id, "MCP-Protocol-Version": header},
        json={"jsonrpc": "2.0", "id": 2, "method": "ping"},
    )
    assert refused.status_code == 400
    error = refused.json()["error"]
    assert error["code"] == INVALID_REQUEST
    assert error["data"]["supported"] == ["2025-11-25", "2025-06-18"]
    assert "2025-03-26" not in error["data"]["supported"]
