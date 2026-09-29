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
* An init script observes, and only observes, when the page starts each earcon and
  each utterance it hands to the browser's speech engine, and when it cancels speech.
  Those timestamps place the product's own sound in the mix.
* Three turns are voiced, one per beat that carries a product sound window: the press
  of Hear this code review, Findings on the pull request, and Confirm. For each, the
  earcon mixed into the video is the WAV the server returned for that turn, byte for
  byte, and every sentence is the exact text the page handed to speechSynthesis,
  rendered again with the Windows system voice of the same name, because headless
  Chromium records no audio. The build captions them as the product's voice.
* Two turns are not voiced: opening the pull request and Request changes happen while
  the narrator speaks. The page still plays its cue and speaks for them; the capture
  logs exactly when, until the next command interrupts it, and the build labels that
  stretch as the page's voice not being in the recording.
* Two marker pages, one before and one after the journey, turn from white to black
  at a logged wall-clock time. Finding those two frames in the recording maps page
  time to video time, so the product's sound lands on the frame where the page made
  it, and any drift across the take is measured rather than assumed.
* The take fails if a voiced turn's speech has not ended inside its window or was
  interrupted, if the page logs an error, if the review dialogue refuses a turn, if the
  Alexa+ replay serves fewer than three clients, if the picture goes flat for 0.75 s,
  or if the recording is shorter than the narration.

Environment:
  VOLCAN_VIDEO_ROOT    media root, outside git (reads narration/, writes capture/)
  VOLCAN_RELEASE_SHA   the 40 character commit the server was started from
  VOLCAN_APP_URL       default http://127.0.0.1:8801/
  FFMPEG               path to ffmpeg, for finding the marker frames
  VOLCAN_SPEECH_VOICE  default "Microsoft David Desktop", the System.Speech voice
  VOLCAN_PR_URL        default PULL_REQUEST_URL below, the public pull request of beat 3
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
    "beat_01_press",
    "beat_02_what_you_heard",
    "beat_03_open_pull_request",
    "beat_04_request_changes",
    "beat_05_mcp_handshake",
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
  let media = 0;
  const play = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function () {
    const element = this;
    if (element.__volcanId === undefined) {
      element.__volcanId = ++media;
      const id = element.__volcanId;
      element.addEventListener("playing", () => note("media.playing", { id, at: element.currentTime }));
      element.addEventListener("timeupdate", () => note("media.timeupdate", { id, at: element.currentTime }));
      element.addEventListener("ended", () => note("media.ended", { id, at: element.currentTime }));
    }
    note("media.play", { id: element.__volcanId });
    return play.apply(this, arguments);
  };
  if (window.speechSynthesis) {
    let spoken = 0;
    const speak = window.speechSynthesis.speak.bind(window.speechSynthesis);
    window.speechSynthesis.speak = function (utterance) {
      const index = spoken++;
      note("speech.speak", { index, text: utterance.text, rate: utterance.rate });
      utterance.addEventListener("start", () => note("speech.start", { index }));
      utterance.addEventListener("end", () => note("speech.end", { index }));
      utterance.addEventListener("error", (event) => note("speech.error", { index, error: event.error }));
      return speak(utterance);
    };
    const cancel = window.speechSynthesis.cancel.bind(window.speechSynthesis);
    window.speechSynthesis.cancel = function () {
      note("speech.cancel");
      return cancel();
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


def blank_stretches(video: pathlib.Path, work: pathlib.Path, start: float, end: float,
                    min_seconds: float = 0.75) -> list[tuple[float, float]]:
    """Stretches of the take where the picture is one flat colour.

    A page frame always has text on it, so its darkest and brightest pixels differ by
    far more than a flat frame's. A long scroll on a loaded machine can outrun
    rasterisation and record blank tiles; this finds them from the pixels."""
    stats = work / "blank-range.txt"
    filters = (f"trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS,fps=4,scale=320:180,signalstats,"
               f"metadata=print:file={stats.name}")
    subprocess.run(
        [env("FFMPEG"), "-v", "error", "-i", str(video), "-vf", filters, "-f", "null", "-"],
        check=True, capture_output=True, text=True, cwd=work,
    )
    samples: list[tuple[float, float, float]] = []
    current: float | None = None
    low = high = None
    for line in stats.read_text(encoding="utf-8").splitlines():
        found = re.search(r"pts_time:([0-9.]+)", line)
        if found:
            current, low, high = float(found.group(1)), None, None
        found = re.search(r"YMIN=([0-9.]+)", line)
        if found:
            low = float(found.group(1))
        found = re.search(r"YMAX=([0-9.]+)", line)
        if found:
            high = float(found.group(1))
        if current is not None and low is not None and high is not None:
            samples.append((current, low, high))
            current = None
    stretches = []
    run_start = None
    for when, low, high in samples:
        flat = high - low < 24
        if flat and run_start is None:
            run_start = when
        if not flat and run_start is not None:
            if when - run_start >= min_seconds:
                stretches.append((round(start + run_start, 2), round(start + when, 2)))
            run_start = None
    if run_start is not None and samples and samples[-1][0] - run_start >= min_seconds:
        stretches.append((round(start + run_start, 2), round(start + samples[-1][0], 2)))
    return stretches


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
    if health.get("source_revision") != release_sha:
        raise SystemExit("the server reports a different commit than VOLCAN_RELEASE_SHA; restart it")

    actions: list[dict[str, object]] = []
    errors: list[str] = []
    voiced: list[dict[str, object]] = []
    unvoiced: list[dict[str, object]] = []

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

        def now() -> float:
            return time.monotonic() - origin

        def act(label: str, run) -> None:
            run()
            actions.append({"at": round(now(), 3), "action": label})

        def until(seconds: float) -> None:
            remaining = seconds - now()
            if remaining > 0:
                page.wait_for_timeout(remaining * 1000)

        def beat_start(beat: str) -> float:
            return float(by_id[beat]["startSeconds"])

        def beat_end(beat: str) -> float:
            return beat_start(beat) + float(by_id[beat]["holdSeconds"])

        def window_opens(beat: str) -> float:
            """Where the narrator stops and the beat's product sound window begins."""
            return beat_start(beat) + float(by_id[beat]["durationSeconds"]) + float(timing["tailSeconds"])

        def sentence(beat: str, index: int, fraction: float = 0.0) -> float:
            window = by_id[beat]["sentences"][index]
            return beat_start(beat) + float(window["start"]) + fraction * (
                float(window["end"]) - float(window["start"]))

        def scroll_to(selector: str, offset: int = 16, behavior: str = "smooth") -> None:
            page.evaluate(
                """([selector, offset, behavior]) => {
                  const top = document.querySelector(selector).getBoundingClientRect().top + scrollY - offset;
                  window.scrollTo({ top, behavior });
                }""",
                [selector, offset, behavior],
            )

        def page_epoch() -> float:
            return page.evaluate("performance.timeOrigin + performance.now()")

        def log_length() -> int:
            return page.evaluate("window.__volcanCaptureLog.length")

        def speak_count() -> int:
            return page.evaluate("window.__volcanCaptureLog.filter(e => e.kind === 'speech.speak').length")

        def start_turn(label: str, run, endpoint: str, utterances: int, predicate=None) -> dict[str, object]:
            """Press, and keep the server's response: its earcon bytes are what the mix plays."""
            def matches(response) -> bool:
                if not response.url.endswith(endpoint) or response.request.method != "POST":
                    return False
                return predicate(response) if predicate else True

            first_speech = speak_count()
            log_from = log_length()
            with page.expect_response(matches, timeout=20_000) as answered:
                act(label, run)
            return {"label": label, "data": answered.value.json(), "firstSpeech": first_speech,
                    "logFrom": log_from, "utterances": utterances,
                    "timelineAction": actions[-1]["at"]}

        def finish_voiced(turn: dict[str, object], deadline: float) -> None:
            """Wait for the last sentence of a voiced turn to end, inside its window."""
            last = int(turn["firstSpeech"]) + int(turn["utterances"]) - 1
            page.wait_for_function(
                """(last) => window.__volcanCaptureLog.some(e =>
                     (e.kind === 'speech.end' || e.kind === 'speech.error') && e.detail.index === last)""",
                arg=last, timeout=max(0.5, deadline - now()) * 1000,
            )
            actions.append({"at": round(now(), 3), "action": f"{turn['label']}: speech ended"})
            voiced.append(turn)

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

        def is_press(response) -> bool:
            return '"engine"' not in (response.request.post_data or "")

        # Beat 1: the first viewport, the keyboard press, then the product's own sound.
        until(sentence("beat_01_press", 2, 0.6))
        act("Alt+1 focuses Hear this code review", lambda: page.keyboard.press("Alt+1"))
        until(window_opens("beat_01_press"))
        press = start_turn("Enter presses Hear this code review", lambda: page.keyboard.press("Enter"),
                           "/api/digest_semantic_diff", 1, is_press)
        page.wait_for_function(
            "window.__volcanCaptureLog.some(e => e.kind === 'speech.start')", timeout=10_000)
        act("scroll so the earcon, the sentence and the Braille share the frame",
            lambda: scroll_to(".r-earcon", 16))
        finish_voiced(press, beat_start("beat_02_what_you_heard"))

        # Beat 2: what was heard, and why the local engine answered.
        until(sentence("beat_02_what_you_heard", 3))
        act("open why this engine answered", lambda: page.click("#meterEngineWhy"))

        # Beat 3: a real public pull request, opened by keyboard, then Findings, voiced.
        until(beat_start("beat_03_open_pull_request"))
        act("scroll to Talk through a real pull request", lambda: scroll_to("#review", 8))
        until(sentence("beat_03_open_pull_request", 1))
        act("Alt+6 focuses the pull request URL box", lambda: page.keyboard.press("Alt+6"))
        act("type the pull request URL", lambda: page.keyboard.type(
            os.environ.get("VOLCAN_PR_URL", PULL_REQUEST_URL), delay=30))
        before = turns()
        opened = start_turn("Enter opens the pull request", lambda: page.keyboard.press("Enter"),
                            "/api/review/turn", 2)
        answered(before)
        if "Opened octocat/Hello-World pull request 1" not in page.inner_text("#dialogueLog"):
            raise SystemExit("the dialogue did not open the pull request")
        until(sentence("beat_03_open_pull_request", 2))
        act("scroll to the dialogue and the outlined next steps",
            lambda: scroll_to("#reviewConvo", 12))
        outlined = page.evaluate("[...document.querySelectorAll('button.suggested')].map(b => b.id)")
        if "cmdFindings" not in outlined:
            raise SystemExit(f"Findings is not an outlined next step: {outlined}")
        until(window_opens("beat_03_open_pull_request"))
        before = turns()
        findings = start_turn("Findings", lambda: page.click("#cmdFindings"), "/api/review/turn", 2)
        unvoiced.append({"turn": opened, "interruptedBy": "Findings", "cutAt": findings["logFrom"]})
        answered(before)
        finish_voiced(findings, beat_start("beat_04_request_changes"))

        # Beat 4: request changes while the narrator speaks, then Confirm, voiced.
        until(beat_start("beat_04_request_changes"))
        act("type the review comment", lambda: (page.click("#reviewComment"),
                                                 page.keyboard.type(REVIEW_COMMENT, delay=12)))
        before = turns()
        staged = start_turn("Request changes", lambda: page.click("#cmdRequestChanges"), "/api/review/turn", 2)
        answered(before)
        outlined = page.evaluate("[...document.querySelectorAll('button.suggested')].map(b => b.id)")
        if "cmdConfirm" not in outlined:
            raise SystemExit(f"Confirm is not an outlined next step: {outlined}")
        until(window_opens("beat_04_request_changes"))
        before = turns()
        confirm = start_turn("Confirm", lambda: page.click("#cmdConfirm"), "/api/review/turn", 2)
        unvoiced.append({"turn": staged, "interruptedBy": "Confirm", "cutAt": confirm["logFrom"]})
        answered(before)
        if "recorded and not sent" not in page.inner_text("#reviewPane"):
            raise SystemExit("the review pane does not show a recorded, unsent review")
        until(window_opens("beat_04_request_changes") + 0.5 * float(by_id["beat_04_request_changes"]["productSoundSeconds"]))
        act("scroll to the recorded request", lambda: scroll_to("#reviewPane", 150))
        finish_voiced(confirm, beat_start("beat_05_mcp_handshake"))

        # Beat 5: a real MCP handshake.
        until(beat_start("beat_05_mcp_handshake"))
        act("scroll to Evidence", lambda: scroll_to("#evidence"))
        until(sentence("beat_05_mcp_handshake", 1))
        act("Run a real MCP handshake", lambda: page.click("#runMcp"))
        page.wait_for_selector("#mcpPane details", timeout=10_000)
        act("scroll to the handshake facts", lambda: scroll_to("#mcp .row-actions", 24))
        until(sentence("beat_05_mcp_handshake", 1, 0.62))
        act("expand the first tool", lambda: page.click("#mcpPane details summary"))
        act("scroll to its schema", lambda: scroll_to("#mcpPane", 90))

        # Beat 6: the counts, the Alexa+ replay, the honest boundary, then the heading.
        until(beat_start("beat_06_verification"))
        act("Server and MCP tab", lambda: page.click("#tabServer"))
        act("jump to the connection strip", lambda: scroll_to("#evidenceTabs", 24, "instant"))
        until(sentence("beat_06_verification", 1))
        # The replay section ends the tab, so the page cannot scroll it to the top
        # until its results have made the page taller: press, wait, then scroll.
        act("jump to the Alexa+ replay", lambda: scroll_to("#alexaReplay", 24, "instant"))
        page.wait_for_timeout(400)
        act("Replay the documented Alexa+ requests", lambda: page.click("#runReplay"))
        page.wait_for_function(
            "/of 3 clients served/.test(document.querySelector('#replayPane').textContent)", timeout=10_000)
        if "3 of 3 clients served" not in page.inner_text("#replayPane"):
            raise SystemExit("the Alexa+ replay did not serve all three clients")
        act("scroll to the replay results", lambda: scroll_to("#alexaReplay", 24))
        until(sentence("beat_06_verification", 2))
        act("jump to the connection strip and the Alexa+ box",
            lambda: scroll_to("#evidenceTabs", 24, "instant"))
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

    def speech_events(index: int) -> dict[str, dict[str, object]]:
        found: dict[str, dict[str, object]] = {}
        for entry in log:
            detail = entry["detail"]
            if isinstance(detail, dict) and detail.get("index") == index and entry["kind"].startswith("speech."):
                found.setdefault(entry["kind"], entry)
        return found

    def turn_earcon(turn: dict[str, object]) -> dict[str, object] | None:
        """Where the page's own playback clock says this turn's cue started.

        Each timeupdate reports how far into the WAV the element is, so its wall time
        minus that position is the start. Headless Chromium fires "playing" a few
        hundred milliseconds before the clock moves, and the waveform's playhead
        follows the clock, so this is the moment the picture shows the cue sounding."""
        entries = log[int(turn["logFrom"]):]
        play = next((entry for entry in entries if entry["kind"] == "media.play"), None)
        if play is None:
            return None
        ident = play["detail"]["id"]
        ended = next((entry for entry in entries if entry["kind"] == "media.ended"
                      and entry["detail"]["id"] == ident and entry["epoch"] >= play["epoch"]), None)
        if ended is None:
            raise SystemExit(f"{turn['label']}: the page never finished playing its cue")
        clock_starts = sorted(
            entry["epoch"] - float(entry["detail"]["at"]) * 1000
            for entry in entries
            if entry["kind"] == "media.timeupdate" and entry["detail"]["id"] == ident
            and play["epoch"] <= entry["epoch"] <= ended["epoch"]
            and 0 < float(entry["detail"]["at"] or 0) < float(ended["detail"]["at"])
        )
        if clock_starts:
            start = clock_starts[len(clock_starts) // 2]
            basis = f"median of {len(clock_starts)} timeupdate events, wall time minus currentTime"
        else:
            start = ended["epoch"] - float(ended["detail"]["at"]) * 1000
            basis = "ended event minus the WAV length reported by currentTime"
        return {"epoch": start, "basis": basis, "ended": ended["epoch"]}

    def expected_sentences(turn: dict[str, object]) -> list[str]:
        data = turn["data"]
        if "voice_summary_for_speech" in data:
            return [data["voice_summary_for_speech"]]
        pairs = [(data.get("readback"), data.get("readback_for_speech")),
                 (data.get("spoken"), data.get("spoken_for_speech"))]
        return [said or text for text, said in pairs if text]

    def render_voice(text: str, stem: str) -> pathlib.Path:
        text_file = capture / f"{stem}.txt"
        text_file.write_text(text, encoding="utf-8")
        wav = capture / f"{stem}.wav"
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
             "-TextFile", str(text_file), "-OutWav", str(wav), "-Voice", voice],
            check=True, capture_output=True, text=True,
        )
        return wav

    script = capture / "render-system-voice.ps1"
    script.write_text(SAPI, encoding="utf-8")
    product_audio: list[dict[str, object]] = []
    beat_ids = [scene["id"] for scene in scenes]
    for number, turn in enumerate(voiced, start=1):
        slug = re.sub(r"[^a-z0-9]+", "-", str(turn["label"]).lower()).strip("-")[:24]
        start_timeline = float(turn["timelineAction"])
        beat = next(beat for beat in reversed(beat_ids) if beat_start(beat) <= start_timeline)
        closes = beat_end(beat)
        sentences = expected_sentences(turn)
        if len(sentences) != int(turn["utterances"]):
            raise SystemExit(f"{turn['label']}: expected {turn['utterances']} sentences, the server returned {len(sentences)}")
        earcon = turn_earcon(turn)
        data = turn["data"]
        if earcon is not None:
            if not (data.get("earcon") or {}).get("wav_base64"):
                raise SystemExit(f"{turn['label']}: the page played a cue the response did not carry")
            wav = capture / f"earcon-{number}-{slug}.wav"
            wav.write_bytes(base64.b64decode(data["earcon"]["wav_base64"]))
            product_audio.append({
                "kind": "earcon", "turn": turn["label"], "beat": beat, "file": wav.name,
                "earconType": data["earcon"].get("type"),
                "sha256": sha256(wav), "seconds": round(probe_duration(wav), 3),
                "source": "the earcon.wav_base64 bytes of the server's response to this turn, unchanged",
                "timelineSeconds": timeline_time(earcon["epoch"]),
                "timelineBasis": earcon["basis"],
                "pageEndedTimelineSeconds": timeline_time(earcon["ended"]),
            })
        for offset, expected in enumerate(sentences):
            index = int(turn["firstSpeech"]) + offset
            events = speech_events(index)
            if "speech.error" in events:
                raise SystemExit(f"{turn['label']}: sentence {offset + 1} was interrupted "
                                 f"({events['speech.error']['detail'].get('error')}); record again")
            if not {"speech.speak", "speech.start", "speech.end"} <= set(events):
                raise SystemExit(f"{turn['label']}: sentence {offset + 1} has no start and end events")
            text = events["speech.speak"]["detail"]["text"]
            if text != expected:
                raise SystemExit(f"{turn['label']}: the page spoke a sentence other than the one the server returned")
            ended_at = timeline_time(events["speech.end"]["epoch"])
            if ended_at > closes:
                raise SystemExit(f"{turn['label']}: the browser was still speaking when the next beat began")
            wav = render_voice(text, f"speech-{number}-{offset + 1}-{slug}")
            product_audio.append({
                "kind": "speech", "turn": turn["label"], "beat": beat, "file": wav.name,
                "sha256": sha256(wav), "seconds": round(probe_duration(wav), 3),
                "text": text,
                "pageRate": events["speech.speak"]["detail"]["rate"],
                "browserDefaultVoice": default_voice,
                "renderedWith": f"Windows System.Speech, voice {voice}, rate 0",
                "source": "the exact text the page passed to speechSynthesis.speak, rendered again because headless capture records no audio",
                "timelineSeconds": timeline_time(events["speech.start"]["epoch"]),
                "pageEndedTimelineSeconds": ended_at,
            })

    # The turns the narrator talks over: from the page's first sound for the turn
    # until the next command's cancel, which is where the page stopped speaking.
    unrecorded: list[dict[str, object]] = []
    for item in unvoiced:
        turn = item["turn"]
        entries = log[int(turn["logFrom"]):int(item["cutAt"])]
        sounds = [entry["epoch"] for entry in entries
                  if entry["kind"] in ("media.playing", "speech.start")]
        if not sounds:
            raise SystemExit(f"{turn['label']}: the page made no sound for the turn")
        cut_entries = log[int(item["cutAt"]):]
        stops = [entry["epoch"] for entry in cut_entries if entry["kind"] == "speech.cancel"]
        ends = [entry["epoch"] for entry in log[int(turn["logFrom"]):]
                if entry["kind"] in ("speech.end", "speech.error")
                and isinstance(entry["detail"], dict)
                and entry["detail"].get("index") == int(turn["firstSpeech"]) + int(turn["utterances"]) - 1]
        until_epoch = min([*stops[:1], *ends[:1]]) if (stops or ends) else None
        if until_epoch is None:
            raise SystemExit(f"{turn['label']}: could not tell when the page stopped speaking")
        unrecorded.append({
            "turn": turn["label"],
            "fromTimelineSeconds": timeline_time(min(sounds)),
            "toTimelineSeconds": timeline_time(until_epoch),
            "stoppedBy": item["interruptedBy"],
            "sentences": expected_sentences(turn),
        })

    blanks = blank_stretches(final, capture, trim_lead, trim_lead + total * scale)
    if blanks:
        raise SystemExit(f"the recording shows a blank page at video seconds {blanks}; record again")

    recorded = probe_duration(final)
    if recorded < trim_lead + total * scale:
        raise SystemExit(f"the recording is {recorded:.3f}s, shorter than {trim_lead + total * scale:.3f}s")
    receipt = {
        "schemaVersion": "volcan.video-capture/v2",
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
            "synthesisMode": press["data"].get("synthesis_mode"),
            "fallbackReason": press["data"].get("synthesis_fallback_reason"),
            "earconType": press["data"]["earcon"].get("type"),
            "sentenceOnScreen": press["data"].get("voice_summary"),
        },
        "productAudio": product_audio,
        "unrecordedProductVoice": unrecorded,
        "blankStretches": blanks,
        "pageErrors": errors,
        "bytes": final.stat().st_size,
        "sha256": sha256(final),
    }
    (capture / "capture-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: receipt[key] for key in ("trimLeadSeconds", "recordedSeconds", "markers")}))
    for item in product_audio:
        print(item["kind"], item["turn"], item["timelineSeconds"], "to", item["pageEndedTimelineSeconds"],
              "rendered", item["seconds"])
    for item in unrecorded:
        print("not recorded:", item["turn"], item["fromTimelineSeconds"], "to", item["toTimelineSeconds"])


if __name__ == "__main__":
    main()
