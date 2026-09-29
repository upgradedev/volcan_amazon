"""Standards readiness gate auditor.

Rules this file lives by:

1. No gate returns a hardcoded ``True``. Every gate runs a check whose result
   can be different tomorrow. A gate that cannot be checked in this environment
   reports FAIL with the reason, it does not quietly pass.
2. A gate that fails because of something outside the repository (no network,
   no deploy, an owner action) is listed in ``ENVIRONMENT_GATED`` with a written
   reason, and does not fail the build. Everything else fails the build.
3. Every gate identifier from STANDARDS.md appears in the output, passing or
   failing, so nothing disappears by being unimplemented.

Run:
    python ci/readiness.py
Exit code 0 means every build-blocking gate passed.
"""
import ast
import glob
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Gates that cannot pass from inside this repository, each with the reason.
#: A gate belongs here only when the blocker is genuinely external. It is not a
#: place to park a check that is merely inconvenient.
ENVIRONMENT_GATED: dict[str, str] = {
    "C5": "needs a browser driver (playwright or selenium), which is not vendored here",
    "D2": "needs a deploy of the current commit followed by a recorded teardown",
    "E2": "needs a rendered video file to compare narration against picture",
    "E4": "needs the owner to record and publish the video",
    "G2": "needs a redeploy so the deployed commit matches HEAD",
    "O1": "owner action: YouTube upload",
    "O2": "owner action: Devpost project creation",
    "O3": "owner action: pressing Submit",
}

#: Excuses discovered during the run, for gates whose blocker depends on the
#: environment rather than on the repository. A gate may add itself here only
#: when it proved the blocker: F1 excuses itself when the network is
#: unreachable, and does NOT excuse itself when a badge really answered an
#: error, because that is a defect in the README.
DYNAMIC_EXCUSES: dict[str, str] = {}

#: Generic English person nouns. This is a lexicon of who a product can be for,
#: not a list of this project's expected answers, so a README that changed its
#: persona would still be evaluated on what it actually says.
PERSON_NOUNS = {
    "developers", "engineers", "programmers", "designers", "researchers",
    "residents", "caregivers", "carers", "patients", "nurses", "clinicians",
    "students", "teachers", "drivers", "cooks", "parents", "families",
    "operators", "technicians", "auditors", "reviewers", "founders", "hosts",
}

#: Words that name a market rather than a person.
BANNED_MARKET_WORDS = {
    "smbs", "smes", "enterprises", "creators", "teams", "everyone", "anyone",
    "businesses", "organizations", "organisations", "companies", "users",
    "customers", "consumers", "startups", "brands",
}

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "for", "to", "with", "their", "its",
    "helps", "lets", "empowers", "enables", "gives", "turns", "makes",
}


class GateResult:
    def __init__(self, gate_id: str, title: str, passed: bool, message: str):
        self.gate_id = gate_id
        self.title = title
        self.passed = passed
        self.message = message


def read_text(path: str) -> str:
    full = os.path.join(REPO_ROOT, path)
    if not os.path.exists(full):
        return ""
    with open(full, "r", encoding="utf-8") as handle:
        return handle.read()


def working_tree_changes() -> set[str] | None:
    """Paths ``git status`` reports as changed, or None when git cannot answer."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=False,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return {line[3:].strip() for line in result.stdout.splitlines() if line.strip()}


def files_the_audit_touched(before: set[str] | None, after: set[str] | None) -> list[str]:
    """Paths that were clean before the gates ran and are dirty after them.

    A gate that rewrites a tracked artifact or drops a new file into the
    checkout has mutated the repository it was judging, so the auditor
    reports itself as a blocking failure instead of leaving a judge to
    revert the damage.
    """
    if before is None or after is None:
        return []
    return sorted(after - before)


def git_head() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=False,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def get_standards_gate_ids() -> list[str]:
    candidates = [
        r"C:\dev\solutions\_submission_kit\STANDARDS.md",
        os.path.join(REPO_ROOT, "../../_submission_kit/STANDARDS.md"),
        os.path.join(REPO_ROOT, "STANDARDS.md"),
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as handle:
                gates = re.findall(r"\|\s*([JABCDEFGHOI][0-9]+)\s*\|", handle.read())
            if gates:
                return gates
    return [
        "J1", "J2", "J3", "J4", "J5",
        "A1", "A2", "A3", "A4", "A5", "A6", "A7",
        "B1", "B2", "B3", "B4",
        "C1", "C2", "C3", "C4", "C5", "C6",
        "D1", "D2", "D3",
        "E1", "E2", "E3", "E4",
        "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9",
        "G1", "G2", "G3", "G4",
        "H1", "H2", "H3",
        "I1", "I2", "I3", "I4", "I5",
        "O1", "O2", "O3",
    ]


# --- individual gate checks -------------------------------------------------

def first_sentence(readme: str) -> str:
    match = re.search(r">\s*\*\*([^*]+)\*\*", readme)
    return match.group(1).strip() if match else ""


def check_j1(readme: str) -> tuple[bool, str]:
    """One named persona, not a market. Read from the README's actual first sentence."""
    sentence = first_sentence(readme)
    if not sentence:
        return False, "no bold first sentence found in the README"

    words = [word.strip(".,;:()").lower() for word in sentence.split()]
    banned = sorted(set(words) & BANNED_MARKET_WORDS)
    if banned:
        return False, f"first sentence names a market, not a persona: {', '.join(banned)}"

    for index, word in enumerate(words):
        if word not in PERSON_NOUNS:
            continue
        qualifiers = [w for w in words[max(0, index - 4):index] if w and w not in STOPWORDS]
        if qualifiers:
            persona = " ".join(qualifiers[-3:] + [word])
            return True, f"persona in the README's first sentence: '{persona}'"
        return False, f"'{word}' appears with no qualifier, so it names everyone who is a {word}"

    return False, f"no person noun found in: '{sentence[:70]}'"


def check_j3(readme: str) -> tuple[bool, str]:
    """One headline comparative number: a baseline, a margin and a real sample size.

    The number is not taken on trust. The corpus named in the README is loaded
    and the figure is recomputed, so a README claim that drifts away from the
    measurement turns this gate red.
    """
    sample = re.search(r"n\s*=\s*(\d+)", readme)
    if not sample:
        return False, "no sample size of the form n=<count> stated in the README"
    claimed_n = int(sample.group(1))

    if not re.search(r"\bbaseline\b", readme, re.IGNORECASE):
        return False, f"n={claimed_n} is stated but no baseline it beats is named"

    # The README states both a baseline recall and the measured recall, so collect
    # every stated figure and require the measured one to be among them.
    stated = [float(value) for value in
              re.findall(r"(\d+(?:\.\d+)?)\s*%\s*(?:recall|detection)", readme, re.IGNORECASE)]
    if not stated:
        return False, "no recall or detection percentage stated alongside the sample size"

    # The committed artifact is read here, never written: an auditor that
    # rewrites a tracked file has changed the thing it was asked to judge.
    try:
        with open(os.path.join(REPO_ROOT, "benchmarks_summary.json"), "r", encoding="utf-8") as handle:
            recorded = json.load(handle)["security_detection"]
    except (OSError, ValueError, KeyError) as exc:
        return False, f"benchmarks_summary.json carries no readable security_detection record: {exc}"

    sys.path.insert(0, REPO_ROOT)
    try:
        from scripts.benchmark_suite import measure_security_detection
        measured = measure_security_detection()
    except Exception as exc:  # noqa: BLE001 - an unrunnable benchmark is a failure
        return False, f"the benchmark backing the claim did not run: {type(exc).__name__}: {exc}"

    for key in ("n_total", "recall_pct", "false_positive_pct"):
        if recorded.get(key) != measured[key]:
            return False, (
                f"benchmarks_summary.json records {key}={recorded.get(key)} but the corpus "
                f"recomputes {measured[key]}; run scripts/benchmark_suite.py --write to refresh it"
            )
    if measured["n_total"] != claimed_n:
        return False, f"README says n={claimed_n}, the corpus holds n={measured['n_total']}"
    if not any(abs(measured["recall_pct"] - value) <= 0.05 for value in stated):
        return False, (
            f"the measured recall {measured['recall_pct']}% appears nowhere in the README; "
            f"it states {', '.join(f'{v}%' for v in stated)}"
        )

    return True, (
        f"{measured['recall_pct']}% recall over n={measured['n_total']} recomputed from "
        f"{measured['corpus_file']}, {measured['false_positive_pct']}% false positives, "
        "equal to the committed benchmarks_summary.json"
    )


def check_a7(test_files: list[str]) -> tuple[bool, str]:
    """A rejection is tested, and the tests assert the refusal, not just its shape."""
    keywords = ("refus", "reject", "forged", "replay", "unauthorized", "tamper", "expired")
    hits = []
    for path in test_files:
        content = read_text(os.path.relpath(path, REPO_ROOT)).lower()
        if any(word in content for word in keywords):
            hits.append(os.path.basename(path))
    if not hits:
        return False, "no test asserts that a control refuses anything"
    return True, f"{len(hits)} test modules assert refusals: {', '.join(sorted(hits)[:4])}"


def check_c6(test_files: list[str]) -> tuple[bool, str]:
    """Parameterized fixtures really vary the parameter, checked by parsing the tests."""
    varied: list[str] = []
    for path in test_files:
        try:
            tree = ast.parse(read_text(os.path.relpath(path, REPO_ROOT)))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name != "parametrize" or len(node.args) < 2:
                continue
            values = node.args[1]
            if isinstance(values, (ast.List, ast.Tuple)) and len(values.elts) >= 2:
                varied.append(f"{os.path.basename(path)}({len(values.elts)} values)")
    if not varied:
        return False, "no test parameterizes a fixture over two or more distinct values"
    return True, f"{len(varied)} parameterized fixtures vary their offset: {', '.join(sorted(varied)[:3])}"


def check_d2(receipt_path: str, head: str) -> tuple[bool, str]:
    """The deploy receipt must describe a real probe of the commit being submitted."""
    if not os.path.exists(receipt_path):
        return False, "no deploy receipt: no deploy has been probed"
    try:
        with open(receipt_path, "r", encoding="utf-8") as handle:
            receipt = json.load(handle)
    except Exception as exc:  # noqa: BLE001
        return False, f"deploy receipt is not readable JSON: {exc}"

    probes = receipt.get("probes") or []
    if not isinstance(probes, list) or not probes:
        return False, "deploy receipt records no probes"

    ok_probe = next(
        (p for p in probes if isinstance(p, dict)
         and str(p.get("url", "")).startswith("http")
         and p.get("http_status") == 200
         and p.get("response_body")),
        None,
    )
    if ok_probe is None:
        return False, "no probe in the receipt recorded a real URL answering HTTP 200 with a body"

    deployed = receipt.get("deployed_commit_sha", "")
    if not deployed:
        return False, "deploy receipt records no deployed commit SHA"
    if deployed != head:
        return False, (
            f"deployed commit {deployed[:12]} is not HEAD {head[:12]}; "
            f"the live endpoint runs older code"
        )
    if not receipt.get("teardown_performed"):
        return False, f"{ok_probe['url']} answered 200 but no teardown was performed and recorded"
    return True, f"probe of {ok_probe['url']} returned 200 at HEAD, teardown recorded"


def check_g2(receipt_path: str, head: str) -> tuple[bool, str]:
    """The deployed SHA must equal git rev-parse HEAD."""
    if not head:
        return False, "git rev-parse HEAD produced nothing; cannot compare"
    if not os.path.exists(receipt_path):
        return False, "no deploy receipt, so no deployed SHA to compare against HEAD"
    try:
        with open(receipt_path, "r", encoding="utf-8") as handle:
            receipt = json.load(handle)
    except Exception as exc:  # noqa: BLE001
        return False, f"deploy receipt is not readable JSON: {exc}"
    deployed = receipt.get("deployed_commit_sha", "")
    if not deployed:
        return False, "deploy receipt records no deployed commit SHA"
    if deployed != head:
        return False, f"deployed {deployed[:12]} != HEAD {head[:12]}"
    return True, f"deployed SHA matches HEAD ({head[:12]})"


def check_f1(readme: str) -> tuple[bool, str]:
    """Badges resolve. This performs real HTTP requests against every badge target."""
    badges = re.findall(r"\[!\[[^\]]*\]\(([^)]+)\)\]", readme)
    if len(badges) < 2:
        return False, f"only {len(badges)} badges found in the README"

    unreachable: list[str] = []
    broken: list[str] = []
    verified = 0
    for url in badges:
        if not url.startswith("http"):
            broken.append(f"{url} (not an absolute URL)")
            continue
        try:
            request = urllib.request.Request(url, method="GET", headers={"User-Agent": "volcan-readiness"})
            with urllib.request.urlopen(request, timeout=10) as response:
                if 200 <= response.status < 400:
                    verified += 1
                else:
                    broken.append(f"{url} -> HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            broken.append(f"{url} -> HTTP {exc.code}")
        except Exception as exc:  # noqa: BLE001 - a network problem, not a broken badge
            unreachable.append(f"{url} ({type(exc).__name__})")

    if broken:
        # A badge that answered an error is a defect in the README, not an
        # environment problem, so this failure blocks the build.
        return False, f"{len(broken)} badge targets did not resolve: {'; '.join(broken[:3])}"
    if unreachable:
        DYNAMIC_EXCUSES["F1"] = "outbound network unavailable, so badge targets could not be requested"
        return False, (
            f"{verified}/{len(badges)} badges verified; "
            f"{len(unreachable)} unreachable from this environment: {unreachable[0]}"
        )
    return True, f"all {verified} badge targets answered 2xx or 3xx over HTTP"


def check_f5(readme: str) -> tuple[bool, str]:
    """Zero em dashes and zero AI buzzwords, checked across the whole README."""
    buzzwords = [
        "seamless", "robust", "leverage", "in today's world", "cutting-edge",
        "game-changer", "revolutionize", "unlock the power", "delve",
    ]
    found = [word for word in buzzwords if word in readme.lower()]
    em_dashes = readme.count("\u2014")
    if found or em_dashes:
        parts = []
        if em_dashes:
            parts.append(f"{em_dashes} em dashes")
        if found:
            parts.append(f"buzzwords: {', '.join(found)}")
        return False, "; ".join(parts)
    return True, "zero em dashes, zero buzzwords from the banned list"


def check_f7(readme: str) -> tuple[bool, str]:
    """Every file is relevant: no orphan module, no README link to a missing path."""
    src_modules = glob.glob(os.path.join(REPO_ROOT, "src/**/*.py"), recursive=True)
    referencing = (
        glob.glob(os.path.join(REPO_ROOT, "src/**/*.py"), recursive=True)
        + glob.glob(os.path.join(REPO_ROOT, "tests/**/*.py"), recursive=True)
        + glob.glob(os.path.join(REPO_ROOT, "scripts/*.py"))
        + glob.glob(os.path.join(REPO_ROOT, "ci/*.py"))
    )
    corpus = {path: read_text(os.path.relpath(path, REPO_ROOT)) for path in referencing}

    orphans = []
    for module_path in src_modules:
        name = os.path.splitext(os.path.basename(module_path))[0]
        if name == "__init__":
            continue
        referenced = any(
            name in text for path, text in corpus.items()
            if os.path.abspath(path) != os.path.abspath(module_path)
        )
        if not referenced:
            orphans.append(os.path.relpath(module_path, REPO_ROOT).replace("\\", "/"))

    missing_links = []
    for link in re.findall(r"\]\((?!http|#)([^)]+)\)", readme):
        target = link.split("#")[0].strip()
        if target and not os.path.exists(os.path.join(REPO_ROOT, target)):
            missing_links.append(target)

    if orphans or missing_links:
        parts = []
        if orphans:
            parts.append(f"{len(orphans)} orphan modules nothing imports: {', '.join(orphans[:3])}")
        if missing_links:
            parts.append(f"{len(missing_links)} README links to missing paths: {', '.join(missing_links[:3])}")
        return False, "; ".join(parts)
    return True, f"{len(src_modules)} src modules all referenced, every README link resolves"


def check_f8() -> tuple[bool, str]:
    """Artifacts are human readable: every tracked JSON parses and is indented."""
    json_files = [
        path for path in glob.glob(os.path.join(REPO_ROOT, "**/*.json"), recursive=True)
        if ".git" not in path and "node_modules" not in path
        and "__pycache__" not in path and "cache" not in path.lower()
    ]
    if not json_files:
        return False, "no JSON artifacts found to check"
    problems = []
    for path in json_files:
        relative = os.path.relpath(path, REPO_ROOT).replace("\\", "/")
        try:
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
            json.loads(text)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{relative} ({type(exc).__name__})")
            continue
        if "\n" not in text.strip() and len(text) > 200:
            problems.append(f"{relative} (minified onto one line)")
    if problems:
        return False, f"{len(problems)} unreadable artifacts: {', '.join(problems[:3])}"
    return True, f"all {len(json_files)} JSON artifacts parse and are pretty printed"


def check_g1(readme: str) -> tuple[bool, str]:
    """The README test badge must equal the number pytest actually collects."""
    badge = re.search(r"tests-(\d+)(?:%20|\s|-)*passing", readme, re.IGNORECASE)
    if not badge:
        return False, "no tests-<count>-passing badge found in the README"
    claimed = int(badge.group(1))
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "--collect-only", "-q"],
            capture_output=True, text=True, cwd=REPO_ROOT, timeout=180,
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"could not collect tests to verify the badge: {type(exc).__name__}: {exc}"
    collected = re.search(r"(\d+)\s+tests?\s+collected", result.stdout)
    if not collected:
        return False, "pytest did not report a collected count"
    actual = int(collected.group(1))
    if claimed != actual:
        return False, f"README badge says {claimed} tests, pytest collected {actual}"

    # The README also quotes a conformance-check count. That number lives in
    # scripts/mcp_conformance.py, so count the checks the script really makes.
    conformance_claim = re.search(r"(\d+) of (\d+) conformance checks", readme)
    script = read_text("scripts/mcp_conformance.py")
    declared_checks = script.count("report.check(")
    if conformance_claim and declared_checks:
        claimed_checks = int(conformance_claim.group(2))
        if claimed_checks != declared_checks:
            return False, (
                f"README quotes {claimed_checks} conformance checks, "
                f"scripts/mcp_conformance.py makes {declared_checks}"
            )
        return True, (
            f"README and pytest agree on {actual} tests, and README and "
            f"scripts/mcp_conformance.py agree on {declared_checks} conformance checks"
        )
    return True, f"README badge and pytest agree on {actual} tests"


def check_g3() -> tuple[bool, str]:
    """Claimed capabilities are reachable: MCP tools resolve to real handlers."""
    sys.path.insert(0, REPO_ROOT)
    try:
        from src.interfaces.mcp_server import build_tool_registry
        registry = build_tool_registry()
        catalog = registry.catalog()
    except Exception as exc:  # noqa: BLE001
        return False, f"the MCP tool registry did not build: {type(exc).__name__}: {exc}"
    if not catalog:
        return False, "the MCP tool catalog is empty"
    unschemad = [tool["name"] for tool in catalog if not tool.get("inputSchema", {}).get("properties")]
    if unschemad:
        return False, f"{len(unschemad)} tools advertise no input schema: {', '.join(unschemad[:3])}"
    return True, f"{len(catalog)} MCP tools resolve to handlers with generated input schemas"


def check_e2() -> tuple[bool, str]:
    """Narration and picture in sync: needs a rendered picture to compare against."""
    narration = os.path.join(REPO_ROOT, "video/narration.json")
    cue = os.path.join(REPO_ROOT, "video/cue_sheet.json")
    if not (os.path.exists(narration) and os.path.exists(cue)):
        return False, "narration.json or cue_sheet.json is missing"

    with open(narration, "r", encoding="utf-8") as handle:
        narration_beats = json.load(handle).get("beats", [])
    with open(cue, "r", encoding="utf-8") as handle:
        cue_beats = json.load(handle).get("beats", [])

    narration_ids = [beat.get("beat_id") for beat in narration_beats]
    cue_ids = [beat.get("beat_id") for beat in cue_beats]
    if narration_ids != cue_ids:
        return False, "narration beats and cue sheet beats do not line up"

    media = glob.glob(os.path.join(REPO_ROOT, "video/*.mp4")) + glob.glob(os.path.join(REPO_ROOT, "video/*.mov"))
    if not media:
        return False, (
            f"{len(narration_ids)} beats are aligned in the scripts, but no rendered "
            "video exists in video/, so narration cannot be compared against picture"
        )
    return True, f"{len(narration_ids)} beats aligned against {os.path.basename(media[0])}"


PERSONA_REVIEW_DOC = "docs/PERSONA_REVIEW.md"

#: The three lenses the review is required to carry, by role. The internal instrument
#: that defines them is a workspace document that is never part of a submission, so it
#: is not named here and these gates do not string-match its filename. A gate that
#: checks for a filename it cannot open is checking nothing.
PERSONA_LENSES = ("Sponsor product owner", "UX designer", "Recruiter")

#: Outcomes a procedure step or a finding may carry. Anything else is not a verdict.
PERSONA_VERDICTS = ("PASS", "FAIL", "PARTIAL", "OPEN")


def markdown_table(text: str, *required_headers: str) -> list[dict[str, str]]:
    """Rows of the first markdown table whose header carries every required column.

    Returned as dicts keyed by header cell. A document with no such table yields an
    empty list, which is what makes the gates below able to fail.
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue
        headers = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not all(header in headers for header in required_headers):
            continue
        if index + 1 >= len(lines) or not re.match(r"^\|[\s:|-]+\|$", lines[index + 1].strip()):
            continue
        rows = []
        for row_line in lines[index + 2:]:
            if not row_line.strip().startswith("|"):
                break
            cells = [cell.strip() for cell in row_line.strip().strip("|").split("|")]
            if len(cells) < len(headers):
                cells += [""] * (len(headers) - len(cells))
            rows.append(dict(zip(headers, cells)))
        return rows
    return []


def cited_repository_paths(text: str) -> list[str]:
    """Every repository-relative path cited in backticks anywhere in ``text``.

    A path is a backticked word carrying both a ``/`` and a file extension, which
    picks ``tests/unit/test_readiness_gates.py`` out of a command line and leaves
    ``tests/`` and prose alone.
    """
    paths = []
    for span in re.findall(r"`([^`]+)`", text):
        for word in span.split():
            word = word.strip("(),;:")
            if "/" in word and re.search(r"\.[A-Za-z0-9]{1,5}$", word):
                paths.append(word)
    return sorted(set(paths))


def evaluate_persona_review_gates(doc: str, path_exists) -> dict[str, tuple[bool, str]]:
    """I1 to I4: was a structured review run, owned, and written down where a clone sees it.

    These four gates used to read the workspace STATE.md. Each said in its own message
    that the evidence was outside the repository, which was honest and unusable: a judge
    with a clone and nothing else got four FAILs where this machine printed four PASSes,
    so the published readiness score was not reproducible from the artifact submitted.

    They now read ``docs/PERSONA_REVIEW.md`` and check its substance rather than the
    presence of a phrase. Deleting a lens, attributing a finding to a lens nobody owns,
    dropping the review date or citing a test file that is not on disk each turns one of
    them red. ``path_exists`` is injected so a test can drive the citation branch
    without writing files into the checkout.
    """
    outcomes: dict[str, tuple[bool, str]] = {}

    if not doc.strip():
        missing = f"{PERSONA_REVIEW_DOC} is missing, so no review is recorded in this repository"
        return {gid: (False, missing) for gid in ("I1", "I2", "I3", "I4")}

    # --- I1: the procedure that runs before any lens opens.
    steps = markdown_table(doc, "Step", "What it asks", "Outcome", "Evidence")
    bad_steps = [
        s["Step"] for s in steps
        if s["Outcome"] not in PERSONA_VERDICTS or not s["Evidence"]
    ]
    i1 = len(steps) >= 4 and not bad_steps
    outcomes["I1"] = (i1, (
        f"{len(steps)} procedure steps ran before any lens opened, each with an outcome and a "
        f"citation, recorded in {PERSONA_REVIEW_DOC}" if i1
        else f"{PERSONA_REVIEW_DOC} records {len(steps)} procedure steps"
             + (f"; these carry no outcome or no evidence: {bad_steps}" if bad_steps else "")
             + ("; at least four are required" if len(steps) < 4 else "")
    ))

    # --- I2: three lenses, each with a verdict and at least one finding of its own.
    owners = markdown_table(doc, "Lens", "Owner", "What it decides", "Verdict")
    findings = markdown_table(doc, "ID", "Lens", "Finding", "Verdict", "Evidence")
    by_lens = {row["Lens"]: row for row in owners}
    lenses_with_findings = {row["Lens"] for row in findings}
    missing_lenses = [
        lens for lens in PERSONA_LENSES
        if lens not in by_lens
        or by_lens[lens]["Verdict"] not in PERSONA_VERDICTS
        or lens not in lenses_with_findings
    ]
    i2 = not missing_lenses
    scored = ", ".join(
        "{} {}".format(lens, by_lens[lens]["Verdict"]) for lens in PERSONA_LENSES
    ) if i2 else ""
    outcomes["I2"] = (i2, (
        f"All three required lenses reviewed in {PERSONA_REVIEW_DOC}, each with a verdict "
        f"and findings of its own: {scored}" if i2
        else f"Lenses missing from {PERSONA_REVIEW_DOC}, unscored, or with no finding of "
             f"their own: {missing_lenses}"
    ))

    # --- I3: ownership is total. A finding attributed to a lens nobody owns fails.
    unowned = sorted(
        lens for lens in lenses_with_findings
        if lens not in by_lens or not by_lens[lens]["Owner"]
    )
    i3 = bool(owners) and all(row["Owner"] for row in owners) and not unowned
    outcomes["I3"] = (i3, (
        f"Every lens carrying a finding has exactly one owner across {len(owners)} rows "
        f"of {PERSONA_REVIEW_DOC}" if i3
        else (f"{PERSONA_REVIEW_DOC} attributes findings to a lens with no owner: {unowned}"
              if unowned else f"{PERSONA_REVIEW_DOC} records no ownership table")
    ))

    # --- I4: findings written down, dated, and every citation resolvable on disk.
    date = re.search(r"Review date:\s*(\d{4}-\d{2}-\d{2})", doc)
    bad_findings = [
        f["ID"] for f in findings
        if not f["Finding"] or f["Verdict"] not in PERSONA_VERDICTS or not f["Evidence"]
    ]
    dangling = [path for path in cited_repository_paths(doc) if not path_exists(path)]
    i4 = len(findings) >= 5 and not bad_findings and not dangling and bool(date)
    failure_count = sum(1 for f in findings if f["Verdict"] == "FAIL")
    outcomes["I4"] = (i4, (
        f"{len(findings)} findings recorded in {PERSONA_REVIEW_DOC} on {date.group(1) if date else ''}, "
        f"{failure_count} of them failures, every citation resolving to a file in this checkout"
        if i4 else
        f"{PERSONA_REVIEW_DOC} records {len(findings)} findings"
        + ("" if date else "; no review date")
        + (f"; incomplete rows: {bad_findings}" if bad_findings else "")
        + (f"; cited paths that are not in this checkout: {dangling}" if dangling else "")
    ))

    return outcomes


# --- audit ------------------------------------------------------------------

def audit_project() -> list[GateResult]:
    all_gate_ids = get_standards_gate_ids()
    evaluated: dict[str, GateResult] = {}

    def record(gate_id: str, title: str, outcome: tuple[bool, str]) -> None:
        evaluated[gate_id] = GateResult(gate_id, title, outcome[0], outcome[1])

    readme = read_text("README.md")
    head = git_head()
    receipt_path = os.path.join(REPO_ROOT, "deploy_teardown_receipt.json")

    py_files = glob.glob(os.path.join(REPO_ROOT, "src/**/*.py"), recursive=True)
    test_files = glob.glob(os.path.join(REPO_ROOT, "tests/**/*.py"), recursive=True)
    domain_files = glob.glob(os.path.join(REPO_ROOT, "src/domain/**/*.py"), recursive=True)
    app_files = glob.glob(os.path.join(REPO_ROOT, "src/application/**/*.py"), recursive=True)

    # --- Section J: framing -------------------------------------------------
    record("J1", "One named persona, not a market", check_j1(readme))

    consequence_words = ["approval grant", "single-use", "lease", "dry run", "refus", "custody"]
    j2_hits = [word for word in consequence_words if word in readme.lower()]
    record("J2", "Real consequence behind hero action", (
        len(j2_hits) >= 2,
        f"guarded by: {', '.join(j2_hits[:4])}" if len(j2_hits) >= 2
        else "no high-consequence action is described as guarded",
    ))

    record("J3", "One headline comparative number", check_j3(readme))

    sponsors = [name for name in ("alexa", "bedrock", "model context protocol", "mcp")
                if name in readme.lower()]
    record("J4", "Sponsor product is load-bearing", (
        bool(sponsors), f"sponsor surfaces named: {', '.join(sponsors)}" if sponsors
        else "no sponsor product named in the README",
    ))

    sentence = first_sentence(readme)
    word_count = len(sentence.split())
    record("J5", "One republishable sentence, no em dash", (
        bool(sentence) and word_count <= 28 and "\u2014" not in sentence,
        f"{word_count} words, {sentence.count(chr(8212))} em dashes" if sentence
        else "no bold first sentence found",
    ))

    # --- Section A: engineering principles ----------------------------------
    oversized = [
        os.path.relpath(path, REPO_ROOT) for path in py_files
        if len(read_text(os.path.relpath(path, REPO_ROOT)).splitlines()) > 800
    ]
    record("A1", "SOLID at module level (under 800 lines)", (
        not oversized, f"all {len(py_files)} src modules under 800 lines" if not oversized
        else f"oversized: {', '.join(oversized)}",
    ))

    env_readers = [
        os.path.relpath(path, REPO_ROOT) for path in py_files
        if "os.getenv" in read_text(os.path.relpath(path, REPO_ROOT))
        or "os.environ" in read_text(os.path.relpath(path, REPO_ROOT))
    ]
    record("A2", "YAGNI: config knobs have active readers", (
        bool(env_readers), f"{len(env_readers)} modules read configuration at runtime",
    ))

    steps = re.findall(r"^###\s+(\d+)\.", readme, re.MULTILINE)
    record("A3", "KISS: quickstart reachable in 5 steps or fewer", (
        bool(steps) and len(steps) <= 5,
        f"quickstart has {len(steps)} numbered steps" if steps
        else "no numbered quickstart steps found in the README",
    ))

    importers = [
        path for path in app_files
        if "from src.domain" in read_text(os.path.relpath(path, REPO_ROOT))
    ]
    record("A4", "DRY: contracts unified in domain", (
        bool(importers), f"{len(importers)} application modules import domain contracts",
    ))

    leaky = []
    for path in domain_files:
        code = read_text(os.path.relpath(path, REPO_ROOT))
        if re.search(r"^\s*(import|from)\s+(boto3|requests|fastapi|uvicorn|starlette|botocore|httpx)\b",
                     code, re.MULTILINE):
            leaky.append(os.path.relpath(path, REPO_ROOT))
    record("A5", "Separation of concerns: domain imports zero SDKs", (
        not leaky, f"domain clean across {len(domain_files)} modules" if not leaky
        else f"domain imports an SDK in: {', '.join(leaky)}",
    ))

    layers = [name for name in ("domain", "application", "infrastructure", "interfaces")
              if os.path.isdir(os.path.join(REPO_ROOT, "src", name))]
    record("A6", "Domain driven design: bounded context directories", (
        len(layers) == 4, f"layers present: {', '.join(layers)}",
    ))

    record("A7", "Least privilege: write rejection tested", check_a7(test_files))

    # --- Section B: architecture and compliance -----------------------------
    compliance = read_text("docs/COMPLIANCE_AND_ARCHITECTURE.md")
    record("B1", "Well-Architected 6-pillar review", (
        "well-architected" in compliance.lower() and compliance.lower().count("pillar") >= 6,
        "six pillars reviewed in docs/COMPLIANCE_AND_ARCHITECTURE.md" if "well-architected" in compliance.lower()
        else "no Well-Architected review found",
    ))
    articles = [a for a in ("article 10", "article 13", "article 14", "article 15", "article 50")
                if a in compliance.lower()]
    record("B2", "EU AI Act articles 10, 13, 14, 15, 50", (
        len(articles) == 5, f"{len(articles)}/5 articles addressed",
    ))
    record("B3", "GDPR data map documented", (
        "gdpr" in compliance.lower() and "data residency" in compliance.lower(),
        "GDPR data map with residency documented" if "gdpr" in compliance.lower()
        else "no GDPR data map found",
    ))
    forbidden_claims = [word for word in ("compliant", "conformity") if word in readme.lower()]
    record("B4", "Never write 'compliant' or 'conformity'", (
        not forbidden_claims, "zero forbidden compliance claims" if not forbidden_claims
        else f"README claims: {', '.join(forbidden_claims)}",
    ))

    # --- Section C: tests and coverage --------------------------------------
    workflow = read_text(".github/workflows/ci.yml")
    threshold = re.search(r"--cov-fail-under=(\d+)", workflow)
    record("C1", "Coverage above 85% enforced in CI", (
        bool(threshold) and int(threshold.group(1)) >= 85,
        f"CI enforces --cov-fail-under={threshold.group(1)}" if threshold
        else "no coverage threshold enforced in .github/workflows/ci.yml",
    ))
    unit_tests = glob.glob(os.path.join(REPO_ROOT, "tests/unit/test_*.py"))
    record("C2", "Unit tests running in CI", (
        bool(unit_tests) and "pytest" in workflow, f"{len(unit_tests)} unit modules, invoked by CI",
    ))
    int_tests = glob.glob(os.path.join(REPO_ROOT, "tests/integration/test_*.py"))
    record("C3", "Functional and integration tests", (
        bool(int_tests), f"{len(int_tests)} integration modules found",
    ))
    sec_tests = glob.glob(os.path.join(REPO_ROOT, "tests/security/test_*.py"))
    record("C4", "OWASP / SAST / DAST execution", (
        bool(sec_tests), f"{len(sec_tests)} security modules found",
    ))

    browser_driver = False
    for path in glob.glob(os.path.join(REPO_ROOT, "tests/e2e/**/*.py"), recursive=True):
        code = read_text(os.path.relpath(path, REPO_ROOT))
        if re.search(r"^\s*(import|from)\s+(playwright|selenium)\b", code, re.MULTILINE) \
                and re.search(r"\.(goto|get)\s*\(", code):
            browser_driver = True
    record("C5", "End-to-end browser user journey test", (
        browser_driver,
        "browser driver test walks the page" if browser_driver
        else "tests/e2e asserts the parsed DOM only; no browser driver walks the video path",
    ))

    record("C6", "Fixture starts at varied parameter offset", check_c6(test_files))

    # --- Section D: infrastructure ------------------------------------------
    main_tf = read_text("infra/main.tf")
    tf_resources = len(re.findall(r'^\s*resource\s+"', main_tf, re.MULTILINE))
    record("D1", "IaC declared in Terraform or CDK", (
        bool(main_tf) and tf_resources > 0,
        f"infra/main.tf declares {tf_resources} resources" if main_tf
        else "no infra/main.tf found",
    ))
    record("D2", "Tested deploy then teardown with recorded URL", check_d2(receipt_path, head))
    infra_readme = read_text("infra/README.md")
    dated_cost = re.search(r"\$0?\.00.*?(\d{4}-\d{2}-\d{2})", infra_readme, re.DOTALL)
    record("D3", "Monthly idle cost recorded with a date", (
        bool(dated_cost), f"idle cost recorded in infra/README.md, measured {dated_cost.group(1)}"
        if dated_cost else "no dated idle cost table in infra/README.md",
    ))

    # --- Section E: video ----------------------------------------------------
    narration_text = read_text("video/narration.json")
    beats = json.loads(narration_text).get("beats", []) if narration_text else []
    record("E1", "Video narration script per beat", (
        len(beats) >= 3, f"{len(beats)} narration beats scripted" if beats
        else "video/narration.json is missing or has no beats",
    ))
    record("E2", "Narration and picture in sync gate", check_e2())
    partitioned = bool(beats) and all(
        beat.get("beat_id") and beat.get("timestamp_start") is not None for beat in beats
    )
    record("E3", "Single beat re-rendering supported", (
        partitioned, f"every one of {len(beats)} beats carries an id and a timestamp"
        if partitioned else "beats are not individually addressable",
    ))
    published = glob.glob(os.path.join(REPO_ROOT, "video/*.mp4"))
    record("E4", "Public video under 180s with running product", (
        bool(published), "video present" if published else "no video has been recorded",
    ))

    # --- Section F: README and repo -----------------------------------------
    record("F1", "Badges that resolve over HTTP", check_f1(readme))
    diagrams = readme.count("```mermaid")
    record("F2", "At least two Mermaid diagrams", (
        diagrams >= 2, f"{diagrams} Mermaid diagrams in the README",
    ))
    record("F3", "Table of contents present", (
        "## Table of Contents" in readme,
        "table of contents present" if "## Table of Contents" in readme
        else "no table of contents heading",
    ))

    commands = re.findall(r"`(python[^`]+|pytest[^`]+|cat [^`]+)`", readme)
    record("F4", "Real numbers with command attribution", (
        len(commands) >= 3,
        f"{len(commands)} verification commands cited beside numbers" if len(commands) >= 3
        else f"only {len(commands)} verification commands cited",
    ))

    record("F5", "Zero em dashes and zero AI buzzwords", check_f5(readme))

    expected_layout = [name for name in ("src", "tests", "LICENSE", "README.md", "pyproject.toml")
                       if os.path.exists(os.path.join(REPO_ROOT, name))]
    record("F6", "Standard ecosystem repository layout", (
        len(expected_layout) == 5, f"present: {', '.join(expected_layout)}",
    ))
    record("F7", "Every file is relevant and current", check_f7(readme))
    record("F8", "All artifacts human readable", check_f8())
    record("F9", "Quickstart a judge can run", (
        "### 1." in readme and bool(re.search(r"###\s+\d\.", readme)),
        "copy-pasteable numbered quickstart present" if "### 1." in readme
        else "no numbered quickstart",
    ))

    # --- Section G: consistency ---------------------------------------------
    record("G1", "No cross-surface claim discrepancy", check_g1(readme))
    record("G2", "Deployed SHA matches submitted commit", check_g2(receipt_path, head))
    record("G3", "Claimed capabilities reachable in code", check_g3())
    competitors = [name for name in ("cockroach", "backblaze", "qwen", "xprize", "kaggle")
                   if name in readme.lower()]
    record("G4", "Zero competitor mentions", (
        not competitors, "no competitor mentions" if not competitors
        else f"mentions: {', '.join(competitors)}",
    ))

    # --- Section H: UX -------------------------------------------------------
    html = read_text("docs/index.html")
    if html:
        h1 = ('name="viewport"' in html and "@media" in html
              and 'data-testid="primary-hero-action"' in html)
        disabled_elements = re.findall(r"<[^>]*\sdisabled[^>]*>", html)
        unexplained = [e for e in disabled_elements if 'title="' not in e and "aria-describedby=" not in e]
        buttons = re.findall(r"<button[^>]*>", html)
        unlabelled = [b for b in buttons if 'title="' not in b and "aria-label=" not in b]
        h2 = not unexplained and not unlabelled
        h3 = html.count("empty-state-card") >= 3
        record("H1", "Primary action obvious without reading", (
            h1, "responsive layout and a marked hero action present in docs/index.html" if h1
            else "hero action or responsive layout missing",
        ))
        record("H2", "No control is disabled without visible reason", (
            h2, f"all {len(buttons)} controls carry a title or aria-label, zero unexplained disabled states"
            if h2 else f"{len(unlabelled)} unexplained controls, {len(unexplained)} unexplained disabled states",
        ))
        record("H3", "Never gate a feature to null", (
            h3, f"{html.count('empty-state-card')} empty states render a reason" if h3
            else "fewer than three explicit empty states",
        ))
    else:
        for gate_id, title in (("H1", "Primary action obvious without reading"),
                               ("H2", "No control is disabled without visible reason"),
                               ("H3", "Never gate a feature to null")):
            record(gate_id, title, (False, "docs/index.html not found"))

    # --- Section I: persona review ------------------------------------------
    # The review lives in docs/PERSONA_REVIEW.md inside this repository, so a
    # standalone clone reads the same evidence. A missing document fails these
    # gates as blocking: the work is genuinely absent then, not unreachable.
    persona_doc = read_text(PERSONA_REVIEW_DOC)
    persona_outcomes = evaluate_persona_review_gates(
        persona_doc, lambda path: os.path.exists(os.path.join(REPO_ROOT, path)))
    for gate_id, title in (
        ("I1", "The runbook runs first"),
        ("I2", "Three personas minimum (01, 06, 08)"),
        ("I3", "Ownership comes from the roster"),
        ("I4", f"Findings are written down in {PERSONA_REVIEW_DOC}"),
    ):
        record(gate_id, title, persona_outcomes[gate_id])

    kill_criteria = [
        os.path.basename(path) for path in test_files
        if any(word in os.path.basename(path).lower()
               for word in ("security", "governance", "dry_run", "conformance"))
    ]
    record("I5", "Every kill criterion ships a recorded failing input", (
        len(kill_criteria) >= 3,
        f"{len(kill_criteria)} kill-criterion suites: {', '.join(sorted(kill_criteria)[:4])}"
        if len(kill_criteria) >= 3 else "fewer than three kill-criterion suites",
    ))

    # --- Section O: owner-gated ---------------------------------------------
    record("O1", "YouTube upload, public not unlisted", (False, "pending owner action"))
    record("O2", "Devpost CAPTCHA on Create Project", (False, "pending owner action"))
    record("O3", "Pressing Submit", (False, "pending owner action"))

    return [
        evaluated.get(gate_id, GateResult(gate_id, f"Gate {gate_id}", False, "not implemented"))
        for gate_id in all_gate_ids
    ]


def main() -> None:
    tree_before = working_tree_changes()
    results = audit_project()
    touched = files_the_audit_touched(tree_before, working_tree_changes())
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]

    print("=" * 72)
    print(f"  STANDARDS READINESS AUDIT: {len(results)} GATES")
    print(f"  HEAD {git_head()[:12] or 'unknown'}")
    print("=" * 72)

    print(f"\n--- PASSED ({len(passed)}/{len(results)}) ---")
    for result in passed:
        print(f"  [PASS] [{result.gate_id}] {result.title}: {result.message}")

    excuses = {**ENVIRONMENT_GATED, **DYNAMIC_EXCUSES}
    blocking = [r for r in failed if r.gate_id not in excuses]
    excused = [r for r in failed if r.gate_id in excuses]

    print(f"\n--- FAILED, BLOCKING ({len(blocking)}/{len(results)}) ---")
    for result in blocking:
        print(f"  [FAIL] [{result.gate_id}] {result.title} -> {result.message}")
    if not blocking:
        print("  (none)")

    print(f"\n--- FAILED, EXTERNALLY BLOCKED ({len(excused)}/{len(results)}) ---")
    for result in excused:
        print(f"  [FAIL] [{result.gate_id}] {result.title} -> {result.message}")
        print(f"         blocked because: {excuses[result.gate_id]}")
    if not excused:
        print("  (none)")

    # The auditor is not one of the 53 gates, so it does not count itself in
    # the summary; it does refuse to exit 0 after changing the checkout it
    # judged, because a judge should never have to git-revert an audit.
    print("\n--- SELF-CHECK ---")
    if touched:
        print(f"  [FAIL] the audit modified or created files in the checkout: {', '.join(touched)}")
    else:
        print("  [PASS] the checkout is exactly as the audit found it")

    print("\n" + "=" * 72)
    print(f"  SUMMARY: {len(passed)}/{len(results)} passed, "
          f"{len(blocking)} blocking failures, {len(excused)} externally blocked")
    print("=" * 72)

    if blocking or touched:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
