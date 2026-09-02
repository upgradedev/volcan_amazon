"""Application Use Case: Braille Diff & Tactile Orchestration."""
from typing import Dict, Any
from src.domain.braille_translator import (
    text_to_braille,
    BrailleDiffDigest,
)


class BrailleDiffUseCase:
    """Translates AST diffs and governance leases into Unicode Braille streams."""

    def digest_to_braille(self, raw_diff: str) -> Dict[str, Any]:
        digest = BrailleDiffDigest.from_diff(raw_diff)
        return {
            "total_lines": digest.total_lines,
            "additions": digest.additions_count,
            "deletions": digest.deletions_count,
            "braille_summary": digest.braille_summary,
            "lines": [
                {
                    "type": l.line_type,
                    "text": l.text,
                    "braille": l.braille,
                }
                for l in digest.lines
            ],
        }

    def translate_text(self, text: str) -> Dict[str, Any]:
        return {
            "original_text": text,
            "braille_unicode": text_to_braille(text),
        }
