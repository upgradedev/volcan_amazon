"""Unit tests for AST-aware Semantic Diff Synthesis."""
import asyncio

from src.application.digest_diff_use_case import DigestDiffUseCase
from src.domain.semantic_diff import (
    ChangeCategory,
    ChangeSignificance,
    DiffSectionDigest,
    SemanticDiffReport,
    UnifiedDiffParser,
)

SAMPLE_DIFF = """diff --git a/src/auth/jwt_handler.py b/src/auth/jwt_handler.py
index 83a1b2..94c3d4 100644
--- a/src/auth/jwt_handler.py
+++ b/src/auth/jwt_handler.py
@@ -10,6 +10,12 @@
-import hashlib
+import hmac
+import hashlib
+def verify_token(token: str, secret: str) -> bool:
+    # Validate token expiration and HMAC signature
+    return hmac.compare_digest(token, secret)
diff --git a/docs/README.md b/docs/README.md
index 111..222 100644
--- a/docs/README.md
+++ b/docs/README.md
@@ -1,3 +1,4 @@
+# Volcan Documentation
"""


class MockBedrockSynthesis:
    async def summarize_diff(self, raw_diff: str, sections: list[DiffSectionDigest]) -> SemanticDiffReport:
        return SemanticDiffReport(
            total_files_changed=len(sections),
            total_insertions=sum(s.added_count for s in sections),
            total_deletions=sum(s.removed_count for s in sections),
            executive_spoken_summary="Updated JWT token authentication with HMAC signature validation and updated documentation.",
            category_breakdown={},
            critical_findings=[],
            sections=sections,
            # This mock stands in for a model answer, so it says so: the level 0
            # summary keeps a model's own headline after the finding, and drops
            # only the local engine's headline, which restated the finding.
            synthesis_mode="bedrock",
        )


def test_empty_diff_returns_clean_digest():
    async def _test():
        use_case = DigestDiffUseCase(MockBedrockSynthesis())
        report = await use_case.execute("")
        assert report.total_files_changed == 0
        assert "No code changes" in report.top_level_summary_spoken if hasattr(report, "top_level_summary_spoken") else "No code changes" in report.executive_spoken_summary
    asyncio.run(_test())


def test_unified_diff_parser_security_flags():
    sections = UnifiedDiffParser.parse_patch(SAMPLE_DIFF)
    assert len(sections) == 2
    
    auth_sec = sections[0]
    assert auth_sec.file_path == "src/auth/jwt_handler.py"
    assert auth_sec.category == ChangeCategory.SECURITY_SENSITIVE
    assert auth_sec.significance == ChangeSignificance.CRITICAL
    assert "auth_token" in auth_sec.security_flags or "crypto" in auth_sec.security_flags

    doc_sec = sections[1]
    assert doc_sec.file_path == "docs/README.md"
    assert doc_sec.category == ChangeCategory.DOCUMENTATION
    assert doc_sec.significance == ChangeSignificance.LOW


def test_multi_level_spoken_summaries():
    async def _test():
        use_case = DigestDiffUseCase(MockBedrockSynthesis())
        report = await use_case.execute(SAMPLE_DIFF)
        
        # Level 0
        summary_l0 = report.to_voice_summary(level=0)
        assert "Modified 2 files" in summary_l0
        assert "JWT token authentication" in summary_l0

        # Level 1
        summary_l1 = report.to_voice_summary(level=1)
        assert "Section 1: src/auth/jwt_handler.py" in summary_l1
        assert "Section 2: docs/README.md" in summary_l1

        # Level 2
        summary_l2 = report.to_voice_summary(level=2)
        assert "Critical Findings:" in summary_l2 or "Security Alert" in summary_l2
    asyncio.run(_test())
