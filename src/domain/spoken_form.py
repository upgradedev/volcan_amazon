"""Domain: the spoken form of a sentence that quotes code.

The page shows a finding as the code it is about, ``user.role != 'admin'``,
and the Braille keeps every symbol. A speech engine is less reliable: some
voices drop punctuation, some read ``!=`` as "exclamation equals" and some say
nothing at all for it, and a listener who hears "user dot role admin" on both
sides of a change has been told nothing. The finding this product exists to
catch turns on exactly that difference.

So every sentence a speech engine is handed has its comparison and logical
operators replaced by their names. The text on screen is not changed; this is
a second string, returned beside it, for the synthesiser only.

A model writes Markdown: ``**Spoken summary:**`` and ``*not*`` reached a
speech engine verbatim, which reads the stars aloud or drops the word. The
same second string therefore has lightweight markup stripped first. Only
emphasis-shaped markup goes: a star that could be code (``a*b*c``,
``2 * 3 * x``, ``['*']``) is left alone, and so is ``**`` without letters
inside (``2**10``). Underscore emphasis follows the same guards: ``_not_`` and
``__Note:__`` go, while ``user_role_id``, ``src/_internal_/x.py`` and a
dunder name such as ``__init__`` stay. A ``>`` blockquote marker at a line
start goes; ``>>> print(x)`` and ``x >= 3`` do not.
"""
import re

#: Longest operators first, so ``!==`` is never read as ``!=`` then ``=``.
OPERATOR_NAMES: tuple[tuple[str, str], ...] = (
    ("!==", "not triple equals"),
    ("===", "triple equals"),
    ("!=", "not equals"),
    ("==", "equals equals"),
    ("<=", "less than or equal to"),
    (">=", "greater than or equal to"),
    ("&&", "logical and"),
    ("||", "logical or"),
)

_OPERATOR = re.compile("|".join(re.escape(op) for op, _ in OPERATOR_NAMES))
_NAMES = dict(OPERATOR_NAMES)
#: A quoted star, as in ``allow_origins = ['*']``: a voice that skips
#: symbols would otherwise say "allow origins equals" and stop.
_QUOTED_STAR = re.compile(r"""(['"])\*\1""")
#: Blockquote markers at a line start, nested ones included (``> > x``). Each
#: marker must be followed by a space or a tab, so ``>>>`` and ``>=`` stay.
_BLOCKQUOTE = re.compile(r"(?m)^[ \t]{0,3}(?:>[ \t]+)+")
#: ATX heading and bullet markers at a line start. Handled per line before
#: flattening, so a ``#`` or ``-`` mid-sentence is never touched.
_LINE_MARKUP = re.compile(r"(?m)^[ \t]{0,3}(?:#{1,6}[ \t]+|[*\-+][ \t]+)")
#: Inline code keeps its content and loses its ticks: no voice says a tick.
_CODE_SPAN = re.compile(r"`([^`\n]+)`")
#: Bold-italic ``***word(s)***`` first: three stars are never a code
#: operator, and the bold rule below refuses stars inside its match.
_BOLD_ITALIC = re.compile(r"(?<![\w*])\*{3}([A-Za-z][^*\n]*?)\*{3}(?![\w*])")
#: Bold when the inner text holds a letter and the markers sit outside words,
#: so ``2**10`` and ``a**b**c`` survive and ``**Spoken summary:**`` does not.
_BOLD = re.compile(r"(?<![\w*])\*\*([^*\n]+?)\*\*(?![\w*])")
#: Emphasis outside words, one word or several: ``*not*`` and ``*does not
#: check*`` go, ``a*b*c`` stays. The inner text starts with a letter and ends
#: on a letter, digit or closing punctuation, never a space or a comma, so
#: ``*args, **kwargs`` and ``2 * 3 * x`` are not read as emphasis.
_ITALIC = re.compile(r"""(?<![\w*])\*([A-Za-z](?:[^*\n]*?[A-Za-z0-9.!?'")])?)\*(?![\w*])""")
#: ``__bold__`` when the markers sit outside words and paths. A name shaped
#: like a Python dunder (``__init__``, ``__main__``) is code, not emphasis.
_UNDERSCORE_BOLD = re.compile(r"(?<![\w/.])__([A-Za-z](?:[^_\n]*?\S)?)__(?![\w/])")
#: ``_italic_`` under the same guards: ``user_role_id`` and ``src/_internal_/x``
#: keep their underscores, because the markers there touch a word or a slash.
_UNDERSCORE_ITALIC = re.compile(r"(?<![\w/.])_([A-Za-z](?:[^_\n]*?\S)?)_(?![\w/])")
_DUNDER_NAME = re.compile(r"[a-z][a-z0-9_]*")
#: A link reads as its text; the URL is spelling no listener asked for.
_LINK = re.compile(r"\[([^\[\]\n]+)\]\((?:[^()\n]*)\)")


def _unbold(match):
    inner = match.group(1)
    if not re.search(r"[A-Za-z]", inner):
        return match.group(0)
    return inner


def _un_underscore_bold(match):
    inner = match.group(1)
    if _DUNDER_NAME.fullmatch(inner):
        return match.group(0)
    return inner


def strip_markdown_for_speech(text: str) -> str:
    """``text`` with lightweight Markdown emphasis removed, code kept.

    Blockquotes, headers, bullets, links, code ticks, ``**bold**``,
    ``***both***``, ``*emphasis*`` over one word or several, ``__bold__`` and
    ``_emphasis_`` are normalised to the words a voice should say. Anything
    shaped like code is preserved: see the guards on each pattern above.
    """
    stripped = _BLOCKQUOTE.sub("", text)
    stripped = _LINE_MARKUP.sub("", stripped)
    stripped = _CODE_SPAN.sub(r"\1", stripped)
    stripped = _BOLD_ITALIC.sub(r"\1", stripped)
    stripped = _BOLD.sub(_unbold, stripped)
    stripped = _ITALIC.sub(r"\1", stripped)
    stripped = _UNDERSCORE_BOLD.sub(_un_underscore_bold, stripped)
    stripped = _UNDERSCORE_ITALIC.sub(r"\1", stripped)
    return _LINK.sub(r"\1", stripped)


def speakable(text: str) -> str:
    """``text`` with each code operator spoken by name, for a speech engine."""
    plain = strip_markdown_for_speech(text)
    named = _OPERATOR.sub(lambda match: f" {_NAMES[match.group(0)]} ", plain)
    named = _QUOTED_STAR.sub(r"\1star\1", named)
    return re.sub(r"[ \t]{2,}", " ", named).strip()
