"""Pure Domain Layer: why a pull request could not be read, in words a listener can act on.

The adapter that reads GitHub raises ``PullRequestReadError`` (its own
``GitHubReadError`` subclasses it), so the application layer can explain a
failure without importing infrastructure. ``read_failure_words`` is what the
listener hears; it never names an exception class.
"""


class PullRequestReadError(Exception):
    """A pull request could not be read, with the cause in a form a listener can act on.

    ``reason`` is one of the constants below; ``status`` is the HTTP status
    when the host answered. The message is for logs. What a listener hears is
    ``read_failure_words``, which never names an exception class.
    """

    NOT_FOUND = "not_found"
    REFUSED = "refused"
    UNREACHABLE = "unreachable"
    BAD_ANSWER = "bad_answer"

    def __init__(self, message: str, status: int | None = None, reason: str | None = None,
                 rate_limited: bool = False, host_message: str = ""):
        super().__init__(message)
        self.status = status
        self.rate_limited = rate_limited
        #: The host's own one-line explanation, when it gave one in plain words.
        self.host_message = host_message
        if reason is None:
            if status is None:
                reason = self.UNREACHABLE
            elif status == 404:
                reason = self.NOT_FOUND
            elif status in (401, 403, 429):
                reason = self.REFUSED
            else:
                reason = self.BAD_ANSWER
        self.reason = reason


def read_failure_words(exc: BaseException, url: str, *, retry: str = "open it again",
                       label: str | None = None) -> str:
    """Why a pull request could not be read, and what to do, in plain words.

    ``retry`` names the command that tries again: "open it again" after an
    open, "say resume again" after a refresh. ``label`` is the pull request
    as the rest of the dialogue names it ("octocat/Hello-World pull request
    1"); without one, the link is said instead.
    """
    if isinstance(exc, PullRequestReadError):
        if exc.reason == PullRequestReadError.NOT_FOUND:
            named = label or f"pull request at {url}"
            return (
                f"GitHub found no {named}. Check the owner, the repository and "
                f"the number in the link, then {retry}. A private repository also needs a "
                "GITHUB_TOKEN on the server."
            )
        if exc.reason == PullRequestReadError.REFUSED and exc.rate_limited:
            return (
                "GitHub refused the read because this server has used up its hourly reads "
                "without a token. Wait for the limit to reset, or set a GITHUB_TOKEN on the "
                f"server, then {retry}."
            )
        if exc.reason == PullRequestReadError.REFUSED:
            return (
                "GitHub refused to show this pull request. It may be private, or the token on "
                f"the server may not have access to it. Check the GITHUB_TOKEN, then {retry}."
            )
        if exc.reason == PullRequestReadError.UNREACHABLE:
            return f"GitHub could not be reached from this server. Check its network connection, then {retry}."
        if exc.status is not None and exc.status >= 500:
            return f"GitHub had a server error and sent no pull request. Wait a minute, then {retry}."
        if exc.host_message:
            said = exc.host_message.strip().rstrip(".")
            return f"GitHub did not send the pull request, and said: {said}. Check the link, then {retry}."
        return f"GitHub did not send the pull request and gave no reason. Check the link, then {retry}."
    if isinstance(exc, ValueError):
        return (
            f"{url} is not a link to a GitHub pull request. A pull request link looks like "
            "https://github.com/owner/repository/pull/1."
        )
    return f"Something went wrong while reading it, and nothing changed. Wait a minute, then {retry}."
