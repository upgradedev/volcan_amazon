"""octocat/Hello-World pull request 1, as GitHub served it, for offline tests.

This is the pull request the demo opens. Its only file is ``README``, which
has no extension, and its diff ends both sides with ``\ No newline at end of
file``. Both shapes broke a spoken promise before: "what changed in README"
was not recognised, although the overview offers "what changed in a file
name".

Recorded on 2026-09-28 with an unauthenticated read through the product's own
adapter:

    python -c "from src.infrastructure.github_review_adapter import GitHubReviewAdapter; \
      s = GitHubReviewAdapter(token=None).fetch_pull_request( \
      'https://github.com/octocat/Hello-World/pull/1'); print(s.to_dict()); print(repr(s.diff))"

The metadata keeps only the fields the adapter reads. The diff is verbatim.
"""

URL = "https://github.com/octocat/Hello-World/pull/1"
PULL_PATH = "/repos/octocat/Hello-World/pulls/1"
HEAD = "7044a8a032e85b6ab611033b2ac8af7ce85805b2"

META = {
    "html_url": URL,
    "title": "Edited README via GitHub",
    "state": "closed",
    "head": {"sha": HEAD, "ref": "patch-1"},
    "base": {"ref": "master"},
    "user": {"login": "unoju"},
}

DIFF = (
    'diff --git a/README b/README\nindex c57eff55e..719be62e9 100644\n--- a/README\n+++ b/README\n'
    '@@ -1 +1,6 @@\n-Hello World!\n\ No newline at end of file\n+Hello World!\n'
    '+$ mkdir ~/Hello-WorldCreates a directory for your project called "Hello-World" in your user directory\n'
    '+$ cd ~/Hello-WorldChanges the current working directory to your newly created directory\n'
    '+$ git initSets up the necessary Git files\n'
    '+Initialized empty Git repository in /Users/your_user_directory/Hello-World/.git/\n'
    '+$ touch README\n\ No newline at end of file\n'
)
