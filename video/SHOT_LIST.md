# Volcan: shot list for the re-take on the live build

**Status: a plan, not recorded.** This take is to be recorded on the live build at
https://qylv1gxor9.execute-api.eu-west-1.amazonaws.com, with Amazon Bedrock answering. It
replaces the 2026-09-29 render of a local run of `09d4862`, which [`README.md`](README.md) in
this folder describes. That take's six-beat script is kept in history:
`git show fc10e7d:video/narration.json`.

The beat ids match [`narration.json`](narration.json) and [`cue_sheet.json`](cue_sheet.json)
one for one. The narration is measured by `video/generate-narration.py`. The cold open and
the product windows of beats 4 and 5 are measured in a free rehearsal of 2026-10-06 on the
chosen pull request. Beat 2's window is an ESTIMATE until the billed take, because only Amazon
Bedrock can answer it. The basis for each window is written beside it in `narration.json`.

---

## What this take must show, and where

| Requirement | Where |
|---|---|
| The first spoken product word inside the first 5 seconds, after a 2.0 s title card | Title card, then the cold open |
| A title card and a closing card the sync gate reads as cards | Title card, closing card |
| The Alexa+ value first. "Not an Alexa skill" stays on screen, but it is not the opening line | Beat 1 |
| A real Amazon Bedrock answer, the model coverage line and the model's full answer | Beats 2 and 3 |
| "Amazon Bedrock", "AWS Lambda" and "DynamoDB" said on camera, for the AWS Builder mini | Beat 2 |
| Every product turn on camera in the product's own voice, with nothing talked over. That includes Request changes, which the last take talked over | Cold open, beats 2, 4 and 5 |
| An owned demo pull request with real code in several files, labelled on camera as a demo written for this walkthrough | Cold open band only. Beats 4 and 5 show the same pull request again; their band carries the captions and the commit tag, not the label |
| The screencast ends on narration, so the sync gate's `content-seam<=1s` check can pass | Beat 6 |
| No hard-coded test count | No count is spoken; see the rules at the end |
| End on the repository and live URLs | Closing card |
| Under 170 s measured, inside the kit's 175 s publication budget | 169.6 s measured |

## Time budget (measured, except beat 2)

| Segment | From | To | Seconds | Product sound in it |
|---|---|---|---|---|
| Title card | 0.0 | 2.0 | 2.0 | none |
| Cold open | 2.0 | 15.5 | 13.5 | `line 26` on the opened pull request |
| Beat 1, `beat_01_alexa_value` | 15.5 | 24.4 | 8.9 | none |
| Beat 2, `beat_02_bedrock_press` | 24.4 | 81.5 | 57.0 | the Bedrock answer to Hear this code review (window ESTIMATE) |
| Beat 3, `beat_03_model_coverage` | 81.5 | 86.9 | 5.4 | none |
| Beat 4, `beat_04_request_changes` | 86.9 | 120.4 | 33.6 | Request changes |
| Beat 5, `beat_05_confirm` | 120.4 | 149.7 | 29.3 | Confirm |
| Beat 6, `beat_06_recorded_request` | 149.7 | 156.6 | 6.9 | none |
| Beat 7, `beat_07_mcp_handshake` | 156.6 | 165.1 | 8.5 | none |
| Closing card | 165.1 | 169.6 | 4.5 | none |

`video/generate-narration.py --write-timestamps` measured 149.645 s of beats on 2026-10-06,
so the video is 2.0 + 13.5 + 149.645 + 4.5 = 169.645 s. It synthesized only the four beats this
change rewrote, beats 1, 2, 3 and 7, with 123, 198, 77 and 109 characters (507 in all); beats
4, 5 and 6 reused the cached audio.

* **Beat 2 holds 57.0 s from the press.** Its narration measured 13.886 s, then the generator's
  0.65 s tail, then a 42.5 s product window: 57.036 s. The billed answer is about 47 to 51 s
  from the press (ESTIMATE), the sum of four parts:
  * the model call: one live Bedrock digest took 19.67 s on 2026-10-01, the only live figure;
  * the falling earcon, 0.6 s;
  * the finding and the counts, which the page spoke in 16.7 s for this patch in the rehearsal;
  * the model's headline, about 10 to 14 s (ESTIMATE). `to_voice_summary(level=0)`, the level
    the press asks for, speaks the finding, then `executive_spoken_summary` only when
    `synthesis_mode` is `bedrock`, then the counts. `shorten_for_speech` cuts the headline to
    180 characters; a full 180 at the rehearsal voice's rate is about 14.7 s.

  57.0 s also covers a call that runs to the 25 s timeout with the longest headline: 25 + 0.6
  + 16.7 + 14.7 = 57.0 s. Past the timeout the call falls back to the local engine and the take
  is recorded again anyway. A take whose answer runs past the beat fails and is recorded again.
* **The generator's cap was raised from 30 s to 45 s for this.** The cap is a plan constraint
  in `video/generate-narration.py`, not a gate: `scripts/verify_video_sync.py` never reads it,
  and every window still needs its basis. At 30 s, a 56 s beat would need about 25 s of
  narration over a wait the answer may interrupt after 19.67 s. Beat 2's narration instead
  ends 5.8 s before the one live answer arrived.
* **Beats 1, 3 and 7 were cut to pay for it.** Beat 1 went from 18.2 to 8.9 s, beat 3 from 8.2
  to 5.4 s (beat 2's narration now says what the coverage line is), and beat 7 from 11.3 to
  8.5 s (the page prints the protocol revision; the narrator no longer reads it out).
* **The optional consented clip no longer fits as planned.** At 169.6 s, at most 5.3 s is left
  under the 175 s budget. A clip of 10 to 15 s needs a cut elsewhere first.

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
| Request changes, comment `is_admin is inverted.` | 25.39 s, 25.45 s, 25.28 s | yes: window 26.5 s |
| Request changes, the earlier 69-character comment | 33.4 s (rehearsal receipt) | no: a 34.5 s window, 8 s longer, would put the video at about 177.6 s, over the 175 s budget |
| Confirm | 22.28 s, 22.28 s, 22.27 s, 22.21 s, 23.41 s | yes: window 24.5 s |

---

## Before the camera rolls

| Step | Who | Command or action | What must be true |
|---|---|---|---|
| 0 | Anyone | `video/capture-local.py --rehearsal` and `video/build-video.py --rehearsal` against a local server, as `video/README.md` section 1 says | Free: no Bedrock call. It runs the whole journey on the chosen pull request and lists every failure, and what the local engine cannot show. Its output is never shippable |
| 1 | Owner | Authorise the billed calls above, in writing | The bound and the date are written down before any press |
| 2 | Owner | `curl -s https://qylv1gxor9.execute-api.eu-west-1.amazonaws.com/health` | `source_revision` names the commit that becomes `{sha7}`. `bedrock_model_path` reads `ready_to_attempt`, `durable_state` reads `configured_reachable`, and `github_review_path` reads `dry_run_no_token`. If it reads `dry_run_with_token`, beat 6 must not say "This build has no GitHub token" |
| 3 | Owner | Open the GitHub Actions run for that commit | Green. Note the run id in the take's receipt. If a test count is ever shown, it is this run's count, filmed from this page |
| 4 | Owner | Rehearse on the live page, in the browser and window size used for the take | Each Bedrock press reads **Amazon Bedrock** on the engine meter with no fallback reason. The fastest press's answer arrives at least 1 s after beat 2's measured narration ends, 13.886 s after the press, and the slowest ends inside beat 2's 57.0 s |
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

## Beat 1, `beat_01_alexa_value`, 15.5 to 24.4 seconds

* **Narration:** "That was Volcan. Built for Alexa+, it lets a blind or low-vision developer
  review an AI agent's pull request by voice."
* **On screen:** the view scrolls to the top of the page. It shows the heading **Hear your code
  review instead of scrubbing a diff**, **For blind and low-vision developers**, the silent
  preview of the `Inverted admin check` patch, and the label **Live MCP server, simulated
  Alexa+ front end. Not an Alexa skill. GitHub: dry-run.** On the last sentence,
  <kbd>Alt</kbd>+<kbd>1</kbd> puts the focus ring on **Hear this code review**.

## Beat 2, `beat_02_bedrock_press`, 24.4 to 81.5 seconds

* **At the first frame, before the narrator speaks:** <kbd>Enter</kbd> on **Hear this code
  review**. The model call starts, and the narration covers the wait.
* **Narration:** "This patch, an inverted admin check, goes to Claude on Amazon Bedrock. Volcan
  runs on AWS Lambda, with its review state in Amazon DynamoDB. Then a line says how much of
  the patch the model read." It measured 13.886 s. "This patch" is the stage patch; nothing
  says the model read the pull request.
* **After the narrator stops:** the button still shows it is working until the answer arrives. The page plays the falling earcon the
  server returned and speaks the server's sentence, finding first, while the words light.
  Nothing is cut or sped up: the wait is shown as it happened.
* **Fails the take:** an engine meter that reads local heuristic, a fallback reason, an
  answer that starts while the narrator is still speaking, or an answer still speaking when
  beat 3 begins.
* **In a free rehearsal** the local engine answers at once, so the rehearsal presses when the
  narrator stops instead, and says so under `notRepresentative`.

## Beat 3, `beat_03_model_coverage`, 81.5 to 86.9 seconds

* **Narration:** "Amazon Bedrock on the meter, that coverage line, and the model's full
  answer."
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
include it. At 169.6 s, a clip longer than 5.3 s needs a cut elsewhere first.

* 10 to 15 seconds of a blind or low-vision developer using Volcan with their own screen
  reader, during one of the five timed sessions the README names as the cheapest test of its
  riskiest assumption.
* Written consent to appear in a public video is given before recording. The participant
  decides whether their face, voice and name appear.
* The clip shows what happened, including a failure if that is what happened. It is not
  re-staged, and no praise is scripted.
* The band says it is a recorded session, with its date, and that consent was given. The
  narration adds no claim about the result beyond what the published session results say.

## Beat 4, `beat_04_request_changes`, 86.9 to 120.4 seconds

* **Narration:** "Back on the pull request, request changes stages a review, bound to the head
  commit Volcan read. Listen."
* **After the narrator stops:** the review comment `is_admin is inverted.` goes into the
  comment box, and then **Request changes**. Typing `request changes:` and the comment with
  <kbd>Alt</kbd>+<kbd>4</kbd> works too.
* **Sound:** the page's cue and readback, then `Ready to request changes on` the pull request,
  `bound to head commit` and its short id, `with the comment:`, and `Say confirm to submit it,
  or cancel.` State **AWAITING CONFIRM**. The last take talked over this turn; this one keeps
  all of it, in a 26.5 s window measured on the chosen pull request.

## Beat 5, `beat_05_confirm`, 120.4 to 149.7 seconds

* **Narration:** "Nothing leaves Volcan until you confirm. Confirm, and listen."
* **After the narrator stops:** **Confirm**. The page speaks `Understood: confirm.` and then its
  dry-run answer: nothing was sent to GitHub, the head commit is unchanged, the exact request
  is recorded, and a live send would be refused because no `GITHUB_TOKEN` is set. State
  **RECORDED, NOT SENT**. Midway through, the view moves to the review pane, which shows the
  outcome and the exact `POST` body the server recorded. Nothing talks over the turn.

## Beat 6, `beat_06_recorded_request`, 149.7 to 156.6 seconds

* **Narration:** "This build has no GitHub token: the pane shows the exact request, recorded and
  not sent."
* **On screen:** the review pane, held: outcome recorded and not sent, the live head re-read,
  and the exact `POST` body. No product turn.
* **Why this beat:** the page has stopped speaking before it starts, and the screencast ends
  on its narration. A screencast that ends on the page's own speech ends in silence, because
  the window keeps the slowest-run-plus-1-s margin and the re-rendered system voice ends before
  the browser's, so the sync gate's `content-seam<=1s` check failed by 4.0 s on the earlier
  plan. Ending on narration leaves the generator's 0.65 s tail.

## Beat 7, `beat_07_mcp_handshake`, 156.6 to 165.1 seconds

* **Narration:** "This MCP handshake is a real one with the server under the page. Alexa+
  itself has never called Volcan." The page prints the negotiated revision, 2025-11-25.
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

## Closing card, 165.1 to 169.6 seconds

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
  engine. The meter then reads local heuristic, and the take is recorded again.
* **Beat 2's window.** The beat holds 57.0 s from the press. The billed answer is about 47 to
  51 s (ESTIMATE): 19.67 s for the one live call, 0.6 s of earcon, 16.7 s for the finding and
  the counts, and about 10 to 14 s for the model's headline. A call that reaches the 25 s
  timeout falls back and fails the take anyway; one just under it, with a full 180-character
  headline, ends at about 57.0 s. An answer that starts within 13.886 s of the press starts
  under the narration and fails the take; step 4 above asks for 1 s more than that.
* **No rule matched.** The page now hedges that answer ("No security rule matched this
  change. The rules can miss a risk"), but the cold open is for a finding, so the capture
  refuses it there. The chosen pull request has 2 findings.
* **Latency.** The only live Bedrock figure on record is one digest of 19.67 s on 2026-10-01.
  The live rehearsal measures it again. Every other turn in the take calls no model, and the
  network adds a round trip to each.
