"""Use Case: Digest Raw Code Diffs into Multi-Level Spoken Summaries."""
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
        )
