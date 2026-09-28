"""Pure Domain Layer: the conversational state machine for a spoken code review.

A blind developer does not review a patch by hearing one summary. They open the
change, ask what happened in one file, ask for the exact source lines of a hunk,
go back a line, ask for a line to be spelled out symbol by symbol, correct a
misheard command, and finally say what they want done about it. This module is
that dialogue, as data and transitions, with no speech engine, no HTTP and no
GitHub in it, so the whole machine is driven in tests by injected transcripts.

Three things it promises:

* **Every turn reads back what it understood before it acts**, as ``readback``.
  A misheard "next file" becomes "Understood: next file" a second before the
  file changes, which is what lets the listener say "no, I said next line".
* **Every transition is undoable by one step**, which is what a correction is:
  restore the state before the misheard command, then apply the one meant.
* **Nothing here submits a review.** Staging one produces a readback of the
  body and the head commit and moves to ``CONFIRM_REVIEW``; the application
  layer owns the grant and the send, and reports the outcome back through
  ``record_outcome``.
"""
from dataclasses import dataclass, field
from enum import Enum

from src.domain.review_grammar import Command, parse_command  # noqa: F401 - re-exported
from src.domain.semantic_diff import (
    DiffHunk,
    DiffLine,
    DiffSectionDigest,
    SemanticDiffReport,
    plural,
)
from src.domain.sonification import EarconType, earcon_for_report, earcon_for_section


@dataclass(frozen=True)
class PullRequestSnapshot:
    """A pull request as read at one moment. ``head_sha`` is what a review binds to."""

    owner: str
    repo: str
    number: int
    url: str
    title: str
    state: str
    head_sha: str
    head_ref: str
    base_ref: str
    author: str
    diff: str
    fetched_with_token: bool = False

    @property
    def label(self) -> str:
        return f"{self.owner}/{self.repo} pull request {self.number}"

    def to_dict(self) -> dict:
        return {
            "owner": self.owner, "repo": self.repo, "number": self.number, "url": self.url,
            "title": self.title, "state": self.state, "head_sha": self.head_sha,
            "head_ref": self.head_ref, "base_ref": self.base_ref, "author": self.author,
            "diff_bytes": len(self.diff.encode("utf-8")),
        }


class DialogueState(str, Enum):
    IDLE = "IDLE"
    OVERVIEW = "OVERVIEW"
    FILE = "FILE"
    LINES = "LINES"
    CONFIRM_REVIEW = "CONFIRM_REVIEW"
    #: A confirmed review was sent and GitHub accepted it.
    SUBMITTED = "SUBMITTED"
    #: A confirmed review was recorded as the exact request and not sent.
    RECORDED = "RECORDED"
    REFUSED = "REFUSED"


# The grammar lives in review_grammar.py; Command and parse_command are
# re-exported here so the machine's callers import one module.


# --- speaking code by ear -----------------------------------------------------

SYMBOL_NAMES = {
    " ": "space", "!": "bang", '"': "double quote", "#": "hash", "$": "dollar", "%": "percent",
    "&": "ampersand", "'": "single quote", "(": "open paren", ")": "close paren", "*": "star",
    "+": "plus", ",": "comma", "-": "minus", ".": "dot", "/": "slash", ":": "colon",
    ";": "semicolon", "<": "less than", "=": "equals", ">": "greater than", "?": "question mark",
    "@": "at", "[": "open bracket", "\\": "backslash", "]": "close bracket", "^": "caret",
    "_": "underscore", "`": "backtick", "{": "open brace", "|": "pipe", "}": "close brace",
    "~": "tilde", "\t": "tab",
}


def spell_out(text: str) -> str:
    """Every character of a source line, named, so ``!=`` cannot be heard as ``==``."""
    stripped = text.lstrip(" \t")
    indent = len(text) - len(stripped)
    words: list[str] = []
    if indent:
        words.append(plural(indent, "leading space"))
    for char in stripped:
        if not char.isascii():
            # A non-ASCII letter is spoken as itself, and then named by code
            # point, because "zeta" and "z" are not the same identifier.
            words.append(f"{char} unicode {ord(char):04x}")
        elif char.isupper():
            words.append(f"capital {char.lower()}")
        elif char.isalnum():
            words.append(char)
        else:
            words.append(SYMBOL_NAMES.get(char, f"unicode {ord(char):04x}"))
    return ", ".join(words) if words else "blank line"


def spoken_line(line: DiffLine, index: int, total: int) -> str:
    kind = {"add": "added", "remove": "removed", "context": "unchanged"}[line.kind]
    if line.kind == "add":
        where = f"new line {line.new_no}"
    elif line.kind == "remove":
        where = f"old line {line.old_no}"
    else:
        where = f"line {line.new_no}"
    body = line.text if line.text.strip() else "blank line"
    return f"Line {index + 1} of {total}, {kind}, {where}: {body}"


# --- the machine --------------------------------------------------------------

@dataclass
class DialogueTurn:
    understood: str
    readback: str
    spoken: str
    state: DialogueState
    earcon_type: EarconType | None
    focus: dict
    speech_rate: float
    line: dict | None = None
    error: bool = False
    silent: bool = False
    #: Set when the application layer has to act: "open", "request_changes",
    #: "confirm" or "cancel". Pure navigation leaves it None.
    needs: str | None = None
    command: Command | None = None


RATE_STEP = 0.15
RATE_MIN = 0.5
RATE_MAX = 1.6
#: Lines spoken in one breath when a whole hunk is asked for. Beyond it the
#: cursor stops and "next" continues, because a 300 line hunk read in one go is
#: the failure the product exists to end.
LINES_PER_READ = 20

HELP_TEXT = (
    "You can say: open the pull request, or open the patch. Summary. File by file. "
    "What changed in auth dot py. Next, previous. Read the lines. Next line, previous line, "
    "line fifteen. Spell that. Findings. Repeat. Slower, faster. Stop, resume. "
    "No, I said next line, to correct me. Request changes, followed by your comment; "
    "then confirm or cancel. Where am I. Help."
)


@dataclass
class ReviewDialogue:
    session_id: str
    state: DialogueState = DialogueState.IDLE
    report: SemanticDiffReport | None = None
    pull_request: PullRequestSnapshot | None = None
    file_index: int = 0
    hunk_index: int = 0
    #: The one cursor. "Spell that", "where am I", "next", "previous" and the
    #: line shown on screen all read this field and nothing else, so they can
    #: never disagree about which line the listener is on.
    line_index: int = 0
    speech_rate: float = 1.0
    pending_body: str | None = None
    last_turn: DialogueTurn | None = None
    #: How the last confirmed review ended, in words: "submitted", "recorded
    #: as a dry run and not sent", or "refused".
    last_outcome: str | None = None
    history: list[dict] = field(default_factory=list)
    _undo: dict | None = field(default=None, repr=False)

    # -- helpers -------------------------------------------------------------

    @property
    def sections(self) -> list[DiffSectionDigest]:
        return list(self.report.sections) if self.report else []

    @property
    def section(self) -> DiffSectionDigest | None:
        sections = self.sections
        return sections[self.file_index] if sections and 0 <= self.file_index < len(sections) else None

    @property
    def hunk(self) -> DiffHunk | None:
        section = self.section
        if section is None or not section.hunks:
            return None
        return section.hunks[min(self.hunk_index, len(section.hunks) - 1)]

    def focus(self) -> dict:
        section, hunk = self.section, self.hunk
        return {
            "state": self.state.value,
            "file_index": self.file_index if section else None,
            "file_path": section.file_path if section else None,
            "total_files": len(self.sections),
            "hunk_index": self.hunk_index if hunk else None,
            "total_hunks": len(section.hunks) if section else 0,
            "line_index": self.line_index if hunk else None,
            "total_lines": len(hunk.lines) if hunk else 0,
            "pull_request": self.pull_request.label if self.pull_request else None,
            "head_sha": self.pull_request.head_sha if self.pull_request else None,
            "pending_review": self.pending_body,
        }

    def _turn(self, command: Command | None, understood: str, spoken: str, *,
              earcon: EarconType | None = None, line: dict | None = None, error: bool = False,
              silent: bool = False, needs: str | None = None, readback: str | None = None,
              remember: bool = True) -> DialogueTurn:
        if readback is None:
            prefix = "Corrected, " if command is not None and command.corrected else "Understood: "
            readback = f"{prefix}{understood}."
        turn = DialogueTurn(
            understood=understood, readback=readback, spoken=spoken, state=self.state,
            earcon_type=earcon, focus=self.focus(), speech_rate=round(self.speech_rate, 2),
            line=line, error=error, silent=silent, needs=needs, command=command,
        )
        self.history.append({"role": "developer", "text": command.raw if command else understood})
        self.history.append({"role": "volcan", "text": spoken})
        # "Repeat" repeats content. A rate change, a help text or a silent stop
        # is not content, so those turns leave last_turn alone.
        if remember and not silent:
            self.last_turn = turn
        return turn

    def _snapshot(self) -> None:
        # The speech rate is deliberately not part of the snapshot: "slower"
        # is a preference, not a navigation, and a correction must not undo it.
        self._undo = {
            "state": self.state, "file_index": self.file_index, "hunk_index": self.hunk_index,
            "line_index": self.line_index, "last_turn": self.last_turn,
        }

    def _restore(self) -> bool:
        if not self._undo:
            return False
        for key, value in self._undo.items():
            setattr(self, key, value)
        self._undo = None
        return True

    # -- loading -------------------------------------------------------------

    def load(self, report: SemanticDiffReport, pull_request: PullRequestSnapshot | None = None,
             command: Command | None = None) -> DialogueTurn:
        self.report = report
        self.pull_request = pull_request
        self.file_index = self.hunk_index = self.line_index = 0
        self.pending_body = None
        self._undo = None
        self.state = DialogueState.OVERVIEW
        if pull_request:
            opener = (
                f"Opened {pull_request.label}, {pull_request.title}, by {pull_request.author}, "
                f"head commit {pull_request.head_sha[:7]}. "
            )
        else:
            opener = "Opened the pasted patch. No pull request is attached, so a review cannot be submitted from it. "
        spoken = (
            opener
            + f"Modified {plural(report.total_files_changed, 'file')} with "
            + f"{plural(report.total_insertions, 'addition')} and "
            + f"{plural(report.total_deletions, 'deletion')}; "
            + f"{plural(len(report.critical_findings), 'security finding')}. "
            + "Say summary, file by file, or what changed in a file name."
        )
        # The readback names what was actually opened. "Open the pull request"
        # with the URL typed into a field rather than spoken is still a pull
        # request, and a listener must not hear "the patch" for it.
        if command is None:
            understood = "open"
        elif command.name == "open":
            understood = "open the pull request" if pull_request else "open the patch"
        else:
            understood = command.words
        return self._turn(command, understood, spoken, earcon=earcon_for_report(report), needs=None)

    # -- the dispatcher ------------------------------------------------------

    def apply(self, command: Command) -> DialogueTurn:
        name = command.name

        if name == "stop":
            return self._turn(command, "stop", "Stopped.", silent=True)
        if name == "resume":
            return self._turn(command, "resume", "", needs="resume", remember=False)
        if name == "help":
            return self._turn(command, "help", self._help(), remember=False)
        if name == "repeat":
            if self.last_turn is None:
                return self._turn(command, "repeat", "Nothing has been said yet.", error=True, remember=False)
            previous = self.last_turn
            return self._turn(command, "repeat", previous.spoken, earcon=previous.earcon_type,
                              line=previous.line, readback="Again.", remember=False)
        if name in ("slower", "faster"):
            delta = -RATE_STEP if name == "slower" else RATE_STEP
            self.speech_rate = max(RATE_MIN, min(RATE_MAX, round(self.speech_rate + delta, 2)))
            edge = self.speech_rate in (RATE_MIN, RATE_MAX)
            spoken = f"Speech rate {self.speech_rate:.2f}" + (", the limit." if edge else ".")
            return self._turn(command, name, spoken, remember=False)
        if name == "where":
            return self._turn(command, "where am I", self._where(), remember=False)
        if name == "unknown":
            return self._turn(
                command, "nothing I recognise",
                f"I did not understand '{command.raw.strip()}'. Say help for the commands.",
                error=True, readback=f"I heard '{command.raw.strip()}' and did not recognise a command.",
            )
        if name == "open":
            return self._turn(command, command.words, "", needs="open")
        if name == "undo":
            if not self._restore():
                return self._turn(command, "undo", "There is nothing to undo.", error=True)
            return self._turn(command, "undo", "Undone. " + self._where())
        if name == "cancel":
            if self.state is DialogueState.CONFIRM_REVIEW:
                return self._turn(command, "cancel", "", needs="cancel")
            return self._turn(command, "cancel", "Nothing is waiting for confirmation.", error=True)
        if name == "confirm":
            if self.state is DialogueState.CONFIRM_REVIEW:
                return self._turn(command, "confirm", "", needs="confirm")
            return self._turn(command, "confirm", "Nothing is waiting for confirmation.", error=True)
        if name == "request_changes":
            return self._turn(command, command.words, "", needs="request_changes")

        if self.report is None:
            return self._turn(
                command, command.words,
                "Nothing is open yet. Say open the pull request, or open the patch.", error=True,
            )
        if self.state is DialogueState.CONFIRM_REVIEW:
            return self._turn(
                command, command.words,
                "A review is waiting for your confirmation. Say confirm to submit it or cancel to drop it.",
                error=True,
            )

        if command.corrected:
            self._restore()
        self._snapshot()

        if name == "summary":
            return self._summary(command)
        if name == "files":
            return self._files(command)
        if name == "findings":
            return self._findings(command)
        if name == "focus_file":
            return self._focus_file(command)
        if name == "focus_index":
            return self._focus_index(command)
        if name == "next":
            return self._step(command, +1)
        if name == "previous":
            return self._step(command, -1)
        if name == "read_lines":
            return self._read_lines(command)
        if name == "line_number":
            return self._line_number(command)
        if name == "spell":
            return self._spell(command)
        return self._turn(command, command.words, "That command is not implemented.", error=True)

    # -- transitions ---------------------------------------------------------

    def _help(self) -> str:
        """The command list, with examples that work on the change that is open.

        With nothing open, the examples are generic. With a change open, the
        file example names a file in it and the line example a line in the
        file in focus, so saying either example back works here.
        """
        sections = self.sections
        if not sections:
            return HELP_TEXT
        section = self.section if self.section is not None else sections[0]
        name = section.file_path.rsplit("/", 1)[-1].replace(".", " dot ")
        text = HELP_TEXT.replace("What changed in auth dot py.", f"What changed in {name}.")
        line_no = next(
            (line.new_no if line.new_no is not None else line.old_no
             for hunk in section.hunks for line in hunk.lines
             if line.kind != "context" and (line.new_no or line.old_no)),
            None,
        )
        if line_no is None:
            return text.replace(" line fifteen.", " line and a number.")
        return text.replace(" line fifteen.", f" line {line_no}.")

    def _where(self) -> str:
        if self.report is None:
            return "Nothing is open."
        where = self.pull_request.label if self.pull_request else "the pasted patch"
        parts = [f"In {where}, {plural(len(self.sections), 'file')} changed."]
        if self.state in (DialogueState.FILE, DialogueState.LINES) and self.section:
            parts.append(f"Focused on file {self.file_index + 1}, {self.section.file_path}.")
        if self.state is DialogueState.LINES and self.hunk and self.hunk.lines:
            # The same words "next" and "spell that" use for this line, so a
            # listener hears one position, said one way.
            index = min(self.line_index, len(self.hunk.lines) - 1)
            at = spoken_line(self.hunk.lines[index], index, len(self.hunk.lines)).split(":", 1)[0]
            parts.append(f"In hunk {self.hunk_index + 1} of {len(self.section.hunks)}. {at}.")
        if self.state is DialogueState.CONFIRM_REVIEW:
            parts.append("A request changes review is waiting for confirmation.")
        if self.last_outcome:
            parts.append(f"The last review was {self.last_outcome}.")
        return " ".join(parts)

    def resume(self, command: Command, *, refreshed_from: str | None = None) -> DialogueTurn:
        """Speak a compact, exact checkpoint after an interruption.

        The application refreshes an attached pull request first. This method
        only reports the state it receives, including the file, hunk, source
        line and immutable revision a listener needs to resume safely.
        """
        if self.report is None:
            return self._turn(command, "resume", "Nothing is open yet.", error=True, remember=False)
        pr = self.pull_request
        revision = f" at head commit {pr.head_sha[:7]}" if pr else ""
        changed = ""
        if refreshed_from:
            changed = (
                f"The pull request changed from {refreshed_from[:7]} to {pr.head_sha[:7]}; "
                "the old approval was invalidated and the diff was refreshed. "
            )
        section = self.section
        location = f"{plural(len(self.sections), 'file')} changed."
        line = None
        if section is not None and self.state in (DialogueState.FILE, DialogueState.LINES):
            location = f"File {self.file_index + 1} of {len(self.sections)}: {section.file_path}."
            if self.state is DialogueState.LINES and self.hunk and self.hunk.lines:
                line = self._line_dict()
                source_line = spoken_line(
                    self.hunk.lines[self.line_index], self.line_index, len(self.hunk.lines)
                ).split(":", 1)[0]
                location += (
                    f" Hunk {self.hunk_index + 1} of {len(section.hunks)}; {source_line}."
                )
        pending = " A request changes review is waiting for confirmation." if self.pending_body else ""
        return self._turn(
            command, "resume", f"{changed}Resuming {pr.label if pr else 'the pasted patch'}{revision}. {location}{pending}",
            line=line, remember=False,
        )

    def refresh(self, report: SemanticDiffReport, pull_request: PullRequestSnapshot,
                command: Command, previous_head: str) -> DialogueTurn:
        """Replace a changed PR while retaining the closest valid cursor."""
        old_state = self.state
        old_path = self.section.file_path if self.section else None
        old_hunk, old_line = self.hunk_index, self.line_index
        self.report, self.pull_request = report, pull_request
        self.pending_body = None
        self._undo = None
        self.file_index = 0
        if old_path:
            self.file_index = next(
                (index for index, section in enumerate(self.sections) if section.file_path == old_path), 0
            )
        section = self.section
        if section and section.hunks and old_state is DialogueState.LINES:
            self.state = DialogueState.LINES
            self.hunk_index = min(old_hunk, len(section.hunks) - 1)
            self.line_index = min(old_line, len(self.hunk.lines) - 1)
        elif section and old_state in (DialogueState.FILE, DialogueState.LINES):
            self.state = DialogueState.FILE
            self.hunk_index = self.line_index = 0
        else:
            self.state = DialogueState.OVERVIEW
            self.hunk_index = self.line_index = 0
        return self.resume(command, refreshed_from=previous_head)

    def _summary(self, command: Command) -> DialogueTurn:
        self.state = DialogueState.OVERVIEW
        self.file_index = self.hunk_index = self.line_index = 0
        return self._turn(command, "summary", self.report.to_voice_summary(level=0),
                          earcon=earcon_for_report(self.report))

    def _files(self, command: Command) -> DialogueTurn:
        self.state = DialogueState.OVERVIEW
        sections = self.sections
        if not sections:
            return self._turn(command, "file by file", "This change touches no files.", error=True)
        listed = " ".join(
            f"File {index}: {section.file_path}, {plural(section.added_count, 'addition')}, "
            f"{plural(section.removed_count, 'deletion')}"
            + (", security finding." if section.security_findings or section.security_flags else ".")
            for index, section in enumerate(sections, start=1)
        )
        return self._turn(command, "file by file", f"{plural(len(sections), 'file')}. {listed} Say file and a number, or what changed in a file name.")

    def _findings(self, command: Command) -> DialogueTurn:
        findings = list(self.report.critical_findings)
        if not findings:
            return self._turn(command, "findings", "No security finding in this change.", earcon=EarconType.DIFF_READY)
        return self._turn(command, "findings", f"{plural(len(findings), 'finding')}. " + " ".join(findings),
                          earcon=EarconType.SECURITY_FINDING)

    def _focus_file(self, command: Command) -> DialogueTurn:
        wanted = command.slots["file"].lower()
        sections = self.sections
        matches = _match_files(wanted, sections)
        if not matches and wanted.endswith(" file"):
            # "the readme file": the last word named the kind of thing, not
            # the file, unless it was part of the name ("docker file"), which
            # the first pass already tried.
            wanted = wanted[: -len(" file")].strip()
            matches = _match_files(wanted, sections)
        if not matches:
            names = ", ".join(s.file_path for s in sections) or "none"
            return self._turn(command, command.words,
                              f"No file matching {wanted} in this change. The files are: {names}.", error=True)
        if len(matches) > 1:
            names = ", ".join(sections[i].file_path for i in matches)
            return self._turn(command, command.words, f"{wanted} matches {len(matches)} files: {names}. Say the full path.", error=True)
        self.file_index = matches[0]
        return self._speak_file(command, command.words)

    def _focus_index(self, command: Command) -> DialogueTurn:
        raw = command.slots["n"]
        sections = self.sections
        index = len(sections) - 1 if raw == "last" else int(raw) - 1
        if index < 0 or index >= len(sections):
            return self._turn(command, command.words,
                              f"There is no file {raw}; this change has {plural(len(sections), 'file')}.", error=True)
        self.file_index = index
        return self._speak_file(command, command.words)

    def _speak_file(self, command: Command, understood: str) -> DialogueTurn:
        self.state = DialogueState.FILE
        self.hunk_index = self.line_index = 0
        section = self.section
        spoken = (
            f"File {self.file_index + 1} of {len(self.sections)}: {section.file_path}. "
            f"Category {section.category.value.replace('_', ' ').lower()}, "
            f"significance {section.significance.value.lower()}. {section.summary_spoken}"
        )
        if section.security_findings:
            spoken += " Security alert: " + " ".join(f"{f}." for f in section.security_findings)
        elif section.security_flags:
            spoken += f" Security alert: flagged for {', '.join(section.security_flags)}."
        if section.hunks:
            first = section.hunks[0]
            spoken += (
                f" {plural(len(section.hunks), 'hunk')}; the first covers new lines "
                f"{first.new_start} to {_last_new_line(first)}. Say read the lines."
            )
        else:
            spoken += " This section carries no hunk with line numbers."
        return self._turn(command, understood, spoken, earcon=earcon_for_section(section))

    def _step(self, command: Command, delta: int) -> DialogueTurn:
        unit = command.slots.get("unit")
        if unit is None:
            unit = "line" if self.state is DialogueState.LINES else "file"
        if unit == "file" and self.state is DialogueState.OVERVIEW:
            # From the overview or the file list, no file is in focus yet, so
            # "next" is the first file, not the one after it.
            if not self.sections:
                return self._turn(command, command.words, "This change touches no files.", error=True)
            if delta < 0:
                return self._turn(command, command.words,
                                  "No file is open yet. Say next for file 1.", error=True)
            self.file_index = 0
            return self._speak_file(command, command.words)
        if unit == "file":
            target = self.file_index + delta
            if target < 0 or target >= len(self.sections):
                edge = "first" if delta < 0 else "last"
                return self._turn(command, command.words, f"That was the {edge} file.", error=True)
            self.file_index = target
            return self._speak_file(command, command.words)
        if self.state is not DialogueState.LINES or self.hunk is None:
            return self._turn(command, command.words,
                              "Not reading lines yet. Say read the lines first.", error=True)
        if unit == "hunk":
            section = self.section
            target = self.hunk_index + delta
            if target < 0 or target >= len(section.hunks):
                edge = "first" if delta < 0 else "last"
                return self._turn(command, command.words, f"That was the {edge} hunk of this file.", error=True)
            self.hunk_index = target
            self.line_index = 0
            return self._read_lines(command)
        target = self.line_index + delta
        if target < 0 or target >= len(self.hunk.lines):
            edge = "first" if delta < 0 else "last"
            return self._turn(command, command.words, f"That was the {edge} line of this hunk.", error=True)
        self.line_index = target
        return self._speak_line(command, command.words)

    def _read_lines(self, command: Command) -> DialogueTurn:
        # "Next hunk" lands here too, and the readback must say "next hunk":
        # a readback that names some other command is the one thing this
        # product promises never to do, so the words are the command's own.
        understood = command.words
        if self.state is DialogueState.OVERVIEW:
            if not self.sections:
                return self._turn(command, understood, "This change touches no files.", error=True)
            self.file_index = 0
        section = self.section
        if not section.hunks:
            return self._turn(command, understood,
                              f"{section.file_path} carries no hunk with line numbers to read.", error=True)
        self.state = DialogueState.LINES
        hunk = self.hunk
        total = len(hunk.lines)
        spoken_lines = [spoken_line(line, i, total) for i, line in enumerate(hunk.lines[:LINES_PER_READ])]
        head = (
            f"Hunk {self.hunk_index + 1} of {len(section.hunks)} in {section.file_path}"
            + (f", {hunk.header}" if hunk.header else "")
            + f". Old lines {hunk.old_start} to {_last_old_line(hunk)}, "
            f"new lines {hunk.new_start} to {_last_new_line(hunk)}, "
            f"{plural(total, 'line')}. "
        )
        # After the read the cursor lands where the listener's "that" points,
        # and the turn says so. A whole hunk: the first changed line, because
        # that is the change they just heard, not the context above it. A cut
        # hunk: the last line read, so "next" continues where the voice stopped.
        if total > LINES_PER_READ:
            self.line_index = LINES_PER_READ - 1
            tail = (
                f" {total - LINES_PER_READ} more. Cursor on line {LINES_PER_READ} of {total}; "
                f"say next to continue from line {LINES_PER_READ + 1}."
            )
        else:
            changed = [i for i, line in enumerate(hunk.lines) if line.kind != "context"]
            self.line_index = changed[0] if changed else 0
            what = "the first change" if changed else "no line in this hunk changed"
            tail = (
                f" Cursor on line {self.line_index + 1} of {total}, {what}. "
                "Say spell that, next or previous."
            )
        spoken = head + " ".join(f"{s}." for s in spoken_lines) + tail
        return self._turn(command, understood, spoken, earcon=earcon_for_section(section),
                          line=self._line_dict())

    def _line_number(self, command: Command) -> DialogueTurn:
        wanted = int(command.slots["n"])
        if self.state is DialogueState.OVERVIEW and self.sections:
            self.file_index = 0
        section = self.section
        if section is None or not section.hunks:
            return self._turn(command, command.words, "No hunk with line numbers is open.", error=True)
        # "Line 14" means line 14 of the file as it will be after the change.
        # Only when no such line exists in any hunk does the removed line that
        # used to be 14 answer, so a change that replaces a line lands on the
        # new text first and the old text is one "previous" away.
        for side in ("new", "old"):
            for hunk_index, hunk in enumerate(section.hunks):
                for line_index, line in enumerate(hunk.lines):
                    if side == "new":
                        hit = line.new_no == wanted
                    else:
                        hit = line.new_no is None and line.old_no == wanted
                    if hit:
                        self.state = DialogueState.LINES
                        self.hunk_index, self.line_index = hunk_index, line_index
                        return self._speak_line(command, command.words)
        return self._turn(command, command.words,
                          f"Line {wanted} is not inside any hunk of {section.file_path}.", error=True)

    def _speak_line(self, command: Command, understood: str) -> DialogueTurn:
        hunk = self.hunk
        line = hunk.lines[self.line_index]
        return self._turn(command, understood, spoken_line(line, self.line_index, len(hunk.lines)),
                          line=self._line_dict())

    def _spell(self, command: Command) -> DialogueTurn:
        if self.state is not DialogueState.LINES or self.hunk is None:
            return self._turn(command, command.words, "No line is selected. Say read the lines first.", error=True)
        hunk = self.hunk
        index = min(self.line_index, len(hunk.lines) - 1)
        line = hunk.lines[index]
        kind = {"add": "added", "remove": "removed", "context": "unchanged"}[line.kind]
        return self._turn(command, command.words,
                          f"Line {index + 1} of {len(hunk.lines)}, {kind}, spelled: {spell_out(line.text)}.",
                          line=self._line_dict())

    def _line_dict(self) -> dict | None:
        hunk = self.hunk
        if hunk is None or not hunk.lines:
            return None
        line = hunk.lines[min(self.line_index, len(hunk.lines) - 1)]
        return {
            "kind": line.kind, "text": line.text, "old_no": line.old_no, "new_no": line.new_no,
            "index": self.line_index, "total": len(hunk.lines), "spelled": spell_out(line.text),
        }

    # -- the review, staged here and resolved by the application ---------------

    def stage_review(self, command: Command, body: str) -> DialogueTurn:
        if self.report is None:
            return self._turn(command, command.words, "Nothing is open yet. Open a pull request first.", error=True)
        if self.pull_request is None:
            return self._turn(
                command, command.words,
                "The patch open here was pasted, not fetched, so there is no pull request to review. "
                "Open a pull request by URL to submit a review.", error=True,
            )
        if not body.strip():
            return self._turn(command, command.words,
                              "Say request changes followed by the comment you want on the pull request.", error=True)
        self._snapshot()
        self.pending_body = body.strip()
        self.state = DialogueState.CONFIRM_REVIEW
        pr = self.pull_request
        spoken = (
            f"Ready to request changes on {pr.label}, bound to head commit {pr.head_sha[:7]}, with the comment: "
            f"{self.pending_body}. Say confirm to submit it, or cancel."
        )
        return self._turn(command, command.words, spoken, earcon=EarconType.GOVERNANCE_CHALLENGE)

    def cancel_review(self, command: Command) -> DialogueTurn:
        self.pending_body = None
        self._restore()
        if self.state is DialogueState.CONFIRM_REVIEW:
            self.state = DialogueState.OVERVIEW
        return self._turn(command, "cancel", "Cancelled. Nothing was sent. " + self._where())

    def record_outcome(self, command: Command | None, spoken: str, *, submitted: bool,
                       dry_run: bool, refused: bool, earcon: EarconType) -> DialogueTurn:
        self.pending_body = None
        self._undo = None
        if submitted:
            self.state, self.last_outcome = DialogueState.SUBMITTED, "submitted"
        elif dry_run:
            self.state, self.last_outcome = DialogueState.RECORDED, "recorded as a dry run and not sent"
        elif refused:
            self.state, self.last_outcome = DialogueState.REFUSED, "refused"
        else:
            self.state = DialogueState.OVERVIEW
        return self._turn(command, "confirm", spoken, earcon=earcon, error=refused)


def _squash(name: str) -> str:
    """A name as a recogniser may split it: "read me" and "README" are one name."""
    return "".join(ch for ch in name.lower() if ch.isalnum())


def _match_files(wanted: str, sections: list[DiffSectionDigest]) -> list[int]:
    """The files a spoken or typed name points at, most exact rule first."""
    paths = [s.file_path.lower() for s in sections]
    rules = (
        lambda path: path == wanted,
        lambda path: path.endswith("/" + wanted),
        lambda path: wanted in path,
    )
    for rule in rules:
        matches = [i for i, path in enumerate(paths) if rule(path)]
        if matches:
            return matches
    squashed = _squash(wanted)
    if not squashed:
        return []
    base = [path.rsplit("/", 1)[-1] for path in paths]
    rules = (
        lambda i: _squash(base[i]) == squashed,
        lambda i: _squash(base[i].rsplit(".", 1)[0]) == squashed,
        lambda i: squashed in _squash(paths[i]),
    )
    for rule in rules:
        matches = [i for i in range(len(paths)) if rule(i)]
        if matches:
            return matches
    return []


def _last_new_line(hunk: DiffHunk) -> int:
    """The last new-file line number the hunk actually carries.

    The header's count is what the patch claims; a truncated or hand-edited
    patch can claim seven lines and carry four. A listener is told about the
    lines that exist.
    """
    numbers = [line.new_no for line in hunk.lines if line.new_no is not None]
    return max(numbers) if numbers else hunk.new_start


def _last_old_line(hunk: DiffHunk) -> int:
    numbers = [line.old_no for line in hunk.lines if line.old_no is not None]
    return max(numbers) if numbers else hunk.old_start
