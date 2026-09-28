"""Held-out patches for three classic vulnerability families, written BEFORE their rules.

Why this set exists. An independent review on 2026-09-28 ran the local engine,
the one every judge without cloud credentials hears, on three classic patches:

* a SQL query built by string concatenation (``"SELECT ... WHERE id = " + req.id``)
* an outbound HTTPS call with certificate checks turned off (``verify=False``)
* a shell command built from input and run with ``shell=True``

The first two produced no security flag at all, so the page played the rising
"clean" cue; the third was flagged only as "text matching the exec_call keyword
set". This file was written and committed before any rule for those three
families existed in this repository, so the "before" figure below is the
engine the review measured, and the "after" figure is measured on patches the
rules were not tuned against.

What it holds, fixed before the first case was written: three languages
(Python, JavaScript, TypeScript), three families (``sql``, ``tls``, ``shell``),
and for each language and family four patches that must flag and four that must
not. That is 24 cases per language and 72 in all.

How it was kept from flattering the rules that followed:

* Each family's positives include shapes a line-at-a-time reader is expected to
  miss: a query spread over several lines, a query-builder fragment that does
  not start with a SQL verb, a promisified ``exec`` under another name, a shell
  run through ``spawn('sh', ['-c', ...])``, a certificate check replaced by a
  function that accepts anything.
* Negatives tempt the rules: the fix for each family (a parameterized query, a
  CA bundle, an argument list), a SQL string joined only from constants, a UI
  label that reads "Select ... from", ``shell=True`` with a fixed command, a
  ``RegExp.exec`` call with an interpolated argument, a tagged template that a
  driver parameterizes, a read of ``NODE_TLS_REJECT_UNAUTHORIZED`` that refuses
  to run with it set, a comment that mentions ``shell=True``.
* Negatives were written the way ordinary code is written, so some carry words
  the keyword pass reacts to (``subprocess``, ``exec(``, ``token``, ``key``).
  Those false alarms are the keyword pass, and the benchmark reports them apart
  from any false alarm raised by a named rule.

Limits, stated. The same engineer wrote these cases and, afterwards, the rules.
The cases are self-authored and synthetic, not taken from any real repository,
and small: four per language, family and label. The held-out figure is
independent of the tuning, not of the author. After the first measurement no
case or label here is changed; a label later judged wrong is reported, not
flipped.

Measured by ``python scripts/benchmark_classic_families.py``.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class LabelledDiff:
    fixture_id: str
    language: str  # "python", "javascript" or "typescript"
    family: str  # "sql", "tls" or "shell"
    description: str
    expect_security_flag: bool
    raw_diff: str


def _patch(path: str, body: str) -> str:
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1,3 +1,4 @@\n{body}\n"


PY = "python"
JS = "javascript"
TS = "typescript"

CASES: list[LabelledDiff] = [
    # ================================================================ Python
    # ---------------------------------------------------------- sql, flag
    LabelledDiff(
        "cl-py-sql-pos-01", PY, "sql", "Parameterized lookup replaced by concatenation", True,
        _patch("app/orders/repository.py",
               " def orders_for(cursor, customer_id):\n"
               '-    cursor.execute("SELECT * FROM orders WHERE customer_id = %s", (customer_id,))\n'
               '+    cursor.execute("SELECT * FROM orders WHERE customer_id = " + customer_id)\n'
               "     return cursor.fetchall()"),
    ),
    LabelledDiff(
        "cl-py-sql-pos-02", PY, "sql", "DELETE built with an f-string", True,
        _patch("app/cart/cleanup.py",
               " def clear_cart(conn, session_id):\n"
               "+    conn.execute(f\"DELETE FROM carts WHERE session_id = '{session_id}'\")\n"
               "     conn.commit()"),
    ),
    LabelledDiff(
        "cl-py-sql-pos-03", PY, "sql", "Query formatted with % into a variable, executed on the next line", True,
        _patch("app/users/lookup.py",
               " def find_by_email(conn, email):\n"
               "+    sql = \"SELECT name FROM users WHERE email = '%s'\" % email\n"
               "+    return conn.execute(sql).fetchone()"),
    ),
    LabelledDiff(
        "cl-py-sql-pos-04", PY, "sql", "Concatenated query spread over two lines", True,
        _patch("app/billing/invoices.py",
               " def invoices_for(cursor, account_id):\n"
               '+    query = ("SELECT id, total FROM invoices "\n'
               "+             \"WHERE account = '\" + account_id + \"'\")\n"
               "+    cursor.execute(query)"),
    ),
    # ------------------------------------------------------ sql, no flag
    LabelledDiff(
        "cl-py-sql-neg-01", PY, "sql", "Concatenated query fixed with a bound parameter", False,
        _patch("app/orders/repository.py",
               " def orders_for(cursor, customer_id):\n"
               '-    cursor.execute("SELECT * FROM orders WHERE customer_id = " + customer_id)\n'
               '+    cursor.execute("SELECT * FROM orders WHERE customer_id = %s", (customer_id,))\n'
               "     return cursor.fetchall()"),
    ),
    LabelledDiff(
        "cl-py-sql-neg-02", PY, "sql", "Query joined only from constant strings", False,
        _patch("app/catalog/queries.py",
               "+LIST_PRODUCTS = \"SELECT id, name \" + \"FROM products ORDER BY name\"\n"
               " "),
    ),
    LabelledDiff(
        "cl-py-sql-neg-03", PY, "sql", "UI label that reads like a query", False,
        _patch("app/ui/prompts.py",
               " def folder_prompt(folder_name):\n"
               '+    return "Select the files from " + folder_name'),
    ),
    LabelledDiff(
        "cl-py-sql-neg-04", PY, "sql", "ORM filter added", False,
        _patch("app/orders/views.py",
               " def order_list(request):\n"
               '+    orders = Order.objects.filter(customer_id=request.user.id).select_related("items")\n'
               "     return render(request, \"orders.html\", {\"orders\": orders})"),
    ),
    # ---------------------------------------------------------- tls, flag
    LabelledDiff(
        "cl-py-tls-pos-01", PY, "tls", "Certificate checks turned off on a POST", True,
        _patch("app/clients/payments.py",
               " def charge(url, payload):\n"
               "-    return requests.post(url, json=payload, timeout=10)\n"
               "+    return requests.post(url, json=payload, timeout=10, verify=False)"),
    ),
    LabelledDiff(
        "cl-py-tls-pos-02", PY, "tls", "Session told to skip certificate checks", True,
        _patch("app/clients/partner.py",
               " session = requests.Session()\n"
               "+session.verify = False\n"
               " session.headers.update(DEFAULT_HEADERS)"),
    ),
    LabelledDiff(
        "cl-py-tls-pos-03", PY, "tls", "Unverified SSL context passed to urlopen", True,
        _patch("app/feeds/fetch.py",
               " def fetch(url):\n"
               "+    context = ssl._create_unverified_context()\n"
               "+    return urllib.request.urlopen(url, context=context).read()"),
    ),
    LabelledDiff(
        "cl-py-tls-pos-04", PY, "tls", "urllib3 pool created with CERT_NONE", True,
        _patch("app/clients/pool.py",
               "-http = urllib3.PoolManager(cert_reqs=\"CERT_REQUIRED\", ca_certs=certifi.where())\n"
               "+http = urllib3.PoolManager(cert_reqs=\"CERT_NONE\")"),
    ),
    # ------------------------------------------------------ tls, no flag
    LabelledDiff(
        "cl-py-tls-neg-01", PY, "tls", "verify=False replaced by a CA bundle", False,
        _patch("app/clients/payments.py",
               " def charge(url, payload):\n"
               "-    return requests.post(url, json=payload, timeout=10, verify=False)\n"
               "+    return requests.post(url, json=payload, timeout=10, verify=CA_BUNDLE_PATH)"),
    ),
    LabelledDiff(
        "cl-py-tls-neg-02", PY, "tls", "Outbound GET pinned to certifi", False,
        _patch("app/clients/status.py",
               " def status(url):\n"
               "+    return requests.get(url, timeout=10, verify=certifi.where()).json()"),
    ),
    LabelledDiff(
        "cl-py-tls-neg-03", PY, "tls", "Default SSL context with a private CA", False,
        _patch("app/feeds/fetch.py",
               " def fetch(url):\n"
               "+    context = ssl.create_default_context(cafile=INTERNAL_CA_PATH)\n"
               "+    return urllib.request.urlopen(url, context=context).read()"),
    ),
    LabelledDiff(
        "cl-py-tls-neg-04", PY, "tls", "SSL context hardened to require certificates", False,
        _patch("app/net/tls.py",
               " context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)\n"
               "+context.check_hostname = True\n"
               "+context.verify_mode = ssl.CERT_REQUIRED"),
    ),
    # -------------------------------------------------------- shell, flag
    LabelledDiff(
        "cl-py-shell-pos-01", PY, "shell", "Image conversion run through a shell with an f-string", True,
        _patch("app/media/thumbnails.py",
               " def thumbnail(src, dst):\n"
               '-    subprocess.run(["convert", src, "-resize", "200x200", dst], check=True)\n'
               '+    subprocess.run(f"convert {src} -resize 200x200 {dst}", shell=True, check=True)'),
    ),
    LabelledDiff(
        "cl-py-shell-pos-02", PY, "shell", "os.system with a concatenated archive path", True,
        _patch("app/imports/unpack.py",
               " def unpack(archive_path):\n"
               '+    os.system("tar -xzf " + archive_path)'),
    ),
    LabelledDiff(
        "cl-py-shell-pos-03", PY, "shell", "git log run through a shell with % formatting", True,
        _patch("app/vcs/history.py",
               " def commits_by(author):\n"
               '+    return subprocess.check_output("git log --author=%s" % author, shell=True)'),
    ),
    LabelledDiff(
        "cl-py-shell-pos-04", PY, "shell", "Command built on one line, run with shell=True on the next", True,
        _patch("app/net/ping.py",
               " def reachable(host):\n"
               '+    cmd = "ping -c 1 " + host\n'
               "+    return subprocess.call(cmd, shell=True) == 0"),
    ),
    # ---------------------------------------------------- shell, no flag
    LabelledDiff(
        "cl-py-shell-neg-01", PY, "shell", "Shell string replaced by an argument list", False,
        _patch("app/media/thumbnails.py",
               " def thumbnail(src, dst):\n"
               '-    subprocess.run(f"convert {src} -resize 200x200 {dst}", shell=True, check=True)\n'
               '+    subprocess.run(["convert", src, "-resize", "200x200", dst], check=True)'),
    ),
    LabelledDiff(
        "cl-py-shell-neg-02", PY, "shell", "Fixed build command run through a shell", False,
        _patch("app/build/clean.py",
               " def clean(build_dir):\n"
               '+    subprocess.run("make clean", shell=True, cwd=build_dir, check=True)'),
    ),
    LabelledDiff(
        "cl-py-shell-neg-03", PY, "shell", "Revision read with an argument list", False,
        _patch("app/version.py",
               " def revision():\n"
               '+    out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)\n'
               "+    return out.stdout.strip()"),
    ),
    LabelledDiff(
        "cl-py-shell-neg-04", PY, "shell", "Comment that warns against shell=True", False,
        _patch("app/media/thumbnails.py",
               " def thumbnail(src, dst):\n"
               "+    # never pass shell=True here; the arguments stay a list\n"
               '     subprocess.run(["convert", src, dst], check=True)'),
    ),
    # ============================================================ JavaScript
    # ---------------------------------------------------------- sql, flag
    LabelledDiff(
        "cl-js-sql-pos-01", JS, "sql", "Login lookup built by concatenation", True,
        _patch("src/auth/users.js",
               "-  return db.query('SELECT * FROM users WHERE email = ?', [email]);\n"
               "+  return db.query(\"SELECT * FROM users WHERE email = '\" + email + \"'\");"),
    ),
    LabelledDiff(
        "cl-js-sql-pos-02", JS, "sql", "Balance update built with a template literal", True,
        _patch("src/ledger/accounts.js",
               "+  await pool.query(`UPDATE accounts SET balance = ${amount} WHERE id = ${id}`);"),
    ),
    LabelledDiff(
        "cl-js-sql-pos-03", JS, "sql", "Query string built from the query string, executed on the next line", True,
        _patch("src/orders/list.js",
               "+  const sql = 'SELECT * FROM orders WHERE status = ' + req.query.status;\n"
               "+  connection.query(sql, callback);"),
    ),
    LabelledDiff(
        "cl-js-sql-pos-04", JS, "sql", "Multi-line raw query with an interpolated id", True,
        _patch("src/billing/invoices.js",
               "+  const rows = await knex.raw(`\n"
               "+    SELECT id, total FROM invoices\n"
               "+    WHERE account_id = ${accountId}\n"
               "+  `);"),
    ),
    # ------------------------------------------------------ sql, no flag
    LabelledDiff(
        "cl-js-sql-neg-01", JS, "sql", "Concatenated lookup fixed with a placeholder", False,
        _patch("src/auth/users.js",
               "-  return db.query(\"SELECT * FROM users WHERE email = '\" + email + \"'\");\n"
               "+  return db.query('SELECT * FROM users WHERE email = ?', [email]);"),
    ),
    LabelledDiff(
        "cl-js-sql-neg-02", JS, "sql", "Query joined only from constant strings", False,
        _patch("src/catalog/queries.js",
               "+const LIST_PRODUCTS = 'SELECT id, name ' + 'FROM products ORDER BY name';"),
    ),
    LabelledDiff(
        "cl-js-sql-neg-03", JS, "sql", "UI label that reads like a query", False,
        _patch("src/ui/picker.js",
               "+  label.textContent = 'Select the files from ' + folder.name;"),
    ),
    LabelledDiff(
        "cl-js-sql-neg-04", JS, "sql", "Toast message with an interpolated count", False,
        _patch("src/ui/cart.js",
               "+  showToast(`Deleted ${count} items from your cart`);"),
    ),
    # ---------------------------------------------------------- tls, flag
    LabelledDiff(
        "cl-js-tls-pos-01", JS, "tls", "HTTPS agent that accepts any certificate", True,
        _patch("src/clients/payments.js",
               "-const agent = new https.Agent({ keepAlive: true });\n"
               "+const agent = new https.Agent({ keepAlive: true, rejectUnauthorized: false });"),
    ),
    LabelledDiff(
        "cl-js-tls-pos-02", JS, "tls", "Process-wide certificate checks turned off", True,
        _patch("src/bootstrap.js",
               "+process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';\n"
               " start();"),
    ),
    LabelledDiff(
        "cl-js-tls-pos-03", JS, "tls", "request() told not to check certificates", True,
        _patch("src/clients/legacy.js",
               "-  request({ url, json: true }, done);\n"
               "+  request({ url, json: true, strictSSL: false }, done);"),
    ),
    LabelledDiff(
        "cl-js-tls-pos-04", JS, "tls", "Server identity check replaced by one that accepts anything", True,
        _patch("src/net/socket.js",
               "-  const socket = tls.connect(port, host, { servername: host });\n"
               "+  const socket = tls.connect(port, host, { servername: host, checkServerIdentity: () => undefined });"),
    ),
    # ------------------------------------------------------ tls, no flag
    LabelledDiff(
        "cl-js-tls-neg-01", JS, "tls", "Agent restored to checking certificates", False,
        _patch("src/clients/payments.js",
               "-const agent = new https.Agent({ keepAlive: true, rejectUnauthorized: false });\n"
               "+const agent = new https.Agent({ keepAlive: true, rejectUnauthorized: true });"),
    ),
    LabelledDiff(
        "cl-js-tls-neg-02", JS, "tls", "Agent given a private CA", False,
        _patch("src/clients/internal.js",
               "+const agent = new https.Agent({ keepAlive: true, ca: fs.readFileSync(caPath) });"),
    ),
    LabelledDiff(
        "cl-js-tls-neg-03", JS, "tls", "Startup refuses to run with certificate checks off", False,
        _patch("src/bootstrap.js",
               "+if (process.env.NODE_TLS_REJECT_UNAUTHORIZED === '0') {\n"
               "+  throw new Error('certificate checks must stay on');\n"
               "+}"),
    ),
    LabelledDiff(
        "cl-js-tls-neg-04", JS, "tls", "Client option set to false", False,
        _patch("src/clients/api.js",
               "+const client = new ApiClient({ baseUrl, timeoutMs: 5000, retry: false });"),
    ),
    # -------------------------------------------------------- shell, flag
    LabelledDiff(
        "cl-js-shell-pos-01", JS, "shell", "git clone run through exec with a template literal", True,
        _patch("src/repos/clone.js",
               " const { exec } = require('child_process');\n"
               "-  execFile('git', ['clone', repoUrl, dir], callback);\n"
               "+  exec(`git clone ${repoUrl} ${dir}`, callback);"),
    ),
    LabelledDiff(
        "cl-js-shell-pos-02", JS, "shell", "Request path concatenated into execSync", True,
        _patch("src/admin/files.js",
               "+  child_process.execSync('rm -rf ' + req.body.path);"),
    ),
    LabelledDiff(
        "cl-js-shell-pos-03", JS, "shell", "Host concatenated into sh -c", True,
        _patch("src/net/ping.js",
               "+  const child = spawn('sh', ['-c', 'ping -c 1 ' + host]);"),
    ),
    LabelledDiff(
        "cl-js-shell-pos-04", JS, "shell", "Upload name concatenated into cp.exec", True,
        _patch("src/media/transcode.js",
               "+  cp.exec('ffmpeg -i ' + file + ' out.mp4', done);"),
    ),
    # ---------------------------------------------------- shell, no flag
    LabelledDiff(
        "cl-js-shell-neg-01", JS, "shell", "Regular expression exec on input", False,
        _patch("src/parse/route.js",
               "+  const match = pattern.exec(input);"),
    ),
    LabelledDiff(
        "cl-js-shell-neg-02", JS, "shell", "execFile with an argument list", False,
        _patch("src/repos/clone.js",
               "-  exec(`git clone ${repoUrl} ${dir}`, callback);\n"
               "+  execFile('git', ['clone', repoUrl, dir], callback);"),
    ),
    LabelledDiff(
        "cl-js-shell-neg-03", JS, "shell", "Fixed build command through exec", False,
        _patch("scripts/build.js",
               "+exec('npm run build', { cwd: root }, done);"),
    ),
    LabelledDiff(
        "cl-js-shell-neg-04", JS, "shell", "Regular expression exec on an interpolated string", False,
        _patch("src/parse/header.js",
               "+  const m = tokenPattern.exec(`${header} `);"),
    ),
    # ============================================================ TypeScript
    # ---------------------------------------------------------- sql, flag
    LabelledDiff(
        "cl-ts-sql-pos-01", TS, "sql", "Typed query built by concatenation", True,
        _patch("src/users/user.repository.ts",
               '+    const rows = await this.db.query<User>("SELECT * FROM users WHERE id = " + userId);'),
    ),
    LabelledDiff(
        "cl-ts-sql-pos-02", TS, "sql", "Unsafe raw query with an interpolated customer", True,
        _patch("src/orders/orders.service.ts",
               "+    return prisma.$queryRawUnsafe(`SELECT * FROM orders WHERE customer = '${customerId}'`);"),
    ),
    LabelledDiff(
        "cl-ts-sql-pos-03", TS, "sql", "DELETE string built from a token", True,
        _patch("src/sessions/revoke.ts",
               "+  const sql: string = \"DELETE FROM sessions WHERE token = '\" + token + \"'\";\n"
               "+  await client.query(sql);"),
    ),
    LabelledDiff(
        "cl-ts-sql-pos-04", TS, "sql", "Query-builder where clause concatenated", True,
        _patch("src/users/search.ts",
               "     .createQueryBuilder(\"user\")\n"
               "+    .where(\"user.name = '\" + name + \"'\")\n"
               "     .getMany();"),
    ),
    # ------------------------------------------------------ sql, no flag
    LabelledDiff(
        "cl-ts-sql-neg-01", TS, "sql", "Tagged template the driver parameterizes", False,
        _patch("src/orders/orders.service.ts",
               "-    return prisma.$queryRawUnsafe(`SELECT * FROM orders WHERE customer = '${customerId}'`);\n"
               "+    return prisma.$queryRaw`SELECT * FROM orders WHERE customer = ${customerId}`;"),
    ),
    LabelledDiff(
        "cl-ts-sql-neg-02", TS, "sql", "Repository find with a where object", False,
        _patch("src/users/user.repository.ts",
               "+    const users = await this.repo.find({ where: { email } });"),
    ),
    LabelledDiff(
        "cl-ts-sql-neg-03", TS, "sql", "Heading that reads like a query", False,
        _patch("src/ui/workspaces.ts",
               '+  const heading: string = "Select a workspace from the list: " + workspaces.length;'),
    ),
    LabelledDiff(
        "cl-ts-sql-neg-04", TS, "sql", "Debug log with an interpolated duration", False,
        _patch("src/db/metrics.ts",
               "+  this.logger.debug(`select query took ${ms} ms`);"),
    ),
    # ---------------------------------------------------------- tls, flag
    LabelledDiff(
        "cl-ts-tls-pos-01", TS, "tls", "Keep-alive agent that accepts any certificate", True,
        _patch("src/http/agent.ts",
               "+export const httpsAgent = new Agent({ rejectUnauthorized: false, keepAlive: true });"),
    ),
    LabelledDiff(
        "cl-ts-tls-pos-02", TS, "tls", "Certificate checks turned off through a bracketed env key", True,
        _patch("src/main.ts",
               '+process.env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0";\n'
               " bootstrap();"),
    ),
    LabelledDiff(
        "cl-ts-tls-pos-03", TS, "tls", "got client extended without certificate checks", True,
        _patch("src/http/client.ts",
               "-export const client = got.extend({ prefixUrl: BASE_URL });\n"
               "+export const client = got.extend({ prefixUrl: BASE_URL, https: { rejectUnauthorized: false } });"),
    ),
    LabelledDiff(
        "cl-ts-tls-pos-04", TS, "tls", "Child process started with certificate checks off", True,
        _patch("src/workers/spawn.ts",
               '+  const env = { ...process.env, NODE_TLS_REJECT_UNAUTHORIZED: "0" };\n'
               "   const worker = fork(workerPath, [], { env });"),
    ),
    # ------------------------------------------------------ tls, no flag
    LabelledDiff(
        "cl-ts-tls-neg-01", TS, "tls", "Insecure agent replaced by a private CA", False,
        _patch("src/http/agent.ts",
               "-export const httpsAgent = new Agent({ rejectUnauthorized: false, keepAlive: true });\n"
               "+export const httpsAgent = new Agent({ ca: readFileSync(caPath), keepAlive: true });"),
    ),
    LabelledDiff(
        "cl-ts-tls-neg-02", TS, "tls", "Minimum TLS version raised", False,
        _patch("src/http/tls.ts",
               '+const tlsOptions: SecureContextOptions = { minVersion: "TLSv1.2" };'),
    ),
    LabelledDiff(
        "cl-ts-tls-neg-03", TS, "tls", "Self-signed certificates refused by default", False,
        _patch("src/config/defaults.ts",
               "+  allowSelfSigned: false,"),
    ),
    LabelledDiff(
        "cl-ts-tls-neg-04", TS, "tls", "Health check asserts certificate checks are on", False,
        _patch("src/health/tls-check.ts",
               "+  assert.strictEqual(httpsAgent.options.rejectUnauthorized, true);"),
    ),
    # -------------------------------------------------------- shell, flag
    LabelledDiff(
        "cl-ts-shell-pos-01", TS, "shell", "Container id interpolated into execSync", True,
        _patch("src/ops/logs.ts",
               '+  const logs = execSync(`docker logs ${containerId}`, { encoding: "utf8" });'),
    ),
    LabelledDiff(
        "cl-ts-shell-pos-02", TS, "shell", "Branch name concatenated into a promisified exec", True,
        _patch("src/vcs/checkout.ts",
               " const execAsync = promisify(exec);\n"
               '+  const { stdout } = await execAsync("git checkout " + branchName);'),
    ),
    LabelledDiff(
        "cl-ts-shell-pos-03", TS, "shell", "spawn given a joined command and shell: true", True,
        _patch("src/tasks/run.ts",
               '+  const child = spawn(command + " " + args.join(" "), { shell: true });'),
    ),
    LabelledDiff(
        "cl-ts-shell-pos-04", TS, "shell", "Upload path concatenated into child_process.exec", True,
        _patch("src/uploads/extract.ts",
               '+  child_process.exec("unzip " + upload.path + " -d " + dest, done);'),
    ),
    # ---------------------------------------------------- shell, no flag
    LabelledDiff(
        "cl-ts-shell-neg-01", TS, "shell", "spawnSync with an argument list", False,
        _patch("src/vcs/status.ts",
               '+  const result = spawnSync("git", ["status", "--porcelain"], { encoding: "utf8" });'),
    ),
    LabelledDiff(
        "cl-ts-shell-neg-02", TS, "shell", "Route pattern exec on an interpolated string", False,
        _patch("src/router/match.ts",
               "+  const match: RegExpExecArray | null = ROUTE.exec(`${method} ${path}`);"),
    ),
    LabelledDiff(
        "cl-ts-shell-neg-03", TS, "shell", "Fixed install command through execSync", False,
        _patch("scripts/setup.ts",
               '+execSync("npm ci", { stdio: "inherit" });'),
    ),
    LabelledDiff(
        "cl-ts-shell-neg-04", TS, "shell", "Login shell read from the environment", False,
        _patch("src/terminal/shell.ts",
               '+const shell: string = process.env.SHELL ?? "/bin/sh";'),
    ),
]

LANGUAGES = (PY, JS, TS)
FAMILIES = ("sql", "tls", "shell")
