"""/health says which commit answers, and how it knows.

A deployment sets SOURCE_REVISION; a local run from a git checkout reports the
checkout's HEAD, read from git's own files and labelled as a local reading.
The round 8 review found a local run answering "unavailable", so a judge could
not tell which commit they were testing.
"""
import subprocess

from src.infrastructure import source_revision as module

SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER = "fedcba9876543210fedcba9876543210fedcba98"


def setup_function(_):
    module._local_git_revision.cache_clear()


def teardown_function(_):
    module._local_git_revision.cache_clear()


def test_the_deploy_variable_wins_and_says_where_it_came_from(monkeypatch):
    monkeypatch.setenv("SOURCE_REVISION", "abc123def456")
    assert module.source_revision() == {
        "source_revision": "abc123def456", "source_revision_origin": "SOURCE_REVISION at deploy",
    }


def test_a_local_run_reports_what_git_itself_calls_head(monkeypatch):
    monkeypatch.delenv("SOURCE_REVISION", raising=False)
    # The test may start git; the product may not, which is why it reads files.
    head = subprocess.run(
        ["git", "-C", str(module.REPO_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=False,
    ).stdout.strip()
    reported = module.source_revision()
    if head:
        assert reported == {"source_revision": head, "source_revision_origin": module.LOCAL_ORIGIN}
    else:  # an export without git: nothing to read, and it says so
        assert reported == {"source_revision": "unavailable", "source_revision_origin": "unavailable"}


def test_a_branch_head_resolves_through_a_loose_ref(tmp_path):
    (tmp_path / ".git" / "refs" / "heads").mkdir(parents=True)
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (tmp_path / ".git" / "refs" / "heads" / "main").write_text(SHA + "\n")
    assert module.read_head(tmp_path) == SHA


def test_a_worktree_follows_gitdir_and_commondir_to_packed_refs(tmp_path):
    common = tmp_path / "main.git"
    worktree_git = common / "worktrees" / "wt"
    worktree_git.mkdir(parents=True)
    (worktree_git / "HEAD").write_text("ref: refs/heads/feature\n")
    (worktree_git / "commondir").write_text("../..\n")
    (common / "packed-refs").write_text(f"# pack-refs with: peeled\n{OTHER} refs/heads/main\n{SHA} refs/heads/feature\n")
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".git").write_text(f"gitdir: {worktree_git}\n")
    assert module.read_head(checkout) == SHA


def test_a_detached_head_is_the_sha_itself(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text(SHA + "\n")
    assert module.read_head(tmp_path) == SHA


def test_no_checkout_leaves_unavailable_rather_than_a_guess(monkeypatch, tmp_path):
    monkeypatch.delenv("SOURCE_REVISION", raising=False)
    assert module.read_head(tmp_path) is None
    monkeypatch.setattr(module, "read_head", lambda *args: None)
    assert module.source_revision() == {"source_revision": "unavailable", "source_revision_origin": "unavailable"}


def test_a_ref_that_names_no_commit_is_not_reported(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/gone\n")
    assert module.read_head(tmp_path) is None
