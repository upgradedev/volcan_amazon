"""/health says which commit answers, and how it knows.

A deployment sets SOURCE_REVISION; a local run from a git checkout reports the
checkout's HEAD, labelled as a local reading. The round 8 review found a local
run answering "unavailable", so a judge could not tell which commit they were
testing.
"""
import re
import subprocess

from src.infrastructure import source_revision as module


def setup_function(_):
    module._local_git_revision.cache_clear()


def teardown_function(_):
    module._local_git_revision.cache_clear()


def test_the_deploy_variable_wins_and_says_where_it_came_from(monkeypatch):
    monkeypatch.setenv("SOURCE_REVISION", "abc123def456")
    assert module.source_revision() == {
        "source_revision": "abc123def456", "source_revision_origin": "SOURCE_REVISION at deploy",
    }


def test_a_local_run_reports_the_checkout_head_labelled_local(monkeypatch):
    monkeypatch.delenv("SOURCE_REVISION", raising=False)
    head = subprocess.run(
        ["git", "-C", str(module.REPO_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=False,
    ).stdout.strip()
    reported = module.source_revision()
    if re.fullmatch(r"[0-9a-f]{40}", head):
        assert reported["source_revision"] == head
        assert reported["source_revision_origin"].startswith("local git HEAD")
    else:  # an export without .git: nothing to read, and it says so
        assert reported == {"source_revision": "unavailable", "source_revision_origin": "unavailable"}


def test_uncommitted_changes_are_named_because_head_then_is_not_the_code(monkeypatch):
    monkeypatch.delenv("SOURCE_REVISION", raising=False)
    sha = "0123456789abcdef0123456789abcdef01234567"
    answers = {"rev-parse": sha + "\n", "status": " M src/domain/review_dialogue.py\n"}
    monkeypatch.setattr(module, "_git", lambda *args: answers[args[0]])
    assert module.source_revision() == {
        "source_revision": sha, "source_revision_origin": "local git HEAD, with uncommitted changes",
    }


def test_no_git_leaves_unavailable_rather_than_a_guess(monkeypatch):
    monkeypatch.delenv("SOURCE_REVISION", raising=False)
    monkeypatch.setattr(module, "_git", lambda *args: None)
    assert module.source_revision() == {"source_revision": "unavailable", "source_revision_origin": "unavailable"}


def test_a_missing_git_binary_is_caught(monkeypatch):
    def boom(*_args, **_kwargs):
        raise FileNotFoundError("git")
    monkeypatch.setattr(module.subprocess, "run", boom)
    assert module._git("rev-parse", "HEAD") is None
