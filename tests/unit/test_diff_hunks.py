"""The parser numbers every line of every hunk.

A spoken review that cannot say "old line 14" and "new line 14" is a summary,
and the dialogue promises the exact source lines. These tests pin the line
numbering the domain produces from a unified diff, including the two shapes a
parser gets wrong first: a hunk header with an omitted count, and the
``\\ No newline at end of file`` marker that is not a line.
"""
from src.domain.semantic_diff import UnifiedDiffParser, plural

PATCH = (
    "diff --git a/src/auth/permissions.py b/src/auth/permissions.py\n"
    "--- a/src/auth/permissions.py\n"
    "+++ b/src/auth/permissions.py\n"
    "@@ -12,4 +12,4 @@ def can_delete_workspace(user, workspace):\n"
    "     if workspace.locked:\n"
    "         return False\n"
    "-    return user.role == \"admin\"\n"
    "+    return user.role != \"admin\"\n"
    "@@ -40,2 +40,3 @@ def audit(user):\n"
    "     log(user)\n"
    "+    log(user.role)\n"
    "     return True\n"
    "\\ No newline at end of file\n"
)


def test_every_line_of_a_hunk_is_numbered_on_the_side_it_belongs_to():
    section = UnifiedDiffParser.parse_patch(PATCH)[0]
    assert len(section.hunks) == 2
    first = section.hunks[0]
    assert first.header == "def can_delete_workspace(user, workspace):"
    assert [(line.kind, line.old_no, line.new_no) for line in first.lines] == [
        ("context", 12, 12),
        ("context", 13, 13),
        ("remove", 14, None),
        ("add", None, 14),
    ]
    assert first.lines[2].text == '    return user.role == "admin"'
    assert first.lines[3].text == '    return user.role != "admin"'


def test_the_no_newline_marker_is_not_a_line_and_context_advances_both_counters():
    second = UnifiedDiffParser.parse_patch(PATCH)[0].hunks[1]
    assert [(line.kind, line.old_no, line.new_no) for line in second.lines] == [
        ("context", 40, 40),
        ("add", None, 41),
        ("context", 41, 42),
    ]
    assert second.added_lines == ["    log(user.role)"]
    assert second.removed_lines == []


def test_a_header_with_an_omitted_count_means_one_line():
    section = UnifiedDiffParser.parse_patch(
        "--- a/p.py\n+++ b/p.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
    )[0]
    hunk = section.hunks[0]
    assert (hunk.old_start, hunk.old_lines, hunk.new_start, hunk.new_lines) == (1, 1, 1, 1)
    assert [(line.kind, line.old_no, line.new_no) for line in hunk.lines] == [
        ("remove", 1, None), ("add", None, 1),
    ]


def test_a_plain_unified_patch_gets_hunks_too():
    sections = UnifiedDiffParser.parse_patch(
        "--- a/one.py\n+++ b/one.py\n@@ -3,2 +3,2 @@\n-a\n+b\n"
        "--- a/two.py\n+++ b/two.py\n@@ -7,1 +7,2 @@\n c\n+d\n"
    )
    assert [s.file_path for s in sections] == ["one.py", "two.py"]
    assert sections[1].hunks[0].lines[1].new_no == 8


def test_the_section_summary_pluralises_its_count():
    """'Changed 1 lines' is the defect the product exists to stop."""
    one = UnifiedDiffParser.parse_patch("--- a/p.py\n+++ b/p.py\n@@ -1 +1 @@\n-x\n+y\n")[0]
    many = UnifiedDiffParser.parse_patch("--- a/p.py\n+++ b/p.py\n@@ -1 +1,2 @@\n-x\n+y\n+z\n")[0]
    assert one.summary_spoken.startswith("Changed 1 line in")
    assert many.summary_spoken.startswith("Changed 2 lines in")
    assert "_" not in one.summary_spoken, "a listener hears an underscore as a word"
    assert plural(1, "line") == "1 line"
