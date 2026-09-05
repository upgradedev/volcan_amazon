"""Infrastructure adapter: allowlisted dry-run command planner.

Volcan never runs a shell command on a developer's machine on the strength of a
voice utterance, and this adapter is where that promise is enforced. It parses
the requested command, decides whether the command is inside a narrow
allowlist, and returns the exact argument vector it *would* run. It never calls
``subprocess``, ``os.system`` or ``eval``. There is no code path in this module
that executes anything.

That is a deliberate product decision, not a stub: the honest capability is
"Volcan plans and explains a command and refuses the ones outside its
allowlist", and the README states it in those words.
"""
import shlex
from dataclasses import asdict, dataclass, field

#: Executable -> permitted first subcommand/flag prefixes. An empty tuple means
#: the executable is allowed with no subcommand constraint.
DEFAULT_ALLOWLIST: dict[str, tuple[str, ...]] = {
    "git": ("status", "diff", "log", "show", "branch", "rev-parse"),
    "pytest": (),
    "ruff": ("check", "format"),
    "python": ("-m",),
}

#: Any of these in the raw string means the caller is trying to compose or
#: redirect, which the planner refuses before it even tokenises the command.
SHELL_METACHARACTERS = (";", "&&", "||", "|", ">", "<", "`", "$(", "\n")


@dataclass(frozen=True)
class CommandPlan:
    """The planner's answer. ``executed`` is always False, by construction."""

    requested_command: str
    allowed: bool
    argv: list[str] = field(default_factory=list)
    would_run: str | None = None
    refusal_reason: str | None = None
    executed: bool = False
    allowlist: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def spoken(self) -> str:
        if self.allowed:
            return (
                f"Dry run only, nothing was executed. The approved plan is: {self.would_run}. "
                "Run it yourself to apply it."
            )
        return f"Refused, and nothing was executed. {self.refusal_reason}"


class DryRunExecutor:
    """Plans commands against an allowlist. Executes nothing, ever."""

    def __init__(self, allowlist: dict[str, tuple[str, ...]] | None = None):
        self._allowlist = dict(allowlist if allowlist is not None else DEFAULT_ALLOWLIST)

    @property
    def allowed_executables(self) -> list[str]:
        return sorted(self._allowlist)

    def plan(self, command: str) -> CommandPlan:
        allowlist = self.allowed_executables

        if not command or not command.strip():
            return CommandPlan(
                requested_command=command or "",
                allowed=False,
                refusal_reason="An empty command cannot be planned.",
                allowlist=allowlist,
            )

        for meta in SHELL_METACHARACTERS:
            if meta in command:
                return CommandPlan(
                    requested_command=command,
                    allowed=False,
                    refusal_reason=(
                        f"Refused: the command contains the shell metacharacter '{meta}'. "
                        "Volcan plans single commands only and never composes a shell line."
                    ),
                    allowlist=allowlist,
                )

        try:
            argv = shlex.split(command)
        except ValueError as exc:
            return CommandPlan(
                requested_command=command,
                allowed=False,
                refusal_reason=f"Refused: the command could not be tokenised ({exc}).",
                allowlist=allowlist,
            )

        if not argv:
            return CommandPlan(
                requested_command=command,
                allowed=False,
                refusal_reason="Refused: the command tokenised to nothing.",
                allowlist=allowlist,
            )

        executable = argv[0]
        if executable not in self._allowlist:
            return CommandPlan(
                requested_command=command,
                allowed=False,
                argv=argv,
                refusal_reason=(
                    f"Refused: '{executable}' is not an allowlisted executable. "
                    f"Allowed: {', '.join(allowlist)}."
                ),
                allowlist=allowlist,
            )

        permitted_subcommands = self._allowlist[executable]
        if permitted_subcommands:
            subcommand = argv[1] if len(argv) > 1 else ""
            if subcommand not in permitted_subcommands:
                return CommandPlan(
                    requested_command=command,
                    allowed=False,
                    argv=argv,
                    refusal_reason=(
                        f"Refused: '{executable} {subcommand}'.strip() is outside the read-only "
                        f"subcommand set for '{executable}'. "
                        f"Allowed: {', '.join(permitted_subcommands)}."
                    ),
                    allowlist=allowlist,
                )

        return CommandPlan(
            requested_command=command,
            allowed=True,
            argv=argv,
            would_run=" ".join(shlex.quote(part) for part in argv),
            allowlist=allowlist,
        )

    async def run_command(self, command: str) -> str:
        """Satisfies ``CommandExecutionPort`` without executing the command.

        The name comes from the port. The behaviour is planning only, and the
        returned sentence says so on every path.
        """
        return self.plan(command).spoken
