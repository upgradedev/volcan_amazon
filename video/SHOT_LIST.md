# Volcan: shot list for the re-take on the live build

**Status: a plan, not recorded.** This take is to be recorded on the live build at
https://qylv1gxor9.execute-api.eu-west-1.amazonaws.com, with Amazon Bedrock answering. The live
build serves `716b0f3` (PR #35) since 2026-10-07: default model `anthropic.claude-sonnet-5`,
Lambda memory 1769 MB (deploy receipt
`reviews/deploy_20261006/volcan/volcan_deploy_receipt_716b0f3.json` in the owner's workspace,
outside the repository). It replaces the 2026-09-29 render of a local run of `09d4862`, which [`README.md`](README.md) in
this folder describes. That take's six-beat script is kept in history:
`git show fc10e7d:video/narration.json`.

The beat ids match [`narration.json`](narration.json) and [`cue_sheet.json`](cue_sheet.json)
one for one. The narration is measured by `video/generate-narration.py`. The cold open and
the product windows of beats 4 and 5 are measured in a free rehearsal of 2026-10-06 on the
chosen pull request. Beat 2's window is sized from a 10 s latency allowance, which the capture
enforces, and the longest answer the page can speak, at the speech rate take 3 measured on the
live build on 2026-10-06; the allowance is an ESTIMATE resting on one measured press. The basis
for each window is written beside it in `narration.json`.

---

## What this take must show, and where

| Requirement | Where |
|---|---|
| The first spoken product word inside the first 5 seconds, after a 2.0 s title card | Title card, then the cold open |
| A title card and a closing card the sync gate reads as cards | Title card, closing card |
| The Alexa+ value first. "Not an Alexa skill" stays on screen, but it is not the opening line | Beat 1 |
| A real Amazon Bedrock answer, the model coverage line naming the model that answered, and the model's full answer | Beats 2 and 3 |
| "Claude on Amazon Bedrock", "AWS Lambda" and "DynamoDB" said on camera, for the AWS Builder mini | Beat 3, after the answer (beat 2 names Amazon Bedrock before the press) |
| Every product turn on camera in the product's own voice, with nothing talked over. That includes Request changes, which the last take talked over | Cold open, beats 2, 4 and 5 |
| An owned demo pull request with real code in several files, labelled on camera as a demo written for this walkthrough | Cold open band only. Beats 4 and 5 show the same pull request again; their band carries the captions and the commit tag, not the label |
| The screencast ends on narration, so the sync gate's `content-seam<=1s` check can pass | Beat 6 |
| No hard-coded test count | No count is spoken; see the rules at the end |
| End on the repository and live URLs | Closing card |
| Under 170 s measured, inside the kit's 175 s publication budget | 155.9 s measured |

## Time budget (measured)

| Segment | From | To | Seconds | Product sound in it |
|---|---|---|---|---|
| Title card | 0.0 | 2.0 | 2.0 | none |
| Cold open | 2.0 | 15.5 | 13.5 | `line 26` on the opened pull request |
| Beat 1, `beat_01_alexa_value` | 15.5 | 23.3 | 7.8 | none |
| Beat 2, `beat_02_bedrock_press` | 23.3 | 70.8 | 47.5 | the Bedrock answer to Hear this code review |
| Beat 3, `beat_03_model_coverage` | 70.8 | 79.7 | 8.9 | none |
| Beat 4, `beat_04_request_changes` | 79.7 | 111.6 | 32.0 | Request changes |
| Beat 5, `beat_05_confirm` | 111.6 | 140.9 | 29.3 | Confirm |
| Beat 6, `beat_06_recorded_request` | 140.9 | 145.3 | 4.4 | none |
| Beat 7, `beat_07_mcp_handshake` | 145.3 | 151.4 | 6.1 | none |
| Closing card | 151.4 | 155.9 | 4.5 | none |

`video/generate-narration.py --write-timestamps` measured 135.912 s of beats on 2026-10-07,
so the video is 2.0 + 13.5 + 135.912 + 4.5 = 155.912 s. The first run that day re-synthesized
beat 3 only, 109 characters, for its new line naming Claude; every other beat reused its cached
audio, and shrinking beat 2's window from 58.5 to 43.5 s sent nothing. The second widened beat
4's window from 26.5 to 27.0 s, because the rehearsal that day measured Request changes at
25.763 s, past the 25.45 s slowest run its window was sized from; it sent nothing either. Of the
15.0 s the shorter beat 2 frees, beat 3's longer line takes 0.6 s and beat 4 0.5 s under its own
rule; the rest is not spent: nothing is padded, and the video is shorter.

The fit before it, on 2026-10-06, measured 149.809 s of beats (169.809 s of video) with the
58.5 s window. That fit re-synthesized beats 1, 2,
3, 4, 6 and 7; beat 5 reused its cached audio. Fitting the budget took four runs, which sent
988 characters to ElevenLabs in all (the ledger is `narration/tts-ledger.jsonl` in the media
root): 462 for the first texts, which measured 153.477 s of beats; 245 for shorter beats 1, 3
and 4, of which beat 4 measured 2.972 s and was refused under the generator's 3 s floor; 131
for beats 4 and 7 again (151.063 s); and 150 for shorter beats 3 and 7 (149.309 s, with
beat 2's window half a second shorter). Widening that window to 58.5 s re-used every cached
beat and sent nothing.

* **Beat 2 presses when its narrator stops.** Take 3 on the live build, on 2026-10-06, pressed
  Hear this code review at the beat's first frame, under a 13.886 s narration. Amazon Bedrock
  answered in about 5 s, the answer began under the narration, and the capture refused the
  take. Beat 2 now says one line, "Press once, and this patch goes to Amazon Bedrock." (3.39 s
  measured), and the press follows the generator's 0.65 s tail, in the take as in the
  rehearsal. The model call starts only then, so its answer starts after the narration
  whether the call takes 2 s or runs to its timeout. The capture's check that it did is
  unchanged, and now runs in the rehearsal too.
* **Beat 2's window, 43.5 s from the press, holds an answer that starts within 10 s.** The
  58.5 s window before it was sized for a call that ran to the 25 s timeout on Claude Opus 5.
  The live build now answers with `anthropic.claude-sonnet-5` on a 1769 MB function: one press
  of the take-4 patch answered in 3.44 s at the client (Lambda 3071 ms, model 1266 ms), where
  the same press at 256 MB took 17.88 s (Lambda 17562 ms, model 2959 ms). A fast answer left
  about 20 s of idle picture in the 58.5 s window. The parts of the new one:
  * **a latency allowance of 10 s** (ESTIMATE, `ANSWER_LATENCY_ALLOWANCE_SECONDS` in
    `video/capture-local.py`), from the planned press to the answer's first sound, about three
    times the one press measured at 1769 MB. It covers the press itself, the round trip and the
    model call;
  * **the falling earcon**, which starts 0.65 s before the first word (measured in the
    rehearsal);
  * **the longest sentence the page can speak** for the stage patch. `to_voice_summary(level=0)`
    builds the finding, then the model's headline (only when `synthesis_mode` is `bedrock`),
    then the counts, and the page speaks its `voice_summary_for_speech`. Measured on take 3's
    for-speech sentence of 359 characters:
    * the local finding, 139 characters with the space after it;
    * the headline: `shorten_for_speech` keeps at most 180 characters of the model's line and
      closes a cut with a space and an ellipsis, so at most 182, and `to_voice_summary` adds a
      full stop, 1;
    * the counts, 48 characters with the space before them;
    * 139 + 182 + 1 + 48 = 370 characters. Take 3 spoke its 359 characters, with a 171-character
      headline, in 31.42 s, 0.0875 s a character, so 370 characters take 370 x 31.42 / 359 =
      32.38 s.

  0.65 + 10 + 32.38 = 43.03 s, rounded up to the half second: 43.5 s. Two limits on that
  figure. The operator names (`!=` spoken as "not equals") are added after the cut, so a
  headline with code operators in it speaks more than 182 characters. And the local engine's
  sentence, finding and counts only, took 16.75 s for 186 characters in the rehearsal, 0.090 s
  a character; at that rate 370 characters would take 33.3 s. Either one can run the answer
  past the window, and the capture then fails the take, as below.
* **A slow answer means a retake.** The capture fails the take, and lists a failure in a
  rehearsal, when the answer's first sound comes more than 10 s after the planned press, even
  when the rest would have fitted. It also still fails a take whose speech has not ended when
  beat 3 begins. An answer can never run on, unchecked, past the window.
* **The generator's cap is 45 s again.** It was raised from 45 s to 60 s for the 58.5 s window.
  The cap is a plan constraint in `video/generate-narration.py`, not a gate:
  `scripts/verify_video_sync.py` never reads it, and every window still needs its basis.
* **Beat 3 names Claude.** It says "Claude on Amazon Bedrock answered, on AWS Lambda with
  DynamoDB. That's how much it read, and which model." while the meter and then the coverage
  line are on screen. The coverage line now ends with `Answered by` and the model the answer
  names in `model_answered`, which PR #35 added to the page.
* **Beats 1, 4, 6 and 7 stay as cut on 2026-10-06.** To pay for the 58.5 s window then, beat 1
  went from 8.9 to 7.8 s, beat 4 from 33.6 to 31.5 s, beat 6 from 6.9 to 4.4 s and beat 7 from
  8.5 to 6.1 s. They are not lengthened again: the video is shorter instead. Beat 3 grew from
  8.3 to 8.9 s and beat 2 shrank from 62.5 to 47.5 s.
* **The optional consented clip fits again.** At 155.9 s, a clip of up to 14.0 s keeps the
  video under 170 s, and up to 19.0 s keeps it under the 175 s budget.

Dropped from the 2026-09-29 take to fit: the "what you heard" beat, the Findings turn on
octocat/Hello-World, the Alexa+ replay press (see below), and the spoken test and conformance
counts. The title card stays, cut to 2.0 s: the sync gate samples the middle of the title
segment and must read a card there, and cold-open footage in that slot reads as content
(`video/README.md`, section 4).

**The 5 s rule.** The title card runs 0 to 2.0 s and the cold open's first frame is at 2.0 s.
`line 26` is typed into the command box 0.1 s later and sent with Enter about 0.3 s after
that. The capture fails a take whose first sound comes more than 2.0 s after the title card or
whose first word comes after 5.0 s of video.

---

## What calls Amazon Bedrock on the live build

The owner authorises these presses before rehearsal, because each one is billed. The page
load does not call a model: the silent preview asks for the local engine.

| Action | Model calls |
|---|---|
| **Hear this code review** | one, with the first 3000 characters of the stage patch |
| Opening a pull request in the review dialogue | one, with the pull request's patch (the dialogue digests it with the default engine) |
| **Replay the documented Alexa+ requests** | three, one `digest_semantic_diff` call per client. It is not used in this take |
| `line 26`, Findings, Summary, File by file, Request changes, Confirm, **Run a real MCP handshake** | none |

**Bound to authorise:** at most 12 Bedrock calls. That covers three rehearsals and three takes
at two calls each (opening the pull request, then the press). A take that needs more stops,
and the owner is asked again.

---

## Choosing the pull request

* It is a public pull request on GitHub, so the server reads it without a token.
* It changes real code in two to five files, not only documentation.
* **It may be an owned demo pull request written for this walkthrough, labelled on camera as
  one.** The cold open's band says `A demo pull request in upgradedev/volcan-demo-service,
  written for this walkthrough`, and the narration names nothing about it beyond what the page
  says. A pull request written for the video and not labelled as one is not allowed.
* In rehearsal, the opened overview reports at least one security finding, so the cold open
  is a finding.
* The cold-open turn fits the cold open, the slowest of three runs plus 1 s within the
  capture's 20 s cap. Every finding is a sentence, so Findings and Summary grow with the pull
  request. On the chosen pull request they do not fit (below), so the cold open reads the one
  line the first finding is about.
* The review comment (`REVIEW_COMMENT` in `video/capture-local.py`) is repeated by the readback
  and by the staged answer, so its length decides how long beat 4's window must be, and so
  whether the video stays under 170 s.
* Record the URL, the head commit and the rehearsal's spoken answers in the take's receipt.

**The chosen pull request:** https://github.com/upgradedev/volcan-demo-service/pull/1, `Add
workspace deletion endpoint`, head `74dd0b1`, 5 files, +34 and -3, 2 security findings. It
inverts the comparison in `is_admin` (`user.role == Role.ADMIN` became `user.role !=
Role.ADMIN`) and widens CORS to any origin. Measured on 2026-10-06 against a local server on
port 8813 with no cloud credentials, from the action to the browser's speech end event:

| Turn | Runs | Fits? |
|---|---|---|
| Findings | 29.83 s | no: over the 20 s cold-open cap |
| Summary | 24.63 s, 24.46 s | no: over the cap, and on the live build it also speaks the model's headline, up to 180 characters |
| `line 26`, typed | 12.03 s, 12.04 s, 11.88 s | yes: cold open 13.5 s |
| Request changes, comment `is_admin is inverted.` | 25.39 s, 25.45 s, 25.28 s; 25.763 s in the rehearsal of 2026-10-07 | yes: window 27.0 s |
| Request changes, the earlier 69-character comment | 33.4 s (rehearsal receipt) | no: a 34.5 s window, 8 s longer, would put the video at about 177.6 s, over the 175 s budget |
| Confirm | 22.28 s, 22.28 s, 22.27 s, 22.21 s, 23.41 s | yes: window 24.5 s |

---

## Before the camera rolls

| Step | Who | Command or action | What must be true |
|---|---|---|---|
| 0 | Anyone | `video/capture-local.py --rehearsal` and `video/build-video.py --rehearsal` against a local server, as `video/README.md` section 1 says | Free: no Bedrock call. It runs the whole journey on the chosen pull request and lists every failure, and what the local engine cannot show. Its output is never shippable |
| 1 | Owner | Authorise the billed calls above, in writing | The bound and the date are written down before any press |
| 2 | Owner | `curl -s https://qylv1gxor9.execute-api.eu-west-1.amazonaws.com/health` | `source_revision` names the commit that becomes `{sha7}`, `716b0f3` today. `bedrock_model_path` reads `ready_to_attempt` with `model_id` `anthropic.claude-sonnet-5`, `durable_state` reads `configured_reachable`, and `github_review_path` reads `dry_run_no_token`. If it reads `dry_run_with_token`, beat 6 must not say "No GitHub token here" |
| 3 | Owner | Open the GitHub Actions run for that commit | Green. Note the run id in the take's receipt. If a test count is ever shown, it is this run's count, filmed from this page |
| 4 | Owner | Rehearse on the live page, in the browser and window size used for the take | Each Bedrock press reads **Amazon Bedrock** on the engine meter with no fallback reason, its answer makes its first sound within 10 s of the press and ends inside 43.5 s of it, and the coverage line ends `Answered by anthropic.claude-sonnet-5.`. The press waits for beat 2's narrator, so no latency can start the answer under the narration |
| 5 | Owner | Read the model's full answer in rehearsal | Note whether it shows Markdown marks; see the risks below |
| 6 | Owner | `video/generate-narration.py --write-timestamps` | Measured beat windows written back; total narration 90 to 174 s. With the cached audio it sends nothing to ElevenLabs |
| 7 | Owner | Within 60 s before the take, `GET /health` again, then reload the page and open the chosen pull request | The function is warm, and the opened overview is on screen before recording starts |

---

## Capture

A headed browser at 1280x720, recorded with its own audio, so every product turn is the
page's own voice and earcon. `video/capture-local.py` drives this journey, but records
headless, without audio, and re-renders the page's sentences in a system voice. It presses
nothing billed unless it is run with `--allow-billed-presses`; see [`README.md`](README.md),
sections 1 and 4. If a system voice is used after all, the closing card names it, and
`video/build-video.py` writes that line.

The band under the page carries the captions and a tag naming the live build and its commit.
The tag replaces the last take's "Local run of commit ... Not the public deployment."

---

## Title card, 0 to 2.0 seconds

`Volcan`
`Hear your code review instead of scrubbing a diff.`
`Live build at commit {sha7}. Simulated Alexa+ front end. GitHub review: dry run.`

A flat card, silent. The build writes `Local run` in place of `Live build` when the capture
was not recorded on the live build. It measured an edge mean of 1.98, a card to the sync gate
(threshold 4.5).

## Cold open, 2.0 to 15.5 seconds

* **Before the first frame:** the chosen pull request was opened on the live page. Opening it
  is a Bedrock call, so it happens off camera.
* **First frame:** the dialogue under **Talk through a real pull request, then request
  changes**, showing the opened overview.
* **Within 0.5 s:** <kbd>Alt</kbd>+<kbd>4</kbd> puts the focus in the command box, `line 26`
  is typed, and <kbd>Enter</kbd> sends it.
* **Sound:** the page's readback, `Understood: line 26.`, then the line: `Line 6 of 9, added,
  new line 26: return user.role not equals Role.ADMIN`. That is the inverted comparison in
  `is_admin`. The dialogue log prints the line with `!=` under the overview, which says `2
  security findings`. The turn speaks the comparison, not the word "inverted": the review
  card that names the finding (`an authorization comparison was inverted`) is not in this
  frame, and the capture checks that the turn's answer carries it. The turn reads the parsed
  patch and calls no model, so its words are the same on the live build. The narrator is
  silent.
* **Band:** `Live build at commit {sha7}. A demo pull request in
  upgradedev/volcan-demo-service, written for this walkthrough, opened before this shot.`
* **Gate:** the first product sound by 2.0 s after the title card ends, and the first spoken
  word by 5.0 s into the video, with the turn playing to its end. A take that misses either is
  recorded again. The capture also fails a `line 26` turn that the page refuses, that reads
  another line, or whose file has no security finding on the review card.

## Beat 1, `beat_01_alexa_value`, 15.5 to 23.3 seconds

* **Narration:** "Volcan, built for Alexa+, lets blind and low-vision developers review AI code by
  voice."
* **On screen:** the view scrolls to the top of the page. It shows the heading **Hear your code
  review instead of scrubbing a diff**, **For blind and low-vision developers**, the silent
  preview of the `Inverted admin check` patch, and the label **Live MCP server, simulated
  Alexa+ front end. Not an Alexa skill. GitHub: dry-run.** Late in the line,
  <kbd>Alt</kbd>+<kbd>1</kbd> puts the focus ring on **Hear this code review**.

## Beat 2, `beat_02_bedrock_press`, 23.3 to 70.8 seconds

* **Narration, before the press:** "Press once, and this patch goes to Amazon Bedrock." It
  measured 3.39 s. "This patch" is the stage patch; nothing says the model read the pull
  request.
* **When the narrator stops**, after the generator's 0.65 s tail: <kbd>Enter</kbd> on **Hear
  this code review**. The model call starts only now, so its answer cannot start under the
  narration. The button shows it is working until the answer arrives. Nothing is cut or sped
  up: the wait is shown as it happened.
* **The answer:** the page plays the falling earcon the server returned and speaks the server's
  sentence, the finding, then the model's headline, then the counts, while the words light.
  Nothing talks over it. A fast answer leaves the page holding, silent, until beat 3: after a
  3.44 s answer with a full headline, about 7 s.
* **Window:** 43.5 s from the press, for an answer whose first sound comes within 10 s and the
  longest sentence the page can speak; the parts are under the time budget above.
* **Fails the take:** an engine meter that reads local heuristic, a fallback reason, an
  answer that starts while the narrator is still speaking, an answer whose first sound comes
  more than 10 s after the press, or an answer still speaking when beat 3 begins.
* **In a free rehearsal** the press is made at the same moment. The local engine answers at
  once, and its sentence has no headline, so the page holds, silent, for about 25 s.

## Beat 3, `beat_03_model_coverage`, 70.8 to 79.7 seconds

* **Narration:** "Claude on Amazon Bedrock answered, on AWS Lambda with DynamoDB. That's how much
  it read, and which model." Claude on Amazon Bedrock, AWS Lambda and DynamoDB are said on
  camera here, after the answer.
* **On screen:**
  * On the first sentence, the engine meter reading **Amazon Bedrock**, with the round trip
    the page measured.
  * On the second, the coverage line, exactly as the page prints it. The stage patch is under
    the 3000-character budget, so the line reads `The model read the whole N-character patch.
    Answered by anthropic.claude-sonnet-5.` with the page's own N and the model the answer
    names in `model_answered`. The capture fails the take unless the line is exactly that, for
    the N and the model in the press's own response, and the model is the `model_id` that
    `/health` reports. The other form, `The model read the first N of M patch characters; the
    local rules still read the whole patch.` with the same `Answered by` ending, appears only
    for a longer patch. That would be a second billed press, so this take does not promise it.
  * The details **The model's full answer** are opened and held.

## Optional slot, after beat 3: only if the owner records a consented session

**Only if the owner records a consented session.** Without one, this slot is left out and
nothing replaces it. It is deliberately not in `narration.json`, so a default render can never
include it. At 155.9 s, a clip of up to 14.0 s keeps the video under 170 s.

* 10 to 15 seconds of a blind or low-vision developer using Volcan with their own screen
  reader, during one of the five timed sessions the README names as the cheapest test of its
  riskiest assumption.
* Written consent to appear in a public video is given before recording. The participant
  decides whether their face, voice and name appear.
* The clip shows what happened, including a failure if that is what happened. It is not
  re-staged, and no praise is scripted.
* The band says it is a recorded session, with its date, and that consent was given. The
  narration adds no claim about the result beyond what the published session results say.

## Beat 4, `beat_04_request_changes`, 79.7 to 111.6 seconds

* **Narration:** "Request changes stages a review, bound to the head commit it read."
* **After the narrator stops:** the review comment `is_admin is inverted.` goes into the
  comment box, and then **Request changes**. Typing `request changes:` and the comment with
  <kbd>Alt</kbd>+<kbd>4</kbd> works too.
* **Sound:** the page's cue and readback, then `Ready to request changes on` the pull request,
  `bound to head commit` and its short id, `with the comment:`, and `Say confirm to submit it,
  or cancel.` State **AWAITING CONFIRM**. The last take talked over this turn; this one keeps
  all of it, in a 27.0 s window measured on the chosen pull request.

## Beat 5, `beat_05_confirm`, 111.6 to 140.9 seconds

* **Narration:** "Nothing leaves Volcan until you confirm. Confirm, and listen."
* **After the narrator stops:** **Confirm**. The page speaks `Understood: confirm.` and then its
  dry-run answer: nothing was sent to GitHub, the head commit is unchanged, the exact request
  is recorded, and a live send would be refused because no `GITHUB_TOKEN` is set. State
  **RECORDED, NOT SENT**. Midway through, the view moves to the review pane, which shows the
  outcome and the exact `POST` body the server recorded. Nothing talks over the turn.

## Beat 6, `beat_06_recorded_request`, 140.9 to 145.3 seconds

* **Narration:** "No GitHub token here: the request is recorded, not sent."
* **On screen:** the review pane, held: outcome recorded and not sent, the live head re-read,
  and the exact `POST` body. No product turn.
* **Why this beat:** the page has stopped speaking before it starts, and the screencast ends
  on its narration. A screencast that ends on the page's own speech ends in silence, because
  the window keeps the slowest-run-plus-1-s margin and the re-rendered system voice ends before
  the browser's, so the sync gate's `content-seam<=1s` check failed by 4.0 s on the earlier
  plan. Ending on narration leaves the generator's 0.65 s tail.

## Beat 7, `beat_07_mcp_handshake`, 145.3 to 151.4 seconds

* **Narration:** "This MCP handshake is real. Alexa+ never called Volcan." The page prints the
  negotiated revision, 2025-11-25.
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

## Closing card, 151.4 to 155.9 seconds

`Volcan`
`Live build: qylv1gxor9.execute-api.eu-west-1.amazonaws.com`
`Source: github.com/upgradedev/volcan_amazon`
`Commit {sha7}. Simulated Alexa+, not an Alexa skill. Narration: synthetic ElevenLabs.`
`GitHub review: dry run. Product voice: the page's own speech.`

Five rows, at most: the sync gate must read it as a card. When the capture re-renders the
page's sentences in a system voice, the build replaces the last sentence with `Product voice:
the page's sentences in <voice>.`, which keeps the card at 5 rows; it measured an edge mean of
3.98 against the gate's 4.5. The earlier 9-row card measured 7.59 and read as content. The
build refuses a closing card of more than 5 rows.

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
* The pull request is an owned demo written for this walkthrough, and the band says so while
  it is first on screen. Nothing presents it as someone else's work or as found in the wild.
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
  engine. The meter then reads local heuristic, and the take is recorded again. Any answer
  later than 10 s fails the take first, on the latency allowance.
* **Beat 2's window.** The window holds 43.5 s from the press, which waits for the narrator:
  an answer whose first sound comes within 10 s, then 0.65 s of earcon lead and the longest
  sentence, 32.38 s at take 3's rate. A cold function, a throttled call or a slow model can
  pass 10 s: on the 256 MB function the same press took 17.88 s. The capture fails that take,
  and it is recorded again; warm the function with `GET /health` within 60 s of the take, as
  step 7 says. Since PR #35 the model client is built with `max_retries=0`, so the SDK does not
  retry a call on its own.
* **No rule matched.** The page now hedges that answer ("No security rule matched this
  change. The rules can miss a risk"), but the cold open is for a finding, so the capture
  refuses it there. The chosen pull request has 2 findings.
* **Latency.** The live Bedrock figures on record: one digest of 19.67 s on 2026-10-01; take
  3's press on 2026-10-06, whose answer sounded about 4.3 s after the press; and on `716b0f3`,
  one press of the take-4 patch in 17.88 s at 256 MB and one in 3.44 s at 1769 MB, the memory
  the function has now. Each figure is one press. Every other turn in the take calls no model,
  and the network adds a round trip to each.
