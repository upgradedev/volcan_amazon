"""Infrastructure: which commit this process is running, and how that is known.

A deployment sets ``SOURCE_REVISION`` at build time, and that value wins. A
local run has no such variable, but it usually runs from a git checkout, and a
judge testing it should see which commit that is. So the checkout's HEAD is
read once with ``git rev-parse``, labelled as a local reading, and marked when
the working tree carries uncommitted changes, because then HEAD alone does not
describe the code that answers. Anything that fails leaves ``unavailable``.

``.git`` is not read by hand: in a worktree it is a file, not a directory, and
``git`` already knows how to follow it.
"""
import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SHA = re.compile(r"^[0-9a-f]{40}$")


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            capture_output=True, text=True, timeout=3, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


@lru_cache(maxsize=1)
def _local_git_revision() -> tuple[str, str]:
    head = (_git("rev-parse", "HEAD") or "").strip()
    if not _SHA.match(head):
        return "unavailable", "unavailable"
    status = _git("status", "--porcelain", "--untracked-files=no")
    if status is None:
        return head, "local git HEAD, working tree state unknown"
    if status.strip():
        return head, "local git HEAD, with uncommitted changes"
    return head, "local git HEAD"


def source_revision() -> dict[str, str]:
    """``{"source_revision": ..., "source_revision_origin": ...}`` for /health."""
    configured = os.getenv("SOURCE_REVISION")
    if configured:
        return {"source_revision": configured, "source_revision_origin": "SOURCE_REVISION at deploy"}
    revision, origin = _local_git_revision()
    return {"source_revision": revision, "source_revision_origin": origin}
