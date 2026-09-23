"""The GitHub adapter: real reads, a dry-run write, and three refusals.

Everything here runs against ``httpx.MockTransport``. No request leaves the
process, which is also why the happy path is a test of the request shape and
of the response handling, and not evidence that a review was ever posted. The
README says which of these has been exercised live and which has not.
"""
import json

import httpx
import pytest

from src.application.review_authorization import ReviewPrincipal, current_review_principal
from src.domain.review_dialogue import PullRequestSnapshot
from src.infrastructure.github_review_adapter import (
    CAPABILITY_DRY_RUN_NO_TOKEN,
    CAPABILITY_DRY_RUN_TOKEN,
    CAPABILITY_LIVE,
    CAPABILITY_LIVE_NO_TOKEN,
    REFUSAL_NO_TOKEN,
    REFUSAL_REJECTED,
    REFUSAL_STALE_HEAD,
    REFUSAL_UNAUTHORIZED,
    REFUSAL_UNREACHABLE,
    GitHubReadError,
    GitHubReviewAdapter,
)

HEAD = "a" * 40

@pytest.fixture(autouse=True)
def trusted_caller():
    """These port tests exercise an already authenticated application caller."""
    token = current_review_principal.set(ReviewPrincipal("blind-developer", frozenset({"octo/demo"})))
    try:
        yield
    finally:
        current_review_principal.reset(token)
MOVED = "b" * 40
DIFF = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a = 1\n+a = 2\n"


class FakeGitHub:
    """A scripted GitHub: what the PR head is now, and how the write answers."""

    def __init__(self, head: str = HEAD, write_status: int = 200, write_body=None, user_status: int = 200):
        self.head = head
        self.write_status = write_status
        self.write_body = write_body if write_body is not None else {
            "id": 4242, "html_url": "https://github.com/octo/demo/pull/7#pullrequestreview-4242",
            "state": "CHANGES_REQUESTED", "commit_id": head,
        }
        self.user_status = user_status
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.method == "GET" and path == "/repos/octo/demo/pulls/7":
            if "diff" in request.headers.get("accept", ""):
                return httpx.Response(200, text=DIFF)
            return httpx.Response(200, json={
                "html_url": "https://github.com/octo/demo/pull/7", "title": "Flip the check",
                "state": "open", "head": {"sha": self.head, "ref": "feature"},
                "base": {"ref": "main"}, "user": {"login": "octocat"},
            })
        if request.method == "GET" and path == "/user":
            return httpx.Response(self.user_status, json={"login": "reviewer"} if self.user_status == 200 else {"message": "Bad credentials"})
        if request.method == "POST" and path == "/repos/octo/demo/pulls/7/reviews":
            return httpx.Response(self.write_status, json=self.write_body)
        return httpx.Response(404, json={"message": "Not Found"})


def adapter(fake: FakeGitHub, token: str | None = None, write: bool = False) -> GitHubReviewAdapter:
    return GitHubReviewAdapter(token=token, write_enabled=write, transport=httpx.MockTransport(fake))


def snapshot(head: str = HEAD) -> PullRequestSnapshot:
    return PullRequestSnapshot(
        owner="octo", repo="demo", number=7, url="https://github.com/octo/demo/pull/7",
        title="Flip the check", state="open", head_sha=head, head_ref="feature", base_ref="main",
        author="octocat", diff=DIFF,
    )


# --- URL parsing ---------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://github.com/octo/demo/pull/7",
    "https://github.com/octo/demo/pull/7/files",
    "https://www.github.com/octo/demo/pull/7#discussion_r1",
    "http://github.com/octo/demo/pull/7?diff=split",
])
def test_pull_request_urls_are_parsed(url):
    assert GitHubReviewAdapter.parse_pull_request_url(url) == ("octo", "demo", 7)


@pytest.mark.parametrize("url", [
    "https://github.com/octo/demo",
    "https://github.com/octo/demo/issues/7",
    "https://gitlab.com/octo/demo/-/merge_requests/7",
    "octo/demo#7",
    "",
])
def test_anything_else_is_refused_with_the_expected_shape(url):
    with pytest.raises(ValueError, match="pull/<number>"):
        GitHubReviewAdapter.parse_pull_request_url(url)


# --- reads -----------------------------------------------------------------------

def test_fetch_reads_the_head_sha_and_the_diff_with_no_token():
    fake = FakeGitHub()
    snap = adapter(fake).fetch_pull_request("https://github.com/octo/demo/pull/7")
    assert snap.head_sha == HEAD
    assert snap.diff == DIFF
    assert snap.title == "Flip the check" and snap.author == "octocat"
    assert snap.fetched_with_token is False
    accepts = [r.headers["accept"] for r in fake.requests]
    assert accepts == ["application/vnd.github+json", "application/vnd.github.v3.diff"]
    assert all("authorization" not in r.headers for r in fake.requests)


def test_fetch_sends_the_token_as_a_bearer_when_one_is_set():
    fake = FakeGitHub()
    adapter(fake, token="ghp_secret").fetch_pull_request("https://github.com/octo/demo/pull/7")
    assert fake.requests[0].headers["authorization"] == "Bearer ghp_secret"


def test_a_missing_pull_request_is_a_read_error_carrying_the_status():
    fake = FakeGitHub()
    with pytest.raises(GitHubReadError) as caught:
        adapter(fake).fetch_pull_request("https://github.com/octo/demo/pull/8")
    assert caught.value.status == 404
    assert "Not Found" in str(caught.value)


def test_an_unreachable_github_is_a_read_error_not_a_crash():
    def explode(_request):
        raise httpx.ConnectError("no route to host")

    broken = GitHubReviewAdapter(token=None, write_enabled=False, transport=httpx.MockTransport(explode))
    with pytest.raises(GitHubReadError, match="ConnectError"):
        broken.fetch_pull_request("https://github.com/octo/demo/pull/7")


# --- the write, dry-run by default -------------------------------------------------

def test_dry_run_is_the_default_and_records_the_exact_request_without_sending():
    fake = FakeGitHub()
    gh = adapter(fake, token="ghp_secret")
    outcome = gh.submit_request_changes(snapshot(), "Restore the == comparison.", HEAD)

    assert outcome.dry_run is True and outcome.submitted is False and outcome.refusal_code is None
    assert [r.method for r in fake.requests] == ["GET"], "a dry run re-reads the head and sends nothing"
    assert gh.recorded_requests == [outcome.request]
    assert outcome.request["method"] == "POST"
    assert outcome.request["url"] == "https://api.github.com/repos/octo/demo/pulls/7/reviews"
    assert outcome.request["json"] == {
        "commit_id": HEAD, "event": "REQUEST_CHANGES", "body": "Restore the == comparison.",
    }
    assert outcome.request["headers"]["Authorization"] == "Bearer <redacted GITHUB_TOKEN>"
    assert "ghp_secret" not in json.dumps(outcome.to_dict())
    assert outcome.would_be_refused_live is None
    assert "Dry run" in outcome.spoken and "Nothing was sent" in outcome.spoken


def test_a_dry_run_without_a_token_records_and_names_the_refusal_a_live_send_would_meet():
    gh = adapter(FakeGitHub())
    outcome = gh.submit_request_changes(snapshot(), "body", HEAD)
    assert outcome.dry_run is True
    assert outcome.request["token_present"] is False
    assert outcome.would_be_refused_live == REFUSAL_NO_TOKEN
    assert "no GITHUB_TOKEN" in outcome.spoken


def test_a_moved_head_is_refused_before_anything_is_recorded_or_sent():
    fake = FakeGitHub(head=MOVED)
    gh = adapter(fake, token="ghp_secret", write=True)
    outcome = gh.submit_request_changes(snapshot(HEAD), "body", HEAD)
    assert outcome.refusal_code == REFUSAL_STALE_HEAD
    assert outcome.submitted is False and outcome.dry_run is False
    assert outcome.live_head_sha == MOVED and outcome.expected_head_sha == HEAD
    assert [r.method for r in fake.requests] == ["GET"], "no POST after a stale head"
    assert gh.recorded_requests == []
    assert "moved from aaaaaaa to bbbbbbb" in outcome.detail


def test_a_moved_head_is_refused_in_dry_run_too():
    gh = adapter(FakeGitHub(head=MOVED))
    outcome = gh.submit_request_changes(snapshot(HEAD), "body", HEAD)
    assert outcome.refusal_code == REFUSAL_STALE_HEAD and outcome.dry_run is False
    assert gh.recorded_requests == []


def test_live_write_without_a_token_is_refused_rather_than_sent_unauthenticated():
    fake = FakeGitHub()
    outcome = adapter(fake, token=None, write=True).submit_request_changes(snapshot(), "body", HEAD)
    assert outcome.refusal_code == REFUSAL_NO_TOKEN
    assert [r.method for r in fake.requests] == ["GET"]


@pytest.mark.parametrize("status", [401, 403, 404])
def test_a_token_without_permission_is_refused_as_unauthorized(status):
    fake = FakeGitHub(write_status=status, write_body={"message": "Resource not accessible by personal access token"})
    outcome = adapter(fake, token="ghp_readonly", write=True).submit_request_changes(snapshot(), "body", HEAD)
    assert outcome.submitted is False
    assert outcome.refusal_code == REFUSAL_UNAUTHORIZED
    assert "pull_requests: write" in outcome.detail
    assert outcome.response["status"] == status
    assert "Refused, UNAUTHORIZED" in outcome.spoken


def test_github_validation_errors_are_reported_as_rejected_not_as_unauthorized():
    fake = FakeGitHub(write_status=422, write_body={"message": "Validation Failed"})
    outcome = adapter(fake, token="ghp_secret", write=True).submit_request_changes(snapshot(), "body", HEAD)
    assert outcome.refusal_code == REFUSAL_REJECTED
    assert "422" in outcome.detail


def test_the_live_happy_path_sends_the_bound_review_and_reports_github_answer():
    fake = FakeGitHub()
    outcome = adapter(fake, token="ghp_secret", write=True).submit_request_changes(
        snapshot(), "Restore the == comparison.", HEAD,
    )
    assert outcome.submitted is True and outcome.dry_run is False
    assert outcome.identity == "reviewer"
    assert outcome.response["id"] == 4242 and outcome.response["commit_id"] == HEAD
    post = [r for r in fake.requests if r.method == "POST"][0]
    assert json.loads(post.content) == {
        "commit_id": HEAD, "event": "REQUEST_CHANGES", "body": "Restore the == comparison.",
    }
    assert post.headers["authorization"] == "Bearer ghp_secret"
    assert [r.url.path for r in fake.requests] == [
        "/repos/octo/demo/pulls/7", "/user", "/repos/octo/demo/pulls/7/reviews",
    ]
    assert "Submitted" in outcome.spoken and "as reviewer" in outcome.spoken


def test_a_write_that_cannot_reach_github_is_reported_as_unreachable():
    calls = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if request.method == "POST":
            raise httpx.ReadTimeout("timed out")
        return FakeGitHub()(request)

    gh = GitHubReviewAdapter(token="ghp_secret", write_enabled=True, transport=httpx.MockTransport(flaky))
    outcome = gh.submit_request_changes(snapshot(), "body", HEAD)
    assert outcome.refusal_code == REFUSAL_UNREACHABLE
    assert "ReadTimeout" in outcome.detail


# --- capability, for /health -----------------------------------------------------------

@pytest.mark.parametrize(("token", "write", "expected"), [
    ("ghp_x", True, CAPABILITY_LIVE),
    (None, True, CAPABILITY_LIVE_NO_TOKEN),
    ("ghp_x", False, CAPABILITY_DRY_RUN_TOKEN),
    (None, False, CAPABILITY_DRY_RUN_NO_TOKEN),
])
def test_the_capability_is_the_conjunction_of_the_flag_and_the_token(token, write, expected):
    capability = adapter(FakeGitHub(), token=token, write=write).capability()
    assert capability["resolved_capability"] == expected
    assert capability["token_present"] is bool(token)
    assert capability["write_enabled"] is write
    assert "ghp_x" not in json.dumps(capability), "the token value must never be published"


def test_the_environment_is_read_only_when_nothing_is_injected(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_from_env")
    monkeypatch.setenv("VOLCAN_GITHUB_WRITE", "1")
    gh = GitHubReviewAdapter()
    assert gh.token == "ghp_from_env" and gh.write_enabled is True
    monkeypatch.setenv("VOLCAN_GITHUB_WRITE", "yes")
    assert GitHubReviewAdapter().write_enabled is False, "only the exact value 1 enables a live write"
