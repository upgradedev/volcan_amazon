# Volcan: shot list

**Status: recorded once, on 2026-09-27 (local time), from a local run of commit `de30b11`.**
The render is 168.0 seconds and lives outside the repository, pending upload by the owner. This file is the
journey `video/capture-local.py` drives, beat by beat, and it matches what that take shows.
[`README.md`](README.md) in this folder says how the render was produced.

The beat ids match [`narration.json`](narration.json) and [`cue_sheet.json`](cue_sheet.json)
one for one. Beat windows are measured, not authored: each is the ElevenLabs audio length from
ffprobe plus a 0.65 second tail, and beat 2 adds a measured window for the product's own sound.
Times below are from the start of the video, after the 3.5 second title card.

---

## Before the camera rolls

| Step | Command or action | What must be true |
|---|---|---|
| 1 | `python -m pytest tests/ -q` | `572 passed` on 2026-09-26 and again on 2026-09-27 after the pipeline commits. |
| 2 | `python -m src.interfaces.mcp_server --port 8801`, started fresh, with no AWS credentials and no GitHub token in its environment | `GET /health` reports `unavailable_no_sdk_and_no_credentials` and `dry_run_no_token`. A fresh process means the audit trail on camera holds only this take's record. |
| 3 | `python video/capture-local.py` | The page at `http://127.0.0.1:8801/` in headless Chromium at 1280x720 reads **Online** and has drawn the silent preview before the timeline starts. |

---

## Title card, 0 to 3.5 seconds

`Volcan. Recorded from a local run of commit de30b11. Public deployment pending.` A corner tag
repeats `Local run of commit de30b11. Not the public deployment.` on every page frame.

## Beat 1, `beat_01_hook`, 3.5 to 22.4 seconds

* **On screen:** the page at first paint with the `Inverted admin check` patch, the label
  **Simulated Alexa+ experience, not an Alexa skill** and **GitHub write: dry-run.** On the third
  sentence, <kbd>Alt</kbd>+<kbd>2</kbd> opens the patch box and shows the raw unified diff with
  its hunk header and its plus and minus lines.
* **Not on screen:** a screen reader. Headless capture has none, so the narration states the
  problem instead of pretending to play one.

## Beat 2, `beat_02_one_button`, 22.4 to 63.3 seconds

* **On screen, while the narrator speaks:** the silent preview the page drew from the server's
  answer: the grey waveform, the **Falling** contour, the finding sentence, the Braille cells
  and **Server's first sentence, not played yet.** <kbd>Alt</kbd>+<kbd>1</kbd> puts the focus
  ring on **Hear this code review**.
* **After the narrator says "Listen":** <kbd>Enter</kbd>. The narrator is silent for the
  product window. The page plays the earcon and the playhead crosses the waveform, then the
  browser speaks the server's sentence, finding first, and the meters appear with
  `local heuristic`, the measured round trip and `1 file +1 -1`.
* **Sound:** the earcon is the WAV the server returned for this press, mixed in where the
  page's playback clock started it. The sentence is the exact text the page passed to
  `speechSynthesis`, rendered with the Windows system voice of the same name, and labelled on
  screen as the browser's system voice.
* **Window:** 20.0 seconds, from a rehearsal that measured 17.9 seconds from the press to the
  speech end event. The take fails if speech has not ended inside it; in the final take it
  ended 1.9 seconds early.

## Beat 3, `beat_03_what_you_heard`, 63.3 to 86.1 seconds

* **On screen:** the earcon caption `Security finding cue, falling pitch contour measured from
  its samples, 0.60 seconds of 16-bit PCM at 22050 Hz (SECURITY_FINDING)`, the spoken sentence,
  the red security finding box, then the information button beside **Synthesis engine** opens
  the server's reason: `no AWS credentials were resolved by the boto3 credential chain`.

## Beat 4, `beat_04_mcp_handshake`, 86.1 to 110.2 seconds

* **On screen:** Evidence, tab **Server and MCP**. **Run a real MCP handshake**, then the four
  facts: `2025-11-25`, `volcan-accessible-forge 0.1.0`, a session id from the `Mcp-Session-Id`
  header and `12` tools. The first tool, `braille_diff_digest`, expands to its published
  `inputSchema`.
* **Not on screen:** the terminal run of `python scripts/mcp_conformance.py`. It printed
  `22/22 checks passed` against the same server before the take, and the narration cites it
  in beat 6 without filming it.

## Beat 5, `beat_05_governance`, 110.2 to 139.4 seconds

* **On screen:** tab **Governed actions**. **Stage an action** shows `LEASE ACTIVE` counting
  down from the server's `expires_at_epoch`, and `Planner verdict: allowed true, executed
  false`. **Approve with the grant** shows `GRANT ACCEPTED`, the outcome `released to you,
  nothing run`, the line `Dry run only, nothing was executed. The approved plan is: git diff
  HEAD.` and one audit row.
* **Not on screen:** the terminal run of
  `python -m pytest tests/unit/test_no_execution_in_source_tree.py -q`. The narration states
  what that test does; it is part of the 572.

## Beat 6, `beat_06_verification`, 139.4 to 164.5 seconds

* **On screen:** tab **Server and MCP**: **SERVER REACHED** with the model path
  `unavailable_no_sdk_and_no_credentials`, and the path strip whose Alexa+ box reads
  `not built: no skill, no connection, no device test`. On the last sentence the page returns
  to its heading and the **Simulated Alexa+ experience** label.
* **Not on screen:** `python -m pytest tests/ -q` and `python ci/readiness.py`. The figures in
  the narration, 572 tests and 22 of 22 conformance checks, were printed by those commands on
  2026-09-26 against this commit, the conformance run against an earlier server process of the
  same commit.

## Outro card, 164.5 to 168.0 seconds

`Recorded from a local run of commit de30b11. Public deployment pending. Narration: synthetic
ElevenLabs voice. Product speech: the browser's system voice.`

---

## What must not appear in the recording

* An Echo device, an Alexa wake word, or any Alexa skill screen. No skill exists.
* A Bedrock console, a model id, or a response labelled `synthesis_mode: bedrock`. This take's
  server had no credentials and no SDK, and the page says so.
* A command executing after approval. The planner returns a plan and the audit row says so.
* Any figure typed into an overlay. The overlays are the title and outro cards, the commit tag
  and the two labels naming the product's sound; every number on a page frame is one the page
  printed during the take.
* A deployed URL. The public endpoint runs an older commit.
