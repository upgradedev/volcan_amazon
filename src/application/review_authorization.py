"""Request-scoped authority for the live review journey.

HTTP credentials establish this context, never a JSON user_id or MCP session.
The context propagates through asyncio.to_thread to the final GitHub write.
"""
from contextvars import ContextVar
from dataclasses import dataclass


class ReviewAuthorizationError(Exception):
    def __init__(self, code: str, status: int, detail: str):
        super().__init__(detail)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class ReviewPrincipal:
    identity: str
    repositories: frozenset[str]

    def require_repository(self, owner: str, repo: str) -> None:
        if f"{owner}/{repo}".lower() not in self.repositories:
            raise ReviewAuthorizationError(
                "REPOSITORY_NOT_ALLOWED", 403, "This reviewer may not access that repository."
            )


current_review_principal: ContextVar[ReviewPrincipal | None] = ContextVar(
    "current_review_principal", default=None
)


def require_review_principal() -> ReviewPrincipal:
    principal = current_review_principal.get()
    if principal is None:
        raise ReviewAuthorizationError(
            "REVIEW_AUTH_REQUIRED", 401,
            "Live review access requires a configured reviewer Bearer credential.",
        )
    return principal
