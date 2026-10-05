"""Launch the real Volcan app with the scripted GitHub of tests/fixtures/fake_github.py.

Usage: python tests/fixtures/fake_github_server.py <port>

A browser test needs a pull request it can open, stage a review on and
confirm. This launcher swaps the process-wide GitHub adapter's transport for
``httpx.MockTransport(FakeGitHub())`` before serving, so the pull request at
``tests.fixtures.fake_github.PR_URL`` opens and no request reaches GitHub.
The write stays the dry-run default, and the Bedrock adapter is told no
credentials resolved, so no model call can leave the process either.
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)


def main(port: int) -> None:
    import httpx
    import uvicorn

    from src.interfaces.composition import bedrock_adapter, github_adapter
    from src.interfaces.mcp_server import app
    from tests.fixtures.fake_github import FakeGitHub

    github_adapter.transport = httpx.MockTransport(FakeGitHub())
    github_adapter.token = None
    github_adapter.write_enabled = False
    bedrock_adapter.credentials_present = lambda refresh=False: False

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main(int(sys.argv[1]))
