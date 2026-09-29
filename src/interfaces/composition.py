"""Interfaces Layer: the composition root.

Every adapter, use case and registry the HTTP surfaces need is built exactly
once here, so the REST routes, the MCP tool catalog and the MCP transport all
operate on the same instances and the wiring is readable in one place.
"""
import os

from src.application.accessibility_use_case import AccessibilityOrchestratorUseCase
from src.application.braille_diff_use_case import BrailleDiffUseCase
from src.application.digest_diff_use_case import DigestDiffUseCase
from src.application.ecosystem_companion_use_case import OrchestrateEcosystemCompanionUseCase
from src.application.governed_execution_use_case import GovernedExecutionUseCase
from src.application.review_dialogue_use_case import ReviewDialogueUseCase
from src.application.sonify_event_use_case import SonifyEventUseCase
from src.application.voice_turn_use_case import VoiceTurnUseCase
from src.domain.approval_grant import ApprovalGrantIssuer
from src.domain.ast_completeness_checker import ASTGraphCompletenessChecker
from src.infrastructure.audit_repository import InMemoryAuditRepository
from src.infrastructure.bedrock_adapter import BedrockSynthesisAdapter
from src.infrastructure.dry_run_executor import DryRunExecutor
from src.infrastructure.dynamodb_audit_repository import DynamoAuditRepository
from src.infrastructure.dynamodb_state import DynamoStateStore
from src.infrastructure.github_review_adapter import GitHubReviewAdapter
from src.infrastructure.secret_provider import load_approval_secret
from src.interfaces.mcp_protocol import SessionRegistry

state_store = DynamoStateStore.from_environment()
audit_repo = (
    DynamoAuditRepository(state_store.table_name, table=state_store.table)
    if state_store is not None else InMemoryAuditRepository()
)
bedrock_adapter = BedrockSynthesisAdapter()
dry_run_executor = DryRunExecutor()
ast_checker = ASTGraphCompletenessChecker()
#: Reads public pull requests unauthenticated. Writes a review only when
#: VOLCAN_GITHUB_WRITE=1 and GITHUB_TOKEN are set and a configured reviewer is
#: authorized for the repository. The adapter flag/token are reported on /health.
github_adapter = GitHubReviewAdapter()

#: A durable deployment receives only a Secrets Manager ARN and resolves the
#: value once at cold start. Local mode may use a 32-byte environment value or
#: an ephemeral key whose restart-invalidating behavior is reported in health.
_approval_secret = load_approval_secret(durable=state_store is not None)
grant_issuer = ApprovalGrantIssuer(
    _approval_secret.value,
    replay_store=state_store,
)

digest_use_case = DigestDiffUseCase(bedrock_adapter)
sonify_use_case = SonifyEventUseCase()
ecosystem_use_case = OrchestrateEcosystemCompanionUseCase()
braille_use_case = BrailleDiffUseCase()
accessibility_use_case = AccessibilityOrchestratorUseCase()
governed_use_case = GovernedExecutionUseCase(
    dry_run_executor, audit_repo, grant_issuer, state_store=state_store,
)
voice_turn_use_case = VoiceTurnUseCase(
    digest_use_case, governed_use_case, sonify_use_case, state_store=state_store,
)
review_dialogue_use_case = ReviewDialogueUseCase(
    digest_use_case, github_adapter, grant_issuer, audit_repo, sonify_use_case,
    state_store=state_store,
)

#: The loopback port ``python -m src.interfaces.mcp_server`` binds when nothing
#: else is configured. ``VOLCAN_PORT`` (or ``--port``) changes the bind port and
#: the default Origin allowlist together, so the page the server itself serves
#: can always run the MCP handshake against it.
DEFAULT_PORT = 8000


def local_port() -> int:
    raw = os.getenv("VOLCAN_PORT", str(DEFAULT_PORT)).strip()
    try:
        port = int(raw)
    except ValueError:
        raise RuntimeError(f"VOLCAN_PORT must be a port number, not {raw!r}.") from None
    if not 0 < port < 65536:
        raise RuntimeError(f"VOLCAN_PORT must be between 1 and 65535, not {port}.")
    return port


def default_allowed_origins() -> tuple[str, str]:
    """The two loopback spellings of the origin this process serves.

    This is still an explicit allowlist: it names loopback on the configured
    port and nothing else. Trusting the request's Host header instead would
    reopen the DNS-rebinding case the Origin check exists to stop.
    """
    port = local_port()
    return (f"http://127.0.0.1:{port}", f"http://localhost:{port}")


#: The allowlist for the default port, kept for callers that import it.
DEFAULT_ALLOWED_ORIGINS = (f"http://127.0.0.1:{DEFAULT_PORT}", f"http://localhost:{DEFAULT_PORT}")


def allowed_origins() -> set[str]:
    configured = os.getenv("VOLCAN_ALLOWED_ORIGINS")
    if configured:
        return {origin.strip() for origin in configured.split(",") if origin.strip()}
    return set(default_allowed_origins())


def mcp_session_mode() -> str:
    """Return the configured MCP transport mode.

    Stateful mode is useful for a single local process. The public Lambda uses
    a stateless *transport* because consecutive requests are not guaranteed to
    hit the same execution environment. This transport setting itself does not
    persist application state; ``VOLCAN_STATE_TABLE`` independently selects the
    shared DynamoDB backend for dialogue, actions, nonces and audit records.
    """
    mode = os.getenv("VOLCAN_MCP_SESSION_MODE", "stateful").strip().lower()
    if mode not in {"stateful", "stateless"}:
        raise RuntimeError("VOLCAN_MCP_SESSION_MODE must be 'stateful' or 'stateless'.")
    return mode


def durable_state_capability() -> dict[str, object]:
    if state_store is None:
        return {
            "backend": "process_memory",
            "configured": False,
            "reachable": None,
            "resolved_capability": "process_memory",
            "durable_across_restart": False,
            "shared_across_workers": False,
            "approval_secret_persistent": _approval_secret.source == "environment",
            "approval_secret_source": _approval_secret.source,
        }
    return {
        **state_store.capability(),
        "approval_secret_persistent": True,
        "approval_secret_source": _approval_secret.source,
        "audit_chain": "transactional_scoped_hash_chains",
    }


#: MCP session identifiers this process has issued.
sessions = SessionRegistry()
