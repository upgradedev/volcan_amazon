"""Infrastructure Adapter: GitHub pull request reads, and a review submission
that is dry-run by default.

Two halves, with different trust:

* **Reading** a pull request is an unauthenticated GitHub REST call for a
  public repository, so ``fetch_pull_request`` works with no token at all. It
  returns the head commit SHA together with the diff, because a review is only
  meaningful against the exact commit the reviewer heard.
* **Writing** a ``REQUEST_CHANGES`` review is a real external side effect and
  ships behind a dry-run default. Without ``VOLCAN_GITHUB_WRITE=1`` the adapter
  performs the same live checks it would perform before sending, then records
  the exact request it would have sent, token redacted, and sends nothing. With
  the variable set it sends the request with the token in ``GITHUB_TOKEN`` and
  reports GitHub's answer, refusal included.

Before a review leaves this process, live or dry-run, the adapter re-reads the
pull request's head SHA and refuses with ``STALE_HEAD`` when it no longer equals
the SHA the review was prepared against. A live send is also refused with
``NO_TOKEN`` when no token is present and with ``UNAUTHORIZED`` when GitHub
answers 401, 403 or 404 for the write, which is how GitHub reports a token that
lacks the ``pull_requests: write`` permission on that repository.

The HTTP transport is injectable so every path here is exercised against a
mock in ``tests/unit/test_github_review_adapter.py``. No live write has been
performed from this repository; see the README for the owner action that
produces one.
"""
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

from src.domain.review_dialogue import PullRequestSnapshot

GITHUB_API = "https://api.github.com"
API_VERSION = "2022-11-28"
USER_AGENT = "volcan-accessible-forge"
WRITE_FLAG = "VOLCAN_GITHUB_WRITE"
TOKEN_ENV = "GITHUB_TOKEN"

PR_URL = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)"
    r"/pull/(?P<number>\d+)(?:[/?#].*)?$"
)

REFUSAL_STALE_HEAD = "STALE_HEAD"
REFUSAL_NO_TOKEN = "NO_TOKEN"
REFUSAL_UNAUTHORIZED = "UNAUTHORIZED"
REFUSAL_REJECTED = "REJECTED_BY_GITHUB"
REFUSAL_UNREACHABLE = "GITHUB_UNREACHABLE"

CAPABILITY_LIVE = "live_write_enabled"
CAPABILITY_DRY_RUN_TOKEN = "dry_run_with_token"
CAPABILITY_DRY_RUN_NO_TOKEN = "dry_run_no_token"
CAPABILITY_LIVE_NO_TOKEN = "live_write_requested_but_no_token"


class GitHubReadError(Exception):
    """A pull request could not be read. ``status`` is GitHub's HTTP status."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class ReviewSubmission:
    """What presenting a review produced. A refusal is a first-class outcome."""

    submitted: bool
    dry_run: bool
    refusal_code: str | None
    detail: str
    expected_head_sha: str
    live_head_sha: str | None
    identity: str | None = None
    #: The exact request that was, or would have been, sent. The token is
    #: redacted; everything else is verbatim.
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    #: In a dry run, the refusal a live send would have met, when one is known
    #: without sending. ``NO_TOKEN`` is the only one knowable in advance.
    would_be_refused_live: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def spoken(self) -> str:
        short = self.expected_head_sha[:7]
        if self.submitted:
            review = self.response or {}
            who = f" as {self.identity}" if self.identity else ""
            return (
                f"Submitted. A request changes review, id {review.get('id')}, is now on the "
                f"pull request at commit {short}{who}."
            )
        if self.dry_run:
            base = (
                f"Dry run. Nothing was sent to GitHub. The head commit is still {short}, and "
                "the exact request Volcan would send has been recorded."
            )
            if self.would_be_refused_live == REFUSAL_NO_TOKEN:
                base += " A live send would be refused: no GITHUB_TOKEN is set."
            return base
        return f"Refused, {self.refusal_code}. {self.detail}"


@dataclass
class GitHubReviewAdapter:
    token: str | None = field(default=None)
    write_enabled: bool | None = field(default=None)
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    base_url: str = GITHUB_API
    timeout_sec: float = 15.0
    #: Every dry-run request this process has recorded, newest last.
    recorded_requests: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.token is None:
            self.token = os.getenv(TOKEN_ENV) or None
        if self.write_enabled is None:
            self.write_enabled = os.getenv(WRITE_FLAG) == "1"

    # -- capability, for /health ---------------------------------------------

    def capability(self) -> dict[str, Any]:
        """What ``/health`` can honestly say about the review path. No token value leaks."""
        token = bool(self.token)
        if self.write_enabled and token:
            resolved, detail = CAPABILITY_LIVE, (
                f"{WRITE_FLAG}=1 and a {TOKEN_ENV} are both set, so a confirmed request "
                "changes review is sent to GitHub for real. Reads need no token."
            )
        elif self.write_enabled:
            resolved, detail = CAPABILITY_LIVE_NO_TOKEN, (
                f"{WRITE_FLAG}=1 is set but no {TOKEN_ENV} is, so a confirmed review is "
                f"refused with {REFUSAL_NO_TOKEN} rather than sent unauthenticated."
            )
        elif token:
            resolved, detail = CAPABILITY_DRY_RUN_TOKEN, (
                f"A {TOKEN_ENV} is set and {WRITE_FLAG} is not, so a confirmed review is "
                "recorded as the exact request Volcan would send, and nothing is sent."
            )
        else:
            resolved, detail = CAPABILITY_DRY_RUN_NO_TOKEN, (
                f"Neither {WRITE_FLAG} nor {TOKEN_ENV} is set, so a confirmed review is "
                "recorded and not sent, and public pull requests are read unauthenticated."
            )
        return {
            "resolved_capability": resolved,
            "detail": detail,
            "write_enabled": bool(self.write_enabled),
            "token_present": token,
            "api": self.base_url,
        }

    # -- HTTP plumbing ---------------------------------------------------------

    def _headers(self, accept: str = "application/vnd.github+json") -> dict[str, str]:
        headers = {
            "Accept": accept,
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": USER_AGENT,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            transport=self.transport,
            timeout=self.timeout_sec,
            follow_redirects=True,
        )

    @staticmethod
    def _redact(headers: dict[str, str]) -> dict[str, str]:
        redacted = dict(headers)
        if "Authorization" in redacted:
            redacted["Authorization"] = "Bearer <redacted GITHUB_TOKEN>"
        return redacted

    @staticmethod
    def parse_pull_request_url(url: str) -> tuple[str, str, int]:
        match = PR_URL.match((url or "").strip())
        if not match:
            raise ValueError(
                f"'{url}' is not a GitHub pull request URL; expected "
                "https://github.com/<owner>/<repo>/pull/<number>."
            )
        return match.group("owner"), match.group("repo"), int(match.group("number"))

    # -- reads -----------------------------------------------------------------

    def _get(self, client: httpx.Client, path: str, accept: str) -> httpx.Response:
        try:
            return client.get(path, headers=self._headers(accept))
        except httpx.HTTPError as exc:
            raise GitHubReadError(f"GitHub could not be reached: {type(exc).__name__}: {exc}") from exc

    def fetch_pull_request(self, url: str) -> PullRequestSnapshot:
        """The pull request behind ``url``: its head SHA and its diff, read live."""
        owner, repo, number = self.parse_pull_request_url(url)
        path = f"/repos/{owner}/{repo}/pulls/{number}"
        with self._client() as client:
            meta = self._get(client, path, "application/vnd.github+json")
            if meta.status_code != 200:
                raise GitHubReadError(
                    f"GitHub answered HTTP {meta.status_code} for {owner}/{repo}#{number}: "
                    f"{_message_of(meta)}",
                    status=meta.status_code,
                )
            body = meta.json()
            diff = self._get(client, path, "application/vnd.github.v3.diff")
            if diff.status_code != 200:
                raise GitHubReadError(
                    f"GitHub answered HTTP {diff.status_code} for the diff of "
                    f"{owner}/{repo}#{number}: {_message_of(diff)}",
                    status=diff.status_code,
                )
        return PullRequestSnapshot(
            owner=owner,
            repo=repo,
            number=number,
            url=body.get("html_url") or url,
            title=body.get("title") or "",
            state=body.get("state") or "",
            head_sha=body["head"]["sha"],
            head_ref=body["head"].get("ref") or "",
            base_ref=body.get("base", {}).get("ref") or "",
            author=(body.get("user") or {}).get("login") or "",
            diff=diff.text,
            fetched_with_token=bool(self.token),
        )

    def head_sha(self, owner: str, repo: str, number: int) -> str:
        with self._client() as client:
            meta = self._get(client, f"/repos/{owner}/{repo}/pulls/{number}", "application/vnd.github+json")
        if meta.status_code != 200:
            raise GitHubReadError(
                f"GitHub answered HTTP {meta.status_code} re-reading {owner}/{repo}#{number}: "
                f"{_message_of(meta)}",
                status=meta.status_code,
            )
        return meta.json()["head"]["sha"]

    def whoami(self) -> str | None:
        """The login the token authenticates as, or None without a token or on refusal."""
        if not self.token:
            return None
        with self._client() as client:
            try:
                user = client.get("/user", headers=self._headers())
            except httpx.HTTPError:
                return None
        if user.status_code != 200:
            return None
        return user.json().get("login")

    # -- the write, dry-run by default ----------------------------------------

    def submit_request_changes(
        self, snapshot: PullRequestSnapshot, body: str, expected_head_sha: str,
    ) -> ReviewSubmission:
        """Submit, or in a dry run record, a ``REQUEST_CHANGES`` review.

        The review is bound to ``expected_head_sha`` twice: it is the
        ``commit_id`` in the request, so GitHub attaches the review to that
        commit, and it is compared against the live head first, so a review
        prepared against one commit is never posted against another.
        """
        path = f"/repos/{snapshot.owner}/{snapshot.repo}/pulls/{snapshot.number}/reviews"
        payload = {"commit_id": expected_head_sha, "event": "REQUEST_CHANGES", "body": body}
        request_record = {
            "method": "POST",
            "url": f"{self.base_url}{path}",
            "headers": self._redact(self._headers()),
            "json": payload,
            "token_present": bool(self.token),
        }

        try:
            live_head = self.head_sha(snapshot.owner, snapshot.repo, snapshot.number)
        except GitHubReadError as exc:
            return ReviewSubmission(
                submitted=False, dry_run=False, refusal_code=REFUSAL_UNREACHABLE,
                detail=f"The head commit could not be re-read before submitting: {exc}",
                expected_head_sha=expected_head_sha, live_head_sha=None, request=request_record,
            )

        if live_head != expected_head_sha:
            return ReviewSubmission(
                submitted=False, dry_run=False, refusal_code=REFUSAL_STALE_HEAD,
                detail=(
                    f"The pull request head moved from {expected_head_sha[:7]} to "
                    f"{live_head[:7]} after this review was prepared. Open it again and "
                    "review the new commit; nothing was sent."
                ),
                expected_head_sha=expected_head_sha, live_head_sha=live_head, request=request_record,
            )

        if not self.write_enabled:
            self.recorded_requests.append(request_record)
            return ReviewSubmission(
                submitted=False, dry_run=True, refusal_code=None,
                detail=(
                    f"{WRITE_FLAG} is not set to 1, so the request was recorded and not sent."
                ),
                expected_head_sha=expected_head_sha, live_head_sha=live_head,
                identity=None, request=request_record,
                would_be_refused_live=None if self.token else REFUSAL_NO_TOKEN,
            )

        if not self.token:
            return ReviewSubmission(
                submitted=False, dry_run=False, refusal_code=REFUSAL_NO_TOKEN,
                detail=(
                    f"{WRITE_FLAG}=1 but no {TOKEN_ENV} is set. A review is never sent "
                    "unauthenticated."
                ),
                expected_head_sha=expected_head_sha, live_head_sha=live_head, request=request_record,
            )

        identity = self.whoami()
        with self._client() as client:
            try:
                answer = client.post(path, headers=self._headers(), json=payload)
            except httpx.HTTPError as exc:
                return ReviewSubmission(
                    submitted=False, dry_run=False, refusal_code=REFUSAL_UNREACHABLE,
                    detail=f"GitHub could not be reached for the write: {type(exc).__name__}: {exc}",
                    expected_head_sha=expected_head_sha, live_head_sha=live_head,
                    identity=identity, request=request_record,
                )

        if answer.status_code in (401, 403, 404):
            return ReviewSubmission(
                submitted=False, dry_run=False, refusal_code=REFUSAL_UNAUTHORIZED,
                detail=(
                    f"GitHub answered HTTP {answer.status_code}: {_message_of(answer)}. The token "
                    f"lacks permission to review {snapshot.owner}/{snapshot.repo}; it needs "
                    "pull_requests: write on that repository. GitHub reports a private "
                    "repository the token cannot see as 404."
                ),
                expected_head_sha=expected_head_sha, live_head_sha=live_head,
                identity=identity, request=request_record,
                response={"status": answer.status_code, "message": _message_of(answer)},
            )
        if answer.status_code not in (200, 201):
            return ReviewSubmission(
                submitted=False, dry_run=False, refusal_code=REFUSAL_REJECTED,
                detail=f"GitHub answered HTTP {answer.status_code}: {_message_of(answer)}",
                expected_head_sha=expected_head_sha, live_head_sha=live_head,
                identity=identity, request=request_record,
                response={"status": answer.status_code, "message": _message_of(answer)},
            )

        review = answer.json()
        return ReviewSubmission(
            submitted=True, dry_run=False, refusal_code=None,
            detail="GitHub accepted the review.",
            expected_head_sha=expected_head_sha, live_head_sha=live_head,
            identity=identity, request=request_record,
            response={
                "status": answer.status_code,
                "id": review.get("id"),
                "html_url": review.get("html_url"),
                "state": review.get("state"),
                "commit_id": review.get("commit_id"),
            },
        )


def _message_of(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict) and body.get("message"):
        return str(body["message"])
    return response.text[:200]
