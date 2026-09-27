"""Labelled JavaScript and TypeScript patches for measuring security detection.

How these were written, on 2026-09-27, before any JavaScript or TypeScript rule
existed in this repository. The same engineer who later wrote the rules wrote
every case here, so this is a self-authored, synthetic corpus and every figure
measured over it says so. It is not a claim about any real repository.

What was done to keep it from flattering the rules:

* Positives were written from what a reviewer would want flagged in a Node or
  TypeScript service, family by family, including cases that no rule in this
  repository was expected to catch: a negated ``includes`` check, a reflected
  CORS origin, an ``innerHTML`` sink, a weakened hash, a cookie that lost its
  flags, a route that lost its middleware, a SQL string built by interpolation.
* Negatives were written the way ordinary JavaScript is written, which means
  many of them contain the words the keyword pass reacts to: ``Object.keys``,
  ``keydown``, ``keyof``, ``author``, ``tokenizer``. They were not chosen to
  avoid those words, so the keyword pass's false alarms show up in the figure.
* Other negatives tempt the structural rules: an ARIA ``role`` check flipped, a
  chat message ``role`` check flipped, a floor-plan comparison flipped, CORS
  narrowed rather than widened, a signature check moved into a helper.

The corpus is split once, by a fixed rule, into a training half and a held-out
half. The rules were tuned against the training half only; the held-out half is
reported as a separate figure. See ``split()`` for the rule and
``scripts/benchmark_js_ts_detection.py`` for the command.
"""
import random
from dataclasses import dataclass

#: The seed of the one split. Fixed so the split is reproducible and published.
SPLIT_SEED = 20260927


@dataclass(frozen=True)
class LabelledDiff:
    fixture_id: str
    language: str  # "javascript" or "typescript"
    description: str
    expect_security_flag: bool
    raw_diff: str


def _patch(path: str, body: str) -> str:
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1,2 +1,4 @@\n{body}\n"


JS = "javascript"
TS = "typescript"

CASES: list[LabelledDiff] = [
    # ---------------------------------------------------------------- JS, flag
    LabelledDiff(
        "js-pos-01", JS, "Admin role check inverted in Express middleware", True,
        _patch("src/middleware/admin.js",
               "-  if (req.user.role === 'admin') {\n"
               "+  if (req.user.role !== 'admin') {\n"
               "     return next();"),
    ),
    LabelledDiff(
        "js-pos-02", JS, "Permission lookup result inverted", True,
        _patch("src/policy/billing.js",
               "-  return user.permissions.indexOf('billing:write') !== -1;\n"
               "+  return user.permissions.indexOf('billing:write') === -1;"),
    ),
    LabelledDiff(
        "js-pos-03", JS, "cors() origin widened to a wildcard", True,
        _patch("src/server.js",
               "-app.use(cors({ origin: 'https://console.example.com' }));\n"
               "+app.use(cors({ origin: '*' }));"),
    ),
    LabelledDiff(
        "js-pos-04", JS, "Allow-Origin response header set to any site", True,
        _patch("src/http/headers.js",
               "-  res.setHeader('Access-Control-Allow-Origin', config.consoleUrl);\n"
               "+  res.setHeader('Access-Control-Allow-Origin', '*');"),
    ),
    LabelledDiff(
        "js-pos-05", JS, "cors() told to reflect any origin", True,
        _patch("src/server.js",
               "-  origin: 'https://console.example.com',\n"
               "+  origin: true,\n"
               "   credentials: true,"),
    ),
    LabelledDiff(
        "js-pos-06", JS, "Webhook signature verification call deleted", True,
        _patch("src/webhooks/github.js",
               "-  verifySignature(req.rawBody, req.headers['x-hub-signature-256']);\n"
               "   return processEvent(req.body);"),
    ),
    LabelledDiff(
        "js-pos-07", JS, "Auth middleware dropped from a refund route", True,
        _patch("src/routes/refunds.js",
               "-router.post('/refunds', requireAuth, issueRefund);\n"
               "+router.post('/refunds', issueRefund);"),
    ),
    LabelledDiff(
        "js-pos-08", JS, "eval of a request expression", True,
        _patch("src/api/calc.js",
               "-  const result = safeEvaluate(expr);\n"
               "+  const result = eval(expr);"),
    ),
    LabelledDiff(
        "js-pos-09", JS, "Shell command built from user input", True,
        _patch("src/tools/git.js",
               "-  execFile('git', ['log', '--oneline', ref]);\n"
               "+  exec(`git log --oneline ${ref}`);"),
    ),
    LabelledDiff(
        "js-pos-10", JS, "TLS certificate checks disabled on an agent", True,
        _patch("src/clients/partner.js",
               "+const agent = new https.Agent({ rejectUnauthorized: false });"),
    ),
    LabelledDiff(
        "js-pos-11", JS, "Comment body written as HTML", True,
        _patch("src/ui/comments.js",
               "-  el.textContent = comment.body;\n"
               "+  el.innerHTML = comment.body;"),
    ),
    LabelledDiff(
        "js-pos-12", JS, "Paid-plan check negated with !includes", True,
        _patch("src/billing/entitlements.js",
               "-  if (PAID_PLANS.includes(account.plan)) {\n"
               "+  if (!PAID_PLANS.includes(account.plan)) {\n"
               "     return unlock(account);"),
    ),
    LabelledDiff(
        "js-pos-13", JS, "Session cookie lost httpOnly and secure", True,
        _patch("src/session.js",
               "-  res.cookie('sid', id, { httpOnly: true, secure: true });\n"
               "+  res.cookie('sid', id, { httpOnly: false, secure: false });"),
    ),
    LabelledDiff(
        "js-pos-14", JS, "Live API secret hardcoded", True,
        _patch("src/config.js",
               "+const API_SECRET = 'sk_live_51HqVxKJ2eZvKYlo2C0fake';"),
    ),
    LabelledDiff(
        "js-pos-15", JS, "Access level threshold inverted", True,
        _patch("src/policy/docs.js",
               "-  if (user.accessLevel >= REQUIRED_LEVEL) {\n"
               "+  if (user.accessLevel < REQUIRED_LEVEL) {\n"
               "     return allow();"),
    ),
    LabelledDiff(
        "js-pos-16", JS, "SQL built by string interpolation", True,
        _patch("src/db/users.js",
               "-  return db.query('SELECT * FROM users WHERE id = $1', [id]);\n"
               "+  return db.query(`SELECT * FROM users WHERE id = ${id}`);"),
    ),
    # ------------------------------------------------------------ JS, no flag
    LabelledDiff(
        "js-neg-01", JS, "Empty-list check flipped in a renderer", False,
        _patch("src/ui/list.js",
               "-  if (items.length === 0) {\n"
               "+  if (items.length !== 0) {\n"
               "     return renderEmpty();"),
    ),
    LabelledDiff(
        "js-neg-02", JS, "ARIA role check flipped", False,
        _patch("src/ui/focus.js",
               "-  if (el.getAttribute('role') === 'button') {\n"
               "+  if (el.getAttribute('role') !== 'button') {\n"
               "     el.tabIndex = 0;"),
    ),
    LabelledDiff(
        "js-neg-03", JS, "Iterate config entries with Object.keys", False,
        _patch("src/config/print.js",
               "+  Object.keys(config).forEach((name) => print(name, config[name]));"),
    ),
    LabelledDiff(
        "js-neg-04", JS, "Keyboard shortcut listener added", False,
        _patch("src/ui/shortcuts.js",
               "+window.addEventListener('keydown', onShortcut);"),
    ),
    LabelledDiff(
        "js-neg-05", JS, "Show the post author's name", False,
        _patch("src/ui/post.js",
               "+  const author = post.author.displayName;"),
    ),
    LabelledDiff(
        "js-neg-06", JS, "cors() origin narrowed from a wildcard", False,
        _patch("src/server.js",
               "-app.use(cors({ origin: '*' }));\n"
               "+app.use(cors({ origin: 'https://console.example.com' }));"),
    ),
    LabelledDiff(
        "js-neg-07", JS, "Email format helper removed after inlining", False,
        _patch("src/users/signup.js",
               "-  verifyEmailFormat(payload.email);\n"
               "   return createUser(payload);"),
    ),
    LabelledDiff(
        "js-neg-08", JS, "Status check helper removed", False,
        _patch("src/jobs/monitor.js",
               "-  checkStatus(job);\n"
               "   return job.result;"),
    ),
    LabelledDiff(
        "js-neg-09", JS, "Signature check moved into a helper in the same file", False,
        _patch("src/webhooks/github.js",
               "-  verifySignature(body, sig);\n"
               "+  guard(body, sig);\n"
               "+function guard(body, sig) {\n"
               "+  verifySignature(body, sig);"),
    ),
    LabelledDiff(
        "js-neg-10", JS, "Sort order flipped in a leaderboard", False,
        _patch("src/reports/ranking.js",
               "-  return a.score > b.score ? -1 : 1;\n"
               "+  return a.score < b.score ? -1 : 1;"),
    ),
    LabelledDiff(
        "js-neg-11", JS, "Rename a loop variable", False,
        _patch("src/domain/totals.js",
               "-  for (const i of items) total += i.price;\n"
               "+  for (const item of items) total += item.price;"),
    ),
    LabelledDiff(
        "js-neg-12", JS, "Widen a pagination limit", False,
        _patch("src/api/list.js",
               "-const PAGE_SIZE = 25;\n"
               "+const PAGE_SIZE = 50;"),
    ),
    LabelledDiff(
        "js-neg-13", JS, "New assertion in an auth test file", False,
        _patch("test/auth.test.js",
               "+  expect(res.status).toBe(401);"),
    ),
    LabelledDiff(
        "js-neg-14", JS, "console.log replaced by the logger", False,
        _patch("src/jobs/worker.js",
               "-  console.log('job finished', job.id);\n"
               "+  logger.debug('job finished', { id: job.id });"),
    ),
    LabelledDiff(
        "js-neg-15", JS, "A second named console origin allowed", False,
        _patch("src/server.js",
               "-const allowedOrigins = ['https://a.example.com'];\n"
               "+const allowedOrigins = ['https://a.example.com', 'https://b.example.com'];"),
    ),
    LabelledDiff(
        "js-neg-16", JS, "Floor-plan room threshold flipped", False,
        _patch("src/listings/filter.js",
               "-  if (floorPlan.rooms > 3) {\n"
               "+  if (floorPlan.rooms <= 3) {\n"
               "     tags.push('large');"),
    ),
    # ---------------------------------------------------------------- TS, flag
    LabelledDiff(
        "ts-pos-01", TS, "Role enum check inverted in a guard", True,
        _patch("src/guards/admin.guard.ts",
               "-    if (session.user.role === Role.Admin) {\n"
               "+    if (session.user.role !== Role.Admin) {\n"
               "       return true;"),
    ),
    LabelledDiff(
        "ts-pos-02", TS, "Free-tier check inverted", True,
        _patch("src/billing/limits.ts",
               "-  if (membership.tier !== 'free') {\n"
               "+  if (membership.tier === 'free') {\n"
               "     return UNLIMITED;"),
    ),
    LabelledDiff(
        "ts-pos-03", TS, "Typed CorsOptions widened to a wildcard", True,
        _patch("src/http/cors.ts",
               "-const corsOptions: CorsOptions = { origin: ['https://app.example.com'] };\n"
               "+const corsOptions: CorsOptions = { origin: '*' };"),
    ),
    LabelledDiff(
        "ts-pos-04", TS, "enableCors widened to a wildcard", True,
        _patch("src/main.ts",
               "-  app.enableCors({ origin: 'https://app.example.com' });\n"
               "+  app.enableCors({ origin: '*' });"),
    ),
    LabelledDiff(
        "ts-pos-05", TS, "Allow-Origin header in a headers object widened", True,
        _patch("src/lambda/response.ts",
               "-    'Access-Control-Allow-Origin': env.CONSOLE_ORIGIN,\n"
               "+    'Access-Control-Allow-Origin': '*',"),
    ),
    LabelledDiff(
        "ts-pos-06", TS, "Awaited webhook signature check deleted", True,
        _patch("src/payments/webhook.controller.ts",
               "-    await this.verifyWebhookSignature(payload, signature);\n"
               "     return this.payments.apply(payload);"),
    ),
    LabelledDiff(
        "ts-pos-07", TS, "Guard decorator removed from a refund endpoint", True,
        _patch("src/refunds/refunds.controller.ts",
               "-  @UseGuards(AuthGuard('jwt'))\n"
               "   @Post('refund')"),
    ),
    LabelledDiff(
        "ts-pos-08", TS, "Edit-permission assertion deleted", True,
        _patch("src/docs/docs.service.ts",
               "-    assertCanEdit(user, doc);\n"
               "     return this.repo.save(doc);"),
    ),
    LabelledDiff(
        "ts-pos-09", TS, "jwt.verify replaced by jwt.decode", True,
        _patch("src/auth/session.ts",
               "-  const claims = jwt.verify(raw, secret) as Claims;\n"
               "+  const claims = jwt.decode(raw) as Claims;"),
    ),
    LabelledDiff(
        "ts-pos-10", TS, "Function constructor built from input", True,
        _patch("src/rules/engine.ts",
               "+  const rule = new Function('input', body);"),
    ),
    LabelledDiff(
        "ts-pos-11", TS, "Content hash weakened to MD5", True,
        _patch("src/storage/digest.ts",
               "-  const hash = createHash('sha256');\n"
               "+  const hash = createHash('md5');"),
    ),
    LabelledDiff(
        "ts-pos-12", TS, "Authentication guard block deleted", True,
        _patch("src/routes/admin.ts",
               "-  if (!req.isAuthenticated()) {\n"
               "-    return res.sendStatus(401);\n"
               "   }"),
    ),
    LabelledDiff(
        "ts-pos-13", TS, "No-roles refusal inverted", True,
        _patch("src/guards/roles.guard.ts",
               "-    if (user.roles.length === 0) {\n"
               "+    if (user.roles.length !== 0) {\n"
               "       throw new ForbiddenException();"),
    ),
    LabelledDiff(
        "ts-pos-14", TS, "Allow-Origin reflects the request origin", True,
        _patch("src/http/cors.ts",
               "-  res.header('Access-Control-Allow-Origin', CONSOLE_ORIGIN);\n"
               "+  res.header('Access-Control-Allow-Origin', req.headers.origin);"),
    ),
    LabelledDiff(
        "ts-pos-15", TS, "CSRF middleware no longer mounted", True,
        _patch("src/app.ts",
               "-app.use(csrfProtection);\n"
               " app.use(router);"),
    ),
    LabelledDiff(
        "ts-pos-16", TS, "CSRF token validation call deleted", True,
        _patch("src/forms/submit.ts",
               "-  validateCsrfToken(req);\n"
               "   return save(req.body);"),
    ),
    # ------------------------------------------------------------ TS, no flag
    LabelledDiff(
        "ts-neg-01", TS, "A keyof type alias", False,
        _patch("src/types/user.ts",
               "+export type UserField = keyof User;"),
    ),
    LabelledDiff(
        "ts-neg-02", TS, "Tokenizer used for syntax highlighting", False,
        _patch("src/editor/highlight.ts",
               "+  const tokens = tokenizer.tokenize(source);"),
    ),
    LabelledDiff(
        "ts-neg-03", TS, "HTTP status check flipped in a retry helper", False,
        _patch("src/http/retry.ts",
               "-  if (response.status !== 200) {\n"
               "+  if (response.status === 200) {\n"
               "     return schedule(attempt);"),
    ),
    LabelledDiff(
        "ts-neg-04", TS, "Chat message role check flipped", False,
        _patch("src/chat/render.ts",
               "-  if (message.role === 'assistant') {\n"
               "+  if (message.role !== 'assistant') {\n"
               "     return renderBubble(message);"),
    ),
    LabelledDiff(
        "ts-neg-05", TS, "Optional display name on an interface", False,
        _patch("src/types/profile.ts",
               "+  displayName?: string;"),
    ),
    LabelledDiff(
        "ts-neg-06", TS, "Enum extended with a UI state", False,
        _patch("src/ui/state.ts",
               "+  Collapsed = 'COLLAPSED',"),
    ),
    LabelledDiff(
        "ts-neg-07", TS, "Email validation helper removed", False,
        _patch("src/users/invite.ts",
               "-  validateEmail(input.email);\n"
               "   return this.invites.create(input);"),
    ),
    LabelledDiff(
        "ts-neg-08", TS, "Directory helper removed", False,
        _patch("src/build/output.ts",
               "-  ensureDirectory(outDir);\n"
               "   return writeBundle(outDir, bundle);"),
    ),
    LabelledDiff(
        "ts-neg-09", TS, "enableCors narrowed from a wildcard", False,
        _patch("src/main.ts",
               "-  app.enableCors({ origin: '*' });\n"
               "+  app.enableCors({ origin: 'https://app.example.com' });"),
    ),
    LabelledDiff(
        "ts-neg-10", TS, "Generic parameter renamed", False,
        _patch("src/util/cache.ts",
               "-export function memo<T>(fn: () => T): () => T {\n"
               "+export function memo<Value>(fn: () => Value): () => Value {"),
    ),
    LabelledDiff(
        "ts-neg-11", TS, "Import block reordered", False,
        _patch("src/index.ts",
               "-import { b, a } from './lib';\n"
               "+import { a, b } from './lib';"),
    ),
    LabelledDiff(
        "ts-neg-12", TS, "Retry bound relaxed from < to <=", False,
        _patch("src/http/retry.ts",
               "-  if (retries < MAX_RETRIES) {\n"
               "+  if (retries <= MAX_RETRIES) {\n"
               "     return retry();"),
    ),
    LabelledDiff(
        "ts-neg-13", TS, "Comment about the author field", False,
        _patch("src/blog/post.ts",
               "+  // The author's display name, shown under the title."),
    ),
    LabelledDiff(
        "ts-neg-14", TS, "Private cache field added", False,
        _patch("src/catalog/service.ts",
               "+  private readonly cache = new Map<string, Item>();"),
    ),
    LabelledDiff(
        "ts-neg-15", TS, "Newest-first sort flipped to oldest-first", False,
        _patch("src/feed/sort.ts",
               "-  return b.createdAt - a.createdAt;\n"
               "+  return a.createdAt - b.createdAt;"),
    ),
    LabelledDiff(
        "ts-neg-16", TS, "Canvas origin moved", False,
        _patch("src/canvas/view.ts",
               "-  const origin = { x: 0, y: 0 };\n"
               "+  const origin = { x: 1, y: 1 };"),
    ),
]


def split(cases: list[LabelledDiff] = CASES, seed: int = SPLIT_SEED) -> dict[str, list[LabelledDiff]]:
    """The one published split, into ``train`` and ``heldout``.

    The rule: group the cases into four strata by language and label; sort each
    stratum by fixture id; shuffle it with ``random.Random(seed)``, one fresh
    generator per stratum; the first half of each shuffled stratum is
    ``train`` and the second half ``heldout``. Every stratum here has 16 cases,
    so each split holds 8 of each language and label, 32 in all.
    """
    strata: dict[tuple[str, bool], list[LabelledDiff]] = {}
    for case in cases:
        strata.setdefault((case.language, case.expect_security_flag), []).append(case)
    out: dict[str, list[LabelledDiff]] = {"train": [], "heldout": []}
    for key in sorted(strata, key=lambda k: (k[0], not k[1])):
        members = sorted(strata[key], key=lambda c: c.fixture_id)
        random.Random(seed).shuffle(members)
        half = len(members) // 2
        out["train"].extend(members[:half])
        out["heldout"].extend(members[half:])
    return out
