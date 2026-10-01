"""Second-round probe patches, written against the CURRENT rules' scope.

How these were written, on 2026-10-01. The first eight probes
(``diff_corpus_js_ts_probes.py``) were tuned against: the rules changed until
six of eight behaved, so re-measuring them proves regression, not
generalization. These eight test whether the rules' documented scope holds on
shapes the rules never saw: a new control-flow refactor, a CORS fixture in a
test file, a safer-direction comparison change, a non-auth flip, an
inequality inversion on a tier gate, a new guard-call helper, a reflect
origin, and a removed signature check. Each label was decided from what the
change means before the rules were run on it; the measured figure is reported
by ``python scripts/benchmark_js_ts_detection.py --probes2`` and pinned by
``test_js_ts_detection_corpus.py`` whatever it is.

Like round one, this is self-authored, synthetic, small (four of each label)
and outside the corpus and its held-out half.
"""
from tests.fixtures.diff_corpus_js_ts import JS, TS, LabelledDiff


def _patch(path: str, body: str) -> str:
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1,5 +1,5 @@\n{body}\n"


PROBES_ROUND2: list[LabelledDiff] = [
    # ----------------------------------------- must not flag: same meaning
    LabelledDiff(
        "probe2-01", JS, "If/else rewritten as a guard clause; same behaviour", False,
        _patch("src/ui/panel.js",
               "-  if (user.role === 'admin') {\n"
               "-    proceed();\n"
               "-  } else {\n"
               "-    throw forbidden();\n"
               "-  }\n"
               "+  if (user.role !== 'admin') {\n"
               "+    throw forbidden();\n"
               "+  }\n"
               "+  proceed();"),
    ),
    LabelledDiff(
        "probe2-02", JS, "Wildcard origin in a CORS test fixture", False,
        _patch("test/cors.test.js",
               "   const fixture = {\n"
               "+    origin: '*', // fixture server for the suite\n"
               "   };"),
    ),
    LabelledDiff(
        "probe2-03", TS, "Loose comparison tightened to strict; safer, not inverted", False,
        _patch("src/auth/login.ts",
               "-  if (user.role == 'admin') return grant();\n"
               "+  if (user.role === 'admin') return grant();"),
    ),
    LabelledDiff(
        "probe2-04", JS, "Flipped comparison on non-authorization operands", False,
        _patch("src/jobs/queue.js",
               "-  if (count === 0) return empty();\n"
               "+  if (count !== 0) return empty();"),
    ),
    # --------------------------------------------- must flag: real findings
    LabelledDiff(
        "probe2-05", TS, "Tier gate inequality inverted: low tiers now pass", True,
        _patch("src/routes/billing.ts",
               "-  if (session.tier >= 2) return next();\n"
               "+  if (session.tier < 2) return next();"),
    ),
    LabelledDiff(
        "probe2-06", TS, "Permission guard un-negated before a deny", True,
        _patch("src/docs/edit.ts",
               "-  if (!hasPermission(ctx, 'write')) return deny();\n"
               "+  if (hasPermission(ctx, 'write')) return deny();"),
    ),
    LabelledDiff(
        "probe2-07", JS, "CORS origin set to reflect the caller", True,
        _patch("src/server/http.js",
               "   app.use(cors({\n"
               "-    origin: allowedOrigins,\n"
               "+    origin: true,\n"
               "   }));"),
    ),
    LabelledDiff(
        "probe2-08", JS, "Signature check deleted with no replacement", True,
        _patch("src/middleware/webhook.js",
               "-    verify_signature(payload, request.headers['X-Signature']);\n"
               "+    // signature check moved to the gateway"),
    ),
]
