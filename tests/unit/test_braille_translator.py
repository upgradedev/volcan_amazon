"""Unit tests for Braille Translator & Silent Tactile Terminal."""
from src.domain.braille_translator import text_to_braille, BrailleDiffDigest
from src.application.braille_diff_use_case import BrailleDiffUseCase


def test_text_to_braille_alphabet_and_capitals():
    braille = text_to_braille("Alexa")
    # Capital A followed by l, e, x, a
    assert braille.startswith("\u2820\u2801")
    assert len(braille) == 6


def test_text_to_braille_numbers():
    braille = text_to_braille("2026")
    # Number prefix followed by 2, 0, 2, 6
    assert braille.startswith("\u283c")
    assert len(braille) == 5


def test_braille_diff_digest_lines():
    raw_diff = "+def validate_token():\n-return False"
    digest = BrailleDiffDigest.from_diff(raw_diff)
    assert digest.total_lines == 2
    assert digest.additions_count == 1
    assert digest.deletions_count == 1
    assert digest.lines[0].line_type == "ADD"
    assert "\u282c" in digest.lines[0].braille
    assert digest.lines[1].line_type == "REMOVE"
    assert "\u2824" in digest.lines[1].braille


def test_braille_use_case_digest():
    use_case = BrailleDiffUseCase()
    result = use_case.digest_to_braille('+key = validate_kms_token(token)')
    assert result["additions"] == 1
    assert result["deletions"] == 0
    assert "braille_summary" in result
    assert len(result["lines"]) == 1
