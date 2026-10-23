"""Code fidelity keeps every symbol apart, and literary fidelity says what it lost.

The six-dot literary map has 63 non-blank cells and code uses more symbols
than that, so ``(``, ``)`` and ``=`` share a cell. That was the state of the
product until 2026-09-08 and it was undisclosed. Two things are pinned here:
the eight-dot code table is injective over the 95 printable ASCII characters
and decodes back exactly, and the literary rendering names, per patch, the
characters it made indistinguishable.
"""
import os
import re

from src.application.braille_diff_use_case import BrailleDiffUseCase
from src.domain.braille_translator import (
    CODE_BRAILLE_MAP,
    FIDELITY_CODE,
    FIDELITY_LITERARY,
    UNSUPPORTED_CELL,
    BrailleDiffDigest,
    braille_to_text,
    cell,
    code_fidelity_table,
    dots_of,
    literary_collisions,
    text_to_braille,
)

PRINTABLE = "".join(chr(code) for code in range(32, 127))
# The full code table moved from the README to docs/EVIDENCE.md when the README
# became a one-screen story; the check follows the table to where it now lives.
README_PATH = os.path.join(os.path.dirname(__file__), "../../docs/EVIDENCE.md")


def test_dot_numbers_map_to_the_unicode_block_bit_for_bit():
    assert cell("") == "⠀"
    assert cell("1") == "⠁"
    assert cell("2346") == "⠮", "dots 2, 3, 4 and 6 are bits 1, 2, 3 and 5"
    assert cell("17") == "⡁", "dot 7 is bit 6, the top half of the block"
    assert cell("12345678") == "⣿"
    assert dots_of(cell("124567")) == "124567"


def test_every_printable_ascii_character_has_its_own_cell():
    cells = [CODE_BRAILLE_MAP[char] for char in PRINTABLE]
    assert len(PRINTABLE) == 95
    assert len(set(cells)) == 95, "two printable characters share a cell"
    assert all("⠀" <= c <= "⣿" for c in cells)


def test_the_code_round_trip_is_exact_for_a_code_line():
    line = 'return user.role != "admin"  # (a) [b] {c} <d> _e_ `f` ~g~ \\h\\ |i|'
    assert braille_to_text(text_to_braille(line, FIDELITY_CODE)) == line
    assert braille_to_text(text_to_braille(PRINTABLE, FIDELITY_CODE)) == PRINTABLE


def test_the_symbols_that_collided_in_literary_mode_are_distinct_in_code_mode():
    for group in ("()=", "]w", '">', "'@", "_"):
        rendered = [CODE_BRAILLE_MAP[c] for c in group]
        assert len(set(rendered)) == len(group), f"{group!r} still collide"
    assert CODE_BRAILLE_MAP["A"] != CODE_BRAILLE_MAP["a"]
    assert dots_of(CODE_BRAILLE_MAP["A"]) == "17", "a capital carries dot 7, not a prefix cell"
    assert dots_of(CODE_BRAILLE_MAP["a"]) == "1"


def test_lower_range_symbols_take_the_six_dot_cell_and_their_partners_take_dot_seven():
    assert dots_of(CODE_BRAILLE_MAP["{"]) == "246" and dots_of(CODE_BRAILLE_MAP["["]) == "2467"
    assert dots_of(CODE_BRAILLE_MAP["|"]) == "1256" and dots_of(CODE_BRAILLE_MAP["\\"]) == "12567"
    assert dots_of(CODE_BRAILLE_MAP["}"]) == "12456" and dots_of(CODE_BRAILLE_MAP["]"]) == "124567"
    assert dots_of(CODE_BRAILLE_MAP["~"]) == "45" and dots_of(CODE_BRAILLE_MAP["^"]) == "457"
    assert dots_of(CODE_BRAILLE_MAP["`"]) == "4" and dots_of(CODE_BRAILLE_MAP["@"]) == "47"


def test_literary_mode_is_still_lossy_and_says_so_per_patch():
    patch = '+    return user.role != "admin" or (x) == y > z\n'
    collisions = literary_collisions(patch)
    cells = {entry["dots"]: entry["characters"] for entry in collisions}
    assert cells["2356"] == ["(", ")", "="], "the three collided symbols must be named together"
    assert '"' in cells["5"] and ">" in cells["5"]
    digest = BrailleDiffDigest.from_diff(patch, FIDELITY_LITERARY)
    assert digest.lossless is False
    assert "lossy for code" in digest.disclosure
    assert "'(' and ')' and '='" in digest.disclosure


def test_literary_mode_without_character_collisions_does_not_promise_reversibility():
    digest = BrailleDiffDigest.from_diff("+hello world\n", FIDELITY_LITERARY)
    assert digest.lossless is False
    assert "non-reversible" in digest.disclosure
    assert "nothing was lost here" not in digest.disclosure


def test_code_mode_defaults_for_a_patch_and_declares_itself_lossless():
    digest = BrailleDiffDigest.from_diff('+    return user.role != "admin"\n')
    assert digest.fidelity == FIDELITY_CODE
    assert digest.lossless is True
    assert digest.collisions == []
    assert digest.lines[0].braille.startswith("⠬ "), "the tactile add marker stays"
    assert braille_to_text(digest.lines[0].braille[2:]) == '+    return user.role != "admin"'


def test_a_character_outside_the_table_is_marked_not_blanked():
    digest = BrailleDiffDigest.from_diff("+name = 'Ζεύς'\n")
    assert digest.lossless is False
    assert digest.unsupported == sorted(set("Ζεύς"))
    assert UNSUPPORTED_CELL in digest.lines[0].braille
    assert "non-ASCII" in digest.disclosure
    assert "�" in braille_to_text(digest.lines[0].braille)


def test_an_unknown_fidelity_is_refused():
    try:
        text_to_braille("x", "grade2")
    except ValueError as exc:
        assert "grade2" in str(exc)
    else:
        raise AssertionError("an unknown fidelity must not silently pick one")


def test_the_use_case_reports_fidelity_and_loss_beside_the_cells():
    use_case = BrailleDiffUseCase()
    code = use_case.digest_to_braille("+x = (a) == b\n")
    literary = use_case.digest_to_braille("+x = (a) == b\n", FIDELITY_LITERARY)
    assert code["fidelity"] == "code" and code["lossless"] is True
    assert literary["fidelity"] == "literary" and literary["lossless"] is False
    assert literary["collisions"][0]["characters"] == ["(", ")", "="]
    prose = use_case.translate_text("Aws Bedrock 2026")
    assert prose["fidelity"] == "literary"
    exact = use_case.translate_text("f(x) == y", FIDELITY_CODE)
    assert exact["decoded_text"] == "f(x) == y"


def test_the_readme_prints_the_table_the_code_uses():
    """The evidence document says which symbol lands on which cell. It must be this table."""
    with open(README_PATH, "r", encoding="utf-8") as handle:
        readme = handle.read()
    block = re.search(r"<!-- braille-code-table -->\n```\n(.*?)\n```", readme, flags=re.S)
    assert block, "docs/EVIDENCE.md no longer carries the code-fidelity table block"
    expected = "\n".join(
        f"{char!r:6} dots {dots or 'blank':9} {rendered}" for char, dots, rendered in code_fidelity_table()
    )
    assert block.group(1) == expected, "the docs/EVIDENCE.md table drifted from src/domain/braille_translator.py"
