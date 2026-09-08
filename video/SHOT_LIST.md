# Volcan: shot list

**Status: no footage exists.** This file is the capture plan, not a record of a recording.
Readiness gates E2 and E4 report red until a rendered video sits in `video/`, and
`video_sync_receipt.json` prints
`"narration_and_picture_sync_verified": false` for the same reason.

Every beat below is an action this repository performs today. Each one names the exact
click or the exact command, the platform it happens on, and the result that must appear on
screen. Nothing here waits on work that has not been done. The beat ids match
[`narration.json`](narration.json) and [`cue_sheet.json`](cue_sheet.json) one for one, so a
single beat can be recut without touching the rest.

Total runtime **165 seconds** against a 180 second cap, printed by
`python scripts/synthesize_video_assets.py`.

---

## Before the camera rolls

Two surfaces are recorded and nothing else: a browser at 1280x900 and a terminal. Both were
exercised on Windows 11 with Python 3.11.0 on 2026-09-06.

| Step | Command or action | What must be true before you record |
|---|---|---|
| 1 | `python -m pip install -e ".[dev,bedrock]"` | Dependencies resolve. This is off camera. |
| 2 | `python -m pytest tests/ -q` | Prints `280 passed`. If it does not, stop and fix that first. |
| 3 | `python -m src.interfaces.mcp_server` | Leave it running in terminal 1, off camera. |
| 4 | Open `http://127.0.0.1:8000/` in a fresh profile at 1280x900 | The connection strip reads **SERVER REACHED** with a real `GET /health` duration. If it reads **NO SERVER**, the recording is wrong before it starts. |
| 5 | System audio capture on, microphone off | The earcon in beat 2 is the product speaking. It must reach the recording. |
| 6 | Reset the page with a reload | Every meter must read `not run yet` on the first frame of beat 2, so a judge watches the values arrive. |

Terminal 2 is the on-camera terminal. Keep it at a font size readable at 720p.

---

## Beat 1, `beat_01_hook`. The problem, 0 to 20 seconds

* **Platform:** browser, companion page, plus the operating system screen reader.
* **Exact action:** focus the patch box with <kbd>Alt</kbd>+<kbd>2</kbd> and let the screen
  reader read the raw unified diff aloud from the top. Do not speed it up.
* **On screen:** the `Inverted admin check` preset patch in the left column, the one the page
  loads on first paint, with the screen reader cursor moving character by character through
  `@@ -12,7 +12,7 @@ def can_delete_workspace(user, workspace):` and the plus and minus
  signs.
* **Audio:** the screen reader only. No narration over the first four seconds of it.
* **Why it is safe to record:** the preset is loaded by the page itself on first paint, and
  the screen reader is the viewer's own, not a simulation of one.
* **Cut on:** the reader still spelling out syntax with no comprehension reached.

## Beat 2, `beat_02_one_button`. One button, 20 to 58 seconds

* **Platform:** browser, companion page. This is the beat the submission stands on.
* **Exact action:** press <kbd>Alt</kbd>+<kbd>1</kbd> to focus **Hear this code review**,
  show the focus ring, then press <kbd>Enter</kbd>. Use the keyboard, not the mouse. This
  product is for people who cannot use a pointer, and a mouse click here undercuts the
  argument.
* **On screen, in this order:** the progress bar appears, the earcon audio player appears
  and plays, the spoken digest fills in, the red security finding appears below the split,
  the Braille cells fill the third card, and the three meters change from `not run yet` to
  real values.
* **Expected values:** the engine meter reads whichever engine actually answered, and the
  note under it repeats the raw `synthesis_mode`. On a machine with the `bedrock` extra
  installed and AWS credentials resolving it reads `Amazon Bedrock`; without either it
  reads `local heuristic` with `synthesis_mode: heuristic-local` and the reason beside it.
  Record whichever one your machine produces and say so in the narration. Do not stage the
  other. The round trip meter reads a two or three digit millisecond figure measured in
  that browser. It read **72.6 ms** on the development machine on 2026-09-06, and it will
  differ on yours. Do not retake the shot to get a smaller number.
* **Hold on:** the earcon caption. The preset patch inverts an authorization comparison, so
  the server returns the falling security cue and the caption reads
  `Cue SECURITY_FINDING, 0.60 seconds of 16-bit PCM at 22050 Hz. Written description:
  Security-sensitive change in this patch.` It is the proof that a Deaf viewer gets the
  same information a hearing one does, and that the cue is chosen from the verdict: preset
  4, the labelled clean control, returns `Cue DIFF_READY, 0.44 seconds` instead. Both
  captions were produced by the running server on 2026-09-08.
* **Cut on:** the security finding card, which reads
  `In src/auth/permissions.py, an authorization comparison was inverted: user.role == 'admin'
  became user.role != 'admin'.` That sentence is the whole argument of the project: the words
  on both sides of the change are identical, so nothing that matches keywords can produce it.

## Beat 3, `beat_03_mcp_handshake`. A real MCP handshake, 58 to 92 seconds

* **Platform:** browser first, then terminal 2.
* **Exact action, browser:** scroll to **Model Context Protocol, handshaken in your
  browser** and press **Run a real MCP handshake**. Expand the first tool in the catalog.
* **On screen:** the four facts fill in with `2025-11-25`, `volcan-accessible-forge 0.1.0`,
  a truncated session id taken from the `Mcp-Session-Id` response header, and `11` tools.
  The expanded entry shows the published `inputSchema` JSON.
* **Exact action, terminal:** cut to terminal 2 and run
  `python scripts/mcp_conformance.py http://127.0.0.1:8000/mcp`.
* **On screen:** the per-check pass lines and the final count. Hold long enough for one
  check line to be readable, not the whole list.
* **Cut on:** the conformance summary line.

## Beat 4, `beat_04_governance`. Staged, leased, never executed, 92 to 128 seconds

* **Platform:** browser, then terminal 2.
* **Exact action, browser:** press **Stage an action**, wait for the lease tag to show a
  countdown, then press **Approve with the grant**.
* **On screen after staging:** the lease tag reads a live countdown computed from the
  `expires_at_epoch` the server returned.
* **On screen after approval:** the lease tag reads `GRANT ACCEPTED`, the verdict rows read
  `accepted` and server status `PLANNED`, and the sentence reads
  `Dry run only, nothing was executed. The approved plan is: git diff HEAD.` The audit panel
  fills with a row reading `plan released, not run   [server state EXECUTED]` followed by
  the action id, the command and a payload hash.
* **Exact action, terminal:** run
  `python -m pytest tests/unit/test_no_execution_in_source_tree.py -q`.
* **On screen:** the passing line. That test walks every module's syntax tree, so it is the
  claim rather than a comment about the claim.
* **Cut on:** the passing test line.

## Beat 5, `beat_05_verification`. Verification and the honest boundary, 128 to 165 seconds

* **Platform:** terminal 2, then back to the browser.
* **Exact action, terminal:** run `python -m pytest tests/ -q`, then `python ci/readiness.py`.
* **On screen:** `280 passed`, then the readiness output **scrolled to a red gate**. Do not
  crop the failures out. The gates that were red on 2026-09-08 are the absent video and its
  sync check, the absent browser-driver journey, the deployed endpoint running an older
  commit, and three actions only the owner can perform.
* **Exact action, browser:** scroll to the connection strip at the top of the page.
* **On screen:** the connection strip's model path sentence. The page prints whatever the
  server resolved into the single `bedrock_model_path.resolved_capability` field on
  `/health`, and you record the one your machine produces. On the development machine on
  2026-09-08 credentials resolved from the local boto3 chain while the Anthropic SDK was
  absent, so it reads `Model path: unavailable_sdk_not_installed. Credentials resolved, but
  anthropic is not importable, so no call can leave this process. Install it with: pip
  install 'anthropic[bedrock]'.` Do not read that as bad news on camera: it is the beat
  where the project says what it has not done. Then the page heading.
* **Cut on:** the heading `Hear your code review instead of scrubbing a diff`.

---

## What must not appear in the recording

Each line below is something that does not exist in this repository, so filming it would
mean staging it.

* An Echo device, an Alexa wake word, or any Alexa skill screen. No skill is submitted.
* A Bedrock console, a model id, or a response labelled `synthesis_mode: bedrock` that your
  machine did not actually produce. No model has answered from this repository: boto3
  resolves credentials here, but the Anthropic SDK is not installed, so the call has never
  left the process. If you install the `bedrock` extra and a model really does answer on
  your machine, record that and say in the narration that it is the first time. Do not
  stage the label either way.
* A command actually executing after approval. The planner returns a plan and the audit row
  says so.
* Any figure typed into an overlay in post-production. Every number on screen is one the
  page or a script printed while recording.
* A deployed URL. The deployed endpoint runs an older commit and answers 404 for `/mcp`,
  which `deploy_teardown_receipt.json` records.

## After the recording

1. Put the rendered file in `video/` as `.mp4` or `.mov`.
2. Rerun `python scripts/synthesize_video_assets.py`. The receipt flips
   `narration_and_picture_sync_verified` to true only because a file is now there to compare
   against.
3. Rerun `python ci/readiness.py` and check that E2 and E4 changed for that reason and not
   for any other.
4. Publish the link and record it in the submission. Gate E4 stays red until the link is
   public.
