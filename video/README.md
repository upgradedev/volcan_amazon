# Volcan: how the demo video is made

**Status: rendered locally, not published.** One render exists: `volcan-demo.mp4`, 168.0
seconds, 1920x1080 at 25 fps, recorded on 2026-09-27 (local time) from a local run of commit
`de30b11f34949419cebdbb62103670c288c18b55`. It lives outside the repository, at
`reviews/videos_20260926/volcan_amazon/output/volcan-demo.mp4` in the owner's workspace, next to
`video-receipt.json` and the sync gate's output, and waits for the owner to upload it. There is
no public link yet. The render reproduces from commit `c09e451`, the first commit carrying both
the scripts and the narration spec that built it. Readiness gates E2 and E4 look for footage inside `video/`, so they stay red.

| | |
|---|---|
| SHA-256 of the mp4 | `5382a7204d3ae80d30bcd691145f9eae432c9a760299560492c01b632256b09e` |
| Duration, from ffprobe | 168.000 s: 3.5 s title card, 160.991 s of beats, 3.5 s outro card |
| Sync gate | `scripts/verify_video_sync.py`: all gates passed |
| Narration voice | ElevenLabs, voice id `21m00Tcm4TlvDq8ikWAM`, model `eleven_multilingual_v2` |
| Characters sent to ElevenLabs | 3,167 in total, including one voice check and one re-roll of three trimmed beats; 1,949 in the beats that shipped |
| Product code on camera | `src/` and `docs/` identical to `de30b11` when the video was built |

---

## 1. The pipeline

The scripts are the submission kit's video pipeline, adapted to this repository and committed
so any one beat can be re-rendered later.

| Step | Script | Writes, under `VOLCAN_VIDEO_ROOT` (never into git) |
|---|---|---|
| Narration | `video/generate-narration.py` | `narration/NN-beat.mp3`, `timing.json`, `captions.en.srt`, `tts-ledger.jsonl` |
| Capture | `video/capture-local.py` | `capture/production.webm`, `earcon-press.wav`, `browser-speech.wav`, `capture-receipt.json` |
| Compose | `video/build-video.py` | `output/volcan-demo.mp4`, `video-receipt.json`, `video_manifest.json`, `caption_windows.json` |
| Gate | `scripts/verify_video_sync.py` | pass or fail, from the mp4 itself |

```bash
export VOLCAN_VIDEO_ROOT=/a/folder/outside/the/repo
export VOLCAN_RELEASE_SHA=$(git rev-parse HEAD)   # the commit the server runs
export FFMPEG=$(command -v ffmpeg) FFPROBE=$(command -v ffprobe)
export ELEVENLABS_API_KEY=...                     # read, never printed or written

python video/generate-narration.py --write-timestamps
python -m src.interfaces.mcp_server --port 8801   # fresh process, no cloud credentials
python video/capture-local.py
python video/build-video.py
cd "$VOLCAN_VIDEO_ROOT/output" && VIDEO_MANIFEST=video_manifest.json \
  CAPTION_WINDOWS=caption_windows.json python /path/to/repo/scripts/verify_video_sync.py volcan-demo.mp4
python scripts/synthesize_video_assets.py         # cue sheet and subtitles from the measured beats
```

`python tests/video/verify_gate_selftest.py` proves the gate still fails on a mis-ordered
video, a caption that runs into the outro and an audio track longer than the picture. It
passed on 2026-09-27. It is not collected by pytest. Beat 6 says 572 tests, the count on the
commit it was rendered from; the suite now collects 623, and the page's Alexa+ box now reads
"package built and tested locally, not certified or deployed" rather than "not built", so
beat 6 has to be re-rendered before the final take.

### Re-rendering one beat

Edit that beat's `narration_text` and `speech_text` in `narration.json` and rerun the
generator. It prints `reused` for every unchanged beat and synthesizes only the edited one,
because ElevenLabs does not return identical audio twice and a re-roll would move every
offset after it. Then capture and compose again: the capture is paced by the measured windows,
so a changed beat length changes the take.

---

## 2. What is real in the picture and the sound

* **The picture** is a headless Chromium recording of the page at 1280x720, scaled to 1080p.
  The script presses keys and buttons and scrolls; it never writes into the page and never
  answers a request. Every panel filled from the running server during the take.
* **The narration** is a synthetic ElevenLabs voice. It never speaks for the product.
* **The earcon** is the WAV the server returned for the press, byte for byte (SHA-256
  `22c91bec...`), mixed in where the page's own playback clock started it, which is where the
  playhead starts crossing the waveform.
* **The spoken sentence** is the exact text the page passed to `speechSynthesis`, which is the
  server's `voice_summary_for_speech`. Headless capture records no audio, so it was rendered
  again with Windows System.Speech, voice `Microsoft David Desktop`, the desktop form of the
  `Microsoft David` voice the browser used, and placed at the browser's speech start event. It
  is labelled on screen as the browser's system voice.
* **Two marker pages**, before and after the journey, turn from white to black at a logged
  time. Their frames map page time to video time; across the take the drift was 5 parts per
  million.
* **The overlays** are the title and outro cards, a corner tag naming the local commit, the two
  labels naming the product's sound, and captions derived from the measured narration.

## 3. Known gaps in this render

* No terminal is filmed. The test count and the conformance count in beat 6 were printed by
  `python -m pytest tests/ -q` and `python scripts/mcp_conformance.py` against this commit on
  2026-09-26, and are stated rather than shown.
* No screen reader is filmed in beat 1. Headless capture has none.
* The browser's speech lasted 16.7 s between its start and end events; the System.Speech
  rendering of the same text lasts 15.2 s. The words on screen light from the browser's own
  boundary events, so late in the sentence the lit word may trail the voice you hear. The
  offset was not measured word by word.
* The public endpoint runs an older commit, so the video shows a local run. The title card
  says so.
* Beat 6 says "The page says so on screen" after three facts. The page shows two of them, the
  missing Alexa skill and the model path; the older public commit is stated by the title card
  and the corner tag, not by the page. Fixing the line means re-synthesizing beat 6 and a
  new take.
* Upload `output/captions.en.srt` from the media root as the caption track: it is sentence
  level with the title card offset. `video/subtitles.srt` in this folder is one cue per beat.
