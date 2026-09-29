"""Infrastructure: which commit this process is running, and how that is known.

A deployment sets ``SOURCE_REVISION`` at build time, and that value wins. A
local run has no such variable, but it usually runs from a git checkout, and a
judge testing it should see which commit that is. So the checkout's HEAD is
read once from the repository's own metadata files and labelled as a local
reading. Anything that cannot be read leaves ``unavailable``.

No git process is started: the product imports no process-execution primitive
(``tests/unit/test_no_execution_in_source_tree.py``). The files are read the
way git lays them out, including a worktree, where ``.git`` is a file naming
the real git directory and ``commondir`` names the shared one. Uncommitted
changes cannot be seen this way, and the origin label says so.
"""
import os
import re
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SHA = re.compile(r"^[0-9a-f]{40}$")
LOCAL_ORIGIN = "local git HEAD, uncommitted changes not checked"


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None


def _git_dir(root: Path) -> Path | None:
    dot_git = root / ".git"
    if dot_git.is_dir():
        return dot_git
    pointer = _read(dot_git) if dot_git.is_file() else None
    if pointer and pointer.startswith("gitdir:"):
        target = Path(pointer.split(":", 1)[1].strip())
        return target if target.is_absolute() else (root / target).resolve()
    return None


def _resolve_ref(git_dir: Path, ref: str) -> str | None:
    common = git_dir
    commondir = _read(git_dir / "commondir")
    if commondir:
        common = Path(commondir) if Path(commondir).is_absolute() else (git_dir / commondir).resolve()
    for base in (git_dir, common):
        value = _read(base / ref)
        if value and _SHA.match(value):
            return value
    packed = _read(common / "packed-refs") or ""
    for line in packed.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == ref and _SHA.match(parts[0]):
            return parts[0]
    return None


def read_head(root: Path = REPO_ROOT) -> str | None:
    """The commit HEAD names in the checkout at ``root``, or None."""
    git_dir = _git_dir(root)
    head = _read(git_dir / "HEAD") if git_dir else None
    if not head:
        return None
    if _SHA.match(head):
        return head
    if head.startswith("ref:"):
        return _resolve_ref(git_dir, head.split(":", 1)[1].strip())
    return None


@lru_cache(maxsize=1)
def _local_git_revision() -> tuple[str, str]:
    head = read_head()
    return (head, LOCAL_ORIGIN) if head else ("unavailable", "unavailable")


def source_revision() -> dict[str, str]:
    """``{"source_revision": ..., "source_revision_origin": ...}`` for /health."""
    configured = os.getenv("SOURCE_REVISION")
    if configured:
        return {"source_revision": configured, "source_revision_origin": "SOURCE_REVISION at deploy"}
    revision, origin = _local_git_revision()
    return {"source_revision": revision, "source_revision_origin": origin}
