"""Resolve a reviewer from the server roster, without accepting caller identity."""
import hmac
import json
import os
import re

from src.application.review_authorization import ReviewPrincipal

REVIEWERS_ENV = "VOLCAN_REVIEWERS"
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


def authenticated_reviewer(authorization: str | None) -> ReviewPrincipal | None:
    """Invalid/missing credentials or malformed configuration fail closed.

    Roster: {"alice": {"token": "<32+ chars>", "repositories": ["owner/repo"]}}.
    Never log credentials, accept duplicate credentials, or allow wildcards.
    An identity may not contain ":", which keeps every reviewer apart from the
    fixed anonymous owner (``public:anonymous``) of durable public sessions.
    """
    if not authorization:
        return None
    scheme, separator, supplied = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not supplied or supplied != supplied.strip():
        return None
    try:
        roster = json.loads(os.getenv(REVIEWERS_ENV, "{}"))
        if not isinstance(roster, dict):
            return None
        identities = []
        seen_tokens: set[str] = set()
        for identity, config in roster.items():
            if (
                not isinstance(identity, str) or not identity.strip() or ":" in identity
                or not isinstance(config, dict)
            ):
                return None
            token = config.get("token")
            repositories = config.get("repositories")
            if not isinstance(token, str) or len(token) < 32 or token in seen_tokens:
                return None
            if not isinstance(repositories, list) or not repositories or any(
                not isinstance(repo, str) or not _REPOSITORY.fullmatch(repo)
                or any(part in {".", ".."} for part in repo.split("/"))
                for repo in repositories
            ):
                return None
            seen_tokens.add(token)
            identities.append((token, ReviewPrincipal(identity, frozenset(
                repo.lower() for repo in repositories
            ))))
        for token, principal in identities:
            if hmac.compare_digest(supplied.encode("utf-8"), token.encode("utf-8")):
                return principal
    except (ValueError, TypeError):
        return None
    return None
