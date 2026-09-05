"""Labelled unified-diff corpus used to measure security-flag detection.

Every entry carries a human label: ``expect_security_flag`` states whether a
reviewer would want Volcan to raise a security alert for that patch. The corpus
is the single source of truth for both ``scripts/benchmark_suite.py`` and
``tests/unit/test_security_detection_corpus.py``, so the published detection
rate and the assertion that guards it can never diverge.

The corpus is small and hand-labelled. It measures behaviour on these fixtures
only; it is not a claim about real-world repositories.
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
]

CORPUS: list[LabelledDiff] = POSITIVES + NEGATIVES
