"""Loss is disclosed beside the cells, including cards and terminal drawings."""
import pytest

from scripts.braille_terminal_simulator import render_tactile_pin_cells
from src.application.braille_diff_use_case import BrailleDiffUseCase
from src.application.review_card import build_review_card
from src.domain.braille_translator import (
    BLANK_CELL,
    FIDELITY_CODE,
    FIDELITY_LITERARY,
    LITERARY_UNSUPPORTED_CELL,
    UNSUPPORTED_CELL,
    BrailleDiffDigest,
    braille_to_text,
    cell,
    text_to_braille,
)
from src.domain.review_dialogue import ReviewDialogue
from src.domain.semantic_diff import SemanticDiffReport, UnifiedDiffParser
from src.interfaces.dto import ReviewCard
from src.interfaces.review_card_view import REVIEW_CARD_HTML


@pytest.mark.parametrize("text", ["α", "É", "K", "²", "$", "%", "|", "\x00"])
def test_literary_unsupported_characters_are_marked_and_disclosed(text):
    use_case = BrailleDiffUseCase()
    translated = use_case.translate_text(text, FIDELITY_LITERARY)
    assert translated["braille_unicode"] == LITERARY_UNSUPPORTED_CELL
    assert translated["unsupported"] == [text]
    assert translated["lossless"] is False
    digest = use_case.digest_to_braille("+" + text, FIDELITY_LITERARY)
    assert digest["unsupported"] == [text]
    assert digest["lossless"] is False
    assert "full six-dot cell" in digest["disclosure"]
    assert "nothing was lost here" not in digest["disclosure"]


@pytest.mark.parametrize("fidelity", [FIDELITY_CODE, FIDELITY_LITERARY])
def test_tabs_are_disclosed_as_loss_in_text_and_diff_results(fidelity):
    text = "\treturn ok"
    translated = BrailleDiffUseCase().translate_text(text, fidelity)
    assert translated["lossless"] is False
    assert translated["unsupported"] == []
    assert translated["braille_unicode"].startswith(BLANK_CELL * 4)
    digest = BrailleDiffDigest.from_diff("+" + text, fidelity)
    assert digest.lossless is False
    assert digest.tab_substituted is True
    assert "Tabs were rendered as 4 blank cells." in digest.disclosure
    assert "nothing was lost here" not in digest.disclosure
    assert "decode back to the exact source" not in digest.disclosure
    if fidelity == FIDELITY_CODE:
        assert translated["decoded_text"] == "    return ok"


def test_literary_disclosure_reports_collisions_and_substitutions_together():
    digest = BrailleDiffDigest.from_diff("+\t(x) = α", FIDELITY_LITERARY)
    assert digest.lossless is False
    assert digest.collisions
    assert digest.unsupported == ["α"]
    assert "lossy for code" in digest.disclosure
    assert "full six-dot cell" in digest.disclosure
    assert "Tabs were rendered" in digest.disclosure


def test_code_unsupported_disclosure_does_not_promise_an_exact_round_trip():
    digest = BrailleDiffDigest.from_diff("+α")
    assert digest.lossless is False
    assert UNSUPPORTED_CELL in digest.lines[0].braille
    assert "decode back to the exact source" not in digest.disclosure


@pytest.mark.parametrize(
    ("text", "lossless"), [("\treturn ok", False), ("return α", False), ("    return ok", True)],
)
def test_review_card_loss_agrees_with_the_code_translation(text, lossless):
    patch = (
        "diff --git a/example.py b/example.py\n"
        "--- a/example.py\n+++ b/example.py\n@@ -0,0 +1 @@\n+" + text + "\n"
    )
    sections = UnifiedDiffParser.parse_patch(patch)
    report = SemanticDiffReport(1, 1, 0, "One added line.", {}, [], sections)
    card = build_review_card(ReviewDialogue("braille-test", report=report), False)
    assert card["changed_lines"][0]["text"] == text
    assert card["braille_lossless"] is lossless
    assert card["braille_lossless"] == BrailleDiffUseCase().translate_text(text, "code")["lossless"]
    assert ReviewCard.model_validate(card).braille_lossless is lossless


def test_review_card_disclosure_names_both_tabs_and_unsupported_characters():
    assert "Tabs become blank cells; unsupported characters become full cells." in REVIEW_CARD_HTML


def test_terminal_matrix_preserves_every_distinct_eight_dot_cell():
    drawings = {
        render_tactile_pin_cells(chr(0x2800 + bits), max_cells=1)
        for bits in range(256)
    }
    assert len(drawings) == 256, "no two different cells may have the same pin drawing"
    assert render_tactile_pin_cells(cell("78"), 1).splitlines() == [
        "+--+", "|..|", "|..|", "|..|", "|oo|", "+--+",
    ]


def test_terminal_code_capitals_and_padding_keep_their_meaning():
    lower = text_to_braille("a", FIDELITY_CODE)
    upper = text_to_braille("A", FIDELITY_CODE)
    assert braille_to_text(upper) == "A"
    assert render_tactile_pin_cells(lower, 1) != render_tactile_pin_cells(upper, 1)
    assert render_tactile_pin_cells(" ", 1) == render_tactile_pin_cells(BLANK_CELL, 1)
    assert render_tactile_pin_cells("", 1) == render_tactile_pin_cells(BLANK_CELL, 1)
