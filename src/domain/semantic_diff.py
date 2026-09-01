"""Domain entity and value objects for AST-aware Semantic Diff Synthesis."""
import re
from dataclasses import dataclass, field
from enum import Enum


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
class DiffHunk:
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    header: str
    added_lines: list[str]
    removed_lines: list[str]


@dataclass(frozen=True)
class DiffSectionDigest:
    file_path: str
    symbol_name: str
    category: ChangeCategory
    significance: ChangeSignificance
    summary_spoken: str
    added_count: int
    removed_count: int
    security_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SemanticDiffReport:
    total_files_changed: int
    total_insertions: int
    total_deletions: int
    executive_spoken_summary: str
    category_breakdown: dict[str, int]
    critical_findings: list[str]
    sections: list[DiffSectionDigest] = field(default_factory=list)

    def to_voice_summary(self, level: int = 0) -> str:
        """Render multi-level hierarchical voice digests.
        Level 0: Executive spoken summary (concise for voice).
        Level 1: File-by-file breakdown.
        Level 2: Comprehensive drill-down with security findings.
        """
        if level == 0:
            base = f"{self.executive_spoken_summary}. Modified {self.total_files_changed} files with {self.total_insertions} additions and {self.total_deletions} deletions."
            if self.critical_findings:
                base += f" Note: {len(self.critical_findings)} critical findings require your verification."
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

    @classmethod
    def parse_patch(cls, raw_diff: str) -> list[DiffSectionDigest]:
        if not raw_diff or not raw_diff.strip():
            return []

        sections = []
        file_chunks = raw_diff.split("diff --git ")

        for chunk in file_chunks:
            if not chunk.strip():
                continue

            lines = chunk.strip().splitlines()
            first_line = lines[0]
            # Extract file path
            file_match = re.search(r"a/(.*?)\s+b/(.*)", first_line)
            file_path = file_match.group(2) if file_match else "unknown_file"

            added_lines = [line[1:] for line in lines if line.startswith("+") and not line.startswith("+++")]
            removed_lines = [line[1:] for line in lines if line.startswith("-") and not line.startswith("---")]

            # Security inspection
            security_flags = []
            full_diff_text = "\n".join(added_lines + removed_lines)
            for flag_name, pattern in cls.SECURITY_PATTERNS.items():
                if pattern.search(full_diff_text):
                    security_flags.append(flag_name)

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

            summary_spoken = (
                f"Changed {len(added_lines)} lines in {file_path} focusing on {category.value.lower()}."
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
                )
            )

        return sections
