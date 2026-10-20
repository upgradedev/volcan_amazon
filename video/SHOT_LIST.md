# Volcan: shot list for the re-take on the live build

**Status: recorded as take 6 on 2026-10-19, not yet published.** Take 6 was recorded on the
live build at https://qylv1gxor9.execute-api.eu-west-1.amazonaws.com, at commit `873845d`
(PR #40), with Amazon Bedrock answering: default model `anthropic.claude-sonnet-5`, Lambda
memory 1769 MB. [`README.md`](README.md) in this folder has what take 6 measured. This file is
the plan it followed. Most of it was written while the live build served `716b0f3` (PR #35,
since 2026-10-07), and the windows below were sized then; take 6 kept them unchanged. It
replaced the 2026-09-29 render of a local run of `09d4862`, whose six-beat script is kept in
history: `git show fc10e7d:video/narration.json`.

The beat ids match [`narration.json`](narration.json) and [`cue_sheet.json`](cue_sheet.json)
one for one. The narration is measured by `video/generate-narration.py`. The cold open and
the product windows of beats 4 and 5 are measured in a free rehearsal of 2026-10-06 on the
chosen pull request, and beat 4 was also measured in the free rehearsal of 2026-10-07. Beat 2's
window is sized from a 5.9 s latency allowance, which the capture enforces, and the longest
answer the page can speak, at the slowest speech rate measured for beat 2's sentence plus 1 s;
the allowance is an ESTIMATE resting on one measured press. The basis for each window is
written beside it in `narration.json`.

## Take 6 on `873845d`: take 5's journey

**Decision, 2026-10-19:** take 6 records take 5's seven beats unchanged, on the live
`873845d` build. That means the cold open, Hear with the Amazon Bedrock answer and its coverage
line, Request changes, Confirm, the recorded request and the MCP handshake. No drill-down is
pressed on camera. `drill_down` stays out of `BILLED_PRESSES`, so a drill-down press in the
take or the rehearsal is refused.

The take made 5 billed calls: open, Hear and 3 in the replay clip. It measured 167.448 s with
the replay clip (ffprobe), inside the 175 s publication gate. Shapes A and B
below were not chosen. B would drop Request changes and Confirm, which is the governed write
and a must-show row, and A keeps only 0.04 s to 2.5 s of margin. The drill-down with Claude
stays live for judges to try, and the Devpost text points at it. The replay clip was
re-recorded on `873845d`, because take 5's clip shows `716b0f3`; take 6's band tag names
`873845d`. The arithmetic below is kept as the record of why.

The live build serves `873845d` (PR #40) since 2026-10-19. Its drill-down asks Amazon Bedrock
about one file and shows the answer with its own label and coverage line. Take 6 was meant to
add one beat for it. This section is the arithmetic, and it is why `narration.json` holds
the seven beats of take 5.

**Nothing in this section was measured on a take.** It was written before take 6 was
recorded, and no take or free rehearsal has pressed the drill-down, so every duration below is
ESTIMATE. Take 6, recorded without the drill-down, passed the sync gate
([`README.md`](README.md)).

**The drill-down's sentence.** On the stage patch, `Inverted admin check`, the page has one
file, `src/auth/permissions.py`, so the button reads `Drill into file 1` from page load (the
preset loads on start, and `renderPatchView` sets the section count). The page speaks
`spoken_text_for_speech` as one utterance.

* Measured on `873845d` with `op_drill_down` and no AWS credentials, 2026-10-19:
  `spoken_text` is 294 characters and `spoken_text_for_speech` is 313. The local part already
  speaks the patch's operators by name ("user.role equals equals 'admin' became user.role not
  equals 'admin'"). The ending `No model answered: no AWS credentials were resolved by the
  boto3 credential chain.` is 83 with its space. That leaves 230.
* On the live build that ending becomes ` Claude Sonnet 5 on Amazon Bedrock says: ` (41) and the
  model's line, which `shorten_for_speech` cuts at the 180-character budget, so at most 182
  with its ellipsis. So 230 + 41 + 182 = 453 characters before operators.
* `speakable()` runs after that cut, so every operator the model's line names makes it longer.
  Measured: a 99-character line with one `!=` speaks as 107, so 8 more. `==` adds about 11 by
  the same rule (ESTIMATE). A line that quotes the patch's change, `==` became `!=`, speaks
  about 19 more characters, about 1.7 s at the rate below (ESTIMATE). The stage patch is
  exactly that change, so this case is likely.
* The 2026-10-06 ledger `bedrock-diagnosis-ledger.jsonl` cannot bound the operators: it records
  each answer's length, not its text, so `speakable()` cannot be applied to it. Its 8 Sonnet 5
  answers were 156 to 348 characters, 7 of them over the budget, and they answered the digest
  prompt, not the one-file drill-down prompt. Only a billed take measures the real line.

**The window (ESTIMATE).** By beat 2's rule: the 5.9 s latency allowance, the 0.66 s earcon
lead, and 453 characters at the slowest measured rate, 0.0902 s a character, plus 1 s:
5.9 + 0.66 + 40.86 + 1 = 48.42 s, rounded up to the half second, 48.5 s. A line that quotes
both operators needs about 1.7 s more, so 50.5 s. With a one-line narration before the press
(about 3.4 s, ESTIMATE, like beat 2's) and the 0.65 s tail, the beat holds about 52.55 s, or
about 54.6 s with the larger window. A free rehearsal cannot measure this window: its sentence
is the 313-character local form, about 28.2 s at the same rate.

**Where it can go.** The page writes the drill-down's coverage line and full answer into the
same elements as the digest, and overwrites the engine meter. When Hear is pressed on camera
(shape B), the drill-down comes after beat 3's hold on the digest's coverage line. In shape A
there is no digest press, so the drill-down is beat 2's press and beat 3 holds the
drill-down's own coverage line, which needs new beat 3 text (see below). In either shape the
narration before the press names only the button. Anything that names the model, the label
or the coverage line is said after the answer is on screen.

**The budget.** Take 5 measured 153.412 s, and 167.448 s with the 14.0 s replay clip. The
publication gate is 175 s. All margins are ESTIMATE.

| Shape | Billed calls | Video, ESTIMATE | Margin under 175 s | What it costs |
|---|---|---|---|---|
| Keep every take 5 turn and add the drill-down beat | 6: open, Hear, drill-down, 3 replay | 167.448 + 52.55 = 220.0 s | none, 45 s over | nothing |
| A. The drill-down replaces Hear as beat 2's press | 5: open, drill-down, 3 replay | 167.448 + (52.55 - 45.04) = 174.96 s; 172.5 s after cutting beat 3's second sentence | 0.04 s; 2.5 s with the cut; about 0.5 s with the cut if the line quotes both operators | Hear is not pressed on camera, and beat 3 loses the sentence that points at the coverage line |
| B. Keep Hear and the drill-down, drop beats 4, 5 and 6 and end on a short narration beat | 6: open, Hear, drill-down, 3 replay | 220.0 - 65.62 + about 4.4 = 158.8 s | about 16.2 s; about 14.1 s if the line quotes both operators | Request changes, Confirm and the recorded request leave the video, and with them the governed write |
| Keep Hear and the drill-down, drop only Confirm and beat 6 | 6 | 220.0 - 33.65 + about 4.4 = 190.8 s | none | |

No cut inside a product turn or a model wait is allowed, so the gap cannot be closed by
trimming product speech. Beats 1, 6 and 7 were already cut on 2026-10-06.

**Recommendation before the decision: shape B (not chosen; see above).** Shape A cannot keep 5 s of margin, and as written it has four
defects, each of which would have to be fixed before it could be offered:

1. Its margin is 0.04 s. The 2.5 s exists only after cutting beat 3's second sentence,
   "That's how much it read, and which model.", which is the sentence that points at the
   coverage line and the model label that take 6 exists to show. A line that quotes both
   operators takes about 2 s of what is left, once the window is rounded up.
2. Beat 3's `visual_action` and the capture's `coverage_line_problem` expect the digest's
   line, `The model read the whole N-character patch. Answered by ...`. With no digest press,
   the line on screen is the drill-down's, `Claude Sonnet 5 on Amazon Bedrock read N of M
   characters of src/auth/permissions.py's part of the patch. The local rules read all of this
   file's changes.`, so both would fail the take. Beat 3 needs new text and `visual_action`,
   and `drill_label_problem` in place of `coverage_line_problem`.
3. Beat 2's line, "Press once, and this patch goes to Amazon Bedrock.", names Amazon Bedrock
   before the press, and says "this patch" when only one file's part is sent. That breaks
   the rule above that the narration before the press names only the button.
4. "Keeps every must-show row" holds only after 2 and 3 are fixed: as written, the row for
   the coverage line naming the model rests on a beat the capture would fail.

Shape B, re-derived against the must-show table below, keeps every row but one: "Every
product turn on camera ... That includes Request changes". Request changes and Confirm leave
the video, so the governed write is not shown. The row "The screencast ends on narration"
moves from beat 6 to the new closing narration beat. Choosing B meant accepting that loss.

**What either shape needs before a free rehearsal, in one commit:** the beat in
`narration.json`, `EXPECTED_BEATS` and the journey; `drill_down` in `BILLED_PRESSES`; the
`capture-local.py` module docstring and README section 1, which still describe take 5's
two-call journey; `drill_label_problem` called at the drill-down press, reading
`#meterEngine`'s `firstChild.nodeValue` (the page sets that text node, not `textContent`),
`#modelCoverage`'s `textContent`, the response JSON and `/health`'s
`bedrock_model_path.model_id`, and failing the take on any problem; the answer-latency check
and the speech-ended-before-the-next-beat check extended to the drill-down beat; and a test
that fails if the journey stops calling `drill_label_problem`. The replay clip had to be
re-recorded, because take 5's clip shows `716b0f3`, and take 6's was. A take 6 copy of the
splice script that reads its band tag from `capture/capture-receipt.json` is kept outside the
repository, beside take 5's.

**What the capture checks today for take 6:**

* `billed_kind` names `POST /api/drill_down_section` as a billed `drill_down`. Until a
  shape is chosen it is not in `BILLED_PRESSES`, so a drill-down press in a take or a
  rehearsal is refused.
* `drill_label_problem` is defined and unit-tested, not yet called by the capture: the
  journey has no drill-down press until a shape is chosen. Once wired, in a take the meter
  must read exactly `Claude Sonnet 5 on Amazon Bedrock`, built from the response's
  `model_answered`, which must be the `model_id` that `/health` reports. `Amazon Bedrock,
  model not named` is refused. The coverage line must be exactly the one `renderDrillModel`
  prints. In a rehearsal the meter must read `local rules, no model answered`, no coverage
  line may be printed, and the sentence must end `No model answered: <reason>.`. A rehearsal
  whose drill-down names a model fails.

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
| Under 170 s measured, inside the kit's 175 s publication budget | 153.4 s measured |

## Time budget (measured)

| Segment | From | To | Seconds | Product sound in it |
|---|---|---|---|---|
| Title card | 0.0 | 2.0 | 2.0 | none |
| Cold open | 2.0 | 15.5 | 13.5 | `line 26` on the opened pull request |
| Beat 1, `beat_01_alexa_value` | 15.5 | 23.3 | 7.8 | none |
| Beat 2, `beat_02_bedrock_press` | 23.3 | 68.3 | 45.0 | the Bedrock answer to Hear this code review |
| Beat 3, `beat_03_model_coverage` | 68.3 | 77.2 | 8.9 | none |
| Beat 4, `beat_04_request_changes` | 77.2 | 109.1 | 32.0 | Request changes |
| Beat 5, `beat_05_confirm` | 109.1 | 138.4 | 29.3 | Confirm |
| Beat 6, `beat_06_recorded_request` | 138.4 | 142.8 | 4.4 | none |
| Beat 7, `beat_07_mcp_handshake` | 142.8 | 148.9 | 6.1 | none |
| Closing card | 148.9 | 153.4 | 4.5 | none |

`video/generate-narration.py --write-timestamps` measured 133.412 s of beats on 2026-10-07,
so the video is 2.0 + 13.5 + 133.412 + 4.5 = 153.412 s. It ran three times that day. The first
re-synthesized beat 3 only, 109 characters, for its new line naming Claude; every other beat
reused its cached audio, and shrinking beat 2's window from 58.5 to 43.5 s sent nothing. The
second widened beat 4's window from 26.5 to 27.0 s, because the rehearsal that day measured
Request changes at 25.763 s, past the 25.45 s slowest run its window was sized from; it sent
nothing either. The third shrank beat 2's window from 43.5 to 41.0 s, below; no words changed,
all seven beats reused their cached audio, and it sent 0 characters. Of the 17.5 s the shorter
beat 2 frees against the 58.5 s window, beat 3's longer line takes 0.6 s and beat 4 0.5 s under
its own rule; the rest is not spent: nothing is padded, and the video is shorter.

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
* **Beat 2's window, 41.0 s from the press, holds an answer that starts within 5.9 s.** The
  58.5 s window before it was sized for a call that ran to the 25 s timeout on Claude Opus 5.
  The live build now answers with `anthropic.claude-sonnet-5` on a 1769 MB function: one press
  of the take-4 patch answered in 3.44 s at the client (Lambda 3071 ms, model 1266 ms), where
  the same press at 256 MB took 17.88 s (Lambda 17562 ms, model 2959 ms). A fast answer left
  about 20 s of idle picture in the 58.5 s window, and about 7 s in the 43.5 s window that
  followed, which used a 10 s allowance and take 3's rate. The parts of the 41.0 s window:
  * **a latency allowance of 5.9 s** (ESTIMATE, `ANSWER_LATENCY_ALLOWANCE_SECONDS` in
    `video/capture-local.py`), from the planned press to the answer's first sound, about 1.7
    times the one press measured at 1769 MB. It covers the press itself, the round trip and the
    model call;
  * **the falling earcon, 0.66 s.** It started 0.63 to 0.66 s before the first word in three of
    the four free rehearsals of 2026-10-06 and 2026-10-07, and 0.38 s before it in the fourth,
    so the window takes the longest;
  * **the longest sentence the page can speak** for the stage patch, at the slowest rate
    measured for it, plus 1 s, the margin beats 4 and 5 use. `to_voice_summary(level=0)`
    builds the finding, then the model's headline (only when `synthesis_mode` is `bedrock`),
    then the counts, and the page speaks its `voice_summary_for_speech`. Measured on take 3's
    for-speech sentence of 359 characters:
    * the local finding, 139 characters with the space after it;
    * the headline: `shorten_for_speech` keeps at most 180 characters of the model's line and
      closes a cut with a space and an ellipsis, so at most 182, and `to_voice_summary` adds a
      full stop, 1;
    * the counts, 48 characters with the space before them;
    * 139 + 182 + 1 + 48 = 370 characters.

    The slowest rate is the local engine's: its 186-character sentence, finding and counts
    only, took 16.741 to 16.783 s in those four rehearsals, and 16.783 / 186 = 0.0902 s a
    character. Take 3's Bedrock answer spoke faster, 359 characters in 31.42 s, 0.0875 s a
    character. The 31.42 s comes from take 3's actions in `take3-failure-locals.json`, in the
    media root outside the repository: `speech ended` at 45.328 s, less the scroll that follows
    `speech.start` at 13.906 s, is 45.328 - 13.906 = 31.422 s. At the slowest rate, 370
    characters take 33.39 s, plus 1 s: 34.39 s.

  5.9 + 0.66 + 34.39 = 40.95 s, rounded up to the half second: 41.0 s. The allowance was taken
  from the window. 41.0 s is the longest window, on the half second, that leaves at most 5 s of
  silent page after the measured 3.44 s press with a full headline at take 3's rate: 3.44 +
  0.65 + 32.38 = 36.47 s leaves 4.53 s, where 41.5 s would leave 5.03 s. What 41.0 s leaves for
  the answer to start is 41.0 - 0.66 - 34.39 = 5.95 s, rounded down to a tenth: 5.9 s. One
  limit on that figure: the operator names (`!=` spoken as "not equals") are added after the
  cut, so a headline with code operators in it speaks more than 182 characters and can run the
  answer past the window. The capture then fails the take, as below.
* **A slow answer means a retake.** The capture fails the take, and lists a failure in a
  rehearsal, when the answer's first sound comes more than 5.9 s after the planned press, even
  when the rest would have fitted. It also still fails a take whose speech has not ended when
  beat 3 begins. An answer can never run on, unchecked, past the window.
* **The generator's cap is 45 s again.** It was raised from 45 s to 60 s for the 58.5 s window.
  The cap is a plan constraint in `video/generate-narration.py`, not a gate:
  `scripts/verify_video_sync.py` never reads it, and every window still needs its basis.
* **Beat 3 names Claude.** It says "Claude on Amazon Bedrock answered, on AWS Lambda with
  DynamoDB. That's how much it read, and which model." while the meter and then the coverage
  line are on screen. The coverage line now ends with `Answered by` and the model the answer
  names in `model_answered`, which PR #35 added to the page.
* **Beats 1, 6 and 7 stay as cut on 2026-10-06.** To pay for the 58.5 s window then, beat 1
  went from 8.9 to 7.8 s, beat 6 from 6.9 to 4.4 s and beat 7 from 8.5 to 6.1 s. They are not
  lengthened again: the video is shorter instead. Beat 4, cut then from 33.6 to 31.5 s, grew to
  32.0 s on 2026-10-07 under its own rule, after that day's rehearsal measured Request changes
  at 25.763 s. Beat 3 grew from 8.3 to 8.9 s and beat 2 shrank from 62.5 to 45.0 s.
* **The optional consented clip fits again.** At 153.4 s, a clip of up to 16.5 s keeps the
  video under 170 s, and up to 21.5 s keeps it under the 175 s budget.

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

These presses are authorised in writing before rehearsal, because each one is billed. The page
load does not call a model: the silent preview asks for the local engine.

| Action | Model calls |
|---|---|
| **Hear this code review** | one, with the first 3000 characters of the stage patch |
| Opening a pull request in the review dialogue | one, with the pull request's patch (the dialogue digests it with the default engine) |
| **Replay the documented Alexa+ requests** | three, one `digest_semantic_diff` call per client. The capture never presses it; take 6's replay clip pressed it once, in a separate recording |
| `line 26`, Findings, Summary, File by file, Request changes, Confirm, **Run a real MCP handshake** | none |

**Bound to authorise:** at most 12 Bedrock calls. That covers three rehearsals and three takes
at two calls each (opening the pull request, then the press). A take that needs more stops,
and the authorisation is asked for again.

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
| 1 | Maintainer | Authorise the billed calls above, in writing | The bound and the date are written down before any press |
| 2 | Maintainer | `curl -s https://qylv1gxor9.execute-api.eu-west-1.amazonaws.com/health` | `source_revision` names the commit that becomes `{sha7}`: `873845d` for take 6. `bedrock_model_path` reads `ready_to_attempt` with `model_id` `anthropic.claude-sonnet-5`, `durable_state` reads `configured_reachable`, and `github_review_path` reads `dry_run_no_token`. If it reads `dry_run_with_token`, beat 6 must not say "No GitHub token here" |
| 3 | Maintainer | Open the GitHub Actions run for that commit | Green. Note the run id in the take's receipt. If a test count is ever shown, it is this run's count, filmed from this page |
| 4 | Maintainer | Rehearse on the live page, in the browser and window size used for the take | Each Bedrock press reads **Amazon Bedrock** on the engine meter with no fallback reason, its answer makes its first sound within 5.9 s of the press and ends inside 41.0 s of it, and the coverage line ends `Answered by anthropic.claude-sonnet-5.`. The press waits for beat 2's narrator, so no latency can start the answer under the narration |
| 5 | Maintainer | Read the model's full answer in rehearsal | Note whether it shows Markdown marks; see the risks below |
| 6 | Maintainer | `video/generate-narration.py --write-timestamps` | Measured beat windows written back; total narration 90 to 174 s. With the cached audio it sends nothing to ElevenLabs |
| 7 | Maintainer | Within 60 s before the take, `GET /health` again, then reload the page and open the chosen pull request | The function is warm, and the opened overview is on screen before recording starts |

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

## Beat 2, `beat_02_bedrock_press`, 23.3 to 68.3 seconds

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
  3.44 s answer with a full headline, about 4.5 s. A shorter answer leaves more: the 156-character
  answer, one of four Sonnet 5 answers on the take-4 patch, would leave about 6.8 s. A fixed
  window cannot bound both the latency and the answer's length.
* **Window:** 41.0 s from the press, for an answer whose first sound comes within 5.9 s and the
  longest sentence the page can speak; the parts are under the time budget above.
* **Fails the take:** an engine meter that reads local heuristic, a fallback reason, an
  answer that starts while the narrator is still speaking, an answer whose first sound comes
  more than 5.9 s after the press, or an answer still speaking when beat 3 begins.
* **In a free rehearsal** the press is made at the same moment. The local engine answers at
  once, and its sentence has no headline, so the page holds, silent, for about 22.5 s: 25.06 s
  in the rehearsal of the 43.5 s window, less 2.5 s.

## Beat 3, `beat_03_model_coverage`, 68.3 to 77.2 seconds

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

## Optional slot, after beat 3: only with a recorded, consented session

**Only if a consented session is recorded.** Without one, this slot is left out and
nothing replaces it. It is deliberately not in `narration.json`, so a default render can never
include it. At 153.4 s, a clip of up to 16.5 s keeps the video under 170 s.

* 10 to 15 seconds of a blind or low-vision developer using Volcan with their own screen
  reader, during one of the five timed sessions the README names as the cheapest test of its
  riskiest assumption.
* Written consent to appear in a public video is given before recording. The participant
  decides whether their face, voice and name appear.
* The clip shows what happened, including a failure if that is what happened. It is not
  re-staged, and no praise is scripted.
* The band says it is a recorded session, with its date, and that consent was given. The
  narration adds no claim about the result beyond what the published session results say.

## Beat 4, `beat_04_request_changes`, 77.2 to 109.1 seconds

* **Narration:** "Request changes stages a review, bound to the head commit it read."
* **After the narrator stops:** the review comment `is_admin is inverted.` goes into the
  comment box, and then **Request changes**. Typing `request changes:` and the comment with
  <kbd>Alt</kbd>+<kbd>4</kbd> works too.
* **Sound:** the page's cue and readback, then `Ready to request changes on` the pull request,
  `bound to head commit` and its short id, `with the comment:`, and `Say confirm to submit it,
  or cancel.` State **AWAITING CONFIRM**. The last take talked over this turn; this one keeps
  all of it, in a 27.0 s window measured on the chosen pull request.

## Beat 5, `beat_05_confirm`, 109.1 to 138.4 seconds

* **Narration:** "Nothing leaves Volcan until you confirm. Confirm, and listen."
* **After the narrator stops:** **Confirm**. The page speaks `Understood: confirm.` and then its
  dry-run answer: nothing was sent to GitHub, the head commit is unchanged, the exact request
  is recorded, and a live send would be refused because no `GITHUB_TOKEN` is set. State
  **RECORDED, NOT SENT**. Midway through, the view moves to the review pane, which shows the
  outcome and the exact `POST` body the server recorded. Nothing talks over the turn.

## Beat 6, `beat_06_recorded_request`, 138.4 to 142.8 seconds

* **Narration:** "No GitHub token here: the request is recorded, not sent."
* **On screen:** the review pane, held: outcome recorded and not sent, the live head re-read,
  and the exact `POST` body. No product turn.
* **Why this beat:** the page has stopped speaking before it starts, and the screencast ends
  on its narration. A screencast that ends on the page's own speech ends in silence, because
  the window keeps the slowest-run-plus-1-s margin and the re-rendered system voice ends before
  the browser's, so the sync gate's `content-seam<=1s` check failed by 4.0 s on the earlier
  plan. Ending on narration leaves the generator's 0.65 s tail.

## Beat 7, `beat_07_mcp_handshake`, 142.8 to 148.9 seconds

* **Narration:** "This MCP handshake is real. Alexa+ never called Volcan." The page prints the
  negotiated revision, 2025-11-25.
* **On screen:**
  * Evidence, tab **Server and MCP**, shows **Server reached** with the commit and the model
    path the live server reports.
  * **Run a real MCP handshake** sends `initialize` and `tools/list` and calls no tool. It is
    pressed as the beat starts, and the negotiated version and the tool list are held for at
    least 2.0 s (`MCP_FACTS_HOLD_SECONDS` in `capture-local.py`) and until 40% into the last
    sentence. Take 6's first attempt, on 2026-10-19, pressed it on the first sentence. The live
    build answered 0.81 s later and the page jumped away 0.19 s after that, so frames read by
    index at 144.2 s and 144.8 s showed `not run yet` and then the connection strip.
  * Then the connection strip's Alexa+ box: package built and tested locally, not certified
    or deployed.
* **Not pressed in this beat:** **Replay the documented Alexa+ requests**. On the live build it
  costs three Bedrock calls and could run close to a minute. Take 6 adds a separately recorded
  14.0 s clip of that press on the live build after this beat's narration, so in the final file
  the closing card runs from 162.9 to 167.4 s ([`README.md`](README.md), sections 1 and 2).

## Closing card, 148.9 to 153.4 seconds

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

The repository is private on 2026-10-20 (`gh repo view` reports `PRIVATE`). Before the video
is uploaded, the repository is made public or the judges are added as collaborators; otherwise
the source line points at a page judges cannot open.

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
  later than 5.9 s fails the take first, on the latency allowance.
* **Beat 2's window.** The window holds 41.0 s from the press, which waits for the narrator:
  an answer whose first sound comes within 5.9 s, then 0.66 s of earcon lead and the longest
  sentence, 34.39 s at the slowest measured rate plus 1 s. A cold function, a throttled call or
  a slow model can pass 5.9 s: on the 256 MB function the same press took 17.88 s. The capture
  fails that take, and it is recorded again; warm the function with `GET /health` within 60 s
  of the take, as step 7 says. Since PR #35 the model client is built with `max_retries=0`, so
  the SDK does not retry a call on its own.
* **Confirm on the live build is checked only offline.** That was the risk before take 6, which
  then ran Confirm on the live `873845d`: the page spoke its dry-run answer and the review pane
  showed the recorded, unsent request ([`README.md`](README.md)). Before that, no receipt
  showed Confirm answered on the live `716b0f3`. Its deploy receipt, kept outside the
  repository, checked `/health` and two presses, and no review turn. The one before it, on `22c32ab`, checked opening the pull
  request, `line 26`, Request changes and cancel, not Confirm; Request changes had answered with
  a 503 on `aa3364a`, from a DynamoDB write the `22c32ab` fix (PR #34) corrected. On the live
  build Confirm writes to DynamoDB: it claims the staged action and burns its nonce. That write
  is checked only offline, by
  `test_confirming_claims_the_action_and_burns_the_nonce_once_serialized` in
  `tests/unit/test_dynamodb_wire_shape.py`, and by the free rehearsals, which keep the state in
  process memory. The take fails safe: the build has no GitHub token, so Confirm cannot send a
  review, and the capture fails the take when the dialogue refuses the turn or the review pane
  does not show a recorded, unsent review. A failure there costs a take, two billed calls
  against the bound, and nothing else. Confirm calls no model.
* **No rule matched.** The page now hedges that answer ("No security rule matched this
  change. The rules can miss a risk"), but the cold open is for a finding, so the capture
  refuses it there. The chosen pull request has 2 findings.
* **Latency.** The live Bedrock figures on record: one digest of 19.67 s on 2026-10-01; take
  3's press on 2026-10-06, whose answer sounded about 4.3 s after the press; and on `716b0f3`,
  one press of the take-4 patch in 17.88 s at 256 MB and one in 3.44 s at 1769 MB, the memory
  the function has now. Each figure is one press. Every other turn in the take calls no model,
  and the network adds a round trip to each.
