"""Interfaces Layer: the composition root.

Every adapter, use case and registry the HTTP surfaces need is built exactly
once here, so the REST routes, the MCP tool catalog and the MCP transport all
operate on the same instances and the wiring is readable in one place.
"""
import os
import secrets

from src.application.accessibility_use_case import AccessibilityOrchestratorUseCase
from src.application.braille_diff_use_case import BrailleDiffUseCase
from src.application.digest_diff_use_case import DigestDiffUseCase
from src.application.ecosystem_companion_use_case import OrchestrateEcosystemCompanionUseCase
from src.application.governed_execution_use_case import GovernedExecutionUseCase
from src.application.sonify_event_use_case import SonifyEventUseCase
from src.application.voice_turn_use_case import VoiceTurnUseCase
from src.domain.approval_grant import ApprovalGrantIssuer
from src.domain.ast_completeness_checker import ASTGraphCompletenessChecker
from src.infrastructure.audit_repository import InMemoryAuditRepository
from src.infrastructure.bedrock_adapter import BedrockSynthesisAdapter
from src.infrastructure.dry_run_executor import DryRunExecutor
from src.infrastructure.git_adapter import LocalGitAdapter
from src.interfaces.mcp_protocol import SessionRegistry

audit_repo = InMemoryAuditRepository()
bedrock_adapter = BedrockSynthesisAdapter()
git_adapter = LocalGitAdapter()
dry_run_executor = DryRunExecutor()
ast_checker = ASTGraphCompletenessChecker()

#: Signing secret for approval grants. Set VOLCAN_APPROVAL_SECRET to keep grants
#: valid across restarts; otherwise a fresh per-process secret is generated,
#: which invalidates outstanding grants on restart rather than accepting them.
_secret_env = os.getenv("VOLCAN_APPROVAL_SECRET")
grant_issuer = ApprovalGrantIssuer(
    _secret_env.encode("utf-8") if _secret_env and len(_secret_env) >= 16 else secrets.token_bytes(32)
)

digest_use_case = DigestDiffUseCase(bedrock_adapter)
sonify_use_case = SonifyEventUseCase()
ecosystem_use_case = OrchestrateEcosystemCompanionUseCase()
braille_use_case = BrailleDiffUseCase()
accessibility_use_case = AccessibilityOrchestratorUseCase()
governed_use_case = GovernedExecutionUseCase(dry_run_executor, audit_repo, grant_issuer)
voice_turn_use_case = VoiceTurnUseCase(digest_use_case, governed_use_case, sonify_use_case)

DEFAULT_ALLOWED_ORIGINS = ("http://127.0.0.1:8000", "http://localhost:8000")


def allowed_origins() -> set[str]:
    configured = os.getenv("VOLCAN_ALLOWED_ORIGINS")
    if configured:
        return {origin.strip() for origin in configured.split(",") if origin.strip()}
    return set(DEFAULT_ALLOWED_ORIGINS)



#: MCP session identifiers this process has issued.
sessions = SessionRegistry()
