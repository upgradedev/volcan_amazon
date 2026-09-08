"""Domain rules that read a patch as Python syntax rather than as characters.

The regular expressions in ``semantic_diff.py`` answer one question: does this
text mention authentication, cryptography, a database or a process spawn. They
cannot answer "did this change invert an authorization decision", because the
words on both sides of that change are identical. ``user.role == "admin"`` and
``user.role != "admin"`` share every keyword they contain, so a substring
matcher sees no difference and a listener is told the change is business logic.

The rules here parse the added and removed lines of a patch into Python syntax
trees and compare the trees, so a change is described by what it did rather than
by which keyword it happened to carry. Three classes are covered, chosen because
each is invisible to keyword matching and each is a real outage or breach:

* ``authz_comparison_inverted``  a comparison operator flipped inside a
  predicate that decides authorization
* ``permissive_cors_origin``     a cross-origin policy widened to any origin
* ``security_call_removed``      a verification call deleted and not replaced

Each rule returns a sentence a screen reader can speak, because the finding is
the first thing a blind reviewer hears and "detected auth_token" tells them
nothing about what changed.

The rules are deliberately conservative. A line that does not parse as Python
produces no finding rather than a guess, and every rule needs positive evidence
from the tree, never from the surrounding prose.
"""
import ast
import re
from dataclasses import dataclass

#: Identifiers that make a predicate an authorization decision rather than
#: arithmetic. A comparison flip only matters when it decides who may act.
AUTHORIZATION_TERMS = re.compile(
    r"(role|admin|superuser|staff|permission|privileg|owner|scope|"
    r"authori[sz]|authenticat|allowed|can_|may_|acl|grant|tier|plan)",
    re.IGNORECASE,
)

#: Comparison operators and the operator that reverses their meaning.
_INVERSE_OPERATORS = {
    "Eq": "NotEq", "NotEq": "Eq",
    "Is": "IsNot", "IsNot": "Is",
    "In": "NotIn", "NotIn": "In",
    "Lt": "GtE", "GtE": "Lt",
    "Gt": "LtE", "LtE": "Gt",
}

#: Assignment targets and keyword arguments that carry a cross-origin policy.
_ORIGIN_TARGETS = re.compile(
    r"(allow[_-]?origins?|cors[_-]?origins?|access-control-allow-origin|origin_regex)",
    re.IGNORECASE,
)

#: Origin values that mean "any site may call this".
_WILDCARD_ORIGINS = {"*", "*/*", "null", ".*", "^.*$"}

#: Call names whose removal is a security change on the name alone.
_UNAMBIGUOUS_SECURITY_CALLS = re.compile(
    r"^(verify|authenticate|authori[sz]e|check_signature|verify_signature|"
    r"validate_signature|require_auth\w*|check_auth\w*|ensure_auth\w*)$",
    re.IGNORECASE,
)

#: A verification verb. On its own it proves nothing: ``verify_email_format``
#: is a formatting helper, not a security control.
_VERIFICATION_VERB = re.compile(r"^(verify|validate|check|ensure|assert|require)_", re.IGNORECASE)

#: The object a verification verb has to be applied to before its removal is a
#: security finding rather than a refactor.
_SECURITY_OBJECT = re.compile(
    r"(signature|token|auth|permission|credential|password|hmac|jwt|"
    r"cert|session|access|role|csrf|nonce|scope|grant|sign)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AstFinding:
    """One structural finding, with the sentence a voice surface speaks."""

    rule_id: str
    spoken: str


def parse_fragment(line: str) -> ast.AST | None:
    """Parse a single diff line as Python, or return None.

    Diff lines are fragments. They arrive indented, a block header ends in a
    colon with no body, and a ``return`` has no enclosing function. Each of
    those is a SyntaxError for a bare ``ast.parse``, so the fragment is tried in
    increasingly forgiving forms and abandoned quietly when none of them parse.
    A line that is not Python is not evidence of anything.

    A line lifted out of an argument list keeps the comma that separated it from
    its neighbour, and that comma is not harmless: ``allow_origins=["*"],``
    parses as a one-element tuple, so the rule below describes it as
    ``allow_origins = (['*'],)``. That sentence is true of the fragment and
    false of the code it came from, and a listener hears it. One trailing comma
    is therefore dropped before parsing, which is how real middleware
    configuration is written and how it must be read back.
    """
    text = line.strip()
    if not text or text.startswith("#"):
        return None
    if text.endswith(","):
        text = text[:-1].rstrip()
        if not text:
            return None

    candidates = [text]
    if text.endswith(":"):
        candidates.append(f"{text} pass")
    body = candidates[-1]
    candidates.append("def _volcan_fragment():\n    " + body.replace("\n", "\n    "))

    for candidate in candidates:
        try:
            return ast.parse(candidate)
        except (SyntaxError, ValueError):
            continue
    return None


def _parsed_lines(lines: list[str]) -> list[tuple[str, ast.AST]]:
    parsed = []
    for line in lines:
        tree = parse_fragment(line)
        if tree is not None:
            parsed.append((line.strip(), tree))
    return parsed


def _comparisons(tree: ast.AST) -> list[tuple[str, str, str, str]]:
    """(left, operator, right, source) for every single-operator comparison."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            found.append((
                ast.dump(node.left),
                type(node.ops[0]).__name__,
                ast.dump(node.comparators[0]),
                ast.unparse(node),
            ))
    return found


def _find_inverted_authorization(
    added: list[tuple[str, ast.AST]], removed: list[tuple[str, ast.AST]]
) -> list[AstFinding]:
    """A comparison whose operands are unchanged and whose operator reversed.

    Both sides of the change mention the same identifiers, which is exactly why
    a keyword matcher cannot see it. The operands are compared as dumped syntax
    trees, so whitespace and quoting styles do not produce false differences.
    """
    findings: list[AstFinding] = []
    seen: set[str] = set()
    removed_comparisons = [item for _, tree in removed for item in _comparisons(tree)]

    for _, tree in added:
        for left, operator, right, source in _comparisons(tree):
            for old_left, old_operator, old_right, old_source in removed_comparisons:
                if (left, right) != (old_left, old_right):
                    continue
                if _INVERSE_OPERATORS.get(old_operator) != operator:
                    continue
                if not AUTHORIZATION_TERMS.search(source):
                    continue
                if source in seen:
                    continue
                seen.add(source)
                findings.append(AstFinding(
                    "authz_comparison_inverted",
                    f"an authorization comparison was inverted: {old_source} became {source}",
                ))
    return findings


def _string_constants(node: ast.AST) -> list[str]:
    return [
        child.value for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    ]


def _find_permissive_cors(added: list[tuple[str, ast.AST]]) -> list[AstFinding]:
    """An origin policy assigned or passed a value that accepts any site."""
    findings: list[AstFinding] = []
    seen: set[str] = set()

    def _report(label: str, value_node: ast.AST) -> None:
        values = {value.strip() for value in _string_constants(value_node)}
        if not values & _WILDCARD_ORIGINS:
            return
        if label in seen:
            return
        seen.add(label)
        findings.append(AstFinding(
            "permissive_cors_origin",
            f"a cross-origin policy was widened to accept any origin: {label}",
        ))

    for _, tree in added:
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg and _ORIGIN_TARGETS.search(node.arg):
                _report(f"{node.arg}={ast.unparse(node.value)}", node.value)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if _ORIGIN_TARGETS.search(ast.unparse(target)):
                        _report(ast.unparse(node), node.value)
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                if _ORIGIN_TARGETS.search(ast.unparse(node.target)):
                    _report(ast.unparse(node), node.value)
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if key is None or not isinstance(key, ast.Constant):
                        continue
                    if isinstance(key.value, str) and _ORIGIN_TARGETS.search(key.value):
                        _report(f"{key.value!r}: {ast.unparse(value)}", value)
    return findings


def _is_security_call(name: str) -> bool:
    """Whether deleting a call to ``name`` is a security change.

    A verification verb alone is not enough. ``verify_email_format`` checks a
    string shape; ``verify_signature`` checks a signature. The verb has to be
    applied to a security object before the deletion counts, unless the name is
    one that means nothing else.
    """
    if _UNAMBIGUOUS_SECURITY_CALLS.match(name):
        return True
    return bool(_VERIFICATION_VERB.match(name) and _SECURITY_OBJECT.search(name))


def _called_names(parsed: list[tuple[str, ast.AST]]) -> dict[str, str]:
    """Every called name in these lines, mapped to the source that called it."""
    names: dict[str, str] = {}
    for _, tree in parsed:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name):
                names.setdefault(func.id, ast.unparse(node))
            elif isinstance(func, ast.Attribute):
                names.setdefault(func.attr, ast.unparse(node))
    return names


def _find_removed_security_calls(
    added: list[tuple[str, ast.AST]], removed: list[tuple[str, ast.AST]]
) -> list[AstFinding]:
    """A verification call present before the change and absent after it.

    A call that reappears anywhere in the same file's added lines was moved or
    renamed around, not deleted, so it produces no finding.
    """
    still_called = set(_called_names(added))
    findings = []
    for name, source in _called_names(removed).items():
        if name in still_called or not _is_security_call(name):
            continue
        findings.append(AstFinding(
            "security_call_removed",
            f"the call {source} was removed and nothing replaced it",
        ))
    return findings


def evaluate(added_lines: list[str], removed_lines: list[str]) -> list[AstFinding]:
    """Run every structural rule over one file's added and removed lines."""
    added = _parsed_lines(added_lines)
    removed = _parsed_lines(removed_lines)
    return (
        _find_inverted_authorization(added, removed)
        + _find_permissive_cors(added)
        + _find_removed_security_calls(added, removed)
    )
