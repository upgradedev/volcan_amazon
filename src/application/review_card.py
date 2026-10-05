"""Application Layer: the data the ui:// review card draws.

The card shows one file of the open patch: the first finding a rule matched in
it, its changed lines, and each changed line in eight-dot code Braille. It is
computed from the same dialogue the spoken turn came from, so the card and the
sentence a listener hears cannot be about different files.

Which file: the one in focus while the developer is in a file or reading its
lines; otherwise the first file a rule matched in, and the first file when no
rule matched anywhere. Which lines: the added and removed lines of the hunk in
focus, or of the first hunk with a change, capped at ``CARD_LINE_LIMIT`` with
the total beside them so a cut is never silent.
"""
from typing import Any

from src.domain.braille_translator import FIDELITY_CODE, text_to_braille, unsupported_characters
from src.domain.review_dialogue import DialogueState, ReviewDialogue
from src.domain.semantic_diff import DiffHunk, DiffSectionDigest

REVIEW_CARD_URI = "ui://volcan/review-card"
#: A card is read at a glance or a few cells at a time on a Braille display;
#: past this many lines "read the lines" in the dialogue is the better tool.
CARD_LINE_LIMIT = 8

_FOCUSED_STATES = (DialogueState.FILE, DialogueState.LINES)


def _changed(hunk: DiffHunk) -> list:
    return [line for line in hunk.lines if line.kind in ("add", "remove")]


def _card_file(dialogue: ReviewDialogue) -> tuple[int, DiffSectionDigest]:
    sections = dialogue.sections
    if dialogue.state in _FOCUSED_STATES and dialogue.section is not None:
        return dialogue.file_index, dialogue.section
    for index, section in enumerate(sections):
        if section.security_flags:
            return index, section
    return 0, sections[0]


def _card_hunk(dialogue: ReviewDialogue, section: DiffSectionDigest, focused: bool) -> DiffHunk | None:
    if focused and dialogue.hunk is not None:
        return dialogue.hunk
    for hunk in section.hunks:
        if _changed(hunk):
            return hunk
    return section.hunks[0] if section.hunks else None


def build_review_card(dialogue: ReviewDialogue, awaiting_confirmation: bool) -> dict[str, Any] | None:
    """The card's data, or None while no patch is open."""
    if not dialogue.sections:
        return None
    file_index, section = _card_file(dialogue)
    focused = dialogue.state in _FOCUSED_STATES and file_index == dialogue.file_index
    hunk = _card_hunk(dialogue, section, focused)
    changed = _changed(hunk) if hunk is not None else []
    shown = changed[:CARD_LINE_LIMIT]
    # The drill-down's own rule: sentences when the rules wrote them, the
    # machine labels otherwise, so a flagged file never reads as unflagged.
    findings = list(section.security_findings) or (
        [f"Flagged for {', '.join(section.security_flags)}."] if section.security_flags else []
    )
    lines = [
        {
            "kind": "added" if line.kind == "add" else "removed",
            "number": line.new_no if line.kind == "add" else line.old_no,
            "text": line.text,
            "braille": text_to_braille(line.text, FIDELITY_CODE),
        }
        for line in shown
    ]
    return {
        "resource_uri": REVIEW_CARD_URI,
        "file_path": section.file_path,
        "file_index": file_index,
        "total_files": len(dialogue.sections),
        "finding": findings[0] if findings else None,
        "finding_count": len(findings),
        "changed_lines": lines,
        "changed_lines_shown": len(lines),
        "changed_lines_total": len(changed),
        "braille_fidelity": FIDELITY_CODE,
        "braille_lossless": not any(unsupported_characters(line.text) for line in shown),
        "can_submit": dialogue.pull_request is not None,
        "awaiting_confirmation": awaiting_confirmation,
    }
