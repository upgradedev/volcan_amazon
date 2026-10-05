# Volcan: how the demo video is made

**Next take: planned, not recorded.** [`SHOT_LIST.md`](SHOT_LIST.md) and `narration.json` in
this folder now hold the plan for a re-take on the live build, with Amazon Bedrock answering.
Section 4 lists what the pipeline needs before it can render that take. Everything from here
to section 3 describes the render that exists. Its script is in history:
`git show fc10e7d:video/narration.json`. The `cue_sheet.json`, `subtitles.srt` and
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

```bash
export VOLCAN_VIDEO_ROOT=/a/folder/outside/the/repo
export VOLCAN_RELEASE_SHA=$(git rev-parse HEAD)   # the commit the server runs
export VOLCAN_APP_URL=http://127.0.0.1:8871/
export FFMPEG=/path/to/ffmpeg FFPROBE=/path/to/ffprobe
# ELEVENLABS_API_KEY goes into the generator's environment only; never printed or written.

python video/generate-narration.py --write-timestamps
# A fresh server with no cloud credentials. On a machine with ~/.aws, point the SDK away from it:
AWS_SHARED_CREDENTIALS_FILE=/nonexistent AWS_CONFIG_FILE=/nonexistent AWS_EC2_METADATA_DISABLED=true \
  SOURCE_REVISION=$VOLCAN_RELEASE_SHA python -m src.interfaces.mcp_server --port 8871
python video/capture-local.py
python video/build-video.py
cd "$VOLCAN_VIDEO_ROOT/output" && VIDEO_MANIFEST=video_manifest.json \
  CAPTION_WINDOWS=caption_windows.json python /path/to/repo/scripts/verify_video_sync.py volcan-demo.mp4
python scripts/synthesize_video_assets.py         # cue sheet and subtitles from the measured beats
```

The gate calls `ffmpeg` and `ffprobe` by name, so put their folder on `PATH` for it.
`python tests/video/verify_gate_selftest.py` proves the gate still fails on a mis-ordered
video, a caption that runs into the outro and an audio track longer than the picture. It is
not collected by pytest.

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

A take fails, and has to be recorded again, when the page logs an error, when `/health`
reports a different commit than `VOLCAN_RELEASE_SHA`, when a voiced turn's speech has not ended
before the next beat starts or was interrupted, when the page speaks a sentence other than the
one the server returned, when the review dialogue refuses a turn or does not answer it, when
Findings or Confirm is not an outlined next step, when the review pane does not show a
recorded, unsent review, when the Alexa+ replay serves fewer than three clients, or when the
picture stays one flat colour for 0.75 s or longer. That last check reads the recording's
pixels: on a loaded machine a long smooth scroll can outrun
rasterisation and record blank tiles.

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

## 4. Before the re-take can be rendered

The plan in [`SHOT_LIST.md`](SHOT_LIST.md) is written for the live build. The committed
pipeline was written for the local `09d4862` take, so four of its pieces do not fit the new
plan yet:

* `video/capture-local.py` drives the six beats of the `09d4862` take:
  * Its `EXPECTED_BEATS` lists the old beat ids, so it refuses the new `narration.json`.
  * It opens octocat/Hello-World pull request 1 and checks for that sentence.
  * It presses Hear this code review after the narration; beat 2 now presses before it.
  * It records headless, without audio, and voices three turns.

  It needs updating for this journey, or the take is captured by hand in a headed browser
  with its own audio.
* `video/build-video.py` renders `cards.title_lines` as a text card for `title_seconds`. In
  this plan the title slot carries the cold-open footage, with those lines in the band, so the
  build has to splice that footage in. `scripts/verify_video_sync.py` reads the title
  segment's length from the manifest the build writes.
* The optional consented clip has no place in the pipeline. It goes in during the edit, and
  every later timestamp moves by its length.
* The commands in section 1 start a local server with no cloud credentials. For this take,
  `VOLCAN_APP_URL` points at the live build, and `VOLCAN_RELEASE_SHA` is the
  `source_revision` that its `/health` reports.

`video/generate-narration.py` works as it is. It checks each beat's text, each product
window and its basis, and the 90 to 174 s narration range. `--write-timestamps` offsets the
beats by `title_seconds`, which in this plan is the cold-open length.
