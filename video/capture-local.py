#!/usr/bin/env python3
"""Record the Volcan journey from a locally running server, one beat per measured window.

This is the capture step of the submission kit's video pipeline, rewritten in Python
Playwright because the kit's Node capture drives a deployed site from CI. The pacing
rule is the kit's: each beat holds for exactly the window video/generate-narration.py
measured, and the timeline starts only after the page has drawn the server's answer.

What it records and what it refuses to do:

* Every state on screen is the page reacting to a real response from the running
  server. The script presses keys and buttons and scrolls; it never writes into the
  page's DOM and never answers a request itself.
* An init script observes, and only observes, when the page starts the earcon and
  the browser's speech. Those timestamps place the product's own sound in the mix.
* Headless Chromium records no audio. The earcon mixed into the video is the WAV the
  server returned for the press, byte for byte. The spoken sentence is the exact text
  the page handed to speechSynthesis, rendered again with the Windows system voice
  that has the same name, and the build labels it on screen as the browser's system
  voice.
* Two marker pages, one before and one after the journey, turn from white to black
  at a logged wall-clock time. Finding those two frames in the recording maps page
  time to video time, so the product's sound lands on the frame where the page made
  it, and any drift across the take is measured rather than assumed.
* The take fails if the browser's speech has not ended inside the product sound
  window, if the page logs an error, or if the recording is shorter than the
  narration.

Environment:
  VOLCAN_VIDEO_ROOT    media root, outside git (reads narration/, writes capture/)
  VOLCAN_RELEASE_SHA   the 40 character commit the server was started from
  VOLCAN_APP_URL       default http://127.0.0.1:8801/
  FFMPEG               path to ffmpeg, for finding the marker frames
  VOLCAN_SPEECH_VOICE  default "Microsoft David Desktop", the System.Speech voice
  VOLCAN_PR_URL        default PULL_REQUEST_URL below, the public pull request of beat 5

Only beat 2's product sound is in the mix. In beat 5 the page also plays its own cue
and speaks each dialogue answer; those are not rendered, and the build labels the
beat on screen as missing them.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import time
import urllib.request

from playwright.sync_api import sync_playwright


EXPECTED_BEATS = [
    "beat_01_hook",
    "beat_02_one_button",
    "beat_03_what_you_heard",
    "beat_04_mcp_handshake",
    "beat_05_pull_request",
    "beat_06_verification",
]
VIEWPORT = {"width": 1280, "height": 720}
# A public pull request the server reads from GitHub without a token, and a comment
# that claims nothing about its content. The review is recorded, never sent: the
# server runs without VOLCAN_GITHUB_WRITE and without a token.
PULL_REQUEST_URL = "https://github.com/octocat/Hello-World/pull/1"
REVIEW_COMMENT = "Volcan demo: a dry-run request changes review, recorded and not sent."

OBSERVER = r"""
(() => {
  const epoch = () => performance.timeOrigin + performance.now();
  const log = [];
  Object.defineProperty(window, "__volcanCaptureLog", { value: log });
  const note = (kind, detail) => log.push({ kind, epoch: epoch(), detail: detail === undefined ? null : detail });
  const play = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function () {
    const media = this;
    note("media.play");
    media.addEventListener("playing", () => note("media.playing", media.currentTime), { once: true });
    media.addEventListener("timeupdate", () => note("media.timeupdate", media.currentTime));
    media.addEventListener("ended", () => note("media.ended", media.currentTime), { once: true });
    return play.apply(this, arguments);
  };
  if (window.speechSynthesis) {
    const speak = window.speechSynthesis.speak.bind(window.speechSynthesis);
    window.speechSynthesis.speak = function (utterance) {
      note("speech.speak", { text: utterance.text, rate: utterance.rate });
      utterance.addEventListener("start", () => note("speech.start"));
      utterance.addEventListener("end", () => note("speech.end"));
      utterance.addEventListener("error", (event) => note("speech.error", event.error));
      return speak(utterance);
    };
  }
})();
"""

MARKER_PAGE = "<!doctype html><title>marker</title><body style='margin:0;background:#fff;height:100vh'></body>"
FLIP = """
() => new Promise((resolve) => requestAnimationFrame(() => {
  document.body.style.background = '#000';
  resolve(performance.timeOrigin + performance.now());
}))
"""

SAPI = r"""
param([string]$TextFile, [string]$OutWav, [string]$Voice)
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice($Voice)
$s.Rate = 0
$s.SetOutputToWaveFile($OutWav)
$s.Speak([IO.File]::ReadAllText($TextFile, [Text.Encoding]::UTF8))
$s.Dispose()
"""


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default or "").strip()
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe_duration(path: pathlib.Path) -> float:
    ffprobe = str(pathlib.Path(env("FFMPEG")).with_name("ffprobe" + pathlib.Path(env("FFMPEG")).suffix))
    out = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return float(out)


def marker_times(video: pathlib.Path, work: pathlib.Path) -> list[float]:
    """Video times of every white-to-black flip, read from the recording's pixels."""
    stats = work / "marker-yavg.txt"
    filters = f"scale=64:36,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file={stats.name}"
    subprocess.run(
        [env("FFMPEG"), "-v", "error", "-i", str(video), "-vf", filters, "-f", "null", "-"],
        check=True, capture_output=True, text=True, cwd=work,
    )
    samples: list[tuple[float, float]] = []
    current = None
    for line in stats.read_text(encoding="utf-8").splitlines():
        found = re.search(r"pts_time:([0-9.]+)", line)
        if found:
            current = float(found.group(1))
        found = re.search(r"YAVG=([0-9.]+)", line)
        if found and current is not None:
            samples.append((current, float(found.group(1))))
    flips = []
    for (_, before), (when, after) in zip(samples, samples[1:]):
        if before > 200 and after < 40:
            flips.append(when)
    return flips


def main() -> None:
    root = pathlib.Path(env("VOLCAN_VIDEO_ROOT"))
    release_sha = env("VOLCAN_RELEASE_SHA")
    if not re.fullmatch(r"[0-9a-f]{40}", release_sha):
        raise SystemExit("VOLCAN_RELEASE_SHA must be a full 40 character commit")
    app_url = os.environ.get("VOLCAN_APP_URL", "http://127.0.0.1:8801/").strip()
    voice = os.environ.get("VOLCAN_SPEECH_VOICE", "Microsoft David Desktop").strip()
    timing = json.loads((root / "narration" / "timing.json").read_text(encoding="utf-8"))
    scenes = timing["scenes"]
    if [scene["id"] for scene in scenes] != EXPECTED_BEATS:
        raise SystemExit("the narration beats and this journey differ; update both together")
    by_id = {scene["id"]: scene for scene in scenes}
    total = float(timing["totalSeconds"])

    capture = root / "capture"
    if capture.exists():
        shutil.rmtree(capture)
    (capture / "raw").mkdir(parents=True)

    with urllib.request.urlopen(app_url.rstrip("/") + "/health", timeout=10) as response:
        health = json.load(response)

    actions: list[dict[str, object]] = []
    errors: list[str] = []
    press: dict[str, object] = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--force-device-scale-factor=1"])
        context = browser.new_context(
            viewport=VIEWPORT,
            device_scale_factor=1,
            record_video_dir=str(capture / "raw"),
            record_video_size=VIEWPORT,
        )
        context.add_init_script(OBSERVER)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
        page.on("console", lambda message: errors.append(f"console: {message.text}")
                if message.type == "error" else None)

        page.set_content(MARKER_PAGE)
        page.wait_for_timeout(1200)
        start_marker = page.evaluate(FLIP)
        page.wait_for_timeout(1200)

        page.goto(app_url, wait_until="networkidle", timeout=60_000)
        page.wait_for_selector('#stage[data-preview="ready"]', timeout=30_000)
        page.wait_for_selector('#connPill[data-state="live"]', timeout=30_000)
        page.evaluate("document.fonts.ready.then(() => true)")
        default_voice = page.evaluate(
            "(speechSynthesis.getVoices().find(v => v.default) || {}).name || null")
        page.wait_for_timeout(1000)

        origin = time.monotonic()
        timeline_epoch = page.evaluate("performance.timeOrigin + performance.now()")

        def act(label: str, run) -> None:
            run()
            actions.append({"at": round(time.monotonic() - origin, 3), "action": label})

        def until(seconds: float) -> None:
            remaining = seconds - (time.monotonic() - origin)
            if remaining > 0:
                page.wait_for_timeout(remaining * 1000)

        def beat_start(beat: str) -> float:
            return float(by_id[beat]["startSeconds"])

        def sentence(beat: str, index: int, fraction: float = 0.0) -> float:
            window = by_id[beat]["sentences"][index]
            return beat_start(beat) + float(window["start"]) + fraction * (
                float(window["end"]) - float(window["start"]))

        def scroll_to(selector: str, offset: int = 16) -> None:
            page.evaluate(
                """([selector, offset]) => {
                  const top = document.querySelector(selector).getBoundingClientRect().top + scrollY - offset;
                  window.scrollTo({ top, behavior: 'smooth' });
                }""",
                [selector, offset],
            )

        # Beat 1: the patch, then the raw unified diff in the patch box.
        until(sentence("beat_01_hook", 2))
        act("Alt+2 opens the patch box", lambda: page.keyboard.press("Alt+2"))

        # Beat 2: the silent preview, the keyboard press, then the product's own sound.
        until(beat_start("beat_02_one_button"))
        act("scroll to the stage", lambda: page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})"))
        until(sentence("beat_02_one_button", 2))
        act("Alt+1 focuses Hear this code review", lambda: page.keyboard.press("Alt+1"))
        window_opens = beat_start("beat_02_one_button") + float(by_id["beat_02_one_button"]["durationSeconds"]) \
            + float(timing["tailSeconds"])
        window_closes = beat_start("beat_03_what_you_heard")
        until(window_opens)

        def is_press(response) -> bool:
            body = response.request.post_data or ""
            return response.url.endswith("/api/digest_semantic_diff") and '"engine"' not in body

        with page.expect_response(is_press, timeout=15_000) as pressed:
            act("Enter presses Hear this code review", lambda: page.keyboard.press("Enter"))
        press = pressed.value.json()
        page.wait_for_function(
            "window.__volcanCaptureLog.some(e => e.kind === 'speech.end' || e.kind === 'speech.error')",
            timeout=max(1.0, window_closes - (time.monotonic() - origin)) * 1000,
        )
        actions.append({"at": round(time.monotonic() - origin, 3), "action": "browser speech ended"})

        # Beat 3: what was heard, and why the local engine answered.
        until(beat_start("beat_03_what_you_heard"))
        act("scroll to the earcon caption and meters", lambda: scroll_to(".r-earcon", 120))
        until(sentence("beat_03_what_you_heard", 3))
        act("open why this engine answered", lambda: page.click("#meterEngineWhy"))

        # Beat 4: a real MCP handshake.
        until(beat_start("beat_04_mcp_handshake"))
        act("scroll to Evidence", lambda: scroll_to("#evidence"))
        until(sentence("beat_04_mcp_handshake", 1))
        act("Run a real MCP handshake", lambda: page.click("#runMcp"))
        page.wait_for_selector("#mcpPane details", timeout=10_000)
        act("scroll to the handshake facts", lambda: scroll_to("#mcp .row-actions", 24))
        until(sentence("beat_04_mcp_handshake", 1, 0.72))
        act("expand the first tool", lambda: page.click("#mcpPane details summary"))
        act("scroll to its schema", lambda: scroll_to("#mcpPane", 90))

        def settled(timeout_seconds: float = 20.0) -> None:
            """Wait until the review dialogue has answered the last turn."""
            page.wait_for_timeout(250)
            page.wait_for_function(
                "document.querySelector('#reviewConvo').getAttribute('aria-busy') === 'false'",
                timeout=timeout_seconds * 1000,
            )

        def answered(turns_before: int) -> None:
            settled()
            count = page.evaluate("document.querySelectorAll('#dialogueLog li').length")
            if count <= turns_before:
                raise SystemExit("the review dialogue did not answer the turn")
            rejected = page.evaluate(
                "[...document.querySelectorAll('#dialogueLog li')].some(li => li.textContent.startsWith('Not sent'))")
            if rejected:
                raise SystemExit("the page refused a turn because the last one was still in flight")

        def turns() -> int:
            return page.evaluate("document.querySelectorAll('#dialogueLog li').length")

        # Beat 5: a real public pull request, summary, request changes, confirm.
        until(beat_start("beat_05_pull_request"))
        act("scroll to Talk through a real pull request", lambda: scroll_to("#review", 8))
        until(sentence("beat_05_pull_request", 1))
        act("Alt+6 focuses the pull request URL box", lambda: page.keyboard.press("Alt+6"))
        act("type the pull request URL", lambda: page.keyboard.type(
            os.environ.get("VOLCAN_PR_URL", PULL_REQUEST_URL), delay=35))
        before = turns()
        act("Enter opens the pull request", lambda: page.keyboard.press("Enter"))
        answered(before)
        act("scroll to the dialogue", lambda: scroll_to("#review .review-grid", 8))
        until(sentence("beat_05_pull_request", 2))
        before = turns()
        act("Summary", lambda: page.click("#cmdSummary"))
        answered(before)
        until(sentence("beat_05_pull_request", 3))
        act("type the review comment", lambda: (page.click("#reviewComment"),
                                                 page.keyboard.type(REVIEW_COMMENT, delay=12)))
        before = turns()
        act("Request changes", lambda: page.click("#cmdRequestChanges"))
        answered(before)
        until(sentence("beat_05_pull_request", 4))
        before = turns()
        act("Confirm", lambda: page.click("#cmdConfirm"))
        answered(before)
        if "recorded and not sent" not in page.inner_text("#reviewPane"):
            raise SystemExit("the review pane does not show a recorded, unsent review")
        # Hold on the dialogue's dry-run answer, then show the request it recorded.
        until(sentence("beat_05_pull_request", 4, 0.55))
        act("scroll to the recorded request", lambda: scroll_to("#reviewPane", 150))

        # Beat 6: the counts, the Alexa+ replay, the honest boundary, then the heading.
        until(beat_start("beat_06_verification"))
        act("Server and MCP tab", lambda: page.click("#tabServer"))
        act("scroll to the connection strip", lambda: scroll_to("#evidenceTabs", 24))
        until(sentence("beat_06_verification", 1))
        act("scroll to the Alexa+ replay", lambda: scroll_to("#alexaReplay", 24))
        act("Replay the documented Alexa+ requests", lambda: page.click("#runReplay"))
        page.wait_for_function(
            "/of 3 clients served/.test(document.querySelector('#replayPane').textContent)", timeout=10_000)
        if "3 of 3 clients served" not in page.inner_text("#replayPane"):
            raise SystemExit("the Alexa+ replay did not serve all three clients")
        until(sentence("beat_06_verification", 2))
        act("scroll to the connection strip and the Alexa+ box", lambda: scroll_to("#evidenceTabs", 24))
        until(sentence("beat_06_verification", 3))
        act("scroll to the heading", lambda: page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})"))
        until(total + 1.5)

        log = page.evaluate("window.__volcanCaptureLog")
        page.set_content(MARKER_PAGE)
        page.wait_for_timeout(1200)
        end_marker = page.evaluate(FLIP)
        page.wait_for_timeout(1200)
        video = page.video
        context.close()
        browser.close()
        raw_path = pathlib.Path(video.path())

    final = capture / "production.webm"
    raw_path.replace(final)
    shutil.rmtree(capture / "raw", ignore_errors=True)
    if errors:
        raise SystemExit("the page logged errors during the take: " + "; ".join(errors[:5]))

    flips = marker_times(final, capture)
    if len(flips) != 2:
        raise SystemExit(f"expected two marker flips in the recording, found {len(flips)}: {flips}")
    scale = (flips[1] - flips[0]) / ((end_marker - start_marker) / 1000)

    def video_time(epoch_ms: float) -> float:
        return flips[0] + (epoch_ms - start_marker) / 1000 * scale

    trim_lead = video_time(timeline_epoch)

    # Timeline times are page-clock seconds from the start of the journey. The
    # recording can run slower or faster than the page clock when the machine is
    # loaded; the build retimes it by videoPerPageSecond so both clocks agree.
    def timeline_time(epoch_ms: float) -> float:
        return round((epoch_ms - timeline_epoch) / 1000, 3)

    def first(kind: str) -> dict[str, object]:
        for entry in log:
            if entry["kind"] == kind:
                return entry
        raise SystemExit(f"the page never reported {kind}")

    playing = first("media.playing")
    ended = first("media.ended")
    # Where the page's own playback clock says the cue started: each timeupdate
    # reports how far into the WAV the element is, so its wall time minus that
    # position is the start. Headless Chromium fires "playing" a few hundred
    # milliseconds before the clock moves, and the waveform's playhead follows
    # the clock, so this is the moment the picture shows the cue sounding.
    # Only the press in beat 2: the review turns of beat 5 play cues of their own.
    press_play = first("media.play")["epoch"]
    clock_starts = sorted(
        entry["epoch"] - float(entry["detail"]) * 1000
        for entry in log
        if entry["kind"] == "media.timeupdate"
        and press_play <= entry["epoch"] <= ended["epoch"]
        and 0 < float(entry["detail"] or 0) < float(ended["detail"])
    )
    if clock_starts:
        earcon_start = clock_starts[len(clock_starts) // 2]
        earcon_basis = f"median of {len(clock_starts)} timeupdate events, wall time minus currentTime"
    else:
        earcon_start = ended["epoch"] - float(ended["detail"]) * 1000
        earcon_basis = "ended event minus the WAV length reported by currentTime"
    spoken = first("speech.speak")
    speech_start = first("speech.start")
    speech_end = first("speech.end")
    if spoken["detail"]["text"] != press.get("voice_summary_for_speech"):
        raise SystemExit("the page spoke a sentence other than the one the server returned")
    if timeline_time(speech_end["epoch"]) > window_closes:
        raise SystemExit("the browser was still speaking when the next beat began")

    earcon = capture / "earcon-press.wav"
    earcon.write_bytes(base64.b64decode(press["earcon"]["wav_base64"]))
    text_file = capture / "browser-speech.txt"
    text_file.write_text(spoken["detail"]["text"], encoding="utf-8")
    script = capture / "render-system-voice.ps1"
    script.write_text(SAPI, encoding="utf-8")
    speech_wav = capture / "browser-speech.wav"
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
         "-TextFile", str(text_file), "-OutWav", str(speech_wav), "-Voice", voice],
        check=True, capture_output=True, text=True,
    )

    recorded = probe_duration(final)
    if recorded < trim_lead + total * scale:
        raise SystemExit(f"the recording is {recorded:.3f}s, shorter than {trim_lead + total * scale:.3f}s")
    receipt = {
        "schemaVersion": "volcan.video-capture/v1",
        "releaseSha": release_sha,
        "appUrl": app_url,
        "viewport": VIEWPORT,
        "serverHealth": {
            "service": health.get("service"),
            "version": health.get("version"),
            "sourceRevision": health.get("source_revision"),
            "modelPath": (health.get("bedrock_model_path") or {}).get("resolved_capability"),
            "githubReviewPath": (health.get("github_review_path") or {}).get("resolved_capability"),
            "durableState": (health.get("durable_state") or {}).get("resolved_capability"),
        },
        "trimLeadSeconds": round(trim_lead, 3),
        "timelineSeconds": total,
        "recordedSeconds": round(recorded, 3),
        "markers": {
            "videoSeconds": [round(value, 3) for value in flips],
            "pageClockSeconds": round((end_marker - start_marker) / 1000, 3),
            "videoPerPageSecond": round(scale, 6),
            "note": "timeline times below are page-clock seconds; the build retimes the recording by videoPerPageSecond",
        },
        "actions": actions,
        "press": {
            "synthesisMode": press.get("synthesis_mode"),
            "fallbackReason": press.get("synthesis_fallback_reason"),
            "earconType": press["earcon"].get("type"),
            "sentenceOnScreen": press.get("voice_summary"),
        },
        "productAudio": [
            {
                "kind": "earcon",
                "file": earcon.name,
                "sha256": sha256(earcon),
                "seconds": round(probe_duration(earcon), 3),
                "source": "the earcon.wav_base64 bytes of the server's response to the press, unchanged",
                "timelineSeconds": timeline_time(earcon_start),
                "timelineBasis": earcon_basis,
                "pagePlayingEventTimelineSeconds": timeline_time(playing["epoch"]),
                "pageEndedTimelineSeconds": timeline_time(ended["epoch"]),
            },
            {
                "kind": "browser-speech",
                "file": speech_wav.name,
                "sha256": sha256(speech_wav),
                "seconds": round(probe_duration(speech_wav), 3),
                "text": spoken["detail"]["text"],
                "pageRate": spoken["detail"]["rate"],
                "browserDefaultVoice": default_voice,
                "renderedWith": f"Windows System.Speech, voice {voice}, rate 0",
                "source": "the exact text the page passed to speechSynthesis.speak, rendered again because headless capture records no audio",
                "timelineSeconds": timeline_time(speech_start["epoch"]),
                "pageEndedTimelineSeconds": timeline_time(speech_end["epoch"]),
            },
        ],
        "pageErrors": errors,
        "bytes": final.stat().st_size,
        "sha256": sha256(final),
    }
    (capture / "capture-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: receipt[key] for key in ("trimLeadSeconds", "recordedSeconds", "markers")}))
    for item in receipt["productAudio"]:
        print(item["kind"], item["timelineSeconds"], "to", item["pageEndedTimelineSeconds"],
              "rendered", item["seconds"])


if __name__ == "__main__":
    main()
