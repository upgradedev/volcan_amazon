"""Domain rules that read a patch as Python syntax rather than as characters.

The regular expressions in ``semantic_diff.py`` answer one question: does this
text mention authentication, cryptography, a database or a process spawn. They
cannot answer "did this change invert an authorization decision", because the
words on both sides of that change are identical. ``user.role == "admin"`` and
``user.role != "admin"`` share every keyword they contain, so a substring
matcher sees no difference and a listener is told the change is business logic.

The rules here parse the added and removed lines of a patch into Python syntax
trees and compare the trees, so a change is described by what it did rather than
by which keyword it happened to carry. Three classes are covered because each is
invisible to keyword matching and each is a real outage or breach:

* ``authz_comparison_inverted``  a comparison operator flipped inside a
  predicate that decides authorization
* ``permissive_cors_origin``     a cross-origin policy widened to any origin
* ``security_call_removed``      a verification call deleted and not replaced

A second group names classic families that the keyword pass either misses or
can only gesture at. An independent review on 2026-09-28 found the engine
silent on string-built SQL, and these rules were written after a held-out set
for them was committed (``tests/fixtures/diff_corpus_classic.py``):

* ``sql_built_from_strings``     a SQL statement built by concatenation, an
  f-string, ``%`` or ``str.format`` from a value that is not a constant

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


# --- Classic families: values built into a statement -----------------------

#: The opening of a SQL statement. A ``SELECT`` needs a column list shaped like
#: one (``*``, names, calls, separated by commas) before ``FROM``, so an English
#: sentence that happens to start with "Select" is not read as a query.
SQL_STATEMENT = re.compile(
    r"^\s*(?:"
    r"select\s+(?:distinct\s+)?"
    r"(?:\*|[\w.\"`\[\]()*]+(?:\s+as\s+\w+)?(?:\s*,\s*[\w.\"`\[\]()*]+(?:\s+as\s+\w+)?)*)"
    r"\s+from\b"
    r"|insert\s+(?:or\s+\w+\s+)?into\s"
    r"|update\s+[\w.\"`\[\]]+\s+set\s"
    r"|delete\s+from\s"
    r"|replace\s+into\s"
    r"|merge\s+into\s"
    r"|(?:drop|alter|create|truncate)\s+table\s"
    r")",
    re.IGNORECASE,
)

#: What stands in for a value spliced into a string while its shape is read.
_PLACEHOLDER = "value"


def _is_constant_like(node: ast.AST) -> bool:
    """A literal, or a name written as a module constant (``TABLE_NAME``)."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.Name):
        return node.id.isupper()
    if isinstance(node, ast.Attribute):
        return node.attr.isupper()
    if isinstance(node, ast.JoinedStr):
        return not any(isinstance(part, ast.FormattedValue) for part in node.values)
    return False


def _add_chain(node: ast.AST) -> list[ast.AST]:
    """``a + b + c`` as ``[a, b, c]``."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _add_chain(node.left) + _add_chain(node.right)
    return [node]


def _joined_text(node: ast.JoinedStr) -> tuple[str, list[ast.AST]]:
    text, spliced = [], []
    for part in node.values:
        if isinstance(part, ast.Constant) and isinstance(part.value, str):
            text.append(part.value)
        elif isinstance(part, ast.FormattedValue):
            text.append(_PLACEHOLDER)
            spliced.append(part.value)
    return "".join(text), spliced


def string_built_from_values(node: ast.AST) -> tuple[str, str, list[str]] | None:
    """(text, how, values) when ``node`` builds a string from a non-constant.

    ``text`` is the string with each spliced value replaced by a placeholder,
    ``how`` says in words how it was built, and ``values`` names what was
    spliced in. Four shapes are read: ``+`` with a string literal in the chain,
    an f-string, ``%`` with a literal on the left, and ``.format`` on a
    literal. Anything else returns None.
    """
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        pieces = _add_chain(node)
        if not any(isinstance(p, (ast.Constant, ast.JoinedStr)) for p in pieces):
            return None
        text, spliced = [], []
        for piece in pieces:
            if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                text.append(piece.value)
            elif isinstance(piece, ast.JoinedStr):
                inner, values = _joined_text(piece)
                text.append(inner)
                spliced.extend(values)
            else:
                text.append(_PLACEHOLDER)
                spliced.append(piece)
        how = "string concatenation"
    elif isinstance(node, ast.JoinedStr):
        joined, spliced = _joined_text(node)
        text = [joined]
        how = "an f-string"
    elif (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod)
          and isinstance(node.left, ast.Constant) and isinstance(node.left.value, str)):
        text = [node.left.value]
        spliced = list(node.right.elts) if isinstance(node.right, ast.Tuple) else [node.right]
        how = "% formatting"
    elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
          and node.func.attr == "format" and isinstance(node.func.value, ast.Constant)
          and isinstance(node.func.value.value, str)):
        text = [node.func.value.value]
        spliced = list(node.args) + [keyword.value for keyword in node.keywords]
        how = "str.format"
    else:
        return None
    names: list[str] = []
    for item in spliced:
        if _is_constant_like(item):
            continue
        name = ast.unparse(item)
        if name not in names:
            names.append(name)
    if not names:
        return None
    return "".join(text), how, names


def values_words(names: list[str]) -> str:
    """At most three spliced values, as a sentence lists them."""
    shown = names[:3]
    if len(shown) == 1:
        return shown[0]
    return f"{', '.join(shown[:-1])} and {shown[-1]}"


def _built_strings(parsed: list[tuple[str, ast.AST]]) -> list[tuple[ast.AST, tuple[str, str, list[str]]]]:
    """Every outermost string-building expression in these lines."""
    found = []
    inside: set[int] = set()
    for _, tree in parsed:
        for node in ast.walk(tree):
            if id(node) in inside:
                continue
            built = string_built_from_values(node)
            if built is None:
                continue
            found.append((node, built))
            for child in ast.walk(node):
                inside.add(id(child))
    return found


def _find_sql_built_from_strings(
    added: list[tuple[str, ast.AST]], removed: list[tuple[str, ast.AST]]
) -> list[AstFinding]:
    """A SQL statement assembled from a value rather than bound to a parameter.

    The statement is recognised by its opening (``SELECT ... FROM``,
    ``INSERT INTO``, ``UPDATE ... SET``, ``DELETE FROM`` and the table verbs),
    read from the string with every spliced value replaced by a placeholder. A
    value written as a module constant (``TABLE_NAME``) does not count. The
    same expression on a removed line means the line moved, not that the query
    is new, so it produces no finding.
    """
    before = {ast.unparse(node) for node, _ in _built_strings(removed)}
    findings: list[AstFinding] = []
    seen: set[str] = set()
    for node, (text, how, names) in _built_strings(added):
        statement = SQL_STATEMENT.match(text)
        source = ast.unparse(node)
        if not statement or source in before or source in seen:
            continue
        seen.add(source)
        verb = statement.group(0).split()[0].upper()
        findings.append(AstFinding(
            "sql_built_from_strings",
            f"a SQL {verb} is built by {how} from {values_words(names)}, not bound as a parameter",
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
        + _find_sql_built_from_strings(added, removed)
    )
