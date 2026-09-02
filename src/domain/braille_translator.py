"""Pure Domain Layer: Braille Translator for Silent Tactile Terminal Accessibility.

Supports:
- Computer Braille Code (CBC) & Unified English Braille (UEB Grade 1)
- Unicode Braille Patterns (U+2800 to U+28FF)
- Tactile AST Diff formatting for Refreshable Braille Displays (RBD)
"""
from dataclasses import dataclass
from typing import Dict, List

# Standard ASCII to 6-dot Unicode Braille Mapping (U+2800 - U+283F)
BRAILLE_MAP: Dict[str, str] = {
    " ": "\u2800",
    "a": "\u2801",
    "b": "\u2803",
    "c": "\u2809",
    "d": "\u2819",
    "e": "\u2811",
    "f": "\u280b",
    "g": "\u281b",
    "h": "\u2813",
    "i": "\u280a",
    "j": "\u281a",
    "k": "\u2805",
    "l": "\u2807",
    "m": "\u280d",
    "n": "\u281d",
    "o": "\u2815",
    "p": "\u280f",
    "q": "\u281f",
    "r": "\u2817",
    "s": "\u280e",
    "t": "\u281e",
    "u": "\u2825",
    "v": "\u2827",
    "w": "\u283a",
    "x": "\u282d",
    "y": "\u283d",
    "z": "\u2835",
    "1": "\u2801",
    "2": "\u2803",
    "3": "\u2809",
    "4": "\u2819",
    "5": "\u2811",
    "6": "\u280b",
    "7": "\u281b",
    "8": "\u2813",
    "9": "\u280a",
    "0": "\u281a",
    ",": "\u2802",
    ";": "\u2806",
    ":": "\u2812",
    ".": "\u2832",
    "!": "\u2816",
    "?": "\u2826",
    "(": "\u2836",
    ")": "\u2836",
    "-": "\u2824",
    "+": "\u282c",
    "=": "\u2836",
    "/": "\u280c",
    "\\": "\u2821",
    "*": "\u2814",
    "#": "\u283c",
    "@": "\u2804",
    "_": "\u2820",
    "{": "\u2838",
    "}": "\u281c",
    "[": "\u282a",
    "]": "\u283a",
    "<": "\u2818",
    ">": "\u2810",
    '"': "\u2810",
    "'": "\u2804",
}

CAPITAL_PREFIX = "\u2820"  # Dot 6
NUMBER_PREFIX = "\u283c"   # Dots 3,4,5,6


def text_to_braille(text: str) -> str:
    """Converts plain ASCII text into Unicode Braille patterns."""
    result: List[str] = []
    in_number = False

    for char in text:
        if char.isdigit():
            if not in_number:
                result.append(NUMBER_PREFIX)
                in_number = True
            result.append(BRAILLE_MAP.get(char, "\u2800"))
        else:
            in_number = False
            if char.isupper():
                result.append(CAPITAL_PREFIX)
                result.append(BRAILLE_MAP.get(char.lower(), "\u2800"))
            elif char in BRAILLE_MAP:
                result.append(BRAILLE_MAP[char])
            elif char == "\n":
                result.append("\n")
            else:
                result.append("\u2800")

    return "".join(result)


@dataclass(frozen=True)
class BrailleDiffLine:
    line_type: str  # ADD, REMOVE, HEADER, CONTEXT
    text: str
    braille: str


@dataclass(frozen=True)
class BrailleDiffDigest:
    total_lines: int
    additions_count: int
    deletions_count: int
    lines: List[BrailleDiffLine]
    braille_summary: str

    @classmethod
    def from_diff(cls, diff_text: str) -> "BrailleDiffDigest":
        lines: List[BrailleDiffLine] = []
        adds = 0
        dels = 0

        for raw_line in diff_text.splitlines():
            if raw_line.startswith("+") and not raw_line.startswith("+++"):
                adds += 1
                l_type = "ADD"
                braille_prefix = "\u282c "
            elif raw_line.startswith("-") and not raw_line.startswith("---"):
                dels += 1
                l_type = "REMOVE"
                braille_prefix = "\u2824 "
            elif raw_line.startswith("@@"):
                l_type = "HEADER"
                braille_prefix = "\u283c\u283c "
            else:
                l_type = "CONTEXT"
                braille_prefix = "  "

            b_content = text_to_braille(raw_line)
            lines.append(BrailleDiffLine(line_type=l_type, text=raw_line, braille=f"{braille_prefix}{b_content}"))

        summary_text = f"Diff: +{adds} -{dels} lines."
        braille_summary = text_to_braille(summary_text)

        return cls(
            total_lines=len(lines),
            additions_count=adds,
            deletions_count=dels,
            lines=lines,
            braille_summary=braille_summary,
        )
