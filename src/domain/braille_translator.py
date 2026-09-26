"""Pure Domain Layer: Braille translation for a refreshable display.

Two fidelities, and the difference between them is the whole reason this module
has two:

* ``literary``: six-dot cells with a capital prefix (dot 6) and a number prefix
  (dots 3-4-5-6), the shape of uncontracted English Braille. It is what a
  reader expects for prose. It is **lossy for code**: the six-dot table has 63
  non-blank cells and code uses more symbols than that, so ``(``, ``)`` and
  ``=`` all land on the same cell, ``]`` shares a cell with ``w``, ``"`` with
  ``>``, ``'`` with ``@``, and ``_`` is indistinguishable from the capital
  prefix. A finger reading ``user.role != "admin"`` in this mode cannot tell it
  from ``user.role != >admin>``.
* ``code``: eight-dot computer Braille. Each of the 95 printable ASCII
  characters has its own cell, so the translation is one to one and
  ``braille_to_text`` reverses it exactly. The table is the North American
  Braille ASCII six-dot layout for the 64 characters 0x20 to 0x5F, with dot 7
  added to mark a capital letter and to separate ``@ [ \\ ] ^`` from their
  lower-range partners ``\\` { | } ~``, which is the convention of the North
  American computer Braille code. The property this module promises, and
  ``tests/unit/test_braille_translator.py`` proves, is the round trip: every
  printable character maps to a distinct cell and decodes back to itself. The
  table has not been reviewed by a Braille transcriber, and the README says so
  in the same sentence it names the mode.

Both fidelities render into the Unicode Braille Patterns block, U+2800 to
U+28FF. Dot ``n`` sets bit ``n - 1``, so an eight-dot cell needs the top half of
the block that a six-dot cell never uses.
"""
from dataclasses import dataclass, field
from typing import Dict, List

FIDELITY_LITERARY = "literary"
FIDELITY_CODE = "code"
FIDELITIES = (FIDELITY_CODE, FIDELITY_LITERARY)

BLANK_CELL = "⠀"
#: The full eight-dot cell, used for a character outside the printable ASCII
#: table in code fidelity, so the finger meets a deliberate marker rather than a
#: blank that reads as a space.
UNSUPPORTED_CELL = "⣿"


def cell(dots: str) -> str:
    """The Unicode cell for a dot string such as ``"2346"``. ``""`` is blank."""
    return chr(0x2800 + sum(1 << (int(dot) - 1) for dot in dots))


def dots_of(braille_cell: str) -> str:
    """The dot string of one Unicode Braille cell, ``""`` for the blank."""
    bits = ord(braille_cell) - 0x2800
    return "".join(str(index + 1) for index in range(8) if bits & (1 << index))


# --- literary, six dots, lossy for code --------------------------------------

# Standard ASCII to 6-dot Unicode Braille Mapping (U+2800 - U+283F)
BRAILLE_MAP: Dict[str, str] = {
    " ": "⠀",
    "a": "⠁",
    "b": "⠃",
    "c": "⠉",
    "d": "⠙",
    "e": "⠑",
    "f": "⠋",
    "g": "⠛",
    "h": "⠓",
    "i": "⠊",
    "j": "⠚",
    "k": "⠅",
    "l": "⠇",
    "m": "⠍",
    "n": "⠝",
    "o": "⠕",
    "p": "⠏",
    "q": "⠟",
    "r": "⠗",
    "s": "⠎",
    "t": "⠞",
    "u": "⠥",
    "v": "⠧",
    "w": "⠺",
    "x": "⠭",
    "y": "⠽",
    "z": "⠵",
    "1": "⠁",
    "2": "⠃",
    "3": "⠉",
    "4": "⠙",
    "5": "⠑",
    "6": "⠋",
    "7": "⠛",
    "8": "⠓",
    "9": "⠊",
    "0": "⠚",
    ",": "⠂",
    ";": "⠆",
    ":": "⠒",
    ".": "⠲",
    "!": "⠖",
    "?": "⠦",
    "(": "⠶",
    ")": "⠶",
    "-": "⠤",
    "+": "⠬",
    "=": "⠶",
    "/": "⠌",
    "\\": "⠡",
    "*": "⠔",
    "#": "⠼",
    "@": "⠄",
    "_": "⠠",
    "{": "⠸",
    "}": "⠜",
    "[": "⠪",
    "]": "⠺",
    "<": "⠘",
    ">": "⠐",
    '"': "⠐",
    "'": "⠄",
}

CAPITAL_PREFIX = "⠠"  # Dot 6
NUMBER_PREFIX = "⠼"   # Dots 3,4,5,6


def _literary(text: str) -> str:
    result: List[str] = []
    in_number = False

    for char in text:
        if char.isdigit():
            if not in_number:
                result.append(NUMBER_PREFIX)
                in_number = True
            result.append(BRAILLE_MAP.get(char, BLANK_CELL))
        else:
            in_number = False
            if char.isupper():
                result.append(CAPITAL_PREFIX)
                result.append(BRAILLE_MAP.get(char.lower(), BLANK_CELL))
            elif char in BRAILLE_MAP:
                result.append(BRAILLE_MAP[char])
            elif char == "\n":
                result.append("\n")
            else:
                result.append(BLANK_CELL)

    return "".join(result)


def literary_collisions(text: str) -> List[dict]:
    """Which characters of ``text`` become indistinguishable in literary mode.

    Two characters collide when the six-dot map gives them the same cell. The
    capital and number prefixes are included, because ``_`` is rendered as the
    capital prefix and ``#`` as the number prefix, so a reader cannot tell
    ``my_var`` from ``myVar`` or ``#!`` from ``1!``. Only characters that are
    actually present in ``text`` are reported, so the disclosure names the loss
    in this patch rather than a loss in general.
    """
    by_cell: Dict[str, set] = {}
    for char in set(text):
        if char.isupper():
            rendered = BRAILLE_MAP.get(char.lower())
            by_cell.setdefault(CAPITAL_PREFIX, set()).add("capital prefix")
        elif char.isdigit():
            rendered = BRAILLE_MAP.get(char)
            by_cell.setdefault(NUMBER_PREFIX, set()).add("number prefix")
        else:
            rendered = BRAILLE_MAP.get(char)
        if rendered is None:
            continue
        by_cell.setdefault(rendered, set()).add(char.lower() if char.isupper() else char)

    # A digit and the letter that shares its cell only collide when both appear
    # outside a number prefix, which the prefix itself prevents. Letters and
    # digits are therefore not reported against each other.
    collisions = []
    for rendered, chars in sorted(by_cell.items()):
        letters = {c for c in chars if c.isalpha()}
        digits = {c for c in chars if c.isdigit()}
        others = chars - letters - digits
        if letters and digits and not others:
            continue
        if len(chars) >= 2:
            collisions.append({"cell": rendered, "dots": dots_of(rendered), "characters": sorted(chars)})
    return collisions


# --- code, eight dots, one cell per character ---------------------------------

#: North American Braille ASCII: the six-dot cell of each of the 64 characters
#: from space to underscore, written as dot numbers. Letters are listed in
#: upper case because that is the range the table covers; the code table below
#: derives both cases from it.
_BRAILLE_ASCII_DOTS: Dict[str, str] = {
    " ": "", "!": "2346", '"': "5", "#": "3456", "$": "1246", "%": "146", "&": "12346",
    "'": "3", "(": "12356", ")": "23456", "*": "16", "+": "346", ",": "6", "-": "36",
    ".": "46", "/": "34",
    "0": "356", "1": "2", "2": "23", "3": "25", "4": "256", "5": "26", "6": "235",
    "7": "2356", "8": "236", "9": "35",
    ":": "156", ";": "56", "<": "126", "=": "123456", ">": "345", "?": "1456", "@": "4",
    "A": "1", "B": "12", "C": "14", "D": "145", "E": "15", "F": "124", "G": "1245",
    "H": "125", "I": "24", "J": "245", "K": "13", "L": "123", "M": "134", "N": "1345",
    "O": "135", "P": "1234", "Q": "12345", "R": "1235", "S": "234", "T": "2345",
    "U": "136", "V": "1236", "W": "2456", "X": "1346", "Y": "13456", "Z": "1356",
    "[": "246", "\\": "1256", "]": "12456", "^": "45", "_": "456",
}

#: Characters 0x60 and 0x7B to 0x7E take the six-dot cell of their partner in
#: the 0x40 to 0x5E range, and the partner takes dot 7 in addition.
_LOWER_RANGE_PARTNERS = {"`": "@", "{": "[", "|": "\\", "}": "]", "~": "^"}


def _build_code_dots() -> Dict[str, str]:
    table: Dict[str, str] = {}
    for char, dots in _BRAILLE_ASCII_DOTS.items():
        if char.isalpha():
            table[char.lower()] = dots
            table[char] = dots + "7"
        elif char in _LOWER_RANGE_PARTNERS.values():
            table[char] = dots + "7"
        else:
            table[char] = dots
    for lower, partner in _LOWER_RANGE_PARTNERS.items():
        table[lower] = _BRAILLE_ASCII_DOTS[partner]
    return table


CODE_DOTS: Dict[str, str] = _build_code_dots()
CODE_BRAILLE_MAP: Dict[str, str] = {char: cell(dots) for char, dots in CODE_DOTS.items()}
_CODE_REVERSE: Dict[str, str] = {rendered: char for char, rendered in CODE_BRAILLE_MAP.items()}

#: A tab is not a printable character and has no cell of its own. It is rendered
#: as this many blank cells and the digest discloses the substitution.
TAB_WIDTH_CELLS = 4


def _code(text: str) -> str:
    result: List[str] = []
    for char in text:
        if char == "\n":
            result.append("\n")
        elif char == "\t":
            result.append(BLANK_CELL * TAB_WIDTH_CELLS)
        else:
            result.append(CODE_BRAILLE_MAP.get(char, UNSUPPORTED_CELL))
    return "".join(result)


def braille_to_text(cells: str) -> str:
    """Decodes code-fidelity cells back to text. The round trip is exact.

    An unsupported-character marker decodes to U+FFFD, the replacement
    character, because the original was never encoded and nothing here
    pretends otherwise.
    """
    out: List[str] = []
    for rendered in cells:
        if rendered == "\n":
            out.append("\n")
        elif rendered == UNSUPPORTED_CELL:
            out.append("�")
        else:
            out.append(_CODE_REVERSE.get(rendered, "�"))
    return "".join(out)


def unsupported_characters(text: str) -> List[str]:
    """Characters in ``text`` that the code table cannot represent, sorted."""
    return sorted({c for c in text if c not in CODE_BRAILLE_MAP and c not in ("\n", "\t")})


def code_fidelity_table() -> List[tuple]:
    """``(character, dots, cell)`` for all 95 printable ASCII characters.

    Printed into docs/EVIDENCE.md so a reader can check which symbol lands on which
    cell without opening this file, and pinned there by a test so the two
    cannot drift.
    """
    return [(char, CODE_DOTS[char], CODE_BRAILLE_MAP[char]) for char in sorted(CODE_DOTS)]


def text_to_braille(text: str, fidelity: str = FIDELITY_LITERARY) -> str:
    """Converts text into Unicode Braille patterns at the requested fidelity."""
    if fidelity == FIDELITY_CODE:
        return _code(text)
    if fidelity == FIDELITY_LITERARY:
        return _literary(text)
    raise ValueError(f"Unknown Braille fidelity '{fidelity}'; expected one of {FIDELITIES}.")


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
    fidelity: str = FIDELITY_CODE
    #: True only when every character of the patch decodes back to itself.
    lossless: bool = True
    #: Characters that share a cell in this patch, literary fidelity only.
    collisions: List[dict] = field(default_factory=list)
    #: Characters with no cell in the code table, rendered as the full cell.
    unsupported: List[str] = field(default_factory=list)
    #: True when the patch contained a tab that became blank cells.
    tab_substituted: bool = False

    @property
    def disclosure(self) -> str:
        """One sentence a display or a page can print beside the cells."""
        if self.fidelity == FIDELITY_CODE:
            parts = [
                "Eight-dot computer Braille: one cell per printable character, "
                "so every code symbol keeps its own cell and the cells decode back "
                "to the exact source."
            ]
            if self.unsupported:
                parts.append(
                    f"{len(self.unsupported)} non-ASCII characters have no cell in this "
                    "table and are rendered as the full eight-dot cell: "
                    + ", ".join(repr(c) for c in self.unsupported[:6]) + "."
                )
            if self.tab_substituted:
                parts.append(f"Tabs were rendered as {TAB_WIDTH_CELLS} blank cells.")
            return " ".join(parts)
        if not self.collisions:
            return (
                "Six-dot literary Braille with capital and number prefixes. No two "
                "characters in this patch share a cell, so nothing was lost here; "
                "code symbols outside this patch would be."
            )
        named = "; ".join(
            " and ".join(repr(c) for c in entry["characters"]) + f" all read as dots {entry['dots'] or 'blank'}"
            for entry in self.collisions[:5]
        )
        return (
            "Six-dot literary Braille with capital and number prefixes. This mode is "
            f"lossy for code: in this patch {named}. Switch to code fidelity to keep them apart."
        )

    @classmethod
    def from_diff(cls, diff_text: str, fidelity: str = FIDELITY_CODE) -> "BrailleDiffDigest":
        if fidelity not in FIDELITIES:
            raise ValueError(f"Unknown Braille fidelity '{fidelity}'; expected one of {FIDELITIES}.")
        lines: List[BrailleDiffLine] = []
        adds = 0
        dels = 0

        for raw_line in diff_text.splitlines():
            if raw_line.startswith("+") and not raw_line.startswith("+++"):
                adds += 1
                l_type = "ADD"
                braille_prefix = "⠬ "
            elif raw_line.startswith("-") and not raw_line.startswith("---"):
                dels += 1
                l_type = "REMOVE"
                braille_prefix = "⠤ "
            elif raw_line.startswith("@@"):
                l_type = "HEADER"
                braille_prefix = "⠼⠼ "
            else:
                l_type = "CONTEXT"
                braille_prefix = "  "

            b_content = text_to_braille(raw_line, fidelity)
            lines.append(BrailleDiffLine(line_type=l_type, text=raw_line, braille=f"{braille_prefix}{b_content}"))

        summary_text = f"Diff: +{adds} -{dels} lines."
        braille_summary = text_to_braille(summary_text, fidelity)

        if fidelity == FIDELITY_CODE:
            unsupported = unsupported_characters(diff_text)
            tab = "\t" in diff_text
            return cls(
                total_lines=len(lines),
                additions_count=adds,
                deletions_count=dels,
                lines=lines,
                braille_summary=braille_summary,
                fidelity=fidelity,
                lossless=not unsupported and not tab,
                collisions=[],
                unsupported=unsupported,
                tab_substituted=tab,
            )

        collisions = literary_collisions(diff_text)
        return cls(
            total_lines=len(lines),
            additions_count=adds,
            deletions_count=dels,
            lines=lines,
            braille_summary=braille_summary,
            fidelity=fidelity,
            lossless=not collisions,
            collisions=collisions,
            unsupported=[],
            tab_substituted=False,
        )
