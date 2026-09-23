"""Labelled unified-diff corpus used to measure security-flag detection.

Every entry carries a human label: ``expect_security_flag`` states whether a
reviewer would want Volcan to raise a security alert for that patch. The corpus
is the single source of truth for both ``scripts/benchmark_suite.py`` and
``tests/unit/test_security_detection_corpus.py``, so the published detection
rate and the assertion that guards it can never diverge.

The corpus is small, self-authored and hand-labelled by the same people who
wrote the parser. It measures behaviour on these fixtures only; it is not a
claim about real-world repositories, and a figure measured over fixtures its own
author chose is worth less than a figure measured over someone else's.

Two things push back on that. The adversarial block in each list was written to
defeat the substring matcher rather than to flatter it, and four positives are
kept in the corpus precisely because nothing here detects them. The published
recall is below 100% for that reason and names which fixtures it misses.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class LabelledDiff:
    fixture_id: str
    description: str
    expect_security_flag: bool
    raw_diff: str


def _patch(path: str, body: str) -> str:
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1,2 +1,4 @@\n{body}\n"


def _plain_patch(path: str, body: str) -> str:
    """The same patch as ``diff -u`` writes it, with no ``diff --git`` header.

    The README advertises a unified patch as the input, and ``diff -u`` is a
    unified patch. Fixtures in this shape keep the published figure honest about
    the format a reviewer is most likely to paste in.
    """
    return f"--- a/{path}\n+++ b/{path}\n@@ -1,2 +1,4 @@\n{body}\n"


POSITIVES: list[LabelledDiff] = [
    LabelledDiff(
        "pos-01", "Hardcoded secret replaced by KMS lookup", True,
        _patch("src/auth/service.py",
               '-        return token == "hardcoded_secret"\n'
               '+        kms_key = os.environ.get("KMS_KEY_ID")\n'
               "+        return verify_kms_token(token, kms_key)"),
    ),
    LabelledDiff(
        "pos-02", "JWT signature verification disabled", True,
        _patch("src/api/session.py",
               "-    payload = jwt.decode(raw, key, algorithms=['HS256'])\n"
               "+    payload = jwt.decode(raw, options={'verify_signature': False})"),
    ),
    LabelledDiff(
        "pos-03", "Password hashing weakened", True,
        _patch("src/users/passwords.py",
               "-    return bcrypt.hashpw(raw, bcrypt.gensalt(14))\n"
               "+    return hashlib.md5(raw).hexdigest()"),
    ),
    LabelledDiff(
        "pos-04", "Shell injection via subprocess shell=True", True,
        _patch("src/tools/runner.py",
               "-    subprocess.run(argv, check=True)\n"
               "+    subprocess.run(user_input, shell=True)"),
    ),
    LabelledDiff(
        "pos-05", "Untrusted eval of request body", True,
        _patch("src/api/calc.py",
               "-    result = safe_parse(expr)\n"
               "+    result = eval(expr)"),
    ),
    LabelledDiff(
        "pos-06", "Destructive SQL migration", True,
        _patch("migrations/0004_cleanup.sql",
               "+DROP TABLE audit_records;\n"
               "+DELETE FROM sessions WHERE 1=1;"),
    ),
    LabelledDiff(
        "pos-07", "Bearer token logged in plaintext", True,
        _patch("src/api/middleware.py",
               "+    logger.info('inbound bearer %s', request.headers['authorization'])"),
    ),
    LabelledDiff(
        "pos-08", "AES key rotation removed", True,
        _patch("src/crypto/vault.py",
               "-    cipher = AES.new(rotate_key(), AES.MODE_GCM)\n"
               "+    cipher = AES.new(STATIC_KEY, AES.MODE_GCM)"),
    ),
    LabelledDiff(
        "pos-09", "HMAC comparison made non-constant-time", True,
        _patch("src/webhooks/verify.py",
               "-    return hmac.compare_digest(expected, provided)\n"
               "+    return expected == provided"),
    ),
    LabelledDiff(
        "pos-10", "os.system call added to deploy path", True,
        _patch("src/deploy/release.py",
               "+    os.system('aws ecs update-service --force-new-deployment')"),
    ),
    LabelledDiff(
        "pos-11", "Auth decorator removed from admin route", True,
        _patch("src/api/admin.py",
               "-@requires_auth\n"
               " def purge_accounts():"),
    ),
    LabelledDiff(
        "pos-12", "Bulk UPDATE without predicate", True,
        _patch("src/db/repair.py",
               "+    cursor.execute(\"UPDATE users SET role = 'admin'\")"),
    ),
    # --- Adversarial cases, added 2026-09-08 -----------------------------
    # Each of these was written to defeat the substring matcher: the words on
    # both sides of the change are the same, so only a rule that reads the
    # syntax tree can tell what happened. The first three are the regressions
    # an end-customer review found in the field.
    LabelledDiff(
        "pos-13", "Authorization comparison inverted to != admin", True,
        _patch("src/api/permissions.py",
               '-    if user.role == "admin":\n'
               '+    if user.role != "admin":\n'
               "         return True"),
    ),
    LabelledDiff(
        "pos-14", "CORS origins widened to a wildcard", True,
        _patch("src/api/app.py",
               '-app.add_middleware(CORSMiddleware, allow_origins=["https://console.example.com"])\n'
               '+app.add_middleware(CORSMiddleware, allow_origins=["*"])'),
    ),
    LabelledDiff(
        "pos-15", "Webhook signature verification call deleted", True,
        _plain_patch("src/webhooks/handler.py",
                     '-    verify_signature(request.body, request.headers["x-signature"])\n'
                     "     return process(request.body)"),
    ),
    LabelledDiff(
        "pos-16", "Access-Control-Allow-Origin response header set to any site", True,
        _patch("src/api/middleware.py",
               '-    response.headers["Access-Control-Allow-Origin"] = settings.console_url\n'
               '+    response.headers["Access-Control-Allow-Origin"] = "*"'),
    ),
    LabelledDiff(
        "pos-17", "Paid-tier membership test negated", True,
        _plain_patch("src/billing/entitlements.py",
                     "-    if account.plan in PAID_TIERS:\n"
                     "+    if account.plan not in PAID_TIERS:\n"
                     "         return unlock(account)"),
    ),
    LabelledDiff(
        "pos-18", "authenticate() dropped from the request path", True,
        _patch("src/api/router.py",
               "-    authenticate(request)\n"
               "     return handler(request)"),
    ),
    # Regressions outside every rule this parser implements, kept in the corpus
    # on purpose. A corpus that only holds cases its own author already solved
    # measures nothing, so these were written from what a reviewer would want
    # flagged rather than from what the code can find. They are the reason the
    # published recall is below 100%, and the README names them.
    LabelledDiff(
        "pos-19", "Whole authorization guard block deleted", True,
        _patch("src/api/pages.py",
               "-    if not user.is_admin:\n"
               "-        raise Forbidden()\n"
               "     return render_admin_page()"),
    ),
    LabelledDiff(
        "pos-20", "Permission decorator removed from a billing route", True,
        _patch("src/api/billing.py",
               '-@requires_permission("billing:write")\n'
               " def issue_refund(order_id):"),
    ),
    LabelledDiff(
        "pos-21", "TLS certificate verification disabled on an outbound call", True,
        _plain_patch("src/clients/partner.py",
                     "-    response = requests.get(url, timeout=5)\n"
                     "+    response = requests.get(url, timeout=5, verify=False)"),
    ),
    LabelledDiff(
        "pos-22", "IAM policy action widened to every action", True,
        _patch("infra/bucket_policy.json",
               '-    "Action": "s3:GetObject",\n'
               '+    "Action": "*",'),
    ),
]

NEGATIVES: list[LabelledDiff] = [
    LabelledDiff(
        "neg-01", "New health route", False,
        _patch("src/routes/api.py",
               '+@router.get("/v1/health")\n'
               "+def health():\n"
               '+    return {"status": "ok"}'),
    ),
    LabelledDiff(
        "neg-02", "Null guard in parser", False,
        _patch("src/utils/parser.py",
               "-    return data.strip()\n"
               "+    if not data:\n"
               '+        return ""\n'
               "+    return data.strip()"),
    ),
    LabelledDiff(
        "neg-03", "Docstring wording", False,
        _patch("src/domain/report.py",
               '-    """Builds report."""\n'
               '+    """Build the spoken report for a single review turn."""'),
    ),
    LabelledDiff(
        "neg-04", "README typo", False,
        _patch("README.md",
               "-Volcan is a acessible forge.\n"
               "+Volcan is an accessible forge."),
    ),
    LabelledDiff(
        "neg-05", "Rename a loop variable", False,
        _patch("src/domain/loops.py",
               "-    for i in items:\n"
               "-        total += i\n"
               "+    for item in items:\n"
               "+        total += item"),
    ),
    LabelledDiff(
        "neg-06", "Widen a pagination limit", False,
        _patch("src/api/list_view.py",
               "-    PAGE_SIZE = 25\n"
               "+    PAGE_SIZE = 50"),
    ),
    LabelledDiff(
        "neg-07", "Add a dataclass field", False,
        _patch("src/domain/profile.py",
               "+    display_name: str = ''"),
    ),
    LabelledDiff(
        "neg-08", "Reformat an import block", False,
        _patch("src/domain/imports.py",
               "-import os, sys\n"
               "+import os\n"
               "+import sys"),
    ),
    LabelledDiff(
        "neg-09", "Adjust a log level", False,
        _patch("src/infrastructure/emitter.py",
               "-    logger.debug('frame emitted')\n"
               "+    logger.info('frame emitted')"),
    ),
    LabelledDiff(
        "neg-10", "Extend an enum with a UI state", False,
        _patch("src/domain/states.py",
               "+    COLLAPSED = 'COLLAPSED'"),
    ),
    LabelledDiff(
        "neg-11", "Increase a retry backoff", False,
        _patch("src/infrastructure/retry.py",
               "-    BACKOFF_SECONDS = 1.0\n"
               "+    BACKOFF_SECONDS = 2.5"),
    ),
    LabelledDiff(
        "neg-12", "Add a CSS class to the companion", False,
        _patch("docs/theme.css",
               "+.card-desc { color: #94a3b8; }"),
    ),
    # --- Adversarial cases, added 2026-09-08 -----------------------------
    # Written to tempt the structural rules the adversarial positives above
    # forced into existence. A rule that flags these is over-reaching, and the
    # published false-positive rate is where that shows up.
    LabelledDiff(
        "neg-13", "Retry bound relaxed from < to <=", False,
        _patch("src/infrastructure/retry.py",
               "-    if attempts < MAX_RETRIES:\n"
               "+    if attempts <= MAX_RETRIES:\n"
               "         return schedule(attempts)"),
    ),
    LabelledDiff(
        "neg-14", "CORS origins narrowed from a wildcard to one host", False,
        _patch("src/api/app.py",
               '-app.add_middleware(CORSMiddleware, allow_origins=["*"])\n'
               '+app.add_middleware(CORSMiddleware, allow_origins=["https://console.example.com"])'),
    ),
    LabelledDiff(
        "neg-15", "Email format helper removed after inlining", False,
        _patch("src/users/signup.py",
               "-    verify_email_format(payload.email)\n"
               "     return create_user(payload)"),
    ),
    LabelledDiff(
        "neg-16", "Signature check moved into a helper on the same file", False,
        _plain_patch("src/webhooks/handler.py",
                     "-    verify_signature(body, sig)\n"
                     "+    guard(body, sig)\n"
                     "+def guard(body, sig):\n"
                     "+    verify_signature(body, sig)"),
    ),
    LabelledDiff(
        "neg-17", "Status check helper removed", False,
        _patch("src/jobs/monitor.py",
               "-    check_status(job)\n"
               "     return job.result"),
    ),
    LabelledDiff(
        "neg-18", "Sort order flipped in a report", False,
        _plain_patch("src/reports/ranking.py",
                     "-    if left.score > right.score:\n"
                     "+    if left.score <= right.score:\n"
                     "         return -1"),
    ),
]

CORPUS: list[LabelledDiff] = POSITIVES + NEGATIVES
