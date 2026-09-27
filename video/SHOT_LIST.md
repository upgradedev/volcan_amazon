# Volcan: shot list

**Status: recorded on 2026-09-27 (local time), from a local run of commit `1dc939f`.** The
render is 174.32 seconds and lives outside the repository, pending upload by the owner. This
file is the journey `video/capture-local.py` drives, beat by beat, and it matches what that take
shows. [`README.md`](README.md) in this folder says how the render was produced.

The beat ids match [`narration.json`](narration.json) and [`cue_sheet.json`](cue_sheet.json)
one for one. Beat windows are measured, not authored: each is the ElevenLabs audio length from
ffprobe plus a 0.65 second tail, and beat 2 adds a 21.5 second window for the product's own
sound. Times below are from the start of the video, after the 3.5 second title card.

---

## Before the camera rolls

| Step | Command or action | What must be true |
|---|---|---|
| 1 | `python -m pytest tests/ -q` | `637 passed` on 2026-09-27. |
| 2 | `python -m src.interfaces.mcp_server --port 8841`, started fresh, with no AWS credentials reachable, no GitHub token and `SOURCE_REVISION` set to the commit | `GET /health` reports `unavailable_no_sdk_and_no_credentials`, `dry_run_no_token` and the commit as `source_revision`. |
| 3 | `python scripts/mcp_conformance.py http://127.0.0.1:8841/mcp` against a server of the same `src/` | `23/23 checks passed`. |
| 4 | `python video/capture-local.py` | The page at `http://127.0.0.1:8841/` in headless Chromium at 1280x720 reads **Online** and has drawn the silent preview before the timeline starts. |

---

## Title card, 0 to 3.5 seconds

`Volcan. Recorded from a local run of commit 1dc939f. Public deployment pending.` A corner tag
repeats `Local run of commit 1dc939f. Not the public deployment.` on every page frame.

## Beat 1, `beat_01_hook`, 3.5 to 22.4 seconds

* **On screen:** the page at first paint with the `Inverted admin check` patch and the label
  **Live MCP server, simulated Alexa+ front end. Not an Alexa skill. GitHub: dry-run.** On the
  third sentence, <kbd>Alt</kbd>+<kbd>2</kbd> opens the patch box and shows the raw unified diff
  with its hunk header and its plus and minus lines.
* **Not on screen:** a screen reader. Headless capture has none, so the narration states the
  problem instead of pretending to play one.

## Beat 2, `beat_02_one_button`, 22.4 to 64.8 seconds

* **On screen, while the narrator speaks:** the silent preview the page drew from the server's
  answer: the grey waveform, the **Falling** contour, the finding sentence, the Braille cells
  and **Server's first sentence, not played yet.** <kbd>Alt</kbd>+<kbd>1</kbd> puts the focus
  ring on **Hear this code review**.
* **After the narrator says "Listen":** <kbd>Enter</kbd>. The narrator is silent for the
  product window. The page plays the earcon and the playhead crosses the waveform, then the
  browser speaks the server's sentence, finding first, and the meters show `local heuristic`,
  the measured round trip and `1 file +1 -1`.
* **Sound and captions:** the earcon is the WAV the server returned for this press, mixed in
  where the page's playback clock started it. The sentence is the exact text the page passed to
  `speechSynthesis`, rendered with the Windows system voice of the same name, labelled on screen
  as the browser's system voice and captioned as `Volcan:`.
* **Window:** 21.5 seconds. The take fails if speech has not ended inside it; in the final take
  it ended 0.45 seconds early.

## Beat 3, `beat_03_what_you_heard`, 64.8 to 87.6 seconds

* **On screen:** the earcon caption `Security finding cue, falling pitch contour measured from
  its samples, 0.60 seconds of 16-bit PCM at 22050 Hz (SECURITY_FINDING)`, the spoken sentence,
  the red security finding box, then the information button beside **Synthesis engine** opens
  the server's reason: `no AWS credentials were resolved by the boto3 credential chain`.

## Beat 4, `beat_04_mcp_handshake`, 87.6 to 111.7 seconds

* **On screen:** Evidence, tab **Server and MCP**. **Run a real MCP handshake**, then the four
  facts: `2025-11-25`, `volcan-accessible-forge 0.1.0`, a session id from the `Mcp-Session-Id`
  header and `12` tools. The first tool, `braille_diff_digest`, expands to its published
  `inputSchema`.

## Beat 5, `beat_05_pull_request`, 111.7 to 140.7 seconds

* **On screen:** **Talk through a real pull request, then request changes.**
  <kbd>Alt</kbd>+<kbd>6</kbd> focuses the pull request URL box, the URL of
  `octocat/Hello-World` pull request 1 is typed, and <kbd>Enter</kbd> opens it: the dialogue
  answers `Opened octocat/Hello-World pull request 1 ... head commit 7044a8a ... 0 security
  findings`. **Summary** answers `no security rule matched`. A comment that says it is a dry-run
  demo goes into the comment box and **Request changes** stages the review, bound to head commit
  `7044a8a`, state `AWAITING CONFIRM`. **Confirm** answers `Dry run. Nothing was sent to
  GitHub.`, state `RECORDED, NOT SENT`, then the review pane shows the outcome `recorded and not
  sent`, the live head re-read and the exact `POST .../pulls/1/reviews` body the server recorded.
* **Label:** `Not in this recording: the page's own cue and speech for these review turns.` The
  page plays a cue and speaks each answer; only the narrator is heard.

## Beat 6, `beat_06_verification`, 140.7 to 170.8 seconds

* **On screen:** tab **Server and MCP**: **SERVER REACHED** with the model path
  `unavailable_no_sdk_and_no_credentials`, and the path strip whose Alexa+ add-on box reads
  `package built and tested locally, not certified or deployed; the add-on tools are
  partner-only (hackathon FAQ); no device test`. On the second sentence, **Replay the documented
  Alexa+ requests**, then the three client lines, each `served`, and `3 of 3 clients served`.
  Back to the connection strip and the Alexa+ box, then the page heading and its label.
* **Not on screen:** `python -m pytest tests/ -q` and `python scripts/mcp_conformance.py`. The
  figures in the narration, 637 tests and 23 of 23 conformance checks, were printed by those
  commands on 2026-09-27, as [`README.md`](README.md) records.

## Outro card, 170.8 to 174.3 seconds

`Recorded from a local run of commit 1dc939f. Public deployment pending. Narration: synthetic
ElevenLabs voice. Product speech: the browser's system voice.`

---

## What must not appear in the recording

* An Echo device, an Alexa wake word, or any Alexa skill screen. No skill exists.
* A Bedrock console, a model id, or a response labelled `synthesis_mode: bedrock`. This take's
  server had no credentials and no SDK, and the page says so.
* A review sent to GitHub. The server records the request and sends nothing.
* A command executing after approval.
* Any figure typed into an overlay. The overlays are the title and outro cards, the commit tag,
  the labels naming the product's sound and the captions; every number on a page frame is one
  the page printed during the take.
* A deployed URL. The public endpoint runs an older commit.
