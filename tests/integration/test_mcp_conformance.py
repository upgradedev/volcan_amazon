"""Conformance tests for the MCP Streamable HTTP server (revision 2025-11-25).

These run the full client handshake through FastAPI's TestClient:

    initialize -> notifications/initialized -> tools/list -> tools/call

and then assert the failure modes that separate a real protocol server from a
JSON endpoint wearing the name: unknown sessions, missing protocol version,
each JSON-RPC error code, notification semantics, tool errors that stay inside
the result, and the Allow header on an unsupported HTTP method.
"""
import base64
import json

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
    assert result["capabilities"] == {"tools": {"listChanged": False}}
    assert result["serverInfo"]["name"]
    assert result["serverInfo"]["version"]
    assert len(session_id) >= 32, "session id must be cryptographically sized"


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
        json={"jsonrpc": "2.0", "id": 9, "method": "resources/list"},
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


def test_missing_protocol_version_after_initialize_is_a_jsonrpc_error():
    session_id, _ = initialize()
    response = client.post(
        "/mcp", headers={"Mcp-Session-Id": session_id},
        json={"jsonrpc": "2.0", "id": 6, "method": "tools/list"},
    )
    assert response.status_code == 200
    error = response.json()["error"]
    assert error["code"] == INVALID_REQUEST
    assert "MCP-Protocol-Version" in error["message"]


def test_a_valid_session_never_excuses_a_missing_protocol_version():
    """The failure mode this pins is worse than an error: a plausible answer.

    If holding a session let a request skip the version check, a client that
    forgot one header would receive HTTP 200 with an empty ``tools`` array and
    conclude the server publishes nothing, which on stage is indistinguishable
    from a broken product. Both requests below omit only the version header;
    one carries a live session and the other carries none, and the two answers
    have to be the same refusal.
    """
    session_id, _ = initialize()
    with_session = client.post(
        "/mcp", headers={"Mcp-Session-Id": session_id},
        json={"jsonrpc": "2.0", "id": 61, "method": "tools/list"},
    )
    without_session = client.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 62, "method": "tools/list"},
    )

    for response in (with_session, without_session):
        body = response.json()
        assert "result" not in body, (
            "a request missing the version header must not receive a result at all, "
            f"received {body.get('result')!r}"
        )
        assert body["error"]["code"] == INVALID_REQUEST
        assert "Missing MCP-Protocol-Version header" in body["error"]["message"]

    assert with_session.json()["error"] == without_session.json()["error"], (
        "the presence of a session must not change the refusal"
    )


@pytest.mark.parametrize("method", [
    "tools/list",
    "tools/call",
    "ping",
    "resources/list",
    "definitely/not/a/method",
])
def test_the_version_rule_runs_before_dispatch_for_every_post_initialize_method(method):
    """One rule, every method, session or no session.

    The dangerous failure is not the error; it is the plausible answer. A
    ``tools/call`` that skipped the header check would run the tool, a
    ``ping`` would pong, and an unknown method would be refused as -32601,
    which would tell a client the header was fine and the method was not.
    Every one of these has to be refused as -32600 for the missing header,
    before anything else is consulted, and holding a valid session changes
    nothing.
    """
    session_id, _ = initialize()
    params = {"name": "play_earcon", "arguments": {"earcon_type": "TEST_PASSED"}} if method == "tools/call" else {}
    message = {"jsonrpc": "2.0", "id": 77, "method": method, "params": params}
    with_session = client.post("/mcp", headers={"Mcp-Session-Id": session_id}, json=message)
    without_session = client.post("/mcp", json=message)
    for response in (with_session, without_session):
        assert response.status_code == 200
        body = response.json()
        assert "result" not in body, f"{method} without the header produced a result: {body!r}"
        assert body["error"]["code"] == INVALID_REQUEST, f"{method} was refused with {body['error']}"
        assert body["error"]["code"] != METHOD_NOT_FOUND
        assert "Missing MCP-Protocol-Version header" in body["error"]["message"]
        assert body["id"] == 77, "the refusal must answer the request that was made"
    assert with_session.json()["error"] == without_session.json()["error"]


def test_the_sse_stream_also_requires_the_protocol_version_header():
    """GET is a request after initialize too, and docs/EVIDENCE.md says every one."""
    session_id, _ = initialize()
    refused = client.get("/mcp", headers={"Mcp-Session-Id": session_id})
    assert refused.status_code == 400
    assert refused.json()["error"] == "bad_protocol_version"
    assert "Missing MCP-Protocol-Version header" in refused.json()["detail"]

    accepted = client.get("/mcp", headers=headers_for(session_id))
    assert accepted.status_code == 200


def test_session_termination_also_requires_the_protocol_version_header():
    session_id, _ = initialize()
    refused = client.delete("/mcp", headers={"Mcp-Session-Id": session_id})
    assert refused.status_code == 400
    assert refused.json()["error"] == "bad_protocol_version"

    # The refusal must not have terminated the session as a side effect.
    assert client.delete("/mcp", headers=headers_for(session_id)).status_code == 204


def test_an_unsupported_version_is_refused_on_every_verb():
    session_id, _ = initialize()
    stale = {"Mcp-Session-Id": session_id, "MCP-Protocol-Version": "1999-01-01"}
    assert client.get("/mcp", headers=stale).status_code == 400
    assert client.delete("/mcp", headers=stale).status_code == 400
    posted = client.post("/mcp", headers=stale, json={"jsonrpc": "2.0", "id": 8, "method": "ping"})
    assert posted.json()["error"]["code"] == INVALID_REQUEST


def test_unsupported_protocol_version_is_refused():
    session_id, _ = initialize()
    response = client.post(
        "/mcp",
        headers={"Mcp-Session-Id": session_id, "MCP-Protocol-Version": "1999-01-01"},
        json={"jsonrpc": "2.0", "id": 7, "method": "tools/list"},
    )
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
    error = refused.json()["error"]
    assert error["code"] == INVALID_REQUEST
    assert error["data"]["supported"] == ["2025-11-25", "2025-06-18"]
    assert "2025-03-26" not in error["data"]["supported"]
