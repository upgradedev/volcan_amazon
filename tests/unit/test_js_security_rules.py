"""Unit tests for the JavaScript and TypeScript rules in ``js_security_rules``.

Each rule is tested on the change it exists to catch and on a change that looks
like it from a distance. The lines here are written for these tests; none is
copied from the held-out half of ``tests/fixtures/diff_corpus_js_ts.py``.
"""
from src.domain import js_security_rules
from src.domain.semantic_diff import UnifiedDiffParser


def _ids(added, removed=()):
    return [f.rule_id for f in js_security_rules.evaluate(list(added), list(removed))]


def _spoken(added, removed=()):
    return " ".join(f.spoken for f in js_security_rules.evaluate(list(added), list(removed)))


# --- tokens -------------------------------------------------------------------

def test_strings_and_comments_are_single_tokens():
    tokens = js_security_rules.tokenize("if (a === 'x // y') { // a comment")
    assert ("str", "'x // y'") in tokens
    assert all(kind != "comment" for kind, _ in tokens)
    assert tokens[-1] == ("op", "{")


# --- Rule 1: an authorization comparison inverted ----------------------------

def test_an_inverted_owner_check_is_found_and_names_both_sides():
    spoken = _spoken(["  if (doc.ownerId !== currentUser.id) {"], ["  if (doc.ownerId === currentUser.id) {"])
    assert "doc.ownerId === currentUser.id" in spoken
    assert "doc.ownerId !== currentUser.id" in spoken


def test_an_inverted_privileged_value_check_is_found_without_a_principal():
    assert _ids(["if (ctx.role != 'superuser') {"], ["if (ctx.role == 'superuser') {"]) == [
        "authz_comparison_inverted"
    ]


def test_a_role_word_on_something_that_is_not_a_principal_is_refused():
    assert _ids(["if (node.role !== 'listitem') {"], ["if (node.role === 'listitem') {"]) == []


def test_arithmetic_flips_are_refused():
    assert _ids(["if (total <= limit) {"], ["if (total > limit) {"]) == []


def test_changing_the_value_rather_than_the_operator_is_refused():
    assert _ids(["if (user.role === 'editor') {"], ["if (user.role === 'admin') {"]) == []


def test_a_relaxed_bound_is_not_an_inversion():
    assert _ids(["if (user.plan.seats <= used) {"], ["if (user.plan.seats < used) {"]) == []


# --- Rule 2: a cross-origin policy widened ------------------------------------

def test_a_wildcard_in_an_origin_list_is_found():
    assert _ids(["app.use(cors({ origin: ['https://a.example.com', '*'] }));"]) == ["permissive_cors_origin"]


def test_an_assignment_to_the_allow_origin_header_is_found():
    spoken = _spoken(["  headers['Access-Control-Allow-Origin'] = \"*\";"])
    assert "Access-Control-Allow-Origin = '*'" in spoken


def test_origin_true_is_read_as_reflecting_the_caller():
    assert "reflect whichever origin calls" in _spoken(["  origin: true,"])


def test_a_reflected_origin_header_is_found():
    assert _ids(["res.set('Access-Control-Allow-Origin', req.get('origin'));"]) == ["permissive_cors_origin"]


def test_a_named_origin_is_refused():
    assert _ids(["app.use(cors({ origin: 'https://console.example.com' }));"]) == []


def test_an_origin_that_is_a_point_is_refused():
    assert _ids(["const origin = { x: 0, y: 0 };"]) == []


def test_origin_false_is_refused():
    assert _ids(["  origin: false,"]) == []


# --- Rule 3: a verification call removed --------------------------------------

def test_a_camel_case_signature_check_removed_is_found():
    spoken = _spoken([], ["  await verifyStripeSignature(req.body, header);"])
    assert spoken == "the call verifyStripeSignature(req.body, header) was removed and nothing replaced it"


def test_a_member_call_removed_is_found_and_keeps_its_receiver():
    assert "passport.authenticate('jwt')" in _spoken([], ["  passport.authenticate('jwt');"])


def test_a_call_moved_rather_than_removed_is_refused():
    assert _ids(
        ["  return withGuard(body);", "function withGuard(b) { checkSignature(b); }"],
        ["  checkSignature(body);"],
    ) == []


def test_a_formatting_helper_removed_is_refused():
    assert _ids([], ["  validatePhoneFormat(input.phone);"]) == []


def test_a_function_declaration_removed_is_not_a_removed_call():
    assert _ids([], ["function verifySignature(body, sig) {"]) == []


# --- Classic family: a SQL statement built from a value ---------------------

def test_a_concatenated_query_is_found_and_names_the_value():
    assert _spoken(['  return db.query("SELECT * FROM t WHERE id = " + req.params.id);']) == (
        "a SQL SELECT is built by string concatenation from req.params.id, not bound as a parameter")


def test_an_untagged_template_literal_query_is_found():
    assert _ids(["  return db.query(`UPDATE t SET n = ${n}`);"]) == ["sql_built_from_strings"]
    assert _ids(["  x = `DELETE FROM carts WHERE id = ` + cart.id;"]) == ["sql_built_from_strings"]


def test_a_tagged_template_is_refused_because_the_tag_binds_the_values():
    assert _ids(["  return sql`SELECT name FROM pets WHERE owner = ${ownerId}`;"]) == []


def test_constant_pieces_and_plain_text_are_refused():
    assert _ids(['  const q = "SELECT a, b " + "FROM c";']) == []
    assert _ids(['  const q = "SELECT * FROM " + TABLE_NAME;']) == []
    assert _ids(["  const s = `hello ${name}`;"]) == []


def test_a_concatenated_query_that_only_moved_is_refused():
    line = '  return db.query("SELECT * FROM t WHERE id = " + req.params.id);'
    assert _ids([line], [line]) == []


# --- Classic family: TLS certificate checks turned off ----------------------

def test_an_agent_that_accepts_any_certificate_is_found():
    assert _spoken(["  const a = new https.Agent({ rejectUnauthorized: false });"]) == (
        "TLS certificate checks were turned off: rejectUnauthorized: false")
    assert _ids(["  opts.rejectUnauthorized = false;"]) == ["tls_verification_disabled"]
    assert _ids(["  request({ uri, strictSSL: false });"]) == ["tls_verification_disabled"]


def test_the_process_wide_switch_is_found_when_set_and_refused_when_read():
    assert _ids(['process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";']) == ["tls_verification_disabled"]
    assert _ids(["  env: { NODE_TLS_REJECT_UNAUTHORIZED: 0 },"]) == ["tls_verification_disabled"]
    assert _ids(['  if (process.env.NODE_TLS_REJECT_UNAUTHORIZED === "0") warn();']) == []


def test_certificate_checks_left_on_are_refused():
    assert _ids(["  const a = new https.Agent({ rejectUnauthorized: true });"]) == []


# --- dispatch -------------------------------------------------------------------

def _patch(path, body):
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1,2 +1,2 @@\n{body}\n"


def test_typescript_files_are_read_by_the_token_rules():
    sections = UnifiedDiffParser.parse_patch(_patch(
        "src/guard.tsx", "-  if (user.isAdmin === true) {\n+  if (user.isAdmin !== true) {"))
    assert sections[0].security_flags[0] == "authz_comparison_inverted"


def test_python_files_keep_the_python_rules():
    sections = UnifiedDiffParser.parse_patch(_patch(
        "src/guard.py", '-    if user.role == "admin":\n+    if user.role != "admin":'))
    assert sections[0].security_flags[0] == "authz_comparison_inverted"
    assert "user.role == 'admin' became user.role != 'admin'" in sections[0].security_findings[0]
