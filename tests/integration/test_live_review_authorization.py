"""V-AUTH: only authenticated, allowed, session-bound callers can cause a review.

Every GitHub read/write below uses MockTransport. The original anonymous
open/stage/confirm path, the MCP alias, direct sink and legitimate flow share
the actual application's composition.
"""
import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from src.application.review_authorization import current_review_principal
from src.interfaces.composition import audit_repo, github_adapter
from src.interfaces.mcp_protocol import PROTOCOL_VERSION
from src.interfaces.mcp_server import app
from src.interfaces.review_authorization import authenticated_reviewer
from tests.fixtures.fake_github import PR_URL, FakeGitHub
from tests.unit.test_github_review_adapter import HEAD, snapshot

ALICE = "a" * 40
BOB = "b" * 40
client = TestClient(app)


@pytest.fixture
def live(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(audit_repo, "_records", [])
    monkeypatch.setattr(github_adapter, "transport", httpx.MockTransport(fake))
    monkeypatch.setattr(github_adapter, "token", "fake-github-service-token")
    monkeypatch.setattr(github_adapter, "write_enabled", True)
    monkeypatch.setenv("VOLCAN_REVIEWERS", json.dumps({
        "alice": {"token": ALICE, "repositories": ["octo/demo"]},
        "bob": {"token": BOB, "repositories": ["octo/demo"]},
    }))
    token = current_review_principal.set(None)
    yield fake
    current_review_principal.reset(token)


def rest(session, words, token=None, **extra):
    return client.post("/api/review/turn", headers=(
        {"Authorization": "Bearer " + token} if token else {}
    ), json={"session_id": session, "user_id": "forged-admin",
             "transcript": words, **extra})


def staged(token=ALICE):
    session = str(uuid.uuid4())
    opened = rest(session, "open", token, pr_url=PR_URL)
    assert opened.status_code == 200, opened.text
    response = rest(session, "request changes: restore the equality check", token)
    assert response.status_code == 200, response.text
    return session, response.json()["approval_grant"]


def mcp(arguments, token=None):
    headers = {"MCP-Protocol-Version": PROTOCOL_VERSION}
    if token:
        headers["Authorization"] = "Bearer " + token
    return client.post("/mcp", headers=headers, json={
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "review_dialogue_turn", "arguments": arguments},
    }).json()["result"]


@pytest.mark.parametrize("token", [None, "wrong-token"])
def test_original_anonymous_or_forged_identity_path_refused_before_github(live, token):
    session = str(uuid.uuid4())
    for words in ("open", "request changes: malicious review", "confirm"):
        response = rest(session, words, token, pr_url=PR_URL, approval_grant="v1.forged")
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "REVIEW_AUTH_REQUIRED"
    assert live.requests == []


def test_mcp_alias_and_direct_adapter_cannot_bypass_request_auth(live):
    result = mcp({"session_id": str(uuid.uuid4()), "user_id": "alice",
                  "transcript": "open", "pr_url": PR_URL})
    assert result["isError"] is True
    outcome = github_adapter.submit_request_changes(snapshot(), "attack", HEAD)
    assert outcome.refusal_code == "REVIEW_AUTH_REQUIRED"
    assert live.requests == []


def test_other_principal_cannot_read_modify_or_confirm_owned_session(live):
    session, grant = staged()
    before = len(live.requests)
    for words in ("repeat", "cancel", "request changes: substitute", "confirm"):
        response = rest(session, words, BOB, approval_grant=grant)
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "SESSION_OWNER_MISMATCH"
    assert len(live.requests) == before
    response = rest(session, "confirm", ALICE, approval_grant=grant)
    assert response.json()["review_outcome"]["submitted"] is True
    assert len(live.posts) == 1
    records = audit_repo.list_records()
    assert records[-1].approved_by == "alice"
    assert "reviewer alice" in records[-1].command


def test_grant_cannot_be_replayed_in_another_session(live):
    _session1, grant1 = staged()
    session2, _grant2 = staged()
    result = rest(session2, "confirm", ALICE, approval_grant=grant1).json()
    assert result["review_outcome"]["submitted"] is False
    assert live.posts == []


@pytest.mark.parametrize("url", [
    "https://github.com/other/private/pull/7",
    "https://www.github.com/other/private/pull/7/files",
])
def test_repo_allowlist_before_token_read_including_transcript_override(live, url):
    response = rest(str(uuid.uuid4()), "open " + url, ALICE, pr_url=PR_URL)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "REPOSITORY_NOT_ALLOWED"
    assert live.requests == []


def test_removal_of_repository_authority_between_stage_and_confirm(live, monkeypatch):
    session, grant = staged()
    monkeypatch.setenv("VOLCAN_REVIEWERS", json.dumps({
        "alice": {"token": ALICE, "repositories": ["other/repo"]},
    }))
    response = rest(session, "confirm", ALICE, approval_grant=grant)
    assert response.status_code == 403
    assert live.posts == []


def test_revoked_credential_cannot_resume(live, monkeypatch):
    session, grant = staged()
    monkeypatch.setenv("VOLCAN_REVIEWERS", "{}")
    assert rest(session, "confirm", ALICE, approval_grant=grant).status_code == 401
    assert live.posts == []


def test_bad_live_url_is_an_error_turn_not_a_server_crash(live):
    response = rest(str(uuid.uuid4()), "open", ALICE, pr_url="not-a-github-url")
    assert response.status_code == 200
    assert response.json()["error"] is True
    assert live.requests == []


def test_authorized_mcp_to_rest_journey_and_single_use_grant(live):
    session = str(uuid.uuid4())
    opened = mcp({"session_id": session, "transcript": "open", "pr_url": PR_URL}, ALICE)
    assert opened["isError"] is False
    stage = mcp({"session_id": session, "transcript": "request changes: restore comparison"}, ALICE)
    grant = json.loads(stage["content"][-1]["text"])["approval_grant"]
    done = rest(session, "confirm", ALICE, approval_grant=grant)
    assert done.json()["review_outcome"]["submitted"] is True
    rest(session, "confirm", ALICE, approval_grant=grant)
    assert len(live.posts) == 1
    # Middleware must not leak the previous request's context.
    assert rest(session, "repeat").status_code == 401


def test_public_read_tools_and_default_dry_run_preserved(live, monkeypatch):
    assert client.get("/health").status_code == 200
    response = client.post("/api/braille/translate_text", json={"text": "hello"})
    assert response.status_code == 200
    monkeypatch.setattr(github_adapter, "write_enabled", False)
    session, grant = staged(token=None)
    done = rest(session, "confirm", approval_grant=grant).json()
    assert done["review_outcome"]["dry_run"] is True
    assert live.posts == []


def test_demo_session_cannot_be_promoted_to_live(live, monkeypatch):
    monkeypatch.setattr(github_adapter, "write_enabled", False)
    session, grant = staged(token=None)
    monkeypatch.setattr(github_adapter, "write_enabled", True)
    response = rest(session, "confirm", ALICE, approval_grant=grant)
    assert response.status_code == 403
    assert live.posts == []


@pytest.mark.parametrize("roster", [
    "", "not json", "[]", '{"alice": null}',
    json.dumps({"alice": {"token": "short", "repositories": ["octo/demo"]}}),
    json.dumps({"alice": {"token": ALICE, "repositories": ["*/*"]}}),
    json.dumps({"alice": {"token": ALICE, "repositories": ["../demo"]}}),
    json.dumps({"alice": {"token": ALICE, "repositories": ["octo/demo"]},
                "bob": {"token": ALICE, "repositories": ["octo/demo"]}}),
])
def test_invalid_rosters_fail_closed(roster, monkeypatch):
    monkeypatch.setenv("VOLCAN_REVIEWERS", roster)
    assert authenticated_reviewer("Bearer " + ALICE) is None


def test_header_scheme_and_case_insensitive_repo(live, monkeypatch):
    monkeypatch.setenv("VOLCAN_REVIEWERS", json.dumps({
        "alice": {"token": ALICE, "repositories": ["Octo/Demo"]},
    }))
    principal = authenticated_reviewer("bEaReR " + ALICE)
    principal.require_repository("octo", "demo")
    assert authenticated_reviewer("Basic " + ALICE) is None
    assert authenticated_reviewer("Bearer " + ALICE + " ") is None
