"""The review dialogue, driven by injected transcripts.

The browser's SpeechRecognition API cannot be driven headlessly and no browser
runs in this suite, so what a microphone would produce is injected here as
text. That is the honest boundary: these tests prove that a given transcript
moves the machine to a given state and produces a given readback and answer,
not that any microphone heard it. The page's own contract is asserted
separately in ``tests/e2e/test_html_structure.py``.
"""
import asyncio

import pytest

from src.application.digest_diff_use_case import DigestDiffUseCase
from src.domain.review_dialogue import (
    RATE_MAX,
    RATE_MIN,
    DialogueState,
    PullRequestSnapshot,
    ReviewDialogue,
    parse_command,
    spell_out,
)
from src.infrastructure.bedrock_adapter import BedrockSynthesisAdapter

PATCH = (
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
HEAD = "0123456789abcdef0123456789abcdef01234567"


def report_for(patch: str = PATCH):
    adapter = BedrockSynthesisAdapter(client_factory=lambda _region: None)
    adapter.credentials_present = lambda: False  # type: ignore[method-assign]
    return asyncio.run(DigestDiffUseCase(adapter).execute(patch))


def pull_request() -> PullRequestSnapshot:
    return PullRequestSnapshot(
        owner="octo", repo="demo", number=7, url="https://github.com/octo/demo/pull/7",
        title="Flip admin check", state="open", head_sha=HEAD, head_ref="feature",
        base_ref="main", author="octocat", diff=PATCH,
    )


def opened(with_pr: bool = True) -> ReviewDialogue:
    dialogue = ReviewDialogue(session_id="t")
    dialogue.load(report_for(), pull_request() if with_pr else None)
    return dialogue


def say(dialogue: ReviewDialogue, transcript: str):
    return dialogue.apply(parse_command(transcript))


# --- the grammar -----------------------------------------------------------------------

@pytest.mark.parametrize(("transcript", "name", "slots"), [
    ("What changed in auth.py?", "focus_file", {"file": "auth.py"}),
    ("what changed in auth dot py", "focus_file", {"file": "auth.py"}),
    ("open permissions.py", "focus_file", {"file": "permissions.py"}),
    ("open the pull request", "open", {}),
    ("open https://github.com/octo/demo/pull/7", "open", {"url": "https://github.com/octo/demo/pull/7"}),
    ("https://github.com/octo/demo/pull/7", "open", {"url": "https://github.com/octo/demo/pull/7"}),
    ("Next line", "next", {"unit": "line"}),
    ("previous", "previous", {}),
    ("read the exact source lines", "read_lines", {}),
    ("line fifteen", "line_number", {"n": "15"}),
    ("file two", "focus_index", {"n": "2"}),
    ("Spell that.", "spell", {}),
    ("say that again", "repeat", {}),
    ("slower", "slower", {}),
    ("Request changes: restore the equality check", "request_changes", {"body": "restore the equality check"}),
    ("request changes", "request_changes", {"body": ""}),
    ("confirm", "confirm", {}),
    ("no", "cancel", {}),
    ("stop", "stop", {}),
    ("where am I", "where", {}),
    ("make me a sandwich", "unknown", {}),
])
def test_transcripts_parse_to_commands(transcript, name, slots):
    command = parse_command(transcript)
    assert command.name == name
    assert command.slots == slots
    assert command.corrected is False


@pytest.mark.parametrize(("transcript", "number"), [
    ("line fifteen", 15),
    ("line twenty-one", 21),
    ("line twenty one", 21),
    ("line one hundred and twelve", 112),
    ("line three hundred", 300),
    ("go to line ninety nine", 99),
])
def test_spoken_line_numbers_become_digits_up_to_three_figures(transcript, number):
    command = parse_command(transcript)
    assert (command.name, command.slots) == ("line_number", {"n": str(number)})


def test_a_number_word_that_is_not_a_number_is_left_alone():
    assert parse_command("file last").slots == {"n": "last"}
    assert parse_command("line and").name == "unknown"


def test_the_review_comment_keeps_the_developers_capitals():
    """The grammar lower-cases to match; the comment goes onto a pull request as typed."""
    command = parse_command("Request changes: keep the NEWS entry format for the Misc tooling.")
    assert command.name == "request_changes"
    assert command.slots["body"] == "keep the NEWS entry format for the Misc tooling"
    assert command.words == "request changes, keep the NEWS entry format for the Misc tooling"


def test_a_correction_wraps_the_command_that_was_meant():
    command = parse_command("No, I said next line")
    assert (command.name, command.slots, command.corrected) == ("next", {"unit": "line"}, True)
    assert parse_command("I meant previous").corrected is True
    assert parse_command("correction: file 2").name == "focus_index"


# --- opening, overview, files ------------------------------------------------------------

def test_before_anything_is_open_navigation_says_so_instead_of_guessing():
    dialogue = ReviewDialogue(session_id="t")
    turn = say(dialogue, "next")
    assert turn.error is True and turn.state is DialogueState.IDLE
    assert "Nothing is open yet" in turn.spoken
    assert turn.readback == "Understood: next."


def test_opening_reads_back_the_commit_and_speaks_the_overview_with_the_verdict_cue():
    dialogue = opened()
    turn = dialogue.last_turn
    assert turn.state is DialogueState.OVERVIEW
    assert "head commit 0123456" in turn.spoken
    assert "Modified 2 files with 4 additions and 2 deletions" in turn.spoken
    assert turn.earcon_type.value == "SECURITY_FINDING"
    assert dialogue.focus()["pull_request"] == "octo/demo pull request 7"


def test_file_by_file_lists_every_file_with_agreeing_plurals():
    turn = say(opened(), "file by file")
    assert "File 1: src/auth/permissions.py, 1 addition, 1 deletion, security finding." in turn.spoken
    assert "File 2: src/utils/parser.py, 3 additions, 1 deletion." in turn.spoken
    assert "1 additions" not in turn.spoken


def test_asking_what_changed_in_a_file_focuses_it_by_basename_and_names_the_finding():
    dialogue = opened()
    turn = say(dialogue, "what changed in permissions dot py")
    assert turn.state is DialogueState.FILE
    assert turn.readback == "Understood: what changed in permissions.py."
    assert "File 1 of 2: src/auth/permissions.py" in turn.spoken
    assert "an authorization comparison was inverted" in turn.spoken
    assert "new lines 12 to 14" in turn.spoken
    assert turn.earcon_type.value == "SECURITY_FINDING"


def test_a_file_that_is_not_in_the_change_is_refused_with_the_real_names():
    turn = say(opened(), "what changed in billing.py")
    assert turn.error is True
    assert "No file matching billing.py" in turn.spoken
    assert "src/auth/permissions.py, src/utils/parser.py" in turn.spoken


def test_next_and_previous_walk_the_files_and_stop_at_the_edges():
    dialogue = opened()
    say(dialogue, "file 1")
    assert "src/utils/parser.py" in say(dialogue, "next").spoken
    edge = say(dialogue, "next")
    assert edge.error is True and "last file" in edge.spoken
    assert "src/auth/permissions.py" in say(dialogue, "previous").spoken
    assert "first file" in say(dialogue, "previous").spoken


# --- exact lines -------------------------------------------------------------------------

def test_read_the_lines_speaks_every_numbered_line_of_the_hunk_verbatim():
    dialogue = opened()
    say(dialogue, "what changed in permissions.py")
    turn = say(dialogue, "read the lines")
    assert turn.state is DialogueState.LINES
    assert "Hunk 1 of 1 in src/auth/permissions.py, def can_delete_workspace(user, workspace):" in turn.spoken
    assert "Old lines 12 to 14, new lines 12 to 14, 4 lines" in turn.spoken
    assert 'Line 3 of 4, removed, old line 14:     return user.role == "admin".' in turn.spoken
    assert 'Line 4 of 4, added, new line 14:     return user.role != "admin".' in turn.spoken
    assert turn.line["index"] == 0 and turn.line["total"] == 4


def test_next_line_previous_line_and_the_edges_of_a_hunk():
    dialogue = opened()
    say(dialogue, "file 1")
    say(dialogue, "read the lines")
    assert "Line 2 of 4, unchanged, line 13:" in say(dialogue, "next").spoken
    assert "Line 3 of 4, removed, old line 14:" in say(dialogue, "next line").spoken
    assert "Line 4 of 4, added, new line 14:" in say(dialogue, "next").spoken
    edge = say(dialogue, "next")
    assert edge.error is True and "last line of this hunk" in edge.spoken
    assert "Line 3 of 4" in say(dialogue, "previous").spoken


def test_a_line_number_jumps_straight_to_that_line_and_says_when_none_exists():
    dialogue = opened()
    say(dialogue, "file 2")
    turn = say(dialogue, "line 5")
    assert turn.state is DialogueState.LINES
    # The hunk is one removed line then three added ones, so new line 5 is
    # the third line of the hunk, and the listener is told so.
    assert 'Line 3 of 4, added, new line 5:         return ""' in turn.spoken
    missing = say(dialogue, "line 99")
    assert missing.error is True and "not inside any hunk" in missing.spoken


def test_spell_that_names_every_symbol_so_bang_equals_cannot_be_heard_as_equals():
    dialogue = opened()
    say(dialogue, "file 1")
    say(dialogue, "read the lines")
    say(dialogue, "line 14")
    turn = say(dialogue, "spell that")
    assert turn.spoken.startswith("Line 4, spelled: 4 leading spaces, r, e, t, u, r, n, space, u, s, e, r, dot, r, o, l, e, space, bang, equals, space, double quote, a, d, m, i, n, double quote.")


def test_spell_out_distinguishes_capitals_and_names_unicode():
    assert spell_out("Ab_1 (x)") == "capital a, b, underscore, 1, space, open paren, x, close paren"
    assert spell_out("") == "blank line"
    assert "unicode 03b6" in spell_out("ζ")


def test_spelling_before_any_line_is_selected_is_refused():
    turn = say(opened(), "spell that")
    assert turn.error is True and "read the lines first" in turn.spoken


# --- repeat, rate, stop, correction --------------------------------------------------------

def test_repeat_says_the_last_content_again_and_a_rate_change_is_not_content():
    dialogue = opened()
    first = say(dialogue, "file by file")
    say(dialogue, "slower")
    again = say(dialogue, "repeat")
    assert again.spoken == first.spoken
    assert again.readback == "Again."


def test_slower_and_faster_move_the_rate_in_steps_and_stop_at_the_limits():
    dialogue = opened()
    assert say(dialogue, "slower").speech_rate == 0.85
    for _ in range(10):
        say(dialogue, "slower")
    floor = say(dialogue, "slower")
    assert floor.speech_rate == RATE_MIN and "the limit" in floor.spoken
    for _ in range(20):
        say(dialogue, "faster")
    assert say(dialogue, "faster").speech_rate == RATE_MAX


def test_stop_is_silent_and_changes_nothing():
    dialogue = opened()
    say(dialogue, "file 1")
    turn = say(dialogue, "stop")
    assert turn.silent is True and turn.spoken == "Stopped."
    assert dialogue.state is DialogueState.FILE and dialogue.file_index == 0


def test_a_correction_undoes_the_misheard_command_before_applying_the_meant_one():
    dialogue = opened()
    say(dialogue, "file 1")
    say(dialogue, "read the lines")
    say(dialogue, "next")           # line 2
    say(dialogue, "next")           # line 3, misheard
    turn = say(dialogue, "no, I said previous")
    assert turn.readback == "Corrected, previous."
    assert "Line 1 of 4" in turn.spoken, "undo the misheard next (back to 2), then previous (to 1)"
    assert dialogue.line_index == 0


def test_a_correction_never_reverts_a_speech_rate_change():
    dialogue = opened()
    say(dialogue, "file 1")
    say(dialogue, "slower")
    say(dialogue, "next")
    turn = say(dialogue, "no, I said previous")
    assert turn.speech_rate == 0.85


def test_undo_restores_the_previous_position_and_says_where_you_are():
    dialogue = opened()
    say(dialogue, "file 1")
    say(dialogue, "next")
    turn = say(dialogue, "undo")
    assert turn.spoken.startswith("Undone.")
    assert dialogue.file_index == 0 and "Focused on file 1" in turn.spoken
    assert say(dialogue, "undo").error is True


def test_an_unrecognised_transcript_reads_back_what_was_heard_and_changes_nothing():
    dialogue = opened()
    say(dialogue, "file 2")
    turn = say(dialogue, "make me a sandwich")
    assert turn.error is True
    assert turn.readback == "I heard 'make me a sandwich' and did not recognise a command."
    assert "Say help" in turn.spoken
    assert dialogue.file_index == 1 and dialogue.state is DialogueState.FILE


def test_findings_are_spoken_with_the_security_cue_and_silence_is_the_ready_cue():
    turn = say(opened(), "findings")
    assert "1 finding." in turn.spoken and turn.earcon_type.value == "SECURITY_FINDING"
    clean = ReviewDialogue(session_id="c")
    clean.load(report_for("--- a/p.py\n+++ b/p.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"))
    assert say(clean, "findings").earcon_type.value == "DIFF_READY"


# --- staging the review, in the domain -----------------------------------------------------

def test_staging_a_review_reads_back_the_body_and_the_head_commit_and_waits():
    dialogue = opened()
    turn = dialogue.stage_review(parse_command("request changes: restore the equality"), "restore the equality")
    assert turn.state is DialogueState.CONFIRM_REVIEW
    assert "bound to head commit 0123456" in turn.spoken
    assert "restore the equality" in turn.spoken
    assert "Say confirm" in turn.spoken
    assert turn.earcon_type.value == "GOVERNANCE_CHALLENGE"
    blocked = say(dialogue, "next")
    assert blocked.error is True and "waiting for your confirmation" in blocked.spoken


def test_a_pasted_patch_cannot_be_reviewed_because_there_is_no_pull_request():
    dialogue = opened(with_pr=False)
    turn = dialogue.stage_review(parse_command("request changes: x"), "x")
    assert turn.error is True and dialogue.state is DialogueState.OVERVIEW
    assert "no pull request to review" in turn.spoken


def test_an_empty_review_body_is_refused():
    dialogue = opened()
    turn = dialogue.stage_review(parse_command("request changes"), "")
    assert turn.error is True and "followed by the comment" in turn.spoken


def test_cancel_drops_the_pending_review_and_returns_to_where_you_were():
    dialogue = opened()
    say(dialogue, "file 1")
    dialogue.stage_review(parse_command("request changes: x"), "x")
    turn = dialogue.cancel_review(parse_command("cancel"))
    assert dialogue.state is DialogueState.FILE and dialogue.pending_body is None
    assert turn.spoken.startswith("Cancelled. Nothing was sent.")


def test_confirm_and_cancel_outside_a_pending_review_are_refused():
    dialogue = opened()
    assert say(dialogue, "confirm").error is True
    assert say(dialogue, "cancel").error is True
