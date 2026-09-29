# Volcan: how the demo video is made

**Status: rendered locally, not published.** The current render is `volcan-demo.mp4`, 164.52
seconds, 1920x1080 at 25 fps, recorded on 2026-09-28 (local time) from a local run of commit
`7a3de49d0801aca5059e32a48f0df96eebd42f9e`. It lives outside the repository, at
`reviews/videos_20260928/volcan_amazon/output/volcan-demo.mp4` in the owner's workspace, next to
`video-receipt.json` and the sync gate's output in `sync-gate.txt`, and waits for the owner to
upload it. There is no public link yet. The earlier renders stay where they were and are
superseded: `reviews/videos_20260927/` (174.32 s, from `1dc939f`) held the first viewport for
about 40 s before the press, burned its captions over the sentence the page shows while it
speaks, and had no product sound in the pull-request beat. Readiness gates E2 and E4 look for
footage inside `video/`, so they stay red.

| | |
|---|---|
| SHA-256 of the mp4 | `51f3d087d5f4ee47788903526ac5d4708891235150257a840504e11e44a9c3a5` |
| Duration, from ffprobe | 164.520 s: 3.0 s title card, 157.0 s of beats, 4.5 s outro card |
| Sync gate | `scripts/verify_video_sync.py`: all gates passed, 32 caption windows |
| First press | 15.7 s into the video; the product's own earcon starts at 16.6 s |
| Product voice in the mix | Three turns: the press, Findings on the pull request, and Confirm. 9 caption cues marked `Volcan (product voice):` and 2 earcon cues |
| Narration voice | ElevenLabs, voice id `21m00Tcm4TlvDq8ikWAM`, model `eleven_multilingual_v2` |
| Characters sent to ElevenLabs for this render | 1,585 over two runs: 892 for the first cut of beats 1, 3, 4 and 6, then 693 for beats 1, 5 and 6 cut shorter to keep the total under 174 s. Beat 2 reuses the audio of the 2026-09-27 render's beat 3, unchanged. 1,369 characters are in the beats that shipped |
| Product code on camera | `src/` and `docs/` identical to `7a3de49`, which is also the commit `/health` reports on camera |

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

* No terminal is filmed. Beat 6 states 646 tests and 23 of 23 conformance checks. On
  2026-09-28 `python -m pytest tests/ -q` printed `646 passed` on `7a3de49`, and
  `python scripts/mcp_conformance.py http://127.0.0.1:8871/mcp` printed `23/23 checks passed`
  against a server of `7a3de49`, which was then restarted fresh for the take.
* No screen reader is filmed. Headless capture has none; the narration states the problem.
* The system voice renders each sentence a little faster than the browser spoke it: 15.20 s
  against 16.82 s for the press, 15.79 s against 18.19 s for the Confirm answer. Each sentence
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
