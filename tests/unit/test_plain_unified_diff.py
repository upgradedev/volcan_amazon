"""A plain ``diff -u`` patch must name its file in the spoken sentence.

The README's own diagram calls the input a unified patch, and ``diff -u``
produces a unified patch with no ``diff --git`` header. Before these tests the
parser split only on that header, so an ordinary unified patch narrated as
"Security-sensitive changes in unknown_file". For a reviewer who is listening
rather than reading, that sentence is the whole review.
"""
import asyncio

import pytest

from src.application.digest_diff_use_case import DigestDiffUseCase
from src.domain.semantic_diff import UnifiedDiffParser
from src.infrastructure.bedrock_adapter import BedrockSynthesisAdapter

PLAIN_PATCH = """--- a/src/auth/session.py
+++ b/src/auth/session.py
@@ -12,7 +12,7 @@
 def load(raw):
-    payload = jwt.decode(raw, key, algorithms=["HS256"])
+    payload = jwt.decode(raw, options={"verify_signature": False})
     return payload
"""

#: What ``diff -u old new`` writes: no a/ and b/ prefixes, and a timestamp
#: after a tab on each header line.
DIFF_U_PATCH = (
    "--- src/auth/session.py\t2026-09-08 09:14:02.000000000 +0300\n"
    "+++ src/auth/session.py\t2026-09-08 09:15:31.000000000 +0300\n"
    "@@ -12,7 +12,7 @@\n"
    "-    payload = jwt.decode(raw, key)\n"
    "+    payload = jwt.decode(raw, verify=False)\n"
)

TWO_FILE_PLAIN_PATCH = """--- a/src/api/one.py
+++ b/src/api/one.py
@@ -1,2 +1,2 @@
-    limit = 10
+    limit = 25
--- a/src/api/two.py
+++ b/src/api/two.py
@@ -4,3 +4,3 @@
-    retries = 1
+    retries = 3
"""

#: A deleted SQL comment reaches the patch as a line beginning "--- ", which is
#: the same three characters that open a file header.
SQL_COMMENT_PATCH = """--- a/migrations/0007.sql
+++ b/migrations/0007.sql
@@ -1,3 +1,2 @@
--- legacy backfill, no longer needed
 SELECT 1;
"""


@pytest.fixture
def offline_digest(monkeypatch):
    """A digest use case pinned to the local path, so the sentence is stable."""
    monkeypatch.setattr(BedrockSynthesisAdapter, "credentials_present", lambda self: False)
    return DigestDiffUseCase(BedrockSynthesisAdapter())


def test_a_plain_unified_patch_names_its_file_in_the_voice_summary(offline_digest):
    report = asyncio.run(offline_digest.execute(PLAIN_PATCH))
    summary = report.to_voice_summary(level=0)

    assert "src/auth/session.py" in summary
    assert "unknown_file" not in summary


def test_a_diff_u_patch_with_timestamps_names_its_file(offline_digest):
    report = asyncio.run(offline_digest.execute(DIFF_U_PATCH))
    summary = report.to_voice_summary(level=0)

    assert "src/auth/session.py" in summary
    assert "2026-09-08" not in summary, "the header timestamp must not reach the sentence"


def test_the_git_header_and_the_plain_header_produce_the_same_file_name():
    """Identical content, two patch formats, one spoken file name."""
    git_patch = (
        "diff --git a/src/auth/session.py b/src/auth/session.py\n" + PLAIN_PATCH
    )
    plain = UnifiedDiffParser.parse_patch(PLAIN_PATCH)
    git = UnifiedDiffParser.parse_patch(git_patch)

    assert [s.file_path for s in plain] == [s.file_path for s in git] == ["src/auth/session.py"]
    assert [s.added_count for s in plain] == [s.added_count for s in git]


def test_a_plain_patch_touching_two_files_is_split_into_two_sections():
    sections = UnifiedDiffParser.parse_patch(TWO_FILE_PLAIN_PATCH)
    assert [s.file_path for s in sections] == ["src/api/one.py", "src/api/two.py"]


def test_a_deleted_sql_comment_is_not_mistaken_for_a_file_header():
    sections = UnifiedDiffParser.parse_patch(SQL_COMMENT_PATCH)
    assert [s.file_path for s in sections] == ["migrations/0007.sql"]


def test_a_deleted_file_is_named_from_its_removal_header():
    patch = (
        "--- a/src/legacy/keys.py\n"
        "+++ /dev/null\n"
        "@@ -1,2 +0,0 @@\n"
        "-SECRET = load()\n"
    )
    assert UnifiedDiffParser.parse_patch(patch)[0].file_path == "src/legacy/keys.py"


def test_text_that_is_not_a_patch_still_produces_no_section():
    assert UnifiedDiffParser.parse_patch("just some prose about a change") == []


def test_a_commit_preamble_is_not_read_as_a_nameless_file():
    """`git format-patch` and `git show` put prose above the first header."""
    patch = (
        "commit 38668ad6c16d\n"
        "Author: someone <s@example.com>\n\n"
        "    tighten the admin route\n\n"
        "--- a stray line of prose that opens like a header\n"
        "diff --git a/src/api/admin.py b/src/api/admin.py\n"
        "index 111..222 100644\n"
        "--- a/src/api/admin.py\n"
        "+++ b/src/api/admin.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-x = 1\n"
        "+x = 2\n"
    )
    sections = UnifiedDiffParser.parse_patch(patch)
    assert [s.file_path for s in sections] == ["src/api/admin.py"]
    assert [(s.added_count, s.removed_count) for s in sections] == [(1, 1)]


def test_a_rename_is_named_by_its_new_path():
    patch = (
        "diff --git a/src/old.py b/src/new.py\n"
        "similarity index 90%\n"
        "--- a/src/old.py\n"
        "+++ b/src/new.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-y = 1\n"
        "+y = 2\n"
    )
    assert UnifiedDiffParser.parse_patch(patch)[0].file_path == "src/new.py"
