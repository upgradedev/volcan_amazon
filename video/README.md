# Volcan: how the demo video is made

**Status: rendered locally, not published.** The current render is `volcan-demo.mp4`, 174.32
seconds, 1920x1080 at 25 fps, recorded on 2026-09-27 (local time) from a local run of commit
`1dc939f16e7d0bb00e27625946182b2b43025bbe`. It lives outside the repository, at
`reviews/videos_20260927/volcan_amazon/output/volcan-demo.mp4` in the owner's workspace, next to
`video-receipt.json` and the sync gate's output, and waits for the owner to upload it. There is
no public link yet. The earlier render, from `de30b11`, stays in `reviews/videos_20260926/` and
is superseded: it said 572 tests, showed the old Alexa+ box and left out the pull request.
Readiness gates E2 and E4 look for footage inside `video/`, so they stay red.

| | |
|---|---|
| SHA-256 of the mp4 | `e6f79b268474c330eeb6a47a770f6ac21bb2e85695aaa6788c2ad55d45ca0b0f` |
| Duration, from ffprobe | 174.320 s: 3.5 s title card, 167.32 s of beats, 3.5 s outro card |
| Sync gate | `scripts/verify_video_sync.py`: all gates passed, 25 caption windows |
| Narration voice | ElevenLabs, voice id `21m00Tcm4TlvDq8ikWAM`, model `eleven_multilingual_v2` |
| Characters sent to ElevenLabs for this render | 775, for beats 5 and 6 only. Beats 1 to 4 kept their speech text and reused the audio synthesized on 2026-09-27 for the earlier render. 2,001 characters are in the beats that shipped |
| Product code on camera | `src/` and `docs/` identical to `1dc939f` when the video was built |

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
export VOLCAN_APP_URL=http://127.0.0.1:8841/
export FFMPEG=/path/to/ffmpeg FFPROBE=/path/to/ffprobe
# ELEVENLABS_API_KEY goes into the generator's environment only; never printed or written.

python video/generate-narration.py --write-timestamps
# A fresh server with no cloud credentials. On a machine with ~/.aws, point the SDK away from it:
AWS_SHARED_CREDENTIALS_FILE=/nonexistent AWS_CONFIG_FILE=/nonexistent AWS_EC2_METADATA_DISABLED=true \
  SOURCE_REVISION=$VOLCAN_RELEASE_SHA python -m src.interfaces.mcp_server --port 8841
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
`NN-beat.cache.json` files into the new media root first. Then capture and compose again: the
capture is paced by the measured windows, so a changed beat length changes the take.

### What the capture refuses

A take fails, and has to be recorded again, when the page logs an error, when the browser is
still speaking as beat 3 starts, when the review dialogue refuses a turn or does not answer it,
when the review pane does not show a recorded, unsent review, when the Alexa+ replay serves
fewer than three clients, or when the picture stays one flat colour for 0.75 s or longer. That
last check reads the recording's pixels: on a loaded machine a long smooth scroll can outrun
rasterisation and record blank tiles.

---

## 2. What is real in the picture and the sound

* **The picture** is a headless Chromium recording of the page at 1280x720, scaled to 1080p.
  The script presses keys and buttons, types into the page's own inputs and scrolls; it never
  writes into the page's DOM and never answers a request. Every panel filled from the running
  server during the take.
* **The pull request** in beat 5 is octocat/Hello-World #1, read from GitHub by the server
  without a token. The review comment says it is a dry-run demo and claims nothing about the
  pull request. The server ran without `VOLCAN_GITHUB_WRITE` and without a token, recorded the
  request and sent nothing.
* **The narration** is a synthetic ElevenLabs voice. It never speaks for the product.
* **The earcon** is the WAV the server returned for the press, byte for byte, mixed in where
  the page's own playback clock started it.
* **The spoken sentence** is the exact text the page passed to `speechSynthesis`, which is the
  server's `voice_summary_for_speech`. Headless capture records no audio, so it was rendered
  again with Windows System.Speech, voice `Microsoft David Desktop`, and placed at the
  browser's speech start event. It is labelled on screen as the browser's system voice and
  captioned, marked `Volcan:`, from the same text.
* **Two marker pages**, before and after the journey, turn from white to black at a logged
  time. In this take the recording ran 0.78% longer than the page clock (the machine was
  loaded by other renders), so the build retimes the picture by that measured factor and every
  logged action lands on its timeline second.
* **The overlays** are the title and outro cards, a corner tag naming the local commit, the two
  labels naming the product's sound, a label over beat 5 saying the page's own sound for those
  turns is not recorded, and captions derived from the measured narration and the product
  sentence.

## 3. Known gaps in this render

* No terminal is filmed. Beat 6 states 637 tests and 23 of 23 conformance checks. On
  2026-09-27 `python -m pytest tests/ -q` printed `637 passed` on `b6b4a8c`, whose `src/` and
  `tests/` equal `1dc939f`, and `python scripts/mcp_conformance.py` printed `23/23 checks passed`
  against server processes of `b6b4a8c` and `6924dcc`, whose `src/` equals `1dc939f`.
* No screen reader is filmed in beat 1. Headless capture has none.
* Only beat 2's product sound is in the mix. In beat 5 the page also played a cue and spoke each
  dialogue answer; a label on screen says those are not in the recording, and the narrator
  covers the beat.
* The browser's speech lasted 17.19 s between its start and end events; the System.Speech
  rendering of the same text lasts 15.20 s. The captions follow the rendered voice. The words
  on the page light from the browser's own boundary events, so late in the sentence the lit
  word may run ahead of the voice you hear.
* In this take the page started speaking 2.2 s after the earcon ended, and the earcon started
  about 1 s after the press, both slower than on an idle machine. The video keeps those gaps as
  the page produced them. Beat 2's product-sound window is 21.5 s for that reason; two takes
  with a 20.0 s window failed.
* The patch box in beat 1 renders `==` and `!=` as JetBrains Mono ligatures, a joined double bar
  and a crossed equals sign. The stage above it shows the plain characters. This is the page's
  font setting, not something the video adds.
* After the review turns, the stage at the top of the page shows the last cue the page played,
  the dry-run cue with a level contour, while its sentence is still the first patch's. The
  closing shot shows that state as the page left it.
* The public endpoint runs an older commit, so the video shows a local run. The title card says
  so.
* Upload `output/captions.en.srt` from the media root as the caption track: it is sentence
  level, includes the product sentence and carries the title card offset.
  `video/subtitles.srt` in this folder is one cue per beat.
