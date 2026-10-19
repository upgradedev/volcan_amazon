"""Use Case: Digest Raw Code Diffs into Multi-Level Spoken Summaries."""
import re
from collections import Counter
from typing import Protocol

from src.domain.semantic_diff import (
    DiffSectionDigest,
    SemanticDiffReport,
    UnifiedDiffParser,
)

#: Why the local engine answered when the caller asked for it by name.
LOCAL_ENGINE_REQUESTED = (
    "this request asked for the local deterministic engine, so no model was called"
)

#: A Claude model id as Bedrock names it, read into words. The page has the
#: same rule in ``modelWords``; tests/unit/test_drill_down_shows_the_model_answer.py
#: holds the two to one pattern.
_CLAUDE_ID = re.compile(r"^(?:[a-z]{2,6}\.)?anthropic\.claude-([a-z]+)((?:-\d+)+)$")


def model_words(model_answered: str) -> str:
    """"anthropic.claude-sonnet-5" as "Claude Sonnet 5", read from the id.

    Any id the rule does not fit (a dated snapshot, the fixed label for an
    inference profile) is said as it is, so the name always comes from the
    answer and never from a constant.
    """
    match = _CLAUDE_ID.match(model_answered or "")
    if not match:
        return model_answered
    family = match.group(1).capitalize()
    version = ".".join(match.group(2).strip("-").split("-"))
    return f"Claude {family} {version}"


class BedrockSynthesisPort(Protocol):
    async def summarize_diff(self, raw_diff: str, sections: list[DiffSectionDigest]) -> SemanticDiffReport:
        ...

    def summarize_locally(
        self, raw_diff: str, sections: list[DiffSectionDigest], reason: str,
    ) -> SemanticDiffReport:
        ...


class DigestDiffUseCase:
    def __init__(self, bedrock_adapter: BedrockSynthesisPort):
        self._bedrock = bedrock_adapter

    async def drill_down(
        self, raw_diff: str, section_index: int, engine: str = "auto",
    ) -> tuple[DiffSectionDigest, SemanticDiffReport]:
        """One file of the patch: its locally parsed section, and a digest of
        that file's own part of the patch.

        The index is checked against the local parse before anything else, so
        a press past the last file never reaches a model. The model, when one
        is called, is shown this file's text only, and the report's coverage
        counts are counts of that text.
        """
        pairs = UnifiedDiffParser.parse_patch_with_text(raw_diff)
        if section_index < 0 or section_index >= len(pairs):
            raise IndexError(
                f"Section index {section_index} is out of bounds; the patch has "
                f"{len(pairs)} sections."
            )
        section, file_text = pairs[section_index]
        return section, await self.execute(file_text, engine=engine)

    async def execute(self, raw_diff: str, engine: str = "auto") -> SemanticDiffReport:
        """Digest a patch. ``engine="local"`` never reaches a model."""
        if not raw_diff or not raw_diff.strip():
            return SemanticDiffReport(
                total_files_changed=0,
                total_insertions=0,
                total_deletions=0,
                executive_spoken_summary="No code changes detected in the current workspace.",
                category_breakdown={},
                critical_findings=[],
                sections=[],
                synthesis_mode="heuristic-local",
                fallback_reason="an empty patch is answered locally; no model is called",
            )

        # 1. Deterministic AST & Unified patch parsing
        sections = UnifiedDiffParser.parse_patch(raw_diff)
        
        # 2. Extract metrics
        total_insertions = sum(s.added_count for s in sections)
        total_deletions = sum(s.removed_count for s in sections)
        categories = Counter(s.category.value for s in sections)
        
        # A finding is spoken before anything else in the digest, so it names
        # what changed. "detected auth_token" is a keyword hit dressed up as a
        # conclusion; the parser now supplies the sentence itself.
        critical_findings = []
        for s in sections:
            if s.security_findings:
                for finding in s.security_findings:
                    critical_findings.append(f"In {s.file_path}, {finding}.")
            else:
                for flag in s.security_flags:
                    critical_findings.append(f"Potential security impact in {s.file_path}: detected {flag}.")

        # 3. Enhance via Bedrock Synthesis Adapter
        if engine == "local":
            enhanced_report = self._bedrock.summarize_locally(
                raw_diff, sections, LOCAL_ENGINE_REQUESTED,
            )
        else:
            enhanced_report = await self._bedrock.summarize_diff(raw_diff, sections)
        
        # Merge deterministic bounds with synthesis. The model-evidence fields
        # ride along untouched: rebuilding the report without them answered
        # model_input_truncated:false for a prefix the model never saw whole.
        return SemanticDiffReport(
            total_files_changed=len(sections),
            total_insertions=total_insertions,
            total_deletions=total_deletions,
            executive_spoken_summary=enhanced_report.executive_spoken_summary,
            category_breakdown=dict(categories),
            critical_findings=critical_findings,
            sections=sections,
            synthesis_mode=enhanced_report.synthesis_mode,
            fallback_reason=enhanced_report.fallback_reason,
            model_prose_full=enhanced_report.model_prose_full,
            model_input_chars_sent=enhanced_report.model_input_chars_sent,
            model_input_chars_total=enhanced_report.model_input_chars_total,
            model_answered=enhanced_report.model_answered,
        )
