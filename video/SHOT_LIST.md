# Volcan: shot list for the re-take on the live build

**Status: a plan, not recorded.** This take is to be recorded on the live build at
https://qylv1gxor9.execute-api.eu-west-1.amazonaws.com, with Amazon Bedrock answering. It
replaces the 2026-09-29 render of a local run of `09d4862`, which [`README.md`](README.md) in
this folder describes. That take's six-beat script is kept in history:
`git show fc10e7d:video/narration.json`.

The beat ids match [`narration.json`](narration.json) and [`cue_sheet.json`](cue_sheet.json)
one for one. Every time below is an ESTIMATE until `video/generate-narration.py` measures the
narration and the rehearsal measures the product's turns. The basis for each window is
written beside it in `narration.json`.

---

## What this take must show, and where

| Requirement | Where |
|---|---|
| A full spoken product turn inside the first 5 seconds | Cold open |
| The Alexa+ value first. "Not an Alexa skill" stays on screen, but it is not the opening line | Beat 1 |
| A real Amazon Bedrock answer, the model coverage line and the model's full answer | Beats 2 and 3 |
| "Amazon Bedrock", "AWS Lambda" and "DynamoDB" said on camera, for the AWS Builder mini | Beat 2 |
| Every product turn on camera in the product's own voice, with nothing talked over. That includes Request changes, which the last take talked over | Cold open, beats 2, 4 and 5 |
| A non-trivial pull request | Cold open, beats 4 and 5 |
| No hard-coded test count | No count is spoken; see the rules at the end |
| End on the repository and live URLs | Closing card |
| Under 3:00 | 156.5 s ESTIMATE, or 171.5 s with the optional slot |

## Time budget (ESTIMATE)

| Segment | From | To | Seconds | Product sound in it |
|---|---|---|---|---|
| Cold open | 0.0 | 12.0 | 12.0 | Findings or File by file on the open pull request |
| Beat 1, `beat_01_alexa_value` | 12.0 | 32.7 | 20.7 | none |
| Beat 2, `beat_02_bedrock_press` | 32.7 | 71.0 | 38.4 | the Bedrock answer to Hear this code review |
| Beat 3, `beat_03_model_coverage` | 71.0 | 82.1 | 11.1 | none |
| Optional slot, consented clip | after beat 3 | | 0 to 15 | only if the owner records a consented session; every later segment moves by its length |
| Beat 4, `beat_04_request_changes` | 82.1 | 105.0 | 22.8 | Request changes |
| Beat 5, `beat_05_confirm` | 105.0 | 139.6 | 34.6 | Confirm |
| Beat 6, `beat_06_mcp_handshake` | 139.6 | 152.0 | 12.5 | none |
| Closing card | 152.0 | 156.5 | 4.5 | none |

Narration is estimated at 2.2 words a second, the slowest rate of the 2026-09-29 take's
beats rounded down. If the measured total without the optional slot comes out above 160 s,
shorten the optional clip toward 10 s or trim beat 3, so that the whole stays under the kit's
175 s publication budget.

Dropped from the 2026-09-29 take to fit: the title card (the cold open takes its slot), the
"what you heard" beat, the Findings turn on octocat/Hello-World, the Alexa+ replay press (see
below), and the spoken test and conformance counts.

---

## What calls Amazon Bedrock on the live build

The owner authorises these presses before rehearsal, because each one is billed. The page
load does not call a model: the silent preview asks for the local engine.

| Action | Model calls |
|---|---|
| **Hear this code review** | one, with the first 3000 characters of the stage patch |
| Opening a pull request in the review dialogue | one, with the pull request's patch (the dialogue digests it with the default engine) |
| **Replay the documented Alexa+ requests** | three, one `digest_semantic_diff` call per client. It is not used in this take |
| Findings, File by file, Request changes, Confirm, **Run a real MCP handshake** | none |

**Bound to authorise:** at most 12 Bedrock calls. That covers three rehearsals and three takes
at two calls each (opening the pull request, then the press). A take that needs more stops,
and the owner is asked again.

---

## Choosing the pull request

* It is a public pull request on GitHub, so the server reads it without a token.
* It changes real code in two to five files, not only documentation.
* It is not one written for this video, and the narration names nothing about it beyond what
  the page says.
* In rehearsal, Findings reports at least one finding, so the cold open is a finding. If no
  candidate does, choose one where no rule matched, and use File by file instead of Findings
  in the cold open. On such a pull request the page's Findings answer is "No security finding
  in this change.", which claims more than the rules can know. That turn is kept off camera
  until the product hedges it.
* Record the URL, the head commit and the rehearsal's spoken answers in the take's receipt.

---

## Before the camera rolls

| Step | Who | Command or action | What must be true |
|---|---|---|---|
| 1 | Owner | Authorise the billed calls above, in writing | The bound and the date are written down before any press |
| 2 | Owner | `curl -s https://qylv1gxor9.execute-api.eu-west-1.amazonaws.com/health` | `source_revision` names the commit that becomes `{sha7}`. `bedrock_model_path` reads `ready_to_attempt`, `durable_state` reads `configured_reachable`, and `github_review_path` reads `dry_run_no_token`. If it reads `dry_run_with_token`, beat 5 must not say "this build has no GitHub token" |
| 3 | Owner | Open the GitHub Actions run for that commit | Green. Note the run id in the take's receipt. If a test count is ever shown, it is this run's count, filmed from this page |
| 4 | Owner | Rehearse three times on the live page, in the browser and window size used for the take | Each turn is timed from the action to the browser's speech end event, and each window in `narration.json` is replaced by the slowest run plus 1 s. Each Bedrock press reads **Amazon Bedrock** on the engine meter with no fallback reason. The fastest press's answer arrives at least 1 s after beat 2's measured narration ends |
| 5 | Owner | Read the model's full answer in rehearsal | Note whether it shows Markdown marks; see the risks below |
| 6 | Owner | `video/generate-narration.py --write-timestamps` | Measured beat windows written back; total narration 90 to 174 s |
| 7 | Owner | Within 60 s before the take, `GET /health` again, then reload the page and open the chosen pull request | The function is warm, and the opened overview is on screen before recording starts |

---

## Capture

A headed browser at 1280x720, recorded with its own audio, so every product turn is the
page's own voice and earcon. `video/capture-local.py` records headless, without audio, and
re-renders the page's sentences in a system voice; see [`README.md`](README.md) for what it
needs before it can drive this take. If a system voice is used after all, the closing card
names it.

The band under the page carries the captions and a tag naming the live build and its commit.
The tag replaces the last take's "Local run of commit ... Not the public deployment."

---

## Cold open, 0 to 12.0 seconds

* **Before the first frame:** the chosen pull request was opened on the live page. Opening it
  is a Bedrock call, so it happens off camera, and the band says "Pull request opened before
  this shot."
* **First frame:** the dialogue under **Talk through a real pull request, then request
  changes**, showing the opened overview with the next steps outlined.
* **Within 0.5 s:** **Findings**, or **File by file** when the rehearsal found no finding. The
  same command can be typed with <kbd>Alt</kbd>+<kbd>4</kbd> or said with
  <kbd>Alt</kbd>+<kbd>5</kbd>.
* **Sound:** the page's cue, its readback (`Understood: findings.`), and then its answer: each
  finding as the server words it, or each file with its additions and deletions. The narrator
  is silent.
* **Gate:** the first product sound by 2.0 s and the first spoken word by 5.0 s, with the turn
  playing to its end. A take that misses either is recorded again.

## Beat 1, `beat_01_alexa_value`, 12.0 to 32.7 seconds

* **Narration:** "That was Volcan, live, answering in its own voice. It is a Model Context
  Protocol server built to be called by Alexa+, so a blind or low-vision developer can review
  an AI agent's pull request by voice, and hear the verdict first."
* **On screen:** the view scrolls to the top of the page. It shows the heading **Hear your code
  review instead of scrubbing a diff**, **For blind and low-vision developers**, the silent
  preview of the `Inverted admin check` patch, and the label **Live MCP server, simulated
  Alexa+ front end. Not an Alexa skill. GitHub: dry-run.** On the last sentence,
  <kbd>Alt</kbd>+<kbd>1</kbd> puts the focus ring on **Hear this code review**.

## Beat 2, `beat_02_bedrock_press`, 32.7 to 71.0 seconds

* **At the first frame, before the narrator speaks:** <kbd>Enter</kbd> on **Hear this code
  review**. The model call starts, and the narration covers the wait.
* **Narration:** "This patch, an inverted admin check, goes to Claude on Amazon Bedrock. Volcan
  runs on AWS Lambda, with its review state in Amazon DynamoDB."
* **After the narrator stops:** the answer arrives. The page plays the falling earcon the
  server returned and speaks the server's sentence, finding first, while the words light.
  Nothing is cut or sped up: the wait is shown as it happened.
* **Fails the take:** an engine meter that reads local heuristic, a fallback reason, or an
  answer that starts while the narrator is still speaking.

## Beat 3, `beat_03_model_coverage`, 71.0 to 82.1 seconds

* **Narration:** "The meter names Amazon Bedrock, this line says how much of the patch the model
  read, and this panel opens its full answer."
* **On screen:**
  * The engine meter reading **Amazon Bedrock**, with the round trip the page measured.
  * The coverage line, exactly as the page prints it. The stage patch is under the
    3000-character budget, so the line reads `The model read the whole N-character patch.`
    with the page's own N. The other form, `The model read the first N of M patch
    characters; the local rules still read the whole patch.`, appears only for a longer
    patch. That would be a second billed press, so this take does not promise it.
  * The details **The model's full answer** are opened and held.

## Optional slot, after beat 3: only if the owner records a consented session

**Only if the owner records a consented session.** Without one, this slot is left out and
nothing replaces it. It is deliberately not in `narration.json`, so a default render can never
include it.

* 10 to 15 seconds of a blind or low-vision developer using Volcan with their own screen
  reader, during one of the five timed sessions the README names as the cheapest test of its
  riskiest assumption.
* Written consent to appear in a public video is given before recording. The participant
  decides whether their face, voice and name appear.
* The clip shows what happened, including a failure if that is what happened. It is not
  re-staged, and no praise is scripted.
* The band says it is a recorded session, with its date, and that consent was given. The
  narration adds no claim about the result beyond what the published session results say.

## Beat 4, `beat_04_request_changes`, 82.1 to 105.0 seconds

* **Narration:** "Back on the pull request, request changes stages a review, bound to the head
  commit Volcan read. Listen."
* **After the narrator stops:** a comment that says it is a dry-run demo goes into the comment
  box, and then **Request changes**. Typing `request changes:` and the comment with
  <kbd>Alt</kbd>+<kbd>4</kbd> works too.
* **Sound:** the page's cue and readback, then `Ready to request changes on` the pull request,
  `bound to head commit` and its short id, `with the comment:`, and `Say confirm to submit it,
  or cancel.` State **AWAITING CONFIRM**. The last take talked over this turn; this one keeps
  all of it.

## Beat 5, `beat_05_confirm`, 105.0 to 139.6 seconds

* **Narration:** "Nothing leaves until you confirm, and this build has no GitHub token, so it
  records the review and sends nothing. Confirm, and listen."
* **After the narrator stops:** **Confirm**. The page speaks `Understood: confirm.` and then its
  dry-run answer: nothing was sent to GitHub, the head commit is unchanged, the exact request
  is recorded, and a live send would be refused because no `GITHUB_TOKEN` is set. State
  **RECORDED, NOT SENT**. Midway through, the view moves to the review pane, which shows the
  outcome and the exact `POST` body the server recorded.

## Beat 6, `beat_06_mcp_handshake`, 139.6 to 152.0 seconds

* **Narration:** "This handshake is a real one with the server under the page, at protocol
  revision 2025-11-25. Alexa+ itself has never called Volcan."
* **On screen:**
  * Evidence, tab **Server and MCP**, shows **Server reached** with the commit and the model
    path the live server reports.
  * **Run a real MCP handshake** sends `initialize` and `tools/list` and calls no tool. Hold
    on the negotiated version and the tool list as the page prints them.
  * Then the connection strip's Alexa+ box: package built and tested locally, not certified
    or deployed.
* **Not pressed:** **Replay the documented Alexa+ requests**. On the live build it costs three
  Bedrock calls and could run close to a minute. The README's replay command against a local
  server remains the evidence for it.

## Closing card, 152.0 to 156.5 seconds

`Volcan: code review by ear, by touch and by voice.`
`Live build: https://qylv1gxor9.execute-api.eu-west-1.amazonaws.com`
`Source: https://github.com/upgradedev/volcan_amazon`
`Recorded on the live build at commit {sha7}. Simulated Alexa+ front end, not an Alexa skill.
GitHub review: a dry run, recorded and not sent.`
`Narration: synthetic ElevenLabs voice. Product voice: the page's own speech.`

The repository is private today. Before upload, the owner either makes it public or confirms
that the judges are collaborators. Otherwise the source line points at a page judges cannot
open.

---

## Rules for this take

* No test count is spoken or typed. If one is ever shown, it is filmed from the GitHub Actions
  run of the recorded commit, whose run id goes in the take's receipt.
* No figure is typed over the page. Every number in a page frame is one the page printed during
  the take.
* No cut or speed-up inside a product turn or a model wait.
* Nothing says or implies that Alexa+ called Volcan. No Echo device, no wake word, no Alexa
  skill screen and no Alexa developer console appear.
* Nothing says that Bedrock read the pull request in this take. The open happened off camera,
  and the page shows model coverage only for the stage patch.
* No AWS console, account id, role ARN or request id appears.
* No review is sent to GitHub.
* No person appears without written consent.
* "Not an Alexa skill" is not the opening line. It stays on screen in the page's label and on
  the closing card.

## Known risks on camera

* **Markdown in the full answer.** The speech strings have Markdown stripped; "The model's
  full answer" may still show marks such as asterisks. If the rehearsal shows them, the
  narration still only says the panel holds the model's full answer. Stripping them is product
  work and is not part of this plan.
* **Model timeout.** A model call that runs past its 25 s timeout falls back to the local
  engine. The meter then reads local heuristic, and the take is recorded again.
* **"No security finding in this change."** This sentence claims more than the rules can know.
  The pull request rule above keeps it off camera.
* **Latency.** The only live Bedrock figure on record is one digest of 19.67 s on 2026-10-01.
  The rehearsal measures it again, and beat 2's window follows the measurement.
