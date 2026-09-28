"""A scripted GitHub behind ``httpx.MockTransport``, shared by every test that
opens or reviews a pull request.

Nothing here leaves the process. The fake answers the three requests the
adapter makes: the pull request metadata (with the head SHA), the same URL with
the diff media type, the authenticated user, and the review write. What the
head is *now* and how the write answers are both scripted, because the two
refusals worth proving are a head that moved and a token that lacks permission.
"""
import httpx

HEAD = "a" * 40
MOVED = "b" * 40
PR_URL = "https://github.com/octo/demo/pull/7"

#: The patch the fake serves: an inverted authorization check, then a benign
#: parser change, so a dialogue over it has a security finding to name and a
#: second file to walk to.
DIFF = (
    "diff --git a/src/auth/permissions.py b/src/auth/permissions.py\n"
    "--- a/src/auth/permissions.py\n"
    "+++ b/src/auth/permissions.py\n"
    "@@ -12,4 +12,4 @@ def can_delete_workspace(user, workspace):\n"
    "     if workspace.locked:\n"
    "         return False\n"
    "-    return user.role == \"admin\"\n"
    "+    return user.role != \"admin\"\n"
    "diff --git a/src/utils/parser.py b/src/utils/parser.py\n"
    "--- a/src/utils/parser.py\n"
    "+++ b/src/utils/parser.py\n"
    "@@ -4,1 +4,3 @@ def normalise(data):\n"
    "-    return data.strip()\n"
    "+    if not data:\n"
    "+        return \"\"\n"
    "+    return data.strip()\n"
)


class FakeGitHub:
    """Callable for ``httpx.MockTransport``. Mutate ``head`` to move the PR."""

    def __init__(self, head: str = HEAD, write_status: int = 200, write_body=None,
                 user_status: int = 200, diff: str = DIFF, *, pull_path: str = "/repos/octo/demo/pulls/7",
                 meta: dict | None = None):
        self.head = head
        #: Which pull request this fake serves, and its metadata apart from the
        #: head, so a recorded pull request (tests/fixtures/hello_world_pr1.py)
        #: can be served in its own shape.
        self.pull_path = pull_path
        self.meta = meta
        self.write_status = write_status
        self.write_body = write_body if write_body is not None else {
            "id": 4242, "html_url": f"{PR_URL}#pullrequestreview-4242",
            "state": "CHANGES_REQUESTED", "commit_id": head,
        }
        self.user_status = user_status
        self.diff = diff
        self.requests: list[httpx.Request] = []

    @property
    def posts(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == "POST"]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.method == "GET" and path == self.pull_path:
            if "diff" in request.headers.get("accept", ""):
                return httpx.Response(200, text=self.diff)
            if self.meta is not None:
                meta = dict(self.meta)
                meta["head"] = {**meta.get("head", {}), "sha": self.head}
                return httpx.Response(200, json=meta)
            return httpx.Response(200, json={
                "html_url": PR_URL, "title": "Flip the check",
                "state": "open", "head": {"sha": self.head, "ref": "feature"},
                "base": {"ref": "main"}, "user": {"login": "octocat"},
            })
        if request.method == "GET" and path == "/user":
            if self.user_status == 200:
                return httpx.Response(200, json={"login": "reviewer"})
            return httpx.Response(self.user_status, json={"message": "Bad credentials"})
        if request.method == "POST" and path == self.pull_path + "/reviews":
            return httpx.Response(self.write_status, json=self.write_body)
        return httpx.Response(404, json={"message": "Not Found"})
