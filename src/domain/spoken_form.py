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


def speakable(text: str) -> str:
    """``text`` with each code operator spoken by name, for a speech engine."""
    named = _OPERATOR.sub(lambda match: f" {_NAMES[match.group(0)]} ", text)
    named = _QUOTED_STAR.sub(r"\1star\1", named)
    return re.sub(r"[ \t]{2,}", " ", named).strip()
