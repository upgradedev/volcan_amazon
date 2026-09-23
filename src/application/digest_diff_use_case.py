"""Use Case: Digest Raw Code Diffs into Multi-Level Spoken Summaries."""
from collections import Counter
from typing import Protocol

from src.domain.semantic_diff import (
    DiffSectionDigest,
    SemanticDiffReport,
    UnifiedDiffParser,
)


class BedrockSynthesisPort(Protocol):
    async def summarize_diff(self, raw_diff: str, sections: list[DiffSectionDigest]) -> SemanticDiffReport:
        ...


class DigestDiffUseCase:
    def __init__(self, bedrock_adapter: BedrockSynthesisPort):
        self._bedrock = bedrock_adapter

    async def execute(self, raw_diff: str) -> SemanticDiffReport:
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
        enhanced_report = await self._bedrock.summarize_diff(raw_diff, sections)
        
        # Merge deterministic bounds with synthesis
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
        )
