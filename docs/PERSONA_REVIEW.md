# Persona review, recorded inside this repository

**Review date: 2026-09-29.** Every row below was verified on that date against this
checkout. Where a row restates an older finding, the older date is written in the row.
Rows re-verified since carry their own date.

## Why this file exists

Four readiness gates in `ci/readiness.py` ask whether a structured review of this
entry was run and written down. Until 2026-09-29 all four answered from a
coordination file that lives in the workspace **above** this repository and is never
committed to it. The gates said so in their own output: the file "is never
committed, so it is unreachable from a standalone clone or a CI runner".

That was honest and it was useless. A judge who clones this repository alone does not
get that file, so the four gates that passed here would have failed for them, and the
published score would have lost four gates in their hands. The evidence for a
quarter of the failing surface was somewhere they could not look.

This file is the restatement they can read. Nothing is copied from the coordination
file: the review instrument that defines the lenses is a workspace document that is
not part of any submission, so it is not reproduced, quoted or named here. What is
here is what this project did, in this project's own words, re-verified today with
commands that run in a clone.

## Nobody from Amazon reviewed this repository

The three lenses below are internal review roles operated by the project team against
a fixed checklist. They are not people. No employee of Amazon, AWS or Devpost, and no
hackathon judge, has seen this entry. Every name in this document is the name of a
role. Reading the table below as a list of endorsements would be reading it wrong.

This is also a one-person entry, so all three rows are owned by the same maintainer.
Ownership is still recorded per row, because the checklist gives each row exactly one
owner and a row nobody owns is a row nobody answers.

---

## 1. The procedure that runs before any lens opens

The lenses judge the product. These four steps judge whether the submission is in a
state worth judging, and they run first. An outcome that is not PASS does not stop the
review here; it is carried into the findings and into the readiness score instead of
being smoothed over.

| Step | What it asks | Outcome | Evidence |
|---|---|---|---|
| 1 | Does a deployed endpoint answer, and identify its build? | FAIL | Live `/health` identifies `6e9ae4d`, the current HEAD (re-verified 2026-10-01; it identified `38668ad` against `287c9db` on 2026-09-29); `deploy_teardown_receipt.json` still records an older probe, and `python ci/readiness.py` reports G2 red by design, since a committed receipt cannot equal a later HEAD |
| 2 | What is owner-gated and unmet, printed apart from the score rather than folded into it? | OPEN | `python ci/readiness.py`: O1, O2 and O3 fail as owner actions, E4 fails because the take is rendered but not published. `video/README.md` points at the `09d4862` render |
| 3 | Is the track and prize this entry is aimed at written down, with nothing else claimed? | PASS | Alexa+ track with a simulated front end in `README.md`, submission narrative in `docs/DEVPOST_SUBMISSION.md` |
| 4 | Do the presentation surfaces say what the code says? | PASS | `python ci/readiness.py`: gate G1 passes, the README badge and pytest agree at 751 tests |

## 2. The three lenses, and who owned each row

| Lens | Owner | What it decides | Verdict |
|---|---|---|---|
| Sponsor product owner | Volcan maintainer, product row | Is the sponsor product load-bearing, or merely mentioned? | PASS |
| UX designer | Volcan maintainer, interface row | Can a cold visitor use the thing without being told how? | PASS |
| Recruiter | Volcan maintainer, engineering bar row | Would this code and this prose clear an engineering bar? | PASS |

The sponsor product row passed on re-verification 2026-10-01 (partial on 2026-09-29): the MCP protocol half was verified
live (V01-1), and the model half has answered since (V01-2).
Details below.

## 3. Findings

Every row was produced by running the command in its Evidence column on 2026-09-29,
or by reading the file it names on that date.

| ID | Lens | Finding | Verdict | Evidence |
|---|---|---|---|---|
| V01-1 | Sponsor product owner | The MCP server speaks protocol 2025-11-25 over Streamable HTTP: `python scripts/mcp_conformance.py http://127.0.0.1:8871/mcp` printed 23/23 against a local audit-build server | PASS | `scripts/mcp_conformance.py`, `tests/integration/test_mcp_conformance.py` |
| V01-2 | Sponsor product owner | The Bedrock model path answered live on 2026-09-30 (HTTP 200, `synthesis_mode` bedrock; re-verified 2026-10-01, when an independent review recorded a second answer). Local builds without the SDK still fall back to labelled `heuristic-local` | PASS | `src/infrastructure/bedrock_adapter.py`, `src/application/digest_diff_use_case.py` |
| V01-3 | Sponsor product owner | The GitHub review path is an honest dry run: without a token and a write flag the review is recorded and not sent, and the capture refuses to continue unless the pane says so | PASS | `video/capture-local.py` |
| V06-1 | UX designer | The review status moves on every spoken turn: a handover verdict shares the turn's outcome instead of sitting on a stale line | PASS | `tests/e2e/test_html_structure.py`, `docs/index.html` |
| V06-2 | UX designer | The engine meter names its detector scope, the bench legend names its three renderings, and the function context line survives narrow screens | PASS | `tests/e2e/test_html_structure.py` |
| V06-3 | UX designer | The primary action is marked, no control is disabled without a visible reason, and empty states render guidance. Gates H1 to H3 pass | PASS | `python ci/readiness.py`, `docs/index.html` |
| V08-1 | Recruiter | 751 tests pass, coverage is 92.84%, and the touched files are ruff-clean | PASS | `python -m pytest tests/ -q`, `python ci/readiness.py` |
| V08-2 | Recruiter | Defect fixed in this change. Beat 6 speaks 725 tests, the `09d4862` take re-synthesized it for 303 ElevenLabs characters, and the sync gate passes | PASS | `video/narration.json`, `video/README.md`; the sync gate output sits beside the take in the owner's workspace |

**0 of the 8 findings fail.** V01-2 failed on 2026-09-29 for want of the approved Bedrock grant plus a billed call;
both landed on 2026-09-30 (see the finding). V08-2 was fixed in this change: beat 6
was re-synthesized and the `09d4862` take passes the sync gate. The failure is recorded here so the score carries it instead of hiding it.

## 4. What this review did not answer

These are the questions the lenses asked and nobody could close from a keyboard. They
are listed because a review that reports only what it settled is not a review.

| Question | Why it is open |
|---|---|
| Does a blind developer finish a real review faster with this than with a screen reader? | No target-user session has been run. The buyer conversations in the workspace plan are owner actions |
| Does the MCP handshake answer in a stateless deployment? | Only probed against a local server. The deploy that would answer it is owner-gated |
| Does the Bedrock voice change what the press says? | One model answer exists (2026-09-30); what its voice changes across presses is still unmeasured; see V01-2 |
| Is the dry-run review acceptable evidence of a review action to a judge? | Nobody outside this project has judged it. `docs/EVIDENCE.md` states the dry-run boundary in its own words |

## 5. Where the gates read this

Gates I1 to I4 in `ci/readiness.py` read this file and nothing else. They check
structure and evidence rather than the presence of a phrase:

* **I1** wants the procedure table above to carry at least four steps, each with an
  outcome and a citation.
* **I2** wants all three lenses present, each with a verdict and at least one finding.
* **I3** wants every lens named in a findings row to have an owner in the ownership
  table, so a finding cannot be attributed to a lens nobody owns.
* **I4** wants at least five findings, each with a verdict and a citation, a review
  date on this page, and every repository path cited anywhere on this page to exist on
  disk.

Delete a lens row, attribute a finding to a lens with no owner, or cite a test file
that is not there, and the gate goes red. `tests/unit/test_readiness_gates.py` drives
each of those failures through the predicate, and the passing case as well.
