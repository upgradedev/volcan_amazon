# Volcan: how the demo video is made

**Next take: planned, not recorded.** [`SHOT_LIST.md`](SHOT_LIST.md) and `narration.json` in
this folder now hold the plan for a re-take on the live build, with Amazon Bedrock answering.
Section 1 gives the commands for that take and for a free rehearsal. Section 4 says what the
pipeline does for the take, what the rehearsal of 2026-10-06 found and what is still open.
Sections 2 and 3 describe the render that exists. Its script and its capture are in history:
`git show fc10e7d:video/narration.json` and
`git show fc10e7d:video/capture-local.py`. The `cue_sheet.json`, `subtitles.srt` and
`subtitles.vtt` in this folder are generated from the plan by
`scripts/synthesize_video_assets.py`, not from a render.

**Status: rendered locally, not published.** The current render is `volcan-demo.mp4`, 163.68
seconds, 1920x1080 at 25 fps, recorded on 2026-09-29 (local time) from a local run of commit
`09d48620afde0cbb7d14ed0913efe882bea21a3d`. It lives outside the repository, at
`reviews/videos_muse_20260929/volcan_amazon/output/volcan-demo.mp4` in the owner's workspace, next to
`video-receipt.json` and the sync gate's output in `sync-gate.txt`, and waits for the owner to
upload it. There is no public link yet. The earlier renders stay where they were and are
superseded: `reviews/videos_20260928/` (164.52 s, from `7a3de49`) stated 646 tests in beat 6,
and the earlier `287c9db` rehearsal this folder held was overwritten by this render once the narration was corrected.
Readiness gates E2 and E4 look for footage inside `video/`, so they stay red.

| | |
|---|---|
| SHA-256 of the mp4 | `55fdc2a5c6d1919ec2c63eb42d66b90bafa251f592d2f3d512ebee748fbd0b1c` |
| Duration, from ffprobe | 163.680 s: 3.0 s title card, 156.164 s of beats, 4.5 s outro card |
| Sync gate | `scripts/verify_video_sync.py`: all gates passed, 32 caption windows |
| First press | 15.7 s into the video; the product's own earcon starts at 16.5 s |
| Product voice in the mix | Three turns: the press, Findings on the pull request, and Confirm. 9 caption cues marked `Volcan (product voice):` and 2 earcon cues |
| Narration voice | ElevenLabs, voice id `21m00Tcm4TlvDq8ikWAM`, model `eleven_multilingual_v2` |
| Characters sent to ElevenLabs for this render | 303 for beat 6 only, re-synthesized with the corrected count. Beats 1 to 5 reuse the 2026-09-28 audio unchanged (1,070 characters). 1,373 characters are in the beats that shipped |
| Product code on camera | `src/` and `docs/` identical to `09d4862`, which is also the commit `/health` reports on camera |

---

## 1. The pipeline

The scripts are the submission kit's video pipeline, adapted to this repository and committed
so any one beat can be re-rendered later.

| Step | Script | Writes, under `VOLCAN_VIDEO_ROOT` (never into git) |
|---|---|---|
| Narration | `video/generate-narration.py` | `narration/NN-beat.mp3`, `timing.json`, `captions.en.srt`, `tts-ledger.jsonl` |
| Capture | `video/capture-local.py` | `capture/production.webm`, `earcon-press.wav`, `browser-speech.wav`, `capture-receipt.json` |
| Compose | `video/build-video.py` | `output/volcan-demo.mp4`, `video-receipt.json`, `video_manifest.json`, `caption_windows.json`, `captions.en.srt` |
| Gate | `scripts/verify_video_sync.py` | pass or fail, from the mp4 itself |

For the re-take on the live build:

```bash
export VOLCAN_VIDEO_ROOT=/a/folder/outside/the/repo
export VOLCAN_APP_URL=https://qylv1gxor9.execute-api.eu-west-1.amazonaws.com/
export VOLCAN_RELEASE_SHA=<the 40 character source_revision that GET $VOLCAN_APP_URL/health reports>
export VOLCAN_PR_URL=https://github.com/<owner>/<repo>/pull/<number>   # chosen in rehearsal
export VOLCAN_COLD_OPEN=findings      # or files, when the rehearsal found no finding
export FFMPEG=/path/to/ffmpeg FFPROBE=/path/to/ffprobe
# ELEVENLABS_API_KEY goes into the generator's environment only; never printed or written.

python video/generate-narration.py --write-timestamps
python video/capture-local.py                          # checks only; presses nothing billed
python video/capture-local.py --allow-billed-presses   # the take: two Amazon Bedrock calls
python video/build-video.py
cd "$VOLCAN_VIDEO_ROOT/output" && VIDEO_MANIFEST=video_manifest.json \
  CAPTION_WINDOWS=caption_windows.json python /path/to/repo/scripts/verify_video_sync.py volcan-demo.mp4
python scripts/synthesize_video_assets.py         # cue sheet and subtitles from the measured beats
```

The 2026-09-29 take ran the scripts at `fc10e7d` against a fresh local server with no cloud
credentials; `git show fc10e7d:video/README.md` has those commands.

### Billed presses: `--allow-billed-presses`

Two actions in the re-take call Amazon Bedrock on the live build: opening the chosen pull
request, which the capture does before the cold open and off camera, and **Hear this code
review** at the start of beat 2. Each is one billed model call.

* **Without the flag (the default),** `video/capture-local.py` reads `/health` and the measured
  beats, prints the two calls the take would bill, and exits before it opens a browser. It
  presses nothing and leaves an earlier `capture/` folder in place.
* **With the flag,** a request guard in the browser lets exactly one pull request open and one
  default-engine digest through, each armed just before the script makes that press. Any
  other request that would reach a model is aborted, and the take fails. That includes a
  digest without `"engine"` in its body, a second open, and a `tools/call` on `POST /mcp`.
* The receipt lists the calls that went through, under `billedCalls`.
* **Replay the documented Alexa+ requests** is never pressed. On the live build it is three
  calls.

Pass the flag only after the owner has authorised the calls in writing, as step 1 of
[`SHOT_LIST.md`](SHOT_LIST.md) says. Each run with the flag is one take, and two calls
against the bound of 12.

### Free rehearsal: `--rehearsal`

A rehearsal runs the whole planned journey for nothing, before any billed press. Start a
local server with no cloud credentials and no GitHub token, then capture and compose with
`--rehearsal`:

```bash
export VOLCAN_VIDEO_ROOT=/a/folder/outside/the/repo
export VOLCAN_RELEASE_SHA=$(git rev-parse HEAD)
export VOLCAN_APP_URL=http://127.0.0.1:8813/
export VOLCAN_PR_URL=https://github.com/<owner>/<repo>/pull/<number>
export FFMPEG=/path/to/ffmpeg FFPROBE=/path/to/ffprobe
env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN -u AWS_PROFILE \
    -u GITHUB_TOKEN -u GH_TOKEN -u VOLCAN_GITHUB_WRITE \
  AWS_SHARED_CREDENTIALS_FILE=/nonexistent AWS_CONFIG_FILE=/nonexistent AWS_EC2_METADATA_DISABLED=true \
  SOURCE_REVISION=$VOLCAN_RELEASE_SHA python -m src.interfaces.mcp_server --port 8813 &
python video/capture-local.py --rehearsal     # writes rehearsal/; exits 1 when it finds failures
python video/build-video.py --rehearsal       # writes output-rehearsal/
```

* **It cannot bill.** The capture refuses a `VOLCAN_APP_URL` that is not `127.0.0.1`,
  `localhost` or `::1`, a `/health` that reports `bedrock_model_path` `ready_to_attempt`, a
  `github_review_path` other than `dry_run_no_token`, and `--allow-billed-presses` beside
  `--rehearsal`. A press answered by Amazon Bedrock stops it.
* **The same journey.** The request guard is armed as for the take, so an unplanned model
  request still fails. The receipt lists the planned ones under
  `rehearsal.modelPathRequests`; `billedCalls` is empty.
* **Not shippable.** It writes `rehearsal/`, never `capture/`. Its receipt says
  `"mode": "rehearsal"` and `"shippable": false`. `video/build-video.py` refuses that receipt
  without `--rehearsal`, and with it writes `output-rehearsal/`, never `output/`.
* **Not representative.** Each check that needs Amazon Bedrock is listed under
  `rehearsal.notRepresentative` with what the local engine did: the model path and durable
  state in `/health`, the press's engine and fallback reason, the meter, the coverage line,
  the model's full answer, and an answer that starts while the narrator speaks.
* **Every failure, in one run.** Checks that would fail the take after the journey has run
  are collected under `rehearsal.failures`, so one run reports all of them: speech overruns
  and interruptions, the cold-open timing, page errors, blank stretches and unplanned model
  requests. Focus and dialogue checks during the journey still stop it.
* **Timing.** Without a measured `narration/timing.json`, the capture writes a silent timing
  stub to `rehearsal/narration-stub/`, built from the ESTIMATE windows in `narration.json`.
  Nothing is sent to ElevenLabs. The build leaves the stub's silent narration uncaptioned, so
  on that video the gate's `web-beat-audible` check fails by construction.
* **Only the stub composes.** With a measured `narration/timing.json`, `build-video.py
  --rehearsal` refuses on a caption overlap, because the local engine answers the press while
  beat 2's narration is still captioned. The capture's receipt is still complete.

The gate calls `ffmpeg` and `ffprobe` by name, so put their folder on `PATH` for it.
`python tests/video/verify_gate_selftest.py` proves the gate still fails on a mis-ordered
video, a caption that runs into the outro and an audio track longer than the picture. It is
not collected by pytest. The gate is unchanged; section 4 says which checks the re-take
passes and which it does not yet.

### Re-rendering one beat

Edit that beat's `narration_text` and `speech_text` in `narration.json` and rerun the
generator. It prints `reused` for every unchanged beat and synthesizes only the edited one,
because ElevenLabs does not return identical audio twice and a re-roll would move every
offset after it. To reuse an earlier render's audio, copy its `NN-beat.mp3` and
`NN-beat.cache.json` files into the new media root first, under the beat's new number and id
if they moved: the cache is keyed on the speech text and the voice, not the file name. Do not
copy the old `tts-ledger.jsonl`; the receipt sums it. Then capture and compose again: the
capture is paced by the measured windows, so a changed beat length changes the take.

### What the capture refuses

Before it opens a browser, the capture refuses:

* a `narration.json` whose beats are not the six beats of the re-take, in order;
* a `cards.title_slot` that does not start with `card_then_cold_open`, a title card outside
  1.5 to 3 s, or a cold open outside 3 to 20 s;
* a `/health` that reports a different commit than `VOLCAN_RELEASE_SHA`, a
  `bedrock_model_path` other than `ready_to_attempt`, a `durable_state` other than
  `configured_reachable` (beat 2 names DynamoDB), or a `github_review_path` other than
  `dry_run_no_token` (beat 5 says the build has no GitHub token);
* a run without `--allow-billed-presses`, unless it is a rehearsal (see above).

During or after the take, it fails, and the take has to be recorded again:

* **Errors and focus.** The page logs an error, or a key press would go to an element other
  than the one the journey means. It checks the pull request box before typing and Enter,
  Hear this code review before Enter, and the comment box before typing.
* **The model call.** A request would bill a model call the take did not plan. The press is
  not answered by Amazon Bedrock or carries a fallback reason. The engine meter does not read
  Amazon Bedrock, or the page prints no coverage line. The answer's first sound comes before
  beat 2's narration ends.
* **The cold open.** Its first sound comes later than 2.0 s after the title card ends, or its
  first word later than 5.0 s into the video, which is 3.0 s into the cold open after the
  2.0 s card. Findings answers that no security rule matched (`No security rule matched this
  change.`). The cold-open command is not an outlined next step.
* **Speech.** A voiced turn's speech has not ended before the next segment starts, or was
  interrupted. The page speaks a sentence other than the one the server returned.
* **The review.** The dialogue does not open the chosen pull request, refuses a turn or does
  not answer it. Confirm is not an outlined next step. The review pane does not show a
  recorded, unsent review.
* **The picture.** It stays one flat colour for 0.75 s or longer. This check reads the
  recording's pixels: on a loaded machine a long smooth scroll can outrun rasterisation and
  record blank tiles.

The build refuses:

* a recording that drifted more than 5% from the page clock;
* a capture receipt whose cold open does not match `cold_open.seconds`;
* a `cards.title_slot` that puts the cold-open footage in the title slot, because the gate
  reads the middle of the title segment as a card;
* a closing card of more than 5 rows (`OUTRO_ROWS_MEASURED_AS_CARD`);
* a rehearsal receipt without `--rehearsal`, and a take's receipt with it.

---

## 2. What is real in the picture and the sound

* **The picture** is a headless Chromium recording of the page at 1280x720, scaled to 1632x918
  at the top of the 1080p frame. The script presses keys and buttons, types into the page's own
  inputs and scrolls; it never writes into the page's DOM and never answers a request. Every
  panel filled from the running server during the take.
* **The band under the page** holds everything the build adds: the captions, a grey tag naming
  the local commit, and an amber label while the page's own voice is not in the mix. Nothing is
  drawn over the page, so the sentence the page shows while it speaks stays readable.
* **The pull request** in beats 3 and 4 is octocat/Hello-World #1, read from GitHub by the
  server without a token. The review comment says it is a dry-run demo and claims nothing about
  the pull request. The server ran without `VOLCAN_GITHUB_WRITE` and without a token, recorded
  the request and sent nothing.
* **The narration** is a synthetic ElevenLabs voice. It never speaks for the product.
* **The earcons** are the WAVs the server returned for the press, for Findings and for Confirm,
  byte for byte, each mixed in where the page's own playback clock started it. They share the
  gain measured on the longest, because a cue under 400 ms cannot be measured on its own.
* **The product voice** is the exact text the page passed to `speechSynthesis` for those three
  turns, readback and answer as separate sentences. Headless capture records no audio, so each
  sentence was rendered again with Windows System.Speech, voice `Microsoft David Desktop`, and
  placed at that sentence's own speech start event. It is captioned `Volcan (product voice):`
  from the same text, and the outro names the voice.
* **The turns the narrator talks over** are opening the pull request and Request changes. The
  page played a cue and spoke for each until the next command interrupted it; the capture logged
  when, and the band label `Not in this recording: the page's own cue and voice for this turn`
  covers exactly those stretches (62.6 to 70.5 s and 80.9 to 92.6 s of the timeline, 3.0 s later
  in the video).
* **Two marker pages**, before and after the journey, turn from white to black at a logged
  time. In this take the recording ran 0.15% longer than the page clock, so the build retimes
  the picture by that measured factor and every logged action lands on its timeline second.

## 3. Known gaps in this render

* No terminal is filmed. Beat 6 states 725 tests and 23 of 23 conformance checks. On
  2026-09-29 `python -m pytest tests/ -q` printed `725 passed` on `09d4862`, and
  `python scripts/mcp_conformance.py http://127.0.0.1:8743/mcp` printed `23/23 checks passed`
  against a server of `09d4862`, which was then restarted fresh for the take on port 8801.
* No screen reader is filmed. Headless capture has none; the narration states the problem.
* The system voice renders each sentence a little faster than the browser spoke it: 15.20 s
  against 16.90 s for the press, 15.79 s against 18.21 s for the Confirm answer. Each sentence
  starts where the browser's did, so it ends early, and each product window closes on 2 to 4 s
  of the page without sound. The windows are sized from the browser's own end events, with 0.55 to
  1.5 s of margin over the slowest measured run, because the capture fails a take whose speech
  overruns.
* The words on the page light from the browser's own boundary events, so late in a sentence the
  lit word may run ahead of the voice you hear.
* The patch box renders `==` and `!=` as JetBrains Mono ligatures. This is the page's font
  setting, not something the video adds.
* After the review turns, the stage at the top of the page shows the last cue the page played,
  the dry-run cue with a level contour, while its sentence is still the first patch's. The
  closing shot shows that state as the page left it.
* The schema of the first MCP tool is wider than its box; the page scrolls it sideways, and the
  frame shows the first part of each line.
* The public endpoint runs an older commit, so the video shows a local run. The title card and
  the outro say so.
* Upload `output/captions.en.srt` from the media root as the caption track: it is sentence
  level, includes the product voice and the earcon descriptions, and carries the title card
  offset. `video/subtitles.srt` in this folder is one cue per beat.

## 4. Rendering the re-take

The plan in [`SHOT_LIST.md`](SHOT_LIST.md) is written for the live build. The pipeline now
follows it, with these limits.

* **The video opens on a title card, then the cold open.**
  * `cards.title_slot` starts with `card_then_cold_open`.
  * `cards.title_seconds` is the 2.0 s title card.
  * `cold_open.seconds` is the 12.0 s cold open (ESTIMATE).
  * Beat 1 starts at 14.0 s, and the closing card ends at 158.5 s (ESTIMATE).
* **`video/capture-local.py` drives the re-take journey.**
  * It accepts the six beat ids in `narration.json` and refuses any other list.
  * It opens `VOLCAN_PR_URL` off camera and waits for that turn's speech to end.
  * It records the cold open on timeline seconds from minus `cold_open.seconds` to 0.
  * It presses Hear this code review at the first frame of beat 2.
  * It holds on the meter, the coverage line and the model's full answer in beat 3.
  * It voices Request changes in beat 4 and Confirm in beat 5.
  * In beat 6 it runs the MCP handshake, and it does not press the replay.

  The capture still records headless, without audio. It re-renders the page's sentences in
  the Windows system voice, and the build then names that voice on the closing card. A
  headed capture with the browser's own audio, which the shot list prefers, is not built.
* **`video/build-video.py` plays the title card, then the cold open.**
  * The title card is drawn from `cards.title_lines`.
  * The cold open is the page's footage from its first frame, with `cold_open.band_lines` in
    the band under the page.
  * `{build}` in those lines becomes `Live build` or `Local run`, from the capture's `appUrl`,
    so a local run is never labelled the live build. The band tag after the cold open names
    the build the same way.
  * Card lines too long for the frame wrap.
  * Without `title_slot`, the 2026-09-29 take's title card is followed by beat 1, as before.
  * A title slot holding the footage, and a closing card over 5 rows, are refused.
* **The sync gate's card probes.**
  * `scripts/verify_video_sync.py` and its selftest are unchanged.
  * The gate samples the middle of the title segment and of the outro segment, and expects a
    card in both. It calls a frame a card when its `FIND_EDGES` mean is at most
    `EDGE_CARD_CONTENT_THRESHOLD`, 4.5.
  * The earlier plan failed both probes. Its cold-open footage in the title slot read as
    content, and its 9-row closing card measured 7.59.
  * The plan now draws a real title card and a closing card of 5 rows, the size of the
    2026-09-29 outro (`OUTRO_ROWS_MEASURED_AS_CARD`). The system-voice line stays one row,
    because the build writes it as `Product voice: the page's sentences in <voice>.`

    | Card | Rows | Edge mean |
    |---|---|---|
    | Plan outro, with the system-voice line the headless capture adds | 5 | 3.98 |
    | Plan outro, without that line | 5 | 3.63 |
    | Plan title card | 3 | 1.98 |
    | Earlier plan outro, with the system-voice line (`git show aa3364a:video/narration.json`) | 9 | 7.59 |
    | Outro of the 2026-09-29 take (`git show fc10e7d:video/narration.json`) | 5 | 3.70 |

  The figures come from ffmpeg 8.1.1 and Pillow 12.2.0, with the build's encoder settings
  (libx264, preset medium, crf 20, 25 fps) and the gate's own `frame_edge_mean`. Run from the
  repository root, with `VOLCAN_VIDEO_ROOT` set to an empty folder that has `output/overlays/`:

  ```bash
  python - <<'EOF'
  import importlib.util, json, os, subprocess, sys
  sys.path.insert(0, "scripts")
  from verify_video_sync import frame_edge_mean
  spec = importlib.util.spec_from_file_location("bv", "video/build-video.py")
  bv = importlib.util.module_from_spec(spec); spec.loader.exec_module(bv)
  cards = json.load(open("video/narration.json", encoding="utf-8"))["cards"]
  voice = [{"kind": "speech", "renderedWith": "Windows System.Speech, voice Microsoft David Desktop, rate 0"}]
  live = "https://qylv1gxor9.execute-api.eu-west-1.amazonaws.com/"
  for name, lines in (("outro", bv.outro_lines_for(cards["outro_lines"], "9b2bcb9", voice)),
                      ("outro-no-voice", bv.outro_lines_for(cards["outro_lines"], "9b2bcb9", [])),
                      ("title", bv.filled(cards["title_lines"], "9b2bcb9", live))):
      out = os.path.join(os.environ["VOLCAN_VIDEO_ROOT"], name + ".mp4")
      subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                      bv.card(lines, 1.0, name) + ",format=yuv420p", "-t", "1", "-c:v", "libx264",
                      "-preset", "medium", "-crf", "20", "-r", "25", out], check=True)
      print(name, len(bv.card_rows(lines)), "rows", round(frame_edge_mean(out, 0.5), 2))
  EOF
  ```

  On 2026-10-06 it printed `outro 5 rows 3.98`, `outro-no-voice 5 rows 3.63` and
  `title 3 rows 1.98`. Re-measure after any change to the card lines.
* **The 5 s rule, measured.** The plan's timeline is the 2.0 s title card, the cold open's
  first frame at 2.0 s and the cold-open command 0.3 s later. In the free rehearsal below,
  the cold open's first sound came 1.091 s into the cold open (3.091 s of video) and its
  first word 1.744 s in, so the first spoken product word landed at 3.744 s of the video,
  inside 5.0 s. The capture fails a take whose first word lands later than 5.0 s.
* **The gate still fails the re-take on `content-seam<=1s`.** It is open.
  * The check compares the end of the last sound before beat 6 (`a_main`) with beat 6's
    start, and fails when the gap is over 1 s.
  * Beat 5 ends on the page's Confirm turn, after the narrator.
  * Before this change, `a_main` counted only narration. That gap was 0.65 s plus beat 5's
    23.5 s product window: 24.15 s on the plan. This README then named only `order-pixels`
    as failing; `content-seam` failed on the plan as well.
  * `a_main` now also counts the page's own sentences in the mix, because they are speech.
    In the rehearsal the gap was still 3.196 s:
    * the system voice rendered the Confirm answer in 16.212 s, where the browser took
      18.195 s;
    * the window kept 1.213 s after the browser's speech ended.
  * What closes it is the owner's choice: a headed capture with the browser's own audio,
    which the shot list prefers, or a beat 5 window sized to what is heard.
* **The optional consented clip has no place in the pipeline.** It goes in during the edit,
  and every later timestamp moves by its length.

### The free rehearsal of 2026-10-06

One rehearsal, with no billed call and no ElevenLabs call:

* **Setup.**
  * `video/capture-local.py --rehearsal` at `4d021d9`, against a local server on port 8813
    started with the commands in section 1.
  * `/health` reported `bedrock_model_path` `unavailable_no_sdk_and_no_credentials`,
    `durable_state` `process_memory` and `github_review_path` `dry_run_no_token`.
  * It ran on the silent timing stub, then `video/build-video.py --rehearsal`, then the
    unchanged gate.
* **Where the outputs are.** The capture, the composed video, the gate's output in
  `sync-gate.txt` and six frames are outside the repository, in
  `reviews/volcan_rehearsal_20261006/` in the owner's workspace.
* **The pull request** was https://github.com/alex-pimentel/agenteresolve-services/pull/8,
  head `b255f62`, read from GitHub by the local server without a token.
  * It is a public, merged pull request that changes code in 3 files (+32, -0).
  * It adds a CORS middleware whose allowed origins default to `*`.
  * The page opened it with `4 security findings`, and Findings answered with them. One is
    a structural finding: `a cross-origin policy was widened to accept any origin`. The
    other three are keyword-set matches.
* **The recording.** 208.32 s, drifting 0.0942% from the page clock (`videoPerPageSecond`
  1.000942). No page error, and no blank stretch.
* **The gate on the composed rehearsal.** `order-pixels` passed at all four probes: title
  card 1.9, screencast 11.7, web 10.5 and closing card 4.0. `content-seam<=1s` failed at
  3.196 s, as above. `web-beat-audible` failed because the stub's narration is silent.
  Every other check passed.
* **Failures it found**, two causes behind four failure lines:
  * **The cold open's Findings turn does not fit 12.0 s.**
    * The answer reads all 4 findings, so the page was still speaking when the cold open
      ended.
    * The press in beat 2 interrupted it 27.7 s after the answer began.
    * A cold-open pull request needs a Findings answer short enough for the window, or the
      window re-measured.
  * **Request changes does not fit its 14.0 s window (ESTIMATE).**
    * The readback repeats the whole comment and took 9.5 s.
    * The page was still speaking the answer when beat 5 began, and Confirm interrupted it
      25.1 s after the click.
    * The window needs the slowest rehearsal run plus 1 s, as the plan says.
  * **With this pull request and this comment, the take does not fit the budget.**
    * The cold-open turn ran at least 32.75 s from the cold open's first frame. With the
      plan's rule, the slowest run plus 1 s, the 12.0 s window becomes at least 33.75 s:
      21.75 s more.
    * Request changes ran at least 25.08 s from the click. Its 14.0 s window becomes at least
      26.08 s: 12.08 s more.
    * The video then runs at least 158.536 + 21.75 + 12.08 = 192.4 s. That is over the gate's
      175 s publication budget, the build's own `duration < 175` check and the plan's
      `max_allowed_seconds` of 180. It is a lower bound, because both turns were cut off.
    * So the pull request and the length of `REVIEW_COMMENT` in `video/capture-local.py`
      decide whether the take can be recorded at all. Choose a pull request whose Findings
      answer fits the cold open, keep the comment short, and rehearse again.
* **Not representative of the billed take**, from the receipt's `notRepresentative`:
  * the model path and durable state in `/health`;
  * the press answered by the local engine (`heuristic-local`, `no AWS credentials were
    resolved by the boto3 credential chain`);
  * the meter reading `local heuristic`;
  * no coverage line, and no model answer to open;
  * the answer starting at 21.032 s, while the narrator speaks.
* **What fit.**
  * Confirm ended its speech 1.213 s before beat 6.
  * The local engine's spoken answer to the press took 16.76 s.

`video/generate-narration.py` checks each beat's text, each product window and its basis,
and the 90 to 174 s narration range. `--write-timestamps` offsets the beats by
`cards.title_seconds` plus `cold_open.seconds` when the title slot plays a cold open after
the card, 14.0 s in this plan.

`tests/unit/test_video_retake_pipeline.py` covers the scripts without a browser, ffmpeg or a
request. Its 58 cases (`python -m pytest tests/unit/test_video_retake_pipeline.py -q`) check:

* the plan's title card, cold open and timestamps;
* the beat ids;
* the billed-press flag and the request guard;
* the `/health` refusals, the cold-open timing gate and the clean Findings answer;
* the rehearsal flag, the loopback-only URL check, its `/health` refusals and the silent
  timing stub;
* the title slot shapes, the refused footage slot and the build label;
* the seam's sound end, the band tag and the 5-row closing card;
* the build's refusal of a rehearsal receipt without `--rehearsal`.
