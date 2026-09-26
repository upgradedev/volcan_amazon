"""Domain entity and value objects for AST-aware Semantic Diff Synthesis."""
import re
from dataclasses import dataclass, field
from enum import Enum

from src.domain import ast_security_rules


def plural(count: int, noun: str, suffix: str = "s") -> str:
    """Speech-safe count. A listener hears every one of these words."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}{suffix}"


class ChangeCategory(str, Enum):
    SECURITY_SENSITIVE = "SECURITY_SENSITIVE"
    API_CONTRACT_CHANGE = "API_CONTRACT_CHANGE"
    BUSINESS_LOGIC = "BUSINESS_LOGIC"
    TEST_ONLY = "TEST_ONLY"
    DOCUMENTATION = "DOCUMENTATION"
    FORMATTING = "FORMATTING"


class ChangeSignificance(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class DiffLine:
    """One line of a hunk, with the line numbers a reviewer would quote.

    ``old_no`` is the line's number in the file before the change and
    ``new_no`` its number after it. An added line has no old number and a
    removed line has no new number, which is how a listener is told which side
    of the change a line sits on without hearing a plus or minus sign.
    """

    kind: str  # "context", "add" or "remove"
    text: str  # the source line without its leading marker character
    old_no: int | None
    new_no: int | None


@dataclass(frozen=True)
class DiffHunk:
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    header: str
    added_lines: list[str]
    removed_lines: list[str]
    #: Every line of the hunk in order, numbered. This is what the review
    #: dialogue reads aloud when a developer asks for the exact source lines,
    #: so it is the text as written and not a summary of it.
    lines: list[DiffLine] = field(default_factory=list)


HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")


@dataclass(frozen=True)
class DiffSectionDigest:
    file_path: str
    symbol_name: str
    category: ChangeCategory
    significance: ChangeSignificance
    summary_spoken: str
    added_count: int
    removed_count: int
    #: Machine labels: keyword-matcher names and structural rule ids.
    security_flags: list[str] = field(default_factory=list)
    #: One spoken sentence per flag, in the same order. A listener hears these,
    #: so they say what changed rather than which keyword matched.
    security_findings: list[str] = field(default_factory=list)
    #: The hunks of this file, each with its numbered lines.
    hunks: list[DiffHunk] = field(default_factory=list)


@dataclass(frozen=True)
class SemanticDiffReport:
    total_files_changed: int
    total_insertions: int
    total_deletions: int
    executive_spoken_summary: str
    category_breakdown: dict[str, int]
    critical_findings: list[str]
    sections: list[DiffSectionDigest] = field(default_factory=list)
    #: Which synthesis path produced ``executive_spoken_summary``.
    #: "bedrock" means an Amazon Bedrock model actually answered.
    #: "heuristic-local" means the deterministic local fallback ran and no
    #: model was invoked. Callers surface this so nobody has to guess.
    synthesis_mode: str = "heuristic-local"
    #: Why the model path did not run, when it did not. None when a model
    #: answered. Carried to the API and the companion page so an unexplained
    #: fallback is never presented as a choice.
    fallback_reason: str | None = None

    def to_voice_summary(self, level: int = 0) -> str:
        """Render multi-level hierarchical voice digests.
        Level 0: Executive spoken summary (concise for voice).
        Level 1: File-by-file breakdown.
        Level 2: Comprehensive drill-down with security findings.

        Every count is pluralised. A screen reader speaks this text verbatim,
        so "1 files" and a doubled full stop are defects a sighted reader
        would skim past and a listener cannot.
        """
        if level == 0:
            headline = self.executive_spoken_summary.rstrip().rstrip(".")
            base = (
                f"{headline}. Modified {plural(self.total_files_changed, 'file')} with "
                f"{plural(self.total_insertions, 'addition')} and "
                f"{plural(self.total_deletions, 'deletion')}."
            )
            if self.critical_findings:
                # The finding is the first thing a listener hears. A review
                # found the summary ended "1 critical finding requires your
                # verification" and never said what the finding was, so the
                # inverted comparison the product exists to catch was never
                # spoken. It now leads, and the counts follow it.
                lead = self.critical_findings[0].strip()
                if not lead.endswith("."):
                    lead += "."
                count = len(self.critical_findings)
                verb = "requires" if count == 1 else "require"
                base = f"{lead} {base} Note: {plural(count, 'critical finding')} {verb} your verification."
            return base

        if level == 1:
            lines = [self.to_voice_summary(level=0)]
            for idx, sec in enumerate(self.sections, start=1):
                sec_desc = f"Section {idx}: {sec.file_path}, category {sec.category.value}. {sec.summary_spoken} (+{sec.added_count}, -{sec.removed_count})."
                lines.append(sec_desc)
            return " ".join(lines)

        # Level 2 (Detailed)
        lines = [self.to_voice_summary(level=1)]
        if self.critical_findings:
            lines.append("Critical Findings:")
            for cf in self.critical_findings:
                lines.append(f"Security Alert: {cf}")
        return " ".join(lines)


class UnifiedDiffParser:
    """Deterministic parser that decomposes unified diff strings into structured models."""

    SECURITY_PATTERNS = {
        "auth_token": re.compile(r"(token|secret|password|key|jwt|bearer|auth)", re.IGNORECASE),
        "crypto": re.compile(r"(hashlib|hmac|aes|rsa|encrypt|decrypt|cipher)", re.IGNORECASE),
        "db_mutation": re.compile(r"(drop table|truncate|delete from|update .* set|alter table)", re.IGNORECASE),
        "exec_call": re.compile(r"(eval\(|exec\(|subprocess|os\.system|shell=True)", re.IGNORECASE),
    }

    @staticmethod
    def _split_file_chunks(raw_diff: str) -> list[list[str]]:
        """Group the patch into one list of lines per file.

        ``git diff`` writes a ``diff --git`` header before each file and
        ``diff -u`` writes none, so a parser that only knows the git header
        reports every plain unified patch as one nameless file. When no git
        header is present the ``--- `` line that opens a file's hunks is the
        boundary instead, recognised only when the next line is its ``+++ ``
        partner. That lookahead is what keeps a deleted SQL comment, which
        reaches the patch as ``--- comment``, from being read as a new file.
        """
        lines = raw_diff.splitlines()
        has_git_header = any(line.startswith("diff --git ") for line in lines)

        chunks: list[list[str]] = []
        current: list[str] | None = None
        for index, line in enumerate(lines):
            if has_git_header:
                is_boundary = line.startswith("diff --git ")
            else:
                is_boundary = (
                    line.startswith("--- ")
                    and index + 1 < len(lines)
                    and lines[index + 1].startswith("+++ ")
                )
            if is_boundary:
                if current:
                    chunks.append(current)
                current = [line]
            elif current is not None:
                current.append(line)
        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def _file_path_from(chunk: list[str]) -> str:
        """The file this chunk is about, from whichever header carries it."""
        git_header = re.search(r"a/(.*?)\s+b/(.*)", chunk[0])
        if git_header:
            return git_header.group(2).strip()

        # A plain unified patch names the file on its ``+++`` line, and on the
        # ``---`` line when the file was deleted and ``+++`` reads /dev/null.
        for prefix in ("+++ ", "--- "):
            for line in chunk[:4]:
                if not line.startswith(prefix):
                    continue
                path = line[len(prefix):].split("\t")[0].strip()
                if not path or path == "/dev/null":
                    continue
                if path.startswith(("a/", "b/")):
                    path = path[2:]
                return path
        return "unknown_file"

    @staticmethod
    def parse_hunks(chunk: list[str]) -> list[DiffHunk]:
        """The hunks of one file chunk, with every line numbered.

        Numbering follows the hunk header: the old and new counters start at
        the header's two start lines, a context line advances both, an added
        line advances only the new counter and a removed line only the old one.
        A ``\\ No newline at end of file`` marker belongs to the previous line
        and is not a line of its own. Anything else ends the hunk.
        """
        hunks: list[DiffHunk] = []
        current: dict | None = None

        def close() -> None:
            if current is None:
                return
            hunks.append(DiffHunk(
                old_start=current["old_start"],
                old_lines=current["old_lines"],
                new_start=current["new_start"],
                new_lines=current["new_lines"],
                header=current["header"],
                added_lines=[line.text for line in current["lines"] if line.kind == "add"],
                removed_lines=[line.text for line in current["lines"] if line.kind == "remove"],
                lines=list(current["lines"]),
            ))

        for raw in chunk:
            header = HUNK_HEADER.match(raw)
            if header:
                close()
                old_start = int(header.group(1))
                new_start = int(header.group(3))
                current = {
                    "old_start": old_start,
                    "old_lines": int(header.group(2) or 1),
                    "new_start": new_start,
                    "new_lines": int(header.group(4) or 1),
                    "header": header.group(5).strip(),
                    "old_no": old_start,
                    "new_no": new_start,
                    "lines": [],
                }
                continue
            if current is None:
                continue
            if raw.startswith("\\"):
                continue
            if raw.startswith("+"):
                current["lines"].append(DiffLine("add", raw[1:], None, current["new_no"]))
                current["new_no"] += 1
            elif raw.startswith("-"):
                current["lines"].append(DiffLine("remove", raw[1:], current["old_no"], None))
                current["old_no"] += 1
            elif raw.startswith(" ") or raw == "":
                current["lines"].append(
                    DiffLine("context", raw[1:], current["old_no"], current["new_no"])
                )
                current["old_no"] += 1
                current["new_no"] += 1
            else:
                close()
                current = None
        close()
        return hunks

    @classmethod
    def parse_patch(cls, raw_diff: str) -> list[DiffSectionDigest]:
        if not raw_diff or not raw_diff.strip():
            return []

        sections = []

        for lines in cls._split_file_chunks(raw_diff):
            if not any(line.strip() for line in lines):
                continue

            file_path = cls._file_path_from(lines)
            hunks = cls.parse_hunks(lines)

            added_lines = [line[1:] for line in lines if line.startswith("+") and not line.startswith("+++")]
            removed_lines = [line[1:] for line in lines if line.startswith("-") and not line.startswith("---")]

            # Security inspection, in two passes. The keyword pass answers
            # "is this change near security-relevant vocabulary"; the AST pass
            # answers "what did this change actually do", which is the only one
            # that can see an inverted comparison or a deleted call.
            security_flags = []
            security_findings = []
            full_diff_text = "\n".join(added_lines + removed_lines)
            for flag_name, pattern in cls.SECURITY_PATTERNS.items():
                if pattern.search(full_diff_text):
                    security_flags.append(flag_name)
                    security_findings.append(
                        f"text matching the {flag_name} keyword set appears in this change"
                    )

            for finding in ast_security_rules.evaluate(added_lines, removed_lines):
                # Structural findings lead: they say what happened, so a
                # listener hears the deletion before the vocabulary match.
                security_flags.insert(0, finding.rule_id)
                security_findings.insert(0, finding.spoken)

            # Categorization
            if "test" in file_path.lower():
                category = ChangeCategory.TEST_ONLY
                significance = ChangeSignificance.LOW
            elif file_path.endswith((".md", ".txt", ".rst")):
                category = ChangeCategory.DOCUMENTATION
                significance = ChangeSignificance.LOW
            elif security_flags:
                category = ChangeCategory.SECURITY_SENSITIVE
                significance = ChangeSignificance.CRITICAL
            else:
                category = ChangeCategory.BUSINESS_LOGIC
                significance = ChangeSignificance.MEDIUM if len(added_lines) > 20 else ChangeSignificance.LOW

            # Spoken verbatim by the review dialogue, so the count agrees with
            # its noun and the category is words rather than an identifier.
            summary_spoken = (
                f"Changed {plural(len(added_lines), 'line')} in {file_path}, "
                f"{category.value.replace('_', ' ').lower()}."
            )

            sections.append(
                DiffSectionDigest(
                    file_path=file_path,
                    symbol_name="module_scope",
                    category=category,
                    significance=significance,
                    summary_spoken=summary_spoken,
                    added_count=len(added_lines),
                    removed_count=len(removed_lines),
                    security_flags=security_flags,
                    security_findings=security_findings,
                    hunks=hunks,
                )
            )

        return sections
