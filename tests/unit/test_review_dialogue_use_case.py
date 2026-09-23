"""The review dialogue use case: open, converse, stage, confirm, and every refusal.

The state machine is proven in ``test_review_dialogue.py`` with injected
transcripts. This module proves the three things the domain hands to the
application layer: opening a pull request through the GitHub port, minting the
single-use grant that binds a review to its head commit, and confirming, which
is where the grant, custody, the live head re-read and the dry-run default all
meet. The GitHub behind every test is ``httpx.MockTransport``; no request
leaves the process, and the tests say which outcome is a recording and which
would have been a send.
"""
import asyncio
import time

import httpx
import pytest

from src.application.digest_diff_use_case import DigestDiffUseCase
from src.application.review_authorization import (
    ReviewAuthorizationError,
    ReviewPrincipal,
    current_review_principal,
)
from src.application.review_dialogue_use_case import (
    ACTION_TYPE,
    STAGING_PRINCIPAL,
    ReviewDialogueUseCase,
)
from src.application.sonify_event_use_case import SonifyEventUseCase
from src.domain.approval_grant import ApprovalGrantIssuer
from src.domain.governed_action import ActionState
from src.infrastructure.audit_repository import InMemoryAuditRepository
from src.infrastructure.bedrock_adapter import BedrockSynthesisAdapter
from src.infrastructure.github_review_adapter import GitHubReviewAdapter
from tests.fixtures.fake_github import HEAD, MOVED, PR_URL, FakeGitHub

USER = "blind-developer"

@pytest.fixture(autouse=True)
def trusted_caller():
    """These port tests exercise an already authenticated application caller."""
    token = current_review_principal.set(ReviewPrincipal("blind-developer", frozenset({"octo/demo"})))
    try:
        yield
    finally:
        current_review_principal.reset(token)


def build(fake: FakeGitHub, token: str | None = None, write: bool = False,
          lease_sec: float = 300.0) -> tuple[ReviewDialogueUseCase, GitHubReviewAdapter, InMemoryAuditRepository]:
    bedrock = BedrockSynthesisAdapter(client_factory=lambda _region: None)
    bedrock.credentials_present = lambda: False  # type: ignore[method-assign]
    github = GitHubReviewAdapter(token=token, write_enabled=write, transport=httpx.MockTransport(fake))
    audit = InMemoryAuditRepository()
    use_case = ReviewDialogueUseCase(
        DigestDiffUseCase(bedrock), github, ApprovalGrantIssuer(b"0123456789abcdef0123"),
        audit, SonifyEventUseCase(), lease_sec=lease_sec,
    )
    return use_case, github, audit


def say(use_case: ReviewDialogueUseCase, transcript: str, session: str = "s1", **kwargs) -> dict:
    return asyncio.run(use_case.handle_turn(session_id=session, user_id=USER, transcript=transcript, **kwargs))


def opened(fake: FakeGitHub | None = None, **build_kwargs):
    fake = fake or FakeGitHub()
    use_case, github, audit = build(fake, **build_kwargs)
    first = say(use_case, "open the pull request", pr_url=PR_URL)
    return use_case, github, audit, fake, first


def staged(fake: FakeGitHub | None = None, **build_kwargs):
    use_case, github, audit, fake, _ = opened(fake, **build_kwargs)
    turn = say(use_case, "request changes: restore the equality check")
    return use_case, github, audit, fake, turn


# --- opening -------------------------------------------------------------------------

def test_opening_by_url_reads_the_live_head_and_speaks_the_overview():
    use_case, _, _, fake, turn = opened()
    assert turn["state"] == "OVERVIEW"
    assert turn["readback"] == "Understood: open the pull request."
    assert "Opened octo/demo pull request 7, Flip the check, by octocat, head commit aaaaaaa" in turn["spoken"]
    assert turn["pull_request"]["head_sha"] == HEAD
    assert turn["earcon"]["type"] == "SECURITY_FINDING" and turn["earcon"]["wav_base64"]
    assert isinstance(turn["_wav"], bytes)
    assert turn["review_path"]["resolved_capability"] == "dry_run_no_token"
    assert [r.method for r in fake.requests] == ["GET", "GET"], "one metadata read, one diff read"


def test_a_url_in_the_transcript_wins_over_the_field():
    use_case, _, _, fake, _ = opened()
    turn = say(use_case, f"open {PR_URL}", pr_url="https://github.com/other/repo/pull/1")
    assert turn["pull_request"]["number"] == 7


def test_an_unreadable_pull_request_is_an_error_turn_with_the_reason_not_a_crash():
    use_case, _, _ = build(FakeGitHub())
    turn = say(use_case, "open", pr_url="https://github.com/octo/demo/pull/8")
    assert turn["error"] is True and turn["state"] == "IDLE"
    assert "could not be opened" in turn["spoken"] and "GitHubReadError" in turn["spoken"]
    assert "HTTP 404" in turn["spoken"]
    assert turn["earcon"]["type"] == "TEST_FAILED"


def test_opening_with_neither_a_url_nor_a_patch_asks_for_one():
    use_case, _, _ = build(FakeGitHub())
    turn = say(use_case, "open the pull request")
    assert turn["error"] is True
    assert "Give me a pull request URL, or paste a patch" in turn["spoken"]


def test_a_pasted_patch_opens_but_cannot_be_reviewed():
    use_case, github, _ = build(FakeGitHub())
    turn = say(use_case, "open the patch", raw_diff="--- a/p.py\n+++ b/p.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n")
    assert turn["state"] == "OVERVIEW" and turn["pull_request"] is None
    assert "cannot be submitted" in turn["spoken"]
    refused = say(use_case, "request changes: please add a test")
    assert refused["error"] is True and "no pull request to review" in refused["spoken"]
    assert refused["approval_grant"] is None and refused["awaiting_confirmation"] is False
    assert github.recorded_requests == []


# --- the journey, dry-run by default --------------------------------------------------------

def test_the_whole_journey_ends_in_a_recorded_review_and_a_sealed_audit_record():
    use_case, github, audit, fake, _ = opened()

    focus = say(use_case, "what changed in permissions dot py")
    assert focus["state"] == "FILE" and "authorization comparison was inverted" in focus["spoken"]

    lines = say(use_case, "read the lines")
    assert lines["state"] == "LINES"
    assert 'Line 4 of 4, added, new line 14:     return user.role != "admin".' in lines["spoken"]

    exact = say(use_case, "line 14")
    assert exact["line"]["new_no"] == 14 and exact["line"]["kind"] == "add"
    spelled = say(use_case, "spell that")
    assert "bang, equals" in spelled["spoken"]

    stage = say(use_case, "request changes: restore the equality check")
    assert stage["state"] == "CONFIRM_REVIEW" and stage["awaiting_confirmation"] is True
    assert stage["approval_grant"].startswith("v1.")
    assert stage["pending_review"]["head_sha"] == HEAD
    assert stage["pending_review"]["body"] == "restore the equality check"
    assert stage["earcon"]["type"] == "GOVERNANCE_CHALLENGE"
    assert "bound to head commit aaaaaaa" in stage["spoken"]

    blocked = say(use_case, "next file")
    assert blocked["error"] is True and "waiting for your confirmation" in blocked["spoken"]

    done = say(use_case, "confirm", approval_grant=stage["approval_grant"])
    assert done["state"] == "RECORDED"
    outcome = done["review_outcome"]
    assert outcome["dry_run"] is True and outcome["submitted"] is False and outcome["refusal_code"] is None
    assert outcome["request"]["json"] == {
        "commit_id": HEAD, "event": "REQUEST_CHANGES", "body": "restore the equality check",
    }
    assert outcome["request"]["url"] == "https://api.github.com/repos/octo/demo/pulls/7/reviews"
    assert done["earcon"]["type"] == "DRY_RUN_RECORDED"
    assert "Nothing was sent to GitHub" in done["spoken"]
    assert "no GITHUB_TOKEN is set" in done["spoken"]
    assert done["awaiting_confirmation"] is False

    assert fake.posts == [], "a dry run never posts"
    assert github.recorded_requests == [outcome["request"]]

    records = audit.list_records()
    assert len(records) == 1
    record = records[0]
    assert record.action_type == ACTION_TYPE
    assert record.state is ActionState.APPROVED
    assert record.execution_stdout.startswith("DRY RUN recorded, not sent: POST")
    assert record.staged_by == STAGING_PRINCIPAL and record.approved_by == USER
    assert HEAD in record.command
    assert audit.verify_integrity().intact is True


def test_a_correction_and_a_stop_travel_through_the_use_case_unchanged():
    use_case, _, _, _, _ = opened()
    say(use_case, "file 1")
    say(use_case, "next")
    corrected = say(use_case, "no, I said previous")
    assert corrected["readback"] == "Corrected, previous."
    assert corrected["focus"]["file_index"] == 0
    stopped = say(use_case, "stop")
    assert stopped["silent"] is True and stopped["earcon"] is None
    assert stopped["state"] == "FILE"


def test_stop_then_resume_retains_exact_file_line_and_revision():
    use_case, _, _, _, opened_turn = opened()
    assert len(opened_turn["spoken"].split()) < 45, "the initial answer stays short"
    say(use_case, "what changed in permissions dot py")
    say(use_case, "line 14")
    say(use_case, "stop")

    resumed = say(use_case, "resume")

    assert resumed["state"] == "LINES"
    assert resumed["readback"] == "Understood: resume."
    assert "permissions.py" in resumed["spoken"]
    assert "new line 14" in resumed["spoken"]
    assert "head commit aaaaaaa" in resumed["spoken"]
    assert resumed["line"]["new_no"] == 14


def test_resume_refreshes_a_moved_head_and_invalidates_the_old_approval():
    fake = FakeGitHub()
    use_case, github, _, fake, stage = staged(fake)
    fake.head = MOVED

    resumed = say(use_case, "resume")

    assert resumed["state"] == "OVERVIEW"
    assert "changed from aaaaaaa to bbbbbbb" in resumed["spoken"]
    assert "old approval was invalidated" in resumed["spoken"]
    assert resumed["pull_request"]["head_sha"] == MOVED
    assert resumed["awaiting_confirmation"] is False
    later = say(use_case, "confirm", approval_grant=stage["approval_grant"])
    assert later["error"] is True and later["review_outcome"] is None
    assert github.recorded_requests == []


def test_dry_run_sessions_are_bound_to_the_declared_user():
    use_case, _, _, _, _ = opened()
    with pytest.raises(ReviewAuthorizationError) as raised:
        asyncio.run(use_case.handle_turn(
            session_id="s1", user_id="different-developer", transcript="resume",
        ))
    assert getattr(raised.value, "code", None) == "SESSION_OWNER_MISMATCH"


def test_sessions_do_not_share_a_pending_review():
    use_case, _, _, _, stage = staged()
    other = say(use_case, "confirm", session="s2", approval_grant=stage["approval_grant"])
    assert other["error"] is True
    assert "Nothing is waiting for confirmation" in other["spoken"]
    assert other["review_outcome"] is None


# --- refusals -----------------------------------------------------------------------------

def test_confirming_without_the_grant_is_refused_and_nothing_is_sent():
    use_case, github, audit, fake, _ = staged()
    turn = say(use_case, "confirm")
    assert turn["state"] == "REFUSED" and turn["error"] is True
    assert turn["review_outcome"]["refusal_code"] == "MALFORMED"
    assert "not readable" in turn["spoken"] and "Nothing was sent" in turn["spoken"]
    assert turn["earcon"]["type"] == "TEST_FAILED"
    assert fake.posts == [] and github.recorded_requests == []
    assert audit.list_records()[0].execution_stdout == "REFUSED MALFORMED"


def test_a_tampered_grant_is_refused_on_its_signature():
    use_case, _, _, _, stage = staged()
    grant = stage["approval_grant"]
    tampered = grant[:-1] + ("A" if grant[-1] != "A" else "B")
    turn = say(use_case, "confirm", approval_grant=tampered)
    assert turn["review_outcome"]["refusal_code"] == "BAD_SIGNATURE"


def test_a_grant_for_a_different_review_is_refused_as_the_wrong_action():
    use_case, _, _, _, first = staged()
    say(use_case, "cancel")
    second = say(use_case, "request changes: a different comment")
    assert second["approval_grant"] != first["approval_grant"]
    turn = say(use_case, "confirm", approval_grant=first["approval_grant"])
    assert turn["review_outcome"]["refusal_code"] == "WRONG_ACTION"


def test_the_approver_cannot_be_the_principal_that_staged_the_review():
    fake = FakeGitHub()
    use_case, _, audit = build(fake)
    asyncio.run(use_case.handle_turn(
        session_id="agent-session", user_id=STAGING_PRINCIPAL,
        transcript="open", pr_url=PR_URL,
    ))
    stage = asyncio.run(use_case.handle_turn(
        session_id="agent-session", user_id=STAGING_PRINCIPAL,
        transcript="request changes: restore the equality check",
    ))
    turn = asyncio.run(use_case.handle_turn(
        session_id="agent-session", user_id=STAGING_PRINCIPAL, transcript="confirm",
        approval_grant=stage["approval_grant"],
    ))
    assert turn["review_outcome"]["refusal_code"] == "SELF_APPROVAL"
    assert "Custody refused" in turn["spoken"]
    assert audit.list_records()[0].execution_stdout == "REFUSED SELF_APPROVAL"


def test_an_elapsed_lease_refuses_the_confirmation():
    use_case, _, _, _, stage = staged(lease_sec=0.0)
    time.sleep(0.05)
    turn = say(use_case, "confirm", approval_grant=stage["approval_grant"])
    assert turn["review_outcome"]["refusal_code"] == "LEASE_EXPIRED"
    assert turn["state"] == "REFUSED"


def test_a_head_that_moved_after_staging_is_refused_before_anything_is_recorded():
    fake = FakeGitHub()
    use_case, github, audit, fake, stage = staged(fake)
    fake.head = MOVED
    turn = say(use_case, "confirm", approval_grant=stage["approval_grant"])
    assert turn["state"] == "REFUSED"
    outcome = turn["review_outcome"]
    assert outcome["refusal_code"] == "STALE_HEAD"
    assert outcome["expected_head_sha"] == HEAD and outcome["live_head_sha"] == MOVED
    assert "moved from aaaaaaa to bbbbbbb" in turn["spoken"]
    assert turn["earcon"]["type"] == "TEST_FAILED"
    assert fake.posts == [] and github.recorded_requests == []
    assert audit.list_records()[0].execution_stdout.startswith("REFUSED STALE_HEAD")


def test_cancel_drops_the_pending_review_and_a_later_confirm_has_nothing_to_confirm():
    use_case, _, audit, _, stage = staged()
    cancelled = say(use_case, "cancel")
    assert cancelled["spoken"].startswith("Cancelled. Nothing was sent.")
    assert cancelled["awaiting_confirmation"] is False and use_case._pending == {}
    later = say(use_case, "confirm", approval_grant=stage["approval_grant"])
    assert later["error"] is True and later["review_outcome"] is None
    assert audit.list_records() == [], "a cancelled review was never presented, so nothing is sealed"


# --- the live write, when the owner enables it --------------------------------------------

def test_with_the_flag_and_a_token_the_review_is_sent_and_github_answer_is_relayed():
    fake = FakeGitHub()
    use_case, github, audit, fake, stage = staged(fake, token="ghp_secret", write=True)
    turn = say(use_case, "confirm", approval_grant=stage["approval_grant"])
    assert turn["state"] == "SUBMITTED"
    outcome = turn["review_outcome"]
    assert outcome["submitted"] is True and outcome["dry_run"] is False
    assert outcome["response"]["id"] == 4242 and outcome["response"]["commit_id"] == HEAD
    assert outcome["identity"] == "reviewer"
    assert turn["earcon"]["type"] == "ACTION_COMMITTED"
    assert "Submitted" in turn["spoken"] and "as reviewer" in turn["spoken"]
    assert len(fake.posts) == 1
    assert "ghp_secret" not in str(outcome), "the token never appears in an outcome"
    record = audit.list_records()[0]
    assert record.state is ActionState.EXECUTED
    assert record.execution_stdout == f"SUBMITTED review 4242 at {HEAD}"


@pytest.mark.parametrize("status", [401, 403, 404])
def test_a_token_without_permission_is_refused_as_unauthorized_and_audited(status):
    fake = FakeGitHub(write_status=status, write_body={"message": "Resource not accessible"})
    use_case, _, audit, fake, stage = staged(fake, token="ghp_readonly", write=True)
    turn = say(use_case, "confirm", approval_grant=stage["approval_grant"])
    assert turn["state"] == "REFUSED"
    assert turn["review_outcome"]["refusal_code"] == "UNAUTHORIZED"
    assert "pull_requests: write" in turn["review_outcome"]["detail"]
    assert audit.list_records()[0].execution_stdout.startswith("REFUSED UNAUTHORIZED")
    assert audit.list_records()[0].state is ActionState.FAILED


def test_the_flag_without_a_token_refuses_rather_than_sending_unauthenticated():
    use_case, _, _, fake, stage = staged(token=None, write=True)
    turn = say(use_case, "confirm", approval_grant=stage["approval_grant"])
    assert turn["review_outcome"]["refusal_code"] == "NO_TOKEN"
    assert fake.posts == []
    assert turn["review_path"]["resolved_capability"] == "live_write_requested_but_no_token"
