"""Unit tests for the structural rules in ``src/domain/ast_security_rules.py``.

Each rule is tested twice: once on the change it exists to catch, and once on a
change that looks like it from a distance. A detector that cannot refuse is not
a detector, so the negative half of each pair is the half that matters.
"""
from src.domain import ast_security_rules
from src.domain.semantic_diff import UnifiedDiffParser


def _rule_ids(added, removed):
    return [finding.rule_id for finding in ast_security_rules.evaluate(added, removed)]


def _spoken(added, removed):
    return " ".join(finding.spoken for finding in ast_security_rules.evaluate(added, removed))


# --- Rule 1: an authorization comparison inverted ---------------------------

def test_an_inverted_authorization_comparison_is_found():
    ids = _rule_ids(['    if user.role != "admin":'], ['    if user.role == "admin":'])
    assert ids == ["authz_comparison_inverted"]


def test_the_finding_names_both_sides_of_the_inversion():
    spoken = _spoken(['    if user.role != "admin":'], ['    if user.role == "admin":'])
    assert "user.role == 'admin'" in spoken
    assert "user.role != 'admin'" in spoken


def test_a_membership_test_negated_on_an_entitlement_is_found():
    ids = _rule_ids(
        ["    if account.plan not in PAID_TIERS:"],
        ["    if account.plan in PAID_TIERS:"],
    )
    assert ids == ["authz_comparison_inverted"]


def test_an_inverted_comparison_outside_authorization_is_refused():
    """Arithmetic flips constantly. Only a decision about who may act counts."""
    assert _rule_ids(
        ["    if left.score <= right.score:"],
        ["    if left.score > right.score:"],
    ) == []


def test_changing_the_operands_rather_than_the_operator_is_refused():
    assert _rule_ids(['    if user.role == "owner":'], ['    if user.role == "admin":']) == []


def test_a_relaxed_bound_that_is_not_an_inversion_is_refused():
    assert _rule_ids(
        ["    if attempts <= MAX_RETRIES:"],
        ["    if attempts < MAX_RETRIES:"],
    ) == []


# --- Rule 2: a cross-origin policy widened ----------------------------------

def test_a_wildcard_cors_keyword_argument_is_found():
    ids = _rule_ids(['app.add_middleware(CORSMiddleware, allow_origins=["*"])'], [])
    assert ids == ["permissive_cors_origin"]


def test_a_wildcard_response_header_assignment_is_found():
    ids = _rule_ids(['    response.headers["Access-Control-Allow-Origin"] = "*"'], [])
    assert ids == ["permissive_cors_origin"]


def test_a_wildcard_origin_in_a_dictionary_literal_is_found():
    ids = _rule_ids(['HEADERS = {"Access-Control-Allow-Origin": "*"}'], [])
    assert ids == ["permissive_cors_origin"]


def test_narrowing_an_origin_to_one_host_is_refused():
    """The wildcard is on the removed side. Removing it is the fix, not the bug."""
    assert _rule_ids(
        ['app.add_middleware(CORSMiddleware, allow_origins=["https://console.example.com"])'],
        ['app.add_middleware(CORSMiddleware, allow_origins=["*"])'],
    ) == []


def test_a_wildcard_that_is_not_an_origin_is_refused():
    assert _rule_ids(['    glob_pattern = "*"'], []) == []


def test_an_argument_line_is_described_as_an_assignment_not_a_tuple():
    """The comma that separated the argument from its neighbour is not content.

    ``CORSMiddleware`` is configured over several lines, so the line that
    changes reaches the patch as ``allow_origins=["*"],``. Parsed with the comma
    left on, that is a one-element tuple and the sentence a blind reviewer hears
    reads ``allow_origins = (['*'],)``: true of the fragment and false of the
    code. This pins the reading of the line, not only the rule that fires on it.
    """
    spoken = _spoken(['    allow_origins=["*"],'], ['    allow_origins=["https://console.internal"],'])
    assert "allow_origins = ['*']" in spoken
    assert "(['*'],)" not in spoken


def test_dropping_the_comma_does_not_invent_a_finding_from_an_empty_line():
    assert ast_security_rules.parse_fragment(",") is None
    assert ast_security_rules.parse_fragment("   ,  ") is None


# --- Rule 3: a verification call removed ------------------------------------

def test_a_removed_signature_check_is_found():
    ids = _rule_ids([], ['    verify_signature(request.body, request.headers["x-sig"])'])
    assert ids == ["security_call_removed"]


def test_the_finding_names_the_deleted_call_rather_than_a_keyword():
    spoken = _spoken([], ['    verify_signature(body, sig)'])
    assert "verify_signature(body, sig)" in spoken
    assert "was removed" in spoken


def test_a_removed_authenticate_call_is_found():
    assert _rule_ids(["    return handler(request)"], ["    authenticate(request)"]) == [
        "security_call_removed"
    ]


def test_a_verification_call_still_present_after_the_change_is_refused():
    """Moving a check into a helper is a refactor, not a deletion."""
    assert _rule_ids(
        ["    guard(body, sig)", "def guard(body, sig):", "    verify_signature(body, sig)"],
        ["    verify_signature(body, sig)"],
    ) == []


def test_a_removed_verb_without_a_security_object_is_refused():
    """``verify_email_format`` checks a string shape, not a credential."""
    assert _rule_ids(["    return create_user(payload)"], ["    verify_email_format(payload.email)"]) == []
    assert _rule_ids(["    return job.result"], ["    check_status(job)"]) == []


# --- The harness ------------------------------------------------------------

def test_a_line_that_is_not_python_produces_no_finding():
    assert ast_security_rules.parse_fragment("<<<<<<< HEAD") is None
    assert ast_security_rules.parse_fragment("") is None
    assert _rule_ids(['{"Action": "*",'], ['{"Action": "s3:GetObject",']) == []


def test_indented_and_block_opening_fragments_still_parse():
    assert ast_security_rules.parse_fragment('    if user.role == "admin":') is not None
    assert ast_security_rules.parse_fragment("        return True") is not None


def test_rules_reach_the_parser_and_reword_the_finding():
    """The whole point of the rules is what a listener finally hears."""
    patch = (
        "diff --git a/src/api/permissions.py b/src/api/permissions.py\n"
        "--- a/src/api/permissions.py\n"
        "+++ b/src/api/permissions.py\n"
        "@@ -1,3 +1,3 @@\n"
        '-    if user.role == "admin":\n'
        '+    if user.role != "admin":\n'
    )
    section = UnifiedDiffParser.parse_patch(patch)[0]
    assert "authz_comparison_inverted" in section.security_flags
    assert any("inverted" in finding for finding in section.security_findings)
