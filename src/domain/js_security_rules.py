"""The three structural security rules, for JavaScript and TypeScript lines.

``ast_security_rules`` reads a changed line as a Python syntax tree. A line of
JavaScript or TypeScript is not Python, so that module either refuses it or,
worse, parses a fragment that happens to be valid Python. This module answers
the same three questions for ``.js``, ``.jsx``, ``.mjs``, ``.cjs``, ``.ts``,
``.tsx``, ``.mts`` and ``.cts`` files, with the same rule ids and the same kind
of spoken sentence:

* ``authz_comparison_inverted``  an operator flipped in a comparison that
  decides what a user, session or account may do
* ``permissive_cors_origin``     a cross-origin policy set to any origin, to
  ``true`` (which the ``cors`` package reads as "reflect the caller"), or to the
  request's own ``Origin`` header
* ``security_call_removed``      a verification call deleted and not called
  again anywhere in the file's added lines

and, written after the held-out set in ``tests/fixtures/diff_corpus_classic.py``
was committed, the classic families an independent review found the engine
silent on:

* ``sql_built_from_strings``     a SQL statement built by ``+`` or by an
  untagged template literal from a value that is not a constant
* ``tls_verification_disabled``  ``rejectUnauthorized`` or ``strictSSL`` set to
  false, or ``NODE_TLS_REJECT_UNAUTHORIZED`` set to 0

These are token rules, not a full parse. Each changed line is split into
JavaScript tokens (strings, template literals, numbers, names, operators and
punctuation), and the rules read patterns in that token stream. No parser
package is used, so the product gains no dependency. The cost is stated: a
statement spread over several lines is read one line at a time, and a
construct the token patterns do not describe produces no finding rather than a
guess.

Tuning record. The two choices below were made against the training half of
``tests/fixtures/diff_corpus_js_ts.py`` only:

* A flipped comparison counts only when it reads an authorization attribute of
  a principal (``user``, ``session``, ``account``, ``member`` ...) or compares
  against a privileged value (``admin``, ``owner`` ...). The training case that
  forced this is a chat renderer that flips ``message.role === 'assistant'``:
  ``role`` is an authorization word, but a chat message is not a principal.
* ``origin: true`` and a value read from the request's ``Origin`` header count
  as permissive, because both accept whichever site is calling.
"""
import re

from src.domain.ast_security_rules import (
    AUTHORIZATION_TERMS,
    SQL_STATEMENT,
    AstFinding,
    _ORIGIN_TARGETS,
    _WILDCARD_ORIGINS,
    _is_security_call,
    values_words,
)

#: File extensions these rules own. Every other file keeps the Python rules.
JS_TS_EXTENSIONS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")

_TOKEN = re.compile(
    r"""
    (?P<ws>\s+)
    |(?P<comment>//.*$|/\*.*?(\*/|$))
    |(?P<str>'(?:\\.|[^'\\])*'?|"(?:\\.|[^"\\])*"?|`(?:\\.|[^`\\])*`?)
    |(?P<num>\d[\w.]*)
    |(?P<name>[A-Za-z_$][\w$]*)
    |(?P<op>===|!==|==|!=|<=|>=|=>|&&|\|\||\?\?|\?\.|\.\.\.|[-+*/%<>=!?:.,;(){}\[\]&|^~@#])
    """,
    re.VERBOSE,
)

#: JavaScript comparison operators, named as the Python rule names them, so
#: the inverse table below is the same one the Python rule uses.
_COMPARISON = {
    "===": "Eq", "==": "Eq", "!==": "NotEq", "!=": "NotEq",
    "<": "Lt", ">=": "GtE", ">": "Gt", "<=": "LtE",
}
_INVERSE = {
    "Eq": "NotEq", "NotEq": "Eq",
    "Lt": "GtE", "GtE": "Lt",
    "Gt": "LtE", "LtE": "Gt",
}

#: Who an authorization decision is about. A flipped ``role`` check on a chat
#: message or an ARIA element is not a decision about who may act.
_PRINCIPAL = re.compile(
    r"(user|session|account|member|principal|actor|identity|viewer|caller|"
    r"customer|tenant|claims|currentuser|req\.auth)",
    re.IGNORECASE,
)

#: Values that name a privileged role on their own.
_PRIVILEGED_VALUE = re.compile(r"(admin|owner|superuser|staff|root|moderator)", re.IGNORECASE)

#: An expression that reads the calling site's own Origin header.
_REFLECTED_ORIGIN = re.compile(
    r"(headers\.origin|headers\[['\"]origin['\"]\]|\.get\(['\"]origin['\"]\)|"
    r"\.header\(['\"]origin['\"]\)|\.headers\.get\(['\"]origin['\"]\))",
    re.IGNORECASE,
)

#: Names that precede a parenthesis without calling anything.
_NOT_CALLS = {"if", "for", "while", "switch", "catch", "function", "return", "typeof", "with"}

_ALLOW_ORIGIN_HEADER = "access-control-allow-origin"


def tokenize(line: str) -> list[tuple[str, str]]:
    """(kind, text) for every token of one line, comments and spaces dropped."""
    tokens: list[tuple[str, str]] = []
    position = 0
    while position < len(line):
        match = _TOKEN.match(line, position)
        if match is None:
            position += 1
            continue
        kind = match.lastgroup or "op"
        if kind not in ("ws", "comment"):
            tokens.append((kind, match.group(0)))
        position = match.end()
    return tokens


def _string_value(text: str) -> str:
    """The contents of a string or template literal token."""
    if len(text) >= 2 and text[0] in "'\"`" and text[-1] == text[0]:
        return text[1:-1]
    return text.strip("'\"`")


def _render(tokens: list[tuple[str, str]]) -> str:
    """Tokens back to readable source: strings in single quotes, commas spaced."""
    parts: list[str] = []
    for kind, text in tokens:
        if kind == "str" and text[:1] in "'\"":
            text = "'" + _string_value(text) + "'"
        if text == ",":
            parts.append(", ")
        elif text in _COMPARISON or text in ("=", ":", "=>", "&&", "||", "??"):
            parts.append(f" {text} ")
        elif kind == "name" and parts and parts[-1] and (parts[-1][-1].isalnum() or parts[-1][-1] in "_$"):
            parts.append(" " + text)
        else:
            parts.append(text)
    return "".join(parts).replace(" :", ":").strip()


def _matching(tokens: list[tuple[str, str]], index: int, step: int) -> int:
    """Index of the bracket that balances the one at ``index``, or -1."""
    pairs = {"(": ")", "[": "]", "{": "}"}
    closing = {v: k for k, v in pairs.items()}
    opener = tokens[index][1]
    target = pairs.get(opener) if step > 0 else closing.get(opener)
    depth = 0
    position = index
    while 0 <= position < len(tokens):
        text = tokens[position][1]
        if text == opener:
            depth += 1
        elif text == target:
            depth -= 1
            if depth == 0:
                return position
        position += step
    return -1


def _operand_left(tokens, index) -> list[tuple[str, str]]:
    """The member chain, call or literal immediately left of ``index``."""
    start = index
    position = index - 1
    while position >= 0:
        kind, text = tokens[position]
        if text in (")", "]"):
            opening = _matching(tokens, position, -1)
            if opening < 0:
                break
            position = opening - 1
            start = opening
            continue
        if kind in ("name", "num", "str") and text not in _NOT_CALLS and text not in ("return", "await", "new"):
            start = position
            position -= 1
            if position >= 0 and tokens[position][1] in (".", "?."):
                start = position
                position -= 1
                continue
            break
        break
    if start < index and tokens[start][1] in (".", "?."):
        start += 1
    return tokens[start:index]


def _operand_right(tokens, index) -> list[tuple[str, str]]:
    """The literal, member chain or call immediately right of ``index``."""
    position = index + 1
    start = position
    if position < len(tokens) and tokens[position][1] in ("-", "!"):
        position += 1
    if position >= len(tokens) or tokens[position][0] not in ("name", "num", "str"):
        return tokens[start:position]
    position += 1
    while position < len(tokens):
        text = tokens[position][1]
        if text in (".", "?.") and position + 1 < len(tokens) and tokens[position + 1][0] == "name":
            position += 2
        elif text in ("(", "["):
            closing = _matching(tokens, position, 1)
            if closing < 0:
                break
            position = closing + 1
        else:
            break
    return tokens[start:position]


def _comparisons(line: str) -> list[tuple[str, str, str, str]]:
    """(left, operator name, right, readable source) for each comparison."""
    tokens = tokenize(line)
    found = []
    for index, (kind, text) in enumerate(tokens):
        if kind != "op" or text not in _COMPARISON:
            continue
        left = _operand_left(tokens, index)
        right = _operand_right(tokens, index)
        if not left or not right:
            continue
        left_text, right_text = _render(left), _render(right)
        found.append((left_text, _COMPARISON[text], right_text, f"{left_text} {text} {right_text}"))
    return found


def _decides_authorization(left: str, right: str) -> bool:
    """An authorization attribute of a principal, or a privileged value."""
    text = f"{left} {right}"
    if not AUTHORIZATION_TERMS.search(text):
        return False
    return bool(_PRINCIPAL.search(text) or _PRIVILEGED_VALUE.search(right) or _PRIVILEGED_VALUE.search(left))


def _find_inverted_authorization(added: list[str], removed: list[str]) -> list[AstFinding]:
    findings: list[AstFinding] = []
    seen: set[str] = set()
    before = [item for line in removed for item in _comparisons(line)]
    for line in added:
        for left, operator, right, source in _comparisons(line):
            for old_left, old_operator, old_right, old_source in before:
                if (left, right) != (old_left, old_right):
                    continue
                if _INVERSE.get(old_operator) != operator:
                    continue
                if not _decides_authorization(left, right) or source in seen:
                    continue
                seen.add(source)
                findings.append(AstFinding(
                    "authz_comparison_inverted",
                    f"an authorization comparison was inverted: {old_source} became {source}",
                ))
    return findings


def _value_until(tokens, start: int, stops: tuple[str, ...]) -> list[tuple[str, str]]:
    """Tokens from ``start`` to the first depth-zero stop token."""
    position = start
    while position < len(tokens):
        text = tokens[position][1]
        if text in ("(", "[", "{"):
            closing = _matching(tokens, position, 1)
            if closing < 0:
                return tokens[start:]
            position = closing + 1
            continue
        if text in stops:
            break
        position += 1
    return tokens[start:position]


def _permissive(value: list[tuple[str, str]], key_is_origin: bool) -> str | None:
    """Why this origin value accepts any site, or None."""
    if not value:
        return None
    strings = {_string_value(text).strip() for kind, text in value if kind == "str"}
    if strings & _WILDCARD_ORIGINS:
        return "widened to accept any origin"
    if key_is_origin and len(value) == 1 and value[0][1] == "true":
        return "set to reflect whichever origin calls"
    if _REFLECTED_ORIGIN.search("".join(text for _, text in value)):
        return "set to reflect whichever origin calls"
    return None


def _is_origin_target(text: str) -> bool:
    return bool(_ORIGIN_TARGETS.search(text))


def _find_permissive_cors(added: list[str]) -> list[AstFinding]:
    findings: list[AstFinding] = []
    seen: set[str] = set()

    def report(label: str, why: str) -> None:
        if label in seen:
            return
        seen.add(label)
        findings.append(AstFinding(
            "permissive_cors_origin",
            f"a cross-origin policy was {why}: {label}",
        ))

    for line in added:
        tokens = tokenize(line)
        for index, (kind, text) in enumerate(tokens):
            nxt = tokens[index + 1][1] if index + 1 < len(tokens) else ""
            key = _string_value(text) if kind == "str" else text
            # An object key: ``origin: '*'``, ``'Access-Control-Allow-Origin': '*'``.
            if kind in ("name", "str") and nxt == ":":
                key_is_origin = key == "origin" or _is_origin_target(key)
                if not key_is_origin:
                    continue
                value = _value_until(tokens, index + 2, (",", "}", ";", ")"))
                why = _permissive(value, key_is_origin=True)
                if why:
                    report(f"{key}: {_render(value)}", why)
            # A header call: ``res.setHeader('Access-Control-Allow-Origin', '*')``.
            elif kind == "str" and key.lower() == _ALLOW_ORIGIN_HEADER and nxt == ",":
                value = _value_until(tokens, index + 2, (")", ",", ";"))
                why = _permissive(value, key_is_origin=True)
                if why:
                    report(f"{key}, {_render(value)}", why)
            # An assignment: ``headers['Access-Control-Allow-Origin'] = '*'``.
            elif nxt == "=" and (
                (kind == "name" and _is_origin_target(key))
                or (text == "]" and any(_is_origin_target(_string_value(t)) for k, t in tokens[:index] if k == "str"))
            ):
                target = key if kind == "name" else next(
                    _string_value(t) for k, t in tokens[:index] if k == "str" and _is_origin_target(_string_value(t))
                )
                value = _value_until(tokens, index + 2, (";",))
                why = _permissive(value, key_is_origin=False)
                if why:
                    report(f"{target} = {_render(value)}", why)
    return findings


def _snake(name: str) -> str:
    """``verifyWebhookSignature`` as ``verify_webhook_signature``."""
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name).lower()


def _called_names(lines: list[str]) -> dict[str, str]:
    """Every called name in these lines, mapped to the call as written."""
    names: dict[str, str] = {}
    for line in lines:
        tokens = tokenize(line)
        for index, (kind, text) in enumerate(tokens):
            if kind != "name" or text in _NOT_CALLS:
                continue
            following = index + 1
            if following < len(tokens) and tokens[following][1] == "?.":
                following += 1
            if following >= len(tokens) or tokens[following][1] != "(":
                continue
            if index > 0 and tokens[index - 1][1] == "function":
                continue
            closing = _matching(tokens, following, 1)
            start = index
            while start >= 2 and tokens[start - 1][1] in (".", "?.") and tokens[start - 2][0] == "name":
                start -= 2
            end = closing + 1 if closing > 0 else len(tokens)
            names.setdefault(text, _render(tokens[start:end]))
    return names


def _find_removed_security_calls(added: list[str], removed: list[str]) -> list[AstFinding]:
    still_called = set(_called_names(added))
    findings = []
    for name, source in _called_names(removed).items():
        if name in still_called or not _is_security_call(_snake(name)):
            continue
        findings.append(AstFinding(
            "security_call_removed",
            f"the call {source} was removed and nothing replaced it",
        ))
    return findings


# --- Classic families: values built into a statement -----------------------

#: Names that can sit right before a template literal without tagging it.
_UNTAGGED_BEFORE = {"return", "await", "yield", "typeof", "case", "throw", "new", "in", "of", "else", "do",
                    "void", "delete", "instanceof"}

_INTERPOLATION = re.compile(r"\$\{([^}]*)\}")


def _constant_operand(operand: list[tuple[str, str]]) -> bool:
    """A literal, or a name written as a constant (``TABLE_NAME``, ``cfg.TABLE``)."""
    if all(kind in ("str", "num") for kind, _ in operand):
        return not any(kind == "str" and "${" in text for kind, text in operand)
    names = [text for kind, text in operand if kind == "name"]
    return bool(names) and len(operand) in (1, 3) and names[-1].isupper() and not any(
        text in ("(", "[") for _, text in operand
    )


def _is_tagged(tokens: list[tuple[str, str]], index: int) -> bool:
    """Whether the template literal at ``index`` is a tagged template.

    A tag hands the literal's parts to a function, which is how drivers such as
    ``sql`` tags bind each interpolated value as a parameter; the string is
    never assembled by the program itself.
    """
    if index == 0:
        return False
    kind, text = tokens[index - 1]
    return kind == "name" and text not in _UNTAGGED_BEFORE


def built_strings(line: str) -> list[tuple[str, str, list[str], str]]:
    """(text, how, values, source) for each string built from a non-constant.

    Two shapes are read on one line: a template literal with ``${...}`` that
    is not tagged, and a ``+`` chain holding at least one string literal. The
    text has each spliced value replaced by a placeholder so its shape can be
    read, and values named as constants (``TABLE_NAME``) do not count.
    """
    tokens = tokenize(line)
    found: list[tuple[str, str, list[str], str]] = []
    consumed: set[int] = set()
    for index, (kind, text) in enumerate(tokens):
        if index in consumed:
            continue
        if kind == "str" and text.startswith("`") and "${" in text and not _is_tagged(tokens, index):
            if index + 1 < len(tokens) and tokens[index + 1][1] == "+":
                pass  # read below as the head of a concatenation
            elif index > 0 and tokens[index - 1][1] == "+":
                continue
            else:
                body = _string_value(text)
                values = [v.strip() for v in _INTERPOLATION.findall(body)
                          if v.strip() and not v.strip().isupper()]
                if values:
                    found.append((_INTERPOLATION.sub("value", body), "a template literal",
                                  list(dict.fromkeys(values)), text))
                continue
        # The head of a ``+`` chain: an operand not itself preceded by ``+``.
        if index > 0 and tokens[index - 1][1] == "+":
            continue
        if kind not in ("str", "name", "num"):
            continue
        head = _operand_right(tokens, index - 1) if index > 0 else _operand_right([("op", "(")] + tokens, 0)
        if not head:
            continue
        pieces = [head]
        position = index + len(head)
        while position < len(tokens) and tokens[position][1] == "+":
            operand = _operand_right(tokens, position)
            if not operand:
                break
            pieces.append(operand)
            position += 1 + len(operand)
        if len(pieces) < 2 or not any(len(p) == 1 and p[0][0] == "str" for p in pieces):
            continue
        consumed.update(range(index, position))
        parts, values = [], []
        for piece in pieces:
            if len(piece) == 1 and piece[0][0] == "str":
                body = _string_value(piece[0][1])
                parts.append(_INTERPOLATION.sub("value", body))
                values.extend(v.strip() for v in _INTERPOLATION.findall(body) if v.strip() and not v.strip().isupper())
            else:
                parts.append("value")
                if not _constant_operand(piece):
                    values.append(_render(piece))
        if values:
            found.append(("".join(parts), "string concatenation", list(dict.fromkeys(values)),
                          _render(tokens[index:position])))
    return found


def _find_sql_built_from_strings(added: list[str], removed: list[str]) -> list[AstFinding]:
    """A SQL statement assembled from a value rather than bound to a parameter."""
    before = {source for line in removed for *_, source in built_strings(line)}
    findings: list[AstFinding] = []
    seen: set[str] = set()
    for line in added:
        for text, how, values, source in built_strings(line):
            statement = SQL_STATEMENT.match(text)
            if not statement or source in before or source in seen:
                continue
            seen.add(source)
            verb = statement.group(0).split()[0].upper()
            findings.append(AstFinding(
                "sql_built_from_strings",
                f"a SQL {verb} is built by {how} from {values_words(values)}, not bound as a parameter",
            ))
    return findings


# --- Classic family: TLS certificate checks turned off ----------------------

#: Options that switch certificate checking off when set to ``false``.
_TLS_OPTIONS = {"rejectUnauthorized", "strictSSL"}

#: The Node.js variable that switches certificate checking off process-wide
#: when set to ``0``.
_NODE_TLS_SWITCH = "NODE_TLS_REJECT_UNAUTHORIZED"


def _find_tls_verification_disabled(added: list[str], removed: list[str]) -> list[AstFinding]:
    """Certificate checking switched off for outbound connections.

    Read as ``rejectUnauthorized`` or ``strictSSL`` set to ``false`` (an object
    key or an assignment) and ``NODE_TLS_REJECT_UNAUTHORIZED`` set to ``0``
    (assigned, or given as an environment key). A comparison such as
    ``=== '0'`` reads the variable and is not a finding.
    """
    def collect(lines: list[str]) -> list[str]:
        found: list[str] = []
        for line in lines:
            tokens = tokenize(line)
            for index, (kind, text) in enumerate(tokens):
                key = _string_value(text) if kind == "str" else text
                if kind not in ("name", "str"):
                    continue
                position = index + 1
                if position < len(tokens) and tokens[position][1] == "]":
                    position += 1
                if position + 1 >= len(tokens) or tokens[position][1] not in (":", "="):
                    continue
                value = tokens[position + 1]
                if key in _TLS_OPTIONS and value[1] == "false":
                    source = f"{key}{' = ' if tokens[position][1] == '=' else ': '}false"
                elif key == _NODE_TLS_SWITCH and _string_value(value[1]) == "0":
                    source = f"{key}{' = ' if tokens[position][1] == '=' else ': '}{_render([value])}"
                else:
                    continue
                if source not in found:
                    found.append(source)
        return found

    before = set(collect(removed))
    return [
        AstFinding("tls_verification_disabled", f"TLS certificate checks were turned off: {source}")
        for source in collect(added)
        if source not in before
    ]


def evaluate(added_lines: list[str], removed_lines: list[str]) -> list[AstFinding]:
    """Run every JavaScript and TypeScript rule over one file's changed lines."""
    return (
        _find_inverted_authorization(added_lines, removed_lines)
        + _find_permissive_cors(added_lines)
        + _find_removed_security_calls(added_lines, removed_lines)
        + _find_sql_built_from_strings(added_lines, removed_lines)
        + _find_tls_verification_disabled(added_lines, removed_lines)
    )
