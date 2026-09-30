"""Probe patches for the JavaScript and TypeScript rules, written AFTER them.

How these were written, on 2026-09-27. An audit of the JS/TS rules showed
that the rules read one changed line at a time, so a rewrite that keeps the
meaning can still look like a flipped check, and a flip that goes through a
helper call looks like nothing. The audit described four such patches, written
here as ``probe-01``, ``probe-02``, ``probe-03`` and ``probe-05`` (three that
must not flag, one that must). The engineer who wrote the rules then added four
more of the same kinds, ``probe-04``, ``probe-06``, ``probe-07`` and
``probe-08`` (one that must not flag, three that must), with each label decided
from what the change means before the rules were run on it. ``probe-03``'s label
is a judgement: a wildcard origin is harmless in a server that only ever runs
locally, and the patch says so only in a comment.

This is not part of the 64-case corpus and not part of its held-out half: it
was written with full knowledge of the rules, to find where they break. It is
self-authored and synthetic, it is small (four of each label), and its figure
is reported on its own by ``python scripts/benchmark_js_ts_detection.py
--probes``. The rules were first measured against it unchanged (0 of 4
detected, 4 of 4 over-flagged); the 2026-09-30 rule work answers four of
the eight and documents the other four as fail-closed limits.
"""
from tests.fixtures.diff_corpus_js_ts import JS, TS, LabelledDiff


def _patch(path: str, body: str) -> str:
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1,3 +1,4 @@\n{body}\n"


PROBES: list[LabelledDiff] = [
    # ----------------------------------------- must not flag: same meaning
    LabelledDiff(
        "probe-01", JS, "Early-return refactor of an admin badge check; same behaviour", False,
        _patch("src/ui/badge.js",
               "-  if (user.role === 'admin') {\n"
               "-    showBadge();\n"
               "-  }\n"
               "+  if (user.role !== 'admin') {\n"
               "+    return;\n"
               "+  }\n"
               "+  showBadge();"),
    ),
    LabelledDiff(
        "probe-02", TS, "Test assertion rewritten to an equivalent negated form", False,
        _patch("src/auth/a.test.ts",
               "-    expect(user.role === 'admin').toBe(true);\n"
               "+    expect(user.role !== 'admin').toBe(false);"),
    ),
    LabelledDiff(
        "probe-03", JS, "Wildcard origin in a local development server config", False,
        _patch("tools/dev-server.js",
               "   const devCors = {\n"
               "-    origin: 'http://localhost:5173',\n"
               "+    origin: '*', // local dev only\n"
               "   };"),
    ),
    LabelledDiff(
        "probe-04", TS, "Negated equality rewritten as the opposite operator; same behaviour", False,
        _patch("src/routes/settings.ts",
               "-  if (!(session.user.role === 'owner')) return deny(res);\n"
               "+  if (session.user.role !== 'owner') return deny(res);"),
    ),
    # --------------------------------------------- must flag: real inversions
    LabelledDiff(
        "probe-05", JS, "Negated admin helper un-negated: admins are now the ones denied", True,
        _patch("src/middleware/admin.js",
               "-  if (!isAdmin(user)) return deny();\n"
               "+  if (isAdmin(user)) return deny();"),
    ),
    LabelledDiff(
        "probe-06", TS, "Negated permission helper un-negated before a throw", True,
        _patch("src/docs/guard.ts",
               "-  if (!canEdit(session, doc)) throw forbidden();\n"
               "+  if (canEdit(session, doc)) throw forbidden();"),
    ),
    LabelledDiff(
        "probe-07", JS, "Admin comparison flipped where the statement spans two lines", True,
        _patch("src/routes/admin.js",
               "-  if (req.user.role\n"
               "-      === 'admin') {\n"
               "+  if (req.user.role\n"
               "+      !== 'admin') {\n"
               "     return next();"),
    ),
    LabelledDiff(
        "probe-08", TS, "CORS origin widened to any origin, value on its own line", True,
        _patch("src/server/cors.ts",
               "   app.use(cors({\n"
               "-    origin:\n"
               "-      allowedOrigins,\n"
               "+    origin:\n"
               "+      '*',\n"
               "   }));"),
    ),
]
