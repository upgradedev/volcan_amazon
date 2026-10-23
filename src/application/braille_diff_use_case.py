"""Application Use Case: Braille Diff & Tactile Orchestration."""
from typing import Any, Dict

from src.domain.braille_translator import (
    FIDELITY_CODE,
    FIDELITY_LITERARY,
    BrailleDiffDigest,
    braille_to_text,
    literary_collisions,
    text_to_braille,
    unsupported_characters,
)


class BrailleDiffUseCase:
    """Translates AST diffs and governance leases into Unicode Braille streams."""

    def digest_to_braille(self, raw_diff: str, fidelity: str = FIDELITY_CODE) -> Dict[str, Any]:
        digest = BrailleDiffDigest.from_diff(raw_diff, fidelity)
        return {
            "total_lines": digest.total_lines,
            "additions": digest.additions_count,
            "deletions": digest.deletions_count,
            "braille_summary": digest.braille_summary,
            "fidelity": digest.fidelity,
            # The reader is told, in the same response as the cells, whether
            # what they are about to read can be trusted character for
            # character. A lossy rendering that does not say so is a lie a
            # finger cannot detect.
            "lossless": digest.lossless,
            "disclosure": digest.disclosure,
            "collisions": digest.collisions,
            "unsupported": digest.unsupported,
            "lines": [
                {
                    "type": line.line_type,
                    "text": line.text,
                    "braille": line.braille,
                }
                for line in digest.lines
            ],
        }

    def translate_text(self, text: str, fidelity: str = FIDELITY_LITERARY) -> Dict[str, Any]:
        rendered = text_to_braille(text, fidelity)
        if fidelity == FIDELITY_CODE:
            unsupported = unsupported_characters(text)
            return {
                "original_text": text,
                "braille_unicode": rendered,
                "fidelity": fidelity,
                "lossless": not unsupported and "\t" not in text,
                "decoded_text": braille_to_text(rendered),
                "collisions": [],
                "unsupported": unsupported,
            }
        collisions = literary_collisions(text)
        unsupported = unsupported_characters(text, fidelity)
        return {
            "original_text": text,
            "braille_unicode": rendered,
            "fidelity": fidelity,
            # Literary prefixes have sequence ambiguities (1a/11, _a/A).
            # A per-character collision list cannot prove reversibility.
            "lossless": False,
            "disclosure": BrailleDiffDigest.from_diff(text, fidelity).disclosure,
            "decoded_text": None,
            "collisions": collisions,
            "unsupported": unsupported,
        }
