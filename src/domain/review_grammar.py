"""Pure Domain Layer: the grammar of the spoken code review.

What a developer says, as a recogniser or a keyboard delivers it, becomes one
``Command`` here: a name, its slots (a file, a line number, a review comment)
and whether it was a correction of the command before it. Nothing in this
module knows about pull requests, hunks or GitHub; ``review_dialogue.py`` owns
the machine that acts on the commands, and both are driven in tests by injected
transcripts, because the browser's SpeechRecognition API cannot be driven
headlessly and no test here pretends otherwise.

Two rules of the grammar are worth knowing before reading it:

* Matching is case-insensitive, but a review comment keeps the developer's
  capitals, because it is going onto a pull request under their name.
* Spoken numbers become digits for a file, a section or a line, up to nine
  thousand nine hundred and ninety-nine, so "line one hundred and twelve" is
  line 112 and "line one thousand five hundred and seven", "line fifteen
  hundred and seven" and "line fifteen oh seven" are all line 1507. Digits
  are accepted at any size.
"""
import re
from dataclasses import dataclass, field

# --- what was said ----------------------------------------------------------

@dataclass(frozen=True)
class Command:
    name: str
    slots: dict = field(default_factory=dict)
    raw: str = ""
    corrected: bool = False

    @property
    def words(self) -> str:
        """The command in plain words, for the readback."""
        if self.name == "focus_file":
            return f"what changed in {self.slots['file']}"
        if self.name == "focus_index":
            return f"file {self.slots['n']}"
        if self.name == "line_number":
            return f"line {self.slots['n']}"
        if self.name in ("next", "previous"):
            unit = self.slots.get("unit")
            return f"{self.name} {unit}" if unit else self.name
        if self.name == "request_changes":
            body = self.slots.get("body", "")
            return f"request changes, {body}" if body else "request changes"
        if self.name == "open":
            return "open the pull request" if self.slots.get("url") else "open the patch"
        if self.name == "read_lines":
            return "read the lines"
        if self.name == "spell":
            return "spell that"
        return self.name.replace("_", " ")


#: Spoken numbers, as a recogniser hears them. A line number in a real hunk is
#: often three or four digits, so this covers zero to nine thousand nine hundred
#: and ninety-nine, with hyphens, "and", the ordinals a person uses for a file
#: ("the second file"), and the "fifteen oh seven" reading of a four-digit line.
_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}
_ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}
_NUMBER_VOCABULARY = sorted(
    set(_UNITS) | set(_TENS) | set(_ORDINALS) | {"hundred", "thousand", "and", "oh", "o"},
    key=len, reverse=True,
)
_NUMBER_PHRASE = re.compile(
    r"\b(?P<noun>file|section|line)\s+(?P<phrase>(?:(?:" + "|".join(_NUMBER_VOCABULARY)
    + r")(?:[\s-]+|\b))+)"
)


def words_to_number(phrase: str) -> int | None:
    """``"one hundred and twelve"`` is 112; a phrase with a non-number word is None.

    ``"one thousand five hundred and seven"`` and ``"fifteen hundred and
    seven"`` are 1507. So is ``"fifteen oh seven"``: an "oh" (or "o") marks
    the digit-group reading, where each group is written out as digits and
    the groups are joined, so "twenty three oh five" is 2305.
    """
    words = [w for w in re.split(r"[\s-]+", phrase.strip().lower()) if w]
    if not words:
        return None
    if any(w in ("oh", "o") for w in words):
        return _digit_groups_to_number(words)

    thousands = 0
    current = 0
    seen = False
    for word in words:
        if word == "and":
            continue
        if word in _UNITS:
            current += _UNITS[word]
        elif word in _TENS:
            current += _TENS[word]
        elif word in _ORDINALS:
            current += _ORDINALS[word]
        elif word == "hundred":
            current = (current or 1) * 100
        elif word == "thousand":
            if thousands:
                return None
            thousands = (current or 1) * 1000
            current = 0
        else:
            return None
        seen = True
    return thousands + current if seen else None


def _digit_groups_to_number(words: list[str]) -> int | None:
    """``["fifteen", "oh", "seven"]`` is 1507: each group becomes its digits."""
    digits = ""
    group: list[str] = []

    def flush() -> bool:
        nonlocal digits
        if not group:
            return True
        value = words_to_number(" ".join(group))
        if value is None or value >= 100:
            return False
        digits += str(value)
        group.clear()
        return True

    for word in words:
        if word in ("oh", "o"):
            if not flush():
                return None
            digits += "0"
        elif word == "and":
            continue
        else:
            group.append(word)
    if not flush() or not digits:
        return None
    return int(digits)


def _digits_for_spoken_numbers(match: re.Match) -> str:
    phrase = match.group("phrase")
    number = words_to_number(phrase)
    if number is None:
        return match.group(0)
    trailing = " " if phrase.endswith((" ", "-")) else ""
    return f"{match.group('noun')} {number}{trailing}"

_FILE = r"(?P<file>(?!https?://)[\w./-]*\.\w+)"

#: Order matters: a correction wraps another command, a bare "no" is a cancel,
#: and "open auth.py" is a file focus while "open the pull request" is an open.
GRAMMAR: list[tuple[str, re.Pattern]] = [
    ("stop", re.compile(r"^(?:stop|quiet|silence|hush|be quiet|shush)$")),
    ("correction", re.compile(
        r"^(?:no[,.]?\s+i\s+said|no[,.]?\s+i\s+meant|i\s+meant|i\s+said|correction[:,]?|"
        r"not\s+that[,.]?|scratch\s+that[,.]?|sorry[,.]?)\s+(?P<command>.+)$"
    )),
    ("help", re.compile(r"^(?:help|what can i say|commands|list commands|options)$")),
    ("focus_file", re.compile(
        r"^(?:what changed in|what is different in|what's different in|open|go to|show|show me|"
        r"focus on|focus|inspect|explain|drill into)(?:\s+(?:the\s+)?file)?\s+" + _FILE + r"$"
    )),
    ("focus_file", re.compile(r"^file\s+" + _FILE + r"$")),
    ("focus_index", re.compile(r"^(?:file|section|drill into file)\s+(?P<n>\d+|last)$")),
    ("open", re.compile(
        r"^(?:open|load|review|start)(?:\s+(?:the|this|that|a|my))?(?:\s+(?:pull request|pr|patch|diff|change))?"
        r"(?:\s+(?:at|from))?(?:\s+(?P<url>https?://\S+))?$"
    )),
    ("open", re.compile(r"^(?P<url>https?://github\.com/\S+)$")),
    ("summary", re.compile(
        r"^(?:summary|overview|summarize|summarise|what changed|what changed overall|"
        r"what did it change|start over|top|the summary)$"
    )),
    ("files", re.compile(r"^(?:files|file by file|list(?: the)? files|which files(?: changed)?|what files(?: changed)?)$")),
    ("findings", re.compile(
        r"^(?:findings|security|security findings|any security (?:issues|findings|problems)|"
        r"what is wrong|what's wrong|is it safe)$"
    )),
    ("next", re.compile(r"^next(?:\s+(?P<unit>file|line|hunk))?$")),
    ("previous", re.compile(r"^(?:previous|prev|back)(?:\s+(?P<unit>file|line|hunk))?$")),
    ("read_lines", re.compile(
        r"^(?:(?:read|show|show me|give me|say)(?:\s+(?:me\s+)?(?:the|those|these))?(?:\s+exact)?(?:\s+source)?"
        r"\s+(?:lines|code|hunk|change|diff|source)(?:\s+(?:of|in)\s+.*)?|exact lines|the lines|lines|code)$"
    )),
    ("line_number", re.compile(r"^(?:go to line|jump to line|line)\s+(?P<n>\d+)$")),
    ("spell", re.compile(r"^spell(?:\s+(?:that|it|this|the line|out|that out|it out))?$")),
    ("repeat", re.compile(r"^(?:repeat|again|say (?:that|it) again|say again|what|pardon|once more|repeat that)$")),
    ("slower", re.compile(r"^(?:slower|slow down|too fast|speak slower)$")),
    ("faster", re.compile(r"^(?:faster|speed up|too slow|speak faster)$")),
    ("where", re.compile(r"^(?:where am i|status|where are we|context|where was i)$")),
    ("request_changes", re.compile(
        r"^request(?:\s+a)?\s+changes?(?:[:,]|\s+because|\s+with(?:\s+the)?\s+comment|\s+saying)?\s*(?P<body>.*)$"
    )),
    ("confirm", re.compile(r"^(?:confirm|confirmed|yes|submit|send it|do it|go ahead|approve|yes submit)$")),
    ("cancel", re.compile(r"^(?:cancel|no|never mind|nevermind|abort|discard|forget it|cancel that)$")),
    ("undo", re.compile(r"^(?:undo|go back|take that back)$")),
]


#: The request-changes pattern once more, case-insensitive, for lifting the
#: comment body out of the original transcript with its capitals intact.
GRAMMAR_REQUEST_CHANGES = re.compile(
    dict(GRAMMAR)["request_changes"].pattern.replace("(?P<body>.*)", "(?P<body>.*)"),
    re.IGNORECASE,
)


def normalise(transcript: str) -> str:
    """Lower case, straight quotes, spoken 'dot' inside a file name, one space."""
    text = (transcript or "").strip().lower()
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"(\w)\s+dot\s+(\w)", r"\1.\2", text)
    text = re.sub(r"\s+", " ", text)
    text = text.rstrip(".!?")
    text = _NUMBER_PHRASE.sub(_digits_for_spoken_numbers, text)
    return re.sub(r"\s+", " ", text).strip()


def parse_command(transcript: str) -> Command:
    text = normalise(transcript)
    if not text:
        return Command("unknown", {}, transcript)
    for name, pattern in GRAMMAR:
        match = pattern.match(text)
        if not match:
            continue
        if name == "correction":
            inner = parse_command(match.group("command"))
            return Command(inner.name, inner.slots, transcript, corrected=True)
        slots = {key: value for key, value in match.groupdict().items() if value}
        if name == "request_changes":
            slots["body"] = _review_body(transcript, match.group("body"))
        return Command(name, slots, transcript)
    return Command("unknown", {}, transcript)


def _review_body(transcript: str, lowered_body: str | None) -> str:
    """The review comment as the developer said it, capitals included.

    The grammar matches on a lower-cased transcript so that "Request Changes"
    and "request changes" are one command, but the comment that follows is
    going onto a pull request under the developer's name, so it is lifted from
    the original text. A typed "keep the NEWS format" must not reach GitHub as
    "keep the news format".
    """
    original = re.sub(r"\s+", " ", (transcript or "").strip()).rstrip(".!?")
    match = GRAMMAR_REQUEST_CHANGES.match(original)
    body = match.group("body") if match else (lowered_body or "")
    return body.strip().strip("'\"")
