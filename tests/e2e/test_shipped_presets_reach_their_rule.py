"""The demo's own buttons must reach the rules the demo exists to show.

This is the test that pins the thing that drifted. Until 2026-09-08 the three
preset patches in ``docs/index.html`` triggered no syntax-tree rule at all: the
first removed a hardcoded secret, which is a security *improvement* and which
the server answered from the keyword matcher, and the other two returned
"Changes are mostly business logic" with no finding. The differentiator was
unreachable from the product's own buttons, so the first press showed the
weakest output the product can produce.

Nothing here parses a mock. Each preset is lifted out of the shipped page,
handed to the production parser, and compared against two things:

1. the rule id it is supposed to trigger, and
2. the ``title`` of its own chip, which must quote the sentence the server
   actually produced, word for word.

A preset that stops reaching its rule fails. A chip whose label promises a
sentence the server no longer says fails. And a rule that ships without a
preset fails, because the last assertion reads the rule ids straight out of the
domain module rather than from a list kept by hand here.
"""
import ast
import os
import re

from src.domain.semantic_diff import UnifiedDiffParser

INDEX_PATH = os.path.join(os.path.dirname(__file__), "../../docs/index.html")
RULES_PATH = os.path.join(
    os.path.dirname(__file__), "../../src/domain/ast_security_rules.py"
)

#: The rule each shipped preset must trigger, and ``None`` for the control.
#: The control is not decoration: a detector that cannot stay quiet is not a
#: detector, and the page has to be able to show that too.
EXPECTED_RULE = {
    1: "authz_comparison_inverted",
    2: "permissive_cors_origin",
    3: "security_call_removed",
    4: None,
}


def read_html() -> str:
    with open(INDEX_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def _decode_js_string(literal: str) -> str:
    """The body of a double-quoted JavaScript string literal, unescaped."""
    escapes = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}
    body, out, index = literal[1:-1], [], 0
    while index < len(body):
        char = body[index]
        if char == "\\" and index + 1 < len(body):
            out.append(escapes.get(body[index + 1], body[index + 1]))
            index += 2
        else:
            out.append(char)
            index += 1
    return "".join(out)


def shipped_presets() -> dict[int, str]:
    """The ``PRESETS`` object of the page, as the patches it really holds."""
    html = read_html()
    block = re.search(r"var PRESETS = \{(.*?)\n    \};", html, flags=re.S)
    assert block, "the page no longer defines a PRESETS object"

    presets: dict[int, str] = {}
    for entry in re.finditer(
        r"(\d+):\s*((?:\"(?:[^\"\\]|\\.)*\"\s*\+?\s*)+)", block.group(1)
    ):
        pieces = re.findall(r"\"(?:[^\"\\]|\\.)*\"", entry.group(2))
        presets[int(entry.group(1))] = "".join(_decode_js_string(p) for p in pieces)
    return presets


def chip_titles() -> dict[int, str]:
    """The ``title`` of each preset chip: the promise the label makes."""
    html = read_html()
    titles: dict[int, str] = {}
    for match in re.finditer(
        r"<button\b[^>]*\bid=\"preset(\d+)\"[^>]*\btitle=\"([^\"]*)\"", html, flags=re.S
    ):
        titles[int(match.group(1))] = match.group(2)
    return titles


def findings_for(patch: str) -> tuple[list[str], list[str]]:
    """(rule ids, spoken sentences) the production parser returns for a patch."""
    sections = UnifiedDiffParser.parse_patch(patch)
    flags = [flag for section in sections for flag in section.security_flags]
    spoken = [text for section in sections for text in section.security_findings]
    return flags, spoken


def implemented_rule_ids() -> set[str]:
    """Every rule id the domain module can emit, read out of its own source.

    Reading the ids here rather than repeating them means a fourth rule added
    tomorrow without a preset to demonstrate it turns this file red.
    """
    with open(RULES_PATH, "r", encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    ids = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else None
        if name != "AstFinding" or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            ids.add(first.value)
    return ids


# --- the presets are the ones the page ships --------------------------------

def test_the_page_ships_one_preset_per_rule_plus_a_control():
    presets = shipped_presets()
    assert sorted(presets) == sorted(EXPECTED_RULE), (
        f"the page ships presets {sorted(presets)}, this test expects {sorted(EXPECTED_RULE)}"
    )
    for number, patch in presets.items():
        assert patch.startswith("diff --git "), f"preset {number} is not a unified patch"
        assert "@@" in patch, f"preset {number} carries no hunk header"


def test_every_preset_triggers_the_rule_its_label_promises():
    presets = shipped_presets()
    for number, expected in EXPECTED_RULE.items():
        flags, _ = findings_for(presets[number])
        if expected is None:
            assert flags == [], (
                f"preset {number} is the clean control and must raise nothing, raised {flags}"
            )
        else:
            assert flags == [expected], (
                f"preset {number} was supposed to trigger {expected}, produced {flags}"
            )


def test_every_chip_label_quotes_the_sentence_the_server_really_says():
    """The label and the rule cannot separate without this test going red."""
    presets, titles = shipped_presets(), chip_titles()
    assert sorted(titles) == sorted(EXPECTED_RULE), "a preset chip lost its title"

    for number, expected in EXPECTED_RULE.items():
        _, spoken = findings_for(presets[number])
        if expected is None:
            assert spoken == []
            assert "no finding" in titles[number].lower(), (
                "the control's label must say that finding nothing is the right answer"
            )
            continue
        assert len(spoken) == 1, f"preset {number} produced {len(spoken)} sentences"
        assert spoken[0] in titles[number], (
            f"chip {number} promises\n  {titles[number]}\nthe server says\n  {spoken[0]}"
        )


def test_the_control_still_produces_a_digest_rather_than_silence():
    """A benign patch is not an error. It is the refusal path, and it speaks."""
    sections = UnifiedDiffParser.parse_patch(shipped_presets()[4])
    assert sections, "the control patch parsed into no sections at all"
    assert sections[0].category.value == "BUSINESS_LOGIC"
    assert sections[0].added_count and sections[0].removed_count


def test_no_shipped_rule_is_left_without_a_preset_to_demonstrate_it():
    demonstrated = {rule for rule in EXPECTED_RULE.values() if rule is not None}
    assert demonstrated == implemented_rule_ids(), (
        f"rules with no preset: {sorted(implemented_rule_ids() - demonstrated)}; "
        f"presets naming a rule that no longer exists: {sorted(demonstrated - implemented_rule_ids())}"
    )


def test_the_first_preset_loaded_on_paint_is_a_security_finding():
    """The first press must not show the weakest thing the product can do."""
    html = read_html()
    assert "loadPreset(1);" in html, "the page no longer loads a preset on first paint"
    assert EXPECTED_RULE[1] is not None
    flags, _ = findings_for(shipped_presets()[1])
    assert flags == [EXPECTED_RULE[1]]
