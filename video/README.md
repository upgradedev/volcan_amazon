# Volcan: how the demo video is made

**Next take: planned, not recorded.** [`SHOT_LIST.md`](SHOT_LIST.md) and `narration.json` in
this folder now hold the plan for a re-take on the live build, with Amazon Bedrock answering.
Section 1 gives the commands for that take, and section 4 says what the pipeline does for it
and what is still open. Sections 2 and 3 describe the render that exists. Its script and its
capture are in history: `git show fc10e7d:video/narration.json` and
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

The gate calls `ffmpeg` and `ffprobe` by name, so put their folder on `PATH` for it.
`python tests/video/verify_gate_selftest.py` proves the gate still fails on a mis-ordered
video, a caption that runs into the outro and an audio track longer than the picture. It is
not collected by pytest. The gate is unchanged, and on the re-take it fails one check by
design; see section 4.

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
* a title slot that does not name the cold open;
* a `/health` that reports a different commit than `VOLCAN_RELEASE_SHA`, a
  `bedrock_model_path` other than `ready_to_attempt`, a `durable_state` other than
  `configured_reachable` (beat 2 names DynamoDB), or a `github_review_path` other than
  `dry_run_no_token` (beat 5 says the build has no GitHub token);
* a run without `--allow-billed-presses`.

During or after the take, it fails, and the take has to be recorded again:

* **Errors and focus.** The page logs an error, or a key press would go to an element other
  than the one the journey means. It checks the pull request box before typing and Enter,
  Hear this code review before Enter, and the comment box before typing.
* **The model call.** A request would bill a model call the take did not plan. The press is
  not answered by Amazon Bedrock or carries a fallback reason. The engine meter does not read
  Amazon Bedrock, or the page prints no coverage line. The answer's first sound comes before
  beat 2's narration ends.
* **The cold open.** Its first sound comes later than 2.0 s, or its first word later than
  5.0 s. Findings answers `No security finding in this change.` The cold-open command is not
  an outlined next step.
* **Speech.** A voiced turn's speech has not ended before the next segment starts, or was
  interrupted. The page speaks a sentence other than the one the server returned.
* **The review.** The dialogue does not open the chosen pull request, refuses a turn or does
  not answer it. Confirm is not an outlined next step. The review pane does not show a
  recorded, unsent review.
* **The picture.** It stays one flat colour for 0.75 s or longer. This check reads the
  recording's pixels: on a loaded machine a long smooth scroll can outrun rasterisation and
  record blank tiles.

The build refuses a recording that drifted more than 5% from the page clock, and a capture
receipt whose cold open does not match `cards.title_seconds`.

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

* **`video/capture-local.py` drives the re-take journey.**
  * It accepts the six beat ids in `narration.json` and refuses any other list.
  * It opens `VOLCAN_PR_URL` off camera and waits for that turn's speech to end.
  * It records the cold open on timeline seconds from minus `cards.title_seconds` to 0.
  * It presses Hear this code review at the first frame of beat 2.
  * It holds on the meter, the coverage line and the model's full answer in beat 3.
  * It voices Request changes in beat 4 and Confirm in beat 5.
  * In beat 6 it runs the MCP handshake, and it does not press the replay.

  The capture still records headless, without audio. It re-renders the page's sentences in
  the Windows system voice, and the build then names that voice on the closing card. A
  headed capture with the browser's own audio, which the shot list prefers, is not built.
* **`video/build-video.py` puts the cold open in the title slot.**
  * It does this when `cards.title_slot` starts with `cold_open`.
  * The page's footage from the cold open's first frame fills the title slot, and the title
    lines sit in the band under it.
  * The band tag names the build from the capture's `appUrl`: a local run, or the live build
    and its commit.
  * Card lines too long for the frame wrap.
  * Without `title_slot`, the title card of the 2026-09-29 take is drawn as before.
* **The sync gate fails the re-take on one check, by design.**
  * `scripts/verify_video_sync.py` and its selftest are unchanged.
  * The gate samples the middle of the title segment and expects a card.
  * With cold-open footage there, `order-pixels` fails.
  * The manifest says `"title_slot": "cold_open_footage"`, and the build prints a note.
  * Before this take can pass the gate, the owner decides one of two things:
    * Teach the gate the cold open, and add a cold-open case to the selftest so it still
      proves the gate fails on bad files.
    * Keep a short title card, which the shot list does not want.
* **The optional consented clip has no place in the pipeline.** It goes in during the edit,
  and every later timestamp moves by its length.

`video/generate-narration.py` works as it is. It checks each beat's text, each product
window and its basis, and the 90 to 174 s narration range. `--write-timestamps` offsets the
beats by `title_seconds`, which in this plan is the cold-open length.

`tests/unit/test_video_retake_pipeline.py` covers both scripts without a browser, ffmpeg or a
request. Its 32 cases (`python -m pytest tests/unit/test_video_retake_pipeline.py -q`) check:

* the beat ids;
* the billed-press flag and the request guard;
* the `/health` refusals and the cold-open timing gate;
* the two shapes of the title slot;
* the band tag and the closing card.
