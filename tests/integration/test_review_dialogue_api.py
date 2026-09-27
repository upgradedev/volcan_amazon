"""The review journey over the two surfaces the page and an MCP client use.

A blind developer opens a real pull request, converses about the change,
inspects exact source lines, corrects a misheard command, and submits a
``REQUEST_CHANGES`` review bound to the reviewed commit. The GitHub at the far
end of these tests is ``httpx.MockTransport`` swapped into the process-wide
adapter, so no request leaves the process, and the write is the dry-run default:
what the tests prove is that the exact request was recorded and audited, not
that GitHub ever received one. docs/EVIDENCE.md says which owner action produces the
live receipt.
"""
import httpx
import pytest
from fastapi.testclient import TestClient

from src.interfaces.composition import github_adapter
from src.interfaces.mcp_protocol import PROTOCOL_VERSION
from src.interfaces.mcp_server import app
from tests.fixtures.fake_github import HEAD, MOVED, PR_URL, FakeGitHub

client = TestClient(app)


@pytest.fixture
def fake_github():
    """Point the process-wide adapter at a scripted GitHub, and put it back."""
    fake = FakeGitHub()
    saved = (github_adapter.transport, github_adapter.token, github_adapter.write_enabled,
             list(github_adapter.recorded_requests))
    github_adapter.transport = httpx.MockTransport(fake)
    github_adapter.token = None
    github_adapter.write_enabled = False
    github_adapter.recorded_requests.clear()
    try:
        yield fake
    finally:
        github_adapter.transport, github_adapter.token, github_adapter.write_enabled = saved[:3]
        github_adapter.recorded_requests[:] = saved[3]


def turn(session: str, transcript: str, **extra) -> dict:
    response = client.post("/api/review/turn", json={
        "session_id": session, "user_id": "blind-developer", "transcript": transcript, **extra,
    })
    assert response.status_code == 200, response.text
    return response.json()


# --- /health ----------------------------------------------------------------------------

def test_health_reports_the_resolved_review_path_without_leaking_a_token(fake_github):
    body = client.get("/health").json()
    path = body["github_review_path"]
    assert path["resolved_capability"] == "dry_run_no_token"
    assert path["write_enabled"] is False and path["token_present"] is False
    assert "recorded and not sent" in path["detail"]
    assert set(path) == {"resolved_capability", "detail", "write_enabled", "token_present", "api"}


# --- the REST journey ----------------------------------------------------------------------

def test_the_blind_developer_journey_over_rest(fake_github):
    session = "rest-journey"

    opened = turn(session, "open the pull request", pr_url=PR_URL)
    assert opened["state"] == "OVERVIEW"
    assert opened["readback"] == "Understood: open the pull request."
    assert "head commit aaaaaaa" in opened["spoken"]
    assert "_wav" not in opened, "the REST body carries base64 audio, never raw bytes"
    assert opened["earcon"]["type"] == "SECURITY_FINDING" and opened["earcon"]["wav_base64"]

    focused = turn(session, "what changed in permissions dot py")
    assert focused["state"] == "FILE"
    assert "an authorization comparison was inverted" in focused["spoken"]

    lines = turn(session, "read the lines")
    assert lines["state"] == "LINES"
    assert 'Line 3 of 4, removed, old line 14:     return user.role == "admin".' in lines["spoken"]
    assert 'Line 4 of 4, added, new line 14:     return user.role != "admin".' in lines["spoken"]

    assert "Cursor on line 3 of 4, the first change." in lines["spoken"]
    # The session is saved and loaded between turns; the cursor must survive it.
    assert "Line 3 of 4, removed, spelled:" in turn(session, "spell that")["spoken"]
    assert "Line 3 of 4, removed, old line 14." in turn(session, "where am i")["spoken"]

    turn(session, "line 12")
    turn(session, "next")
    misheard = turn(session, "next")
    assert "Line 3 of 4" in misheard["spoken"]
    corrected = turn(session, "no, I said previous")
    assert corrected["readback"] == "Corrected, previous."
    assert "Line 1 of 4" in corrected["spoken"]

    spelled = turn(session, "line 14")
    spelled = turn(session, "spell that")
    assert "bang, equals" in spelled["spoken"]

    staged = turn(session, "request changes: restore the equality check")
    assert staged["state"] == "CONFIRM_REVIEW" and staged["awaiting_confirmation"] is True
    assert staged["approval_grant"].startswith("v1.")
    assert staged["pending_review"]["head_sha"] == HEAD
    assert staged["earcon"]["type"] == "GOVERNANCE_CHALLENGE"

    done = turn(session, "confirm", approval_grant=staged["approval_grant"])
    assert done["state"] == "RECORDED"
    assert done["review_outcome"]["dry_run"] is True and done["review_outcome"]["submitted"] is False
    assert done["review_outcome"]["request"]["json"]["commit_id"] == HEAD
    assert done["review_outcome"]["request"]["json"]["event"] == "REQUEST_CHANGES"
    assert done["earcon"]["type"] == "DRY_RUN_RECORDED"
    assert "Nothing was sent to GitHub" in done["spoken"]
    assert fake_github.posts == []

    audit = client.get("/api/audit_log").json()
    record = next(r for r in audit["records"] if r["action_type"] == "GITHUB_REQUEST_CHANGES")
    assert record["outcome"].startswith("DRY RUN recorded, not sent: POST")
    assert record["approved_by"] == "blind-developer"
    assert record["staged_by"] == "volcan-review-dialogue"
    assert HEAD in record["command"]


def test_a_head_that_moved_is_refused_over_rest_and_audited(fake_github):
    session = "rest-stale"
    turn(session, "open", pr_url=PR_URL)
    staged = turn(session, "request changes: please keep the equality check")
    fake_github.head = MOVED
    refused = turn(session, "confirm", approval_grant=staged["approval_grant"])
    assert refused["state"] == "REFUSED" and refused["error"] is True
    assert refused["review_outcome"]["refusal_code"] == "STALE_HEAD"
    assert refused["review_outcome"]["live_head_sha"] == MOVED
    assert refused["earcon"]["type"] == "TEST_FAILED"
    assert fake_github.posts == [] and github_adapter.recorded_requests == []
    audit = client.get("/api/audit_log").json()
    assert any(r["outcome"].startswith("REFUSED STALE_HEAD") for r in audit["records"])


def test_an_unrecognised_transcript_over_rest_reads_back_what_was_heard(fake_github):
    body = turn("rest-unknown", "make me a sandwich")
    assert body["error"] is True
    assert body["readback"] == "I heard 'make me a sandwich' and did not recognise a command."
    assert body["state"] == "IDLE"


def test_a_malformed_turn_is_a_422_not_a_crash(fake_github):
    response = client.post("/api/review/turn", json={"session_id": "x"})
    assert response.status_code == 422


# --- the MCP tool ------------------------------------------------------------------------------

def initialize() -> str:
    response = client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                   "clientInfo": {"name": "volcan-review-test", "version": "1.0"}},
    })
    assert response.status_code == 200, response.text
    return response.headers["mcp-session-id"]


def call(session_id: str, arguments: dict, request_id: int = 2) -> dict:
    response = client.post(
        "/mcp", headers={"Mcp-Session-Id": session_id, "MCP-Protocol-Version": PROTOCOL_VERSION},
        json={"jsonrpc": "2.0", "id": request_id, "method": "tools/call",
              "params": {"name": "review_dialogue_turn", "arguments": arguments}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "error" not in body, body
    return body["result"]


def test_the_mcp_tool_reads_back_before_it_answers_and_carries_the_cue(fake_github):
    session_id = initialize()
    result = call(session_id, {"session_id": "mcp-journey", "transcript": "open", "pr_url": PR_URL})
    assert result.get("isError") is not True
    kinds = [block["type"] for block in result["content"]]
    assert kinds == ["text", "audio", "text"], "spoken text, then the earcon, then the detail"
    spoken = result["content"][0]["text"]
    assert spoken.startswith("Understood: open the pull request. Opened octo/demo pull request 7")
    assert result["content"][1]["mimeType"] == "audio/wav"

    staged = call(session_id, {
        "session_id": "mcp-journey", "transcript": "request changes: restore the equality check",
    }, request_id=3)
    detail = staged["content"][-1]["text"]
    assert "approval_grant" in detail and "CONFIRM_REVIEW" in detail


def test_the_mcp_tool_answers_help_without_touching_github(fake_github):
    session_id = initialize()
    result = call(session_id, {"session_id": "mcp-help", "transcript": "help"})
    assert result["content"][0]["text"].startswith("Understood: help. You can say:")
    assert fake_github.requests == []
