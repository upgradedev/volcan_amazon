# Volcan: shot list

**Status: recorded on 2026-09-28 (local time), from a local run of commit `7a3de49`.** The
render is 164.52 seconds and lives outside the repository, pending upload by the owner. This
file is the journey `video/capture-local.py` drives, beat by beat, and it matches what that take
shows. [`README.md`](README.md) in this folder says how the render was produced.

The beat ids match [`narration.json`](narration.json) and [`cue_sheet.json`](cue_sheet.json)
one for one. Beat windows are measured, not authored: each is the ElevenLabs audio length from
ffprobe plus a 0.65 second tail, and beats 1, 3 and 4 add a window in which the page itself
speaks. Times below are from the start of the video, after the 3.0 second title card.

---

## Before the camera rolls

| Step | Command or action | What must be true |
|---|---|---|
| 1 | `python -m pytest tests/ -q` on the commit | `646 passed` on 2026-09-28, on `7a3de49`. |
| 2 | `python -m src.interfaces.mcp_server --port 8871`, started fresh, with no AWS credentials reachable, no GitHub token and `SOURCE_REVISION` set to the commit | `GET /health` reports `unavailable_no_sdk_and_no_credentials`, `dry_run_no_token` and the commit as `source_revision`. |
| 3 | `python scripts/mcp_conformance.py http://127.0.0.1:8871/mcp` against that server, then restart it fresh | `23/23 checks passed` on 2026-09-28. |
| 4 | `python video/capture-local.py` | The page at `http://127.0.0.1:8871/` in headless Chromium at 1280x720 reads **Online** and has drawn the silent preview before the timeline starts, and `/health` reports the same commit as `VOLCAN_RELEASE_SHA`. |

---

## Title card, 0 to 3.0 seconds

`Volcan. Hear your code review instead of scrubbing a diff. A local run of commit 7a3de49.
Simulated Alexa+ front end. GitHub dry run.`

## The frame

The page is scaled to 1632x918 at the top of the 1920x1080 frame. Everything the build adds sits
in the band under it: the captions, a small grey tag `Local run of commit 7a3de49. Not the public
deployment.`, and the amber label for the stretches where the page's own voice is not mixed. No
overlay covers the page.

## Beat 1, `beat_01_press`, 3.0 to 35.1 seconds

* **On screen, while the narrator speaks:** the page at first paint: the heading **Hear your
  code review instead of scrubbing a diff**, **For blind and low-vision developers**, the
  `Inverted admin check` patch, the silent preview (grey waveform, **Falling** contour, the
  finding sentence, **Server's first sentence, not played yet.**) and the label **Live MCP
  server, simulated Alexa+ front end. Not an Alexa skill. GitHub: dry-run.** On "one key press",
  <kbd>Alt</kbd>+<kbd>1</kbd> puts the focus ring on **Hear this code review**.
* **At 15.7 s, after the narrator says "Listen":** <kbd>Enter</kbd>. The page plays the earcon,
  then the view moves so the earcon caption, the spoken sentence, the security finding box and
  the Braille share the frame while the browser speaks the server's sentence, finding first.
* **Sound and captions:** the earcon WAV the server returned, captioned `[Volcan earcon: security
  finding]`, and the sentence the page passed to `speechSynthesis`, rendered with the Windows
  system voice and captioned `Volcan (product voice):`.
* **Window:** 19.5 seconds. The take fails if speech has not ended inside it; in this take it
  ended 0.93 seconds early.

## Beat 2, `beat_02_what_you_heard`, 35.1 to 57.8 seconds

* **On screen:** the same frame: the earcon caption `Security finding cue, falling pitch contour
  measured from its samples, 0.60 seconds of 16-bit PCM at 22050 Hz (SECURITY_FINDING)`, the
  spoken sentence, the red security finding box and the Braille. On the last sentence the
  information button beside **Synthesis engine** opens the server's reason: `no AWS credentials
  were resolved by the boto3 credential chain`.

## Beat 3, `beat_03_open_pull_request`, 57.8 to 82.5 seconds

* **On screen:** **Talk through a real pull request, then request changes.**
  <kbd>Alt</kbd>+<kbd>6</kbd> focuses the pull request URL box, the URL of `octocat/Hello-World`
  pull request 1 is typed, and <kbd>Enter</kbd> opens it: `Opened octocat/Hello-World pull
  request 1, Edited README via GitHub, by unoju, head commit 7044a8a ... 0 security findings`.
  The view moves to the dialogue with the next steps outlined: **File by file**, **Findings**,
  **Read the lines**.
* **Label, while the narrator talks over the page:** `Not in this recording: the page's own cue
  and voice for this turn`, from the page's first sound for the turn until **Findings**
  interrupts it.
* **After the narrator stops:** **Findings**. The page plays its cue and speaks `Understood:
  findings.` then `No security finding in this change.` Both are in the mix, captioned as the
  product voice; the cue is captioned `[Volcan earcon: diff ready]`.

## Beat 4, `beat_04_request_changes`, 82.5 to 119.0 seconds

* **On screen:** a comment that says it is a dry-run demo goes into the comment box and
  **Request changes** stages the review: the dialogue reads back `Ready to request changes on
  octocat/Hello-World pull request 1, bound to head commit 7044a8a ... Say confirm to submit it,
  or cancel.`, state `AWAITING CONFIRM`, with **Confirm** and **Cancel** outlined.
* **Label:** the same band label, from the page's first sound for the turn until **Confirm**
  interrupts it.
* **After the narrator stops:** **Confirm**. The page plays its cue and speaks `Understood:
  confirm.` then `Dry run. Nothing was sent to GitHub. The head commit is still 7044a8a, and the
  exact request Volcan would send has been recorded. A live send would be refused: no
  GITHUB_TOKEN is set.` Both are in the mix, captioned as the product voice. State `RECORDED,
  NOT SENT`. Midway the view moves to the review pane: outcome `recorded and not sent`, the live
  head re-read and the exact `POST .../pulls/1/reviews` body the server recorded.

## Beat 5, `beat_05_mcp_handshake`, 119.0 to 136.6 seconds

* **On screen:** Evidence, tab **Server and MCP**, with **SERVER REACHED** naming commit
  `7a3de49`. **Run a real MCP handshake**, then the four facts: `2025-11-25`,
  `volcan-accessible-forge 0.1.0`, a session id from the `Mcp-Session-Id` header and `12` tools.
  The first tool, `braille_diff_digest`, expands to its published `inputSchema`.

## Beat 6, `beat_06_verification`, 136.6 to 160.0 seconds

* **On screen:** the connection strip, whose Alexa+ add-on box reads `package built and tested
  locally, not certified or deployed; the add-on tools are partner-only (hackathon FAQ); no
  device test`. On the second sentence, **Replay the documented Alexa+ requests**, then the
  three client lines, each `served`, and `3 of 3 clients served`. Back to the connection strip,
  then the page heading and its label.
* **Not on screen:** `python -m pytest tests/ -q` and `python scripts/mcp_conformance.py`. The
  figures in the narration, 646 tests and 23 of 23 conformance checks, were printed by those
  commands on 2026-09-28 against commit `7a3de49`.

## Outro card, 160.0 to 164.5 seconds

`Volcan. Local run of commit 7a3de49. Not the public deployment. Not an Alexa skill. GitHub
review: a dry run, recorded and not sent. Engine: local heuristic. Narration: synthetic
ElevenLabs voice. Product voice: the page's own sentences, rendered with the Windows system
voice.`

---

## What must not appear in the recording

* An Echo device, an Alexa wake word, or any Alexa skill screen. No skill exists.
* A Bedrock console, a model id, or a response labelled `synthesis_mode: bedrock`. This take's
  server had no credentials and no SDK, and the page says so.
* A review sent to GitHub. The server records the request and sends nothing.
* A command executing after approval.
* Any figure typed into an overlay. The overlays are the title and outro cards, the commit tag,
  the band label and the captions; every number on a page frame is one the page printed during
  the take.
* A deployed URL. The public endpoint runs an older commit.
