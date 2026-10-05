#!/usr/bin/env python3
"""Record the Volcan journey from a running server, one beat per measured window.

This is the capture step of the submission kit's video pipeline, rewritten in Python
Playwright because the kit's Node capture drives a deployed site from CI. The pacing
rule is the kit's: each beat holds for exactly the window video/generate-narration.py
measured, and the timeline starts only after the page has drawn the server's answer.

The journey is the re-take in video/SHOT_LIST.md, recorded on the live build with
Amazon Bedrock answering. The six-beat journey of the 2026-09-29 take is in history:
git show fc10e7d:video/capture-local.py.

Billed presses. Two actions in this journey call Amazon Bedrock on the live build:
opening the pull request (before the cold open, off camera) and Hear this code review
(beat 2). Without --allow-billed-presses the script checks /health and the beats,
prints the presses the take would bill, and exits before it opens a browser. With the
flag, a request guard lets exactly those two calls through, one each when the script
makes that press, and aborts any other request that would reach a model, so the take
fails rather than bills more. Replay the documented Alexa+ requests (three calls) is
never pressed.

What it records and what it refuses to do:

* Every state on screen is the page reacting to a real response from the running
  server. The script presses keys and buttons and scrolls; it never writes into the
  page's DOM and never answers a request itself. Before each key press it checks which
  element has the focus.
* An init script observes, and only observes, when the page starts each earcon and
  each utterance it hands to the browser's speech engine, and when it cancels speech.
  Those timestamps place the product's own sound in the mix.
* The cold open fills the title slot: cards.title_seconds of narration.json, before the
  first beat, on timeline seconds from minus that length to 0. The pull request was
  opened before it, and its spoken answer has ended before the first frame. Within
  0.5 s the cold-open command (Findings, or File by file with VOLCAN_COLD_OPEN=files)
  is pressed, and the turn must make its first sound by 2.0 s and speak its first word
  by 5.0 s.
* Four turns are voiced: the cold-open command, the press of Hear this code review,
  Request changes and Confirm. For each, the earcon mixed into the video is the WAV the
  server returned for that turn, byte for byte, and every sentence is the exact text
  the page handed to speechSynthesis, rendered again with the Windows system voice of
  the same name, because headless Chromium records no audio. The build captions them
  as the product's voice. No turn on camera is talked over.
* Two marker pages, one before and one after the journey, turn from white to black
  at a logged wall-clock time. Finding those two frames in the recording maps page
  time to video time, so the product's sound lands on the frame where the page made
  it, and any drift across the take is measured rather than assumed.
* The take fails if /health reports another commit, a model path that is not ready,
  or a GitHub review path other than a dry run without a token; if the beats differ
  from this journey; if the press is not answered by Amazon Bedrock, carries a fallback
  reason, or makes its first sound while the narrator is still speaking; if Findings
  answers that there is no finding; if a voiced turn's speech has not ended inside its
  window or was interrupted; if the page logs an error; if the review dialogue refuses
  a turn; if a request would bill a model call the take did not plan; if the picture
  goes flat for 0.75 s; or if the recording is shorter than the cold open and the
  narration.

Environment:
  VOLCAN_VIDEO_ROOT    media root, outside git (reads narration/, writes capture/)
  VOLCAN_RELEASE_SHA   the 40 character commit /health reports as source_revision
  VOLCAN_APP_URL       default http://127.0.0.1:8801/; the live build for this take
  VOLCAN_PR_URL        required: the public pull request chosen in rehearsal
  VOLCAN_COLD_OPEN     findings (default) or files: the cold-open command
  FFMPEG               path to ffmpeg, for finding the marker frames
  VOLCAN_SPEECH_VOICE  default "Microsoft David Desktop", the System.Speech voice

Usage:
  python video/capture-local.py                          checks only, presses nothing billed
  python video/capture-local.py --allow-billed-presses   records the take: two Bedrock calls
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
import sys
import time
import urllib.parse
import urllib.request

SPEC = pathlib.Path(__file__).with_name("narration.json")
EXPECTED_BEATS = [
    "beat_01_alexa_value",
    "beat_02_bedrock_press",
    "beat_03_model_coverage",
    "beat_04_request_changes",
    "beat_05_confirm",
    "beat_06_mcp_handshake",
]
VIEWPORT = {"width": 1280, "height": 720}
REVIEW_COMMENT = "Volcan demo: a dry-run request changes review, recorded and not sent."
BILLED_FLAG = "--allow-billed-presses"
# The presses this take is allowed to bill, in order, one model call each.
BILLED_PRESSES = (
    ("open_pull_request", "opening the pull request, before the cold open, off camera"),
    ("digest", "Hear this code review, at the start of beat 2"),
)
COLD_OPEN_COMMANDS = {
    "findings": ("#cmdFindings", "Findings", "cmdFindings"),
    "files": ("#cmdFiles", "File by file", "cmdFiles"),
}
NO_FINDING = "No security finding in this change."
COLD_OPEN_FIRST_SOUND_SECONDS = 2.0
COLD_OPEN_FIRST_WORD_SECONDS = 5.0
# A Bedrock call can take up to its 25 s timeout before the server falls back, and
# one live digest took 19.67 s on 2026-10-01; the page waits longer than both.
BILLED_TURN_TIMEOUT_SECONDS = 60.0


def check_beats(scene_ids: list[str]) -> None:
    """The measured narration must be this journey's beats, in this order."""
    if list(scene_ids) != EXPECTED_BEATS:
        raise SystemExit(
            "the narration beats and this journey differ; update both together. "
            f"narration: {list(scene_ids)}; journey: {EXPECTED_BEATS}")


def check_title_slot(cards: dict[str, object]) -> float:
    """This journey records the cold open into the title slot, so the spec must say so."""
    slot = str(cards.get("title_slot", ""))
    if not slot.startswith("cold_open"):
        raise SystemExit("narration.json cards.title_slot does not name the cold open; "
                         "this journey records the cold open into the title slot")
    seconds = float(cards.get("title_seconds", 0))
    if not 3.0 <= seconds <= 20.0:
        raise SystemExit(f"cards.title_seconds is {seconds}; the cold open needs 3 to 20 s")
    return seconds


def billed_presses_allowed(argv: list[str]) -> bool:
    """Billed presses happen only when the owner passes the flag. The default is off."""
    return BILLED_FLAG in argv


def billed_plan() -> str:
    lines = [f"This take bills {len(BILLED_PRESSES)} Amazon Bedrock calls on the server:"]
    lines += [f"  {number}. {label}" for number, (_, label) in enumerate(BILLED_PRESSES, start=1)]
    lines.append(f"Nothing was pressed. Run again with {BILLED_FLAG} once the owner has authorised them.")
    return "\n".join(lines)


def check_health(health: dict[str, object], release_sha: str) -> None:
    """Refuse a server that is not the recorded commit, or that cannot do what the beats say."""
    if health.get("source_revision") != release_sha:
        raise SystemExit("the server reports a different commit than VOLCAN_RELEASE_SHA; restart it")
    model = (health.get("bedrock_model_path") or {}).get("resolved_capability")
    if model != "ready_to_attempt":
        raise SystemExit(f"/health reports bedrock_model_path {model!r}; beat 2 needs ready_to_attempt")
    durable = (health.get("durable_state") or {}).get("resolved_capability")
    if durable != "configured_reachable":
        raise SystemExit(f"/health reports durable_state {durable!r}; beat 2 says the review state is "
                         "in Amazon DynamoDB, so it needs configured_reachable")
    review = (health.get("github_review_path") or {}).get("resolved_capability")
    if review != "dry_run_no_token":
        raise SystemExit(f"/health reports github_review_path {review!r}; beat 5 says the build has "
                         "no GitHub token, so it needs dry_run_no_token")


def pull_request_label(url: str) -> str:
    """The words the dialogue uses for a GitHub pull request URL."""
    found = re.fullmatch(r"https://github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)/?", url.strip())
    if not found:
        raise SystemExit("VOLCAN_PR_URL must be https://github.com/<owner>/<repo>/pull/<number>")
    owner, repo, number = found.groups()
    return f"{owner}/{repo} pull request {number}"


def cold_open_command(value: str | None) -> tuple[str, str, str]:
    key = (value or "findings").strip().lower()
    if key not in COLD_OPEN_COMMANDS:
        raise SystemExit("VOLCAN_COLD_OPEN must be findings or files")
    return COLD_OPEN_COMMANDS[key]


def billed_kind(url: str, method: str, body: str | None) -> str | None:
    """Which model call a request would bill, or None when it calls no model.

    The digest asks the default engine unless the body names one (the silent preview
    asks for "local"). Opening a pull request in the dialogue digests it with the
    default engine. A tools/call on POST /mcp may run digest_semantic_diff, which is
    how the Alexa+ replay bills three calls."""
    if method.upper() != "POST":
        return None
    path = urllib.parse.urlparse(url).path.rstrip("/")
    text = body or ""
    if path.endswith("/api/digest_semantic_diff"):
        return None if '"engine"' in text else "digest"
    if path.endswith("/api/review/turn"):
        try:
            data = json.loads(text)
        except ValueError:
            return "open_pull_request"
        transcript = str(data.get("transcript") or "").strip().lower()
        if re.match(r"^open\b", transcript) and data.get("pr_url"):
            return "open_pull_request"
        return None
    if path.endswith("/mcp") and '"tools/call"' in text:
        return "mcp_tools_call"
    return None


def cold_open_gate(first_sound: float | None, first_word: float | None) -> None:
    """Seconds from the cold open's first frame to its first sound and first word."""
    if first_sound is None or first_sound > COLD_OPEN_FIRST_SOUND_SECONDS:
        raise SystemExit(f"the cold open made its first sound at {first_sound} s; "
                         f"the plan needs it by {COLD_OPEN_FIRST_SOUND_SECONDS} s. Record again")
    if first_word is None or first_word > COLD_OPEN_FIRST_WORD_SECONDS:
        raise SystemExit(f"the cold open spoke its first word at {first_word} s; "
                         f"the plan needs it by {COLD_OPEN_FIRST_WORD_SECONDS} s. Record again")


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
    allow_billed = billed_presses_allowed(sys.argv[1:])
    root = pathlib.Path(env("VOLCAN_VIDEO_ROOT"))
    release_sha = env("VOLCAN_RELEASE_SHA")
    if not re.fullmatch(r"[0-9a-f]{40}", release_sha):
        raise SystemExit("VOLCAN_RELEASE_SHA must be a full 40 character commit")
    app_url = os.environ.get("VOLCAN_APP_URL", "http://127.0.0.1:8801/").strip()
    pr_url = env("VOLCAN_PR_URL")
    pr_label = pull_request_label(pr_url)
    cold_selector, cold_label, cold_id = cold_open_command(os.environ.get("VOLCAN_COLD_OPEN"))
    voice = os.environ.get("VOLCAN_SPEECH_VOICE", "Microsoft David Desktop").strip()
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    cold_seconds = check_title_slot(spec.get("cards") or {})
    timing = json.loads((root / "narration" / "timing.json").read_text(encoding="utf-8"))
    scenes = timing["scenes"]
    check_beats([scene["id"] for scene in scenes])
    by_id = {scene["id"]: scene for scene in scenes}
    total = float(timing["totalSeconds"])

    with urllib.request.urlopen(app_url.rstrip("/") + "/health", timeout=10) as response:
        health = json.load(response)
    check_health(health, release_sha)
    if not allow_billed:
        raise SystemExit(billed_plan())

    from playwright.sync_api import sync_playwright

    capture = root / "capture"
    if capture.exists():
        shutil.rmtree(capture)
    (capture / "raw").mkdir(parents=True)

    actions: list[dict[str, object]] = []
    errors: list[str] = []
    voiced: list[dict[str, object]] = []
    # One model call per planned press, armed just before the script makes it.
    armed = {kind: 0 for kind, _ in BILLED_PRESSES}
    billed: list[dict[str, object]] = []
    refused: list[dict[str, object]] = []

    def guard(route, request) -> None:
        kind = billed_kind(request.url, request.method, request.post_data)
        if kind is None:
            route.continue_()
        elif armed.get(kind, 0) > 0:
            armed[kind] -= 1
            billed.append({"kind": kind, "url": request.url})
            route.continue_()
        else:
            refused.append({"kind": kind, "url": request.url})
            route.abort()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--force-device-scale-factor=1"])
        context = browser.new_context(
            viewport=VIEWPORT,
            device_scale_factor=1,
            record_video_dir=str(capture / "raw"),
            record_video_size=VIEWPORT,
        )
        context.add_init_script(OBSERVER)
        context.route("**/*", guard)
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

        clock: dict[str, float] = {}

        def now() -> float:
            """Timeline seconds: the cold open runs from -cold_seconds to 0, beat 1 starts at 0."""
            return time.monotonic() - clock["origin"] - cold_seconds

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

        def narrator_stops(beat: str) -> float:
            return beat_start(beat) + float(by_id[beat]["durationSeconds"])

        def window_opens(beat: str) -> float:
            """Where the narrator stops and the beat's product sound window begins."""
            return narrator_stops(beat) + float(timing["tailSeconds"])

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

        def focused() -> str | None:
            return page.evaluate("document.activeElement ? document.activeElement.id || null : null")

        def press_key(key: str, focus: str, label: str) -> None:
            """A key press goes only to the element the journey means it for."""
            found = focused()
            if found != focus:
                raise SystemExit(f"{label}: the focus is on {found!r}, not #{focus}; nothing was pressed")
            page.keyboard.press(key)

        def wait_speech_end(last: int, timeout_seconds: float) -> None:
            page.wait_for_function(
                """(last) => window.__volcanCaptureLog.some(e =>
                     (e.kind === 'speech.end' || e.kind === 'speech.error') && e.detail.index === last)""",
                arg=last, timeout=max(0.5, timeout_seconds) * 1000,
            )

        def start_turn(label: str, run, endpoint: str, utterances: int, predicate=None,
                       timeout_seconds: float = 20.0, timeline: bool = True) -> dict[str, object]:
            """Press, and keep the server's response: its earcon bytes are what the mix plays."""
            def matches(response) -> bool:
                if not response.url.endswith(endpoint) or response.request.method != "POST":
                    return False
                return predicate(response) if predicate else True

            first_speech = speak_count()
            log_from = log_length()
            with page.expect_response(matches, timeout=timeout_seconds * 1000) as answered_turn:
                if timeline:
                    act(label, run)
                else:
                    run()
            return {"label": label, "data": answered_turn.value.json(), "firstSpeech": first_speech,
                    "logFrom": log_from, "utterances": utterances,
                    "timelineAction": actions[-1]["at"] if timeline else None}

        def finish_voiced(turn: dict[str, object], deadline: float) -> None:
            """Wait for the last sentence of a voiced turn to end, inside its window."""
            wait_speech_end(int(turn["firstSpeech"]) + int(turn["utterances"]) - 1, deadline - now())
            actions.append({"at": round(now(), 3), "action": f"{turn['label']}: speech ended"})
            voiced.append(turn)

        def settled(timeout_seconds: float = 20.0) -> None:
            """Wait until the review dialogue has answered the last turn."""
            page.wait_for_timeout(250)
            page.wait_for_function(
                "document.querySelector('#reviewConvo').getAttribute('aria-busy') === 'false'",
                timeout=timeout_seconds * 1000,
            )

        def turns() -> int:
            return page.evaluate("document.querySelectorAll('#dialogueLog li').length")

        def answered(turns_before: int, timeout_seconds: float = 20.0) -> None:
            settled(timeout_seconds)
            if turns() <= turns_before:
                raise SystemExit("the review dialogue did not answer the turn")
            rejected = page.evaluate(
                "[...document.querySelectorAll('#dialogueLog li')].some(li => li.textContent.startsWith('Not sent'))")
            if rejected:
                raise SystemExit("the page refused a turn because the last one was still in flight")

        def outlined() -> list[str]:
            return page.evaluate("[...document.querySelectorAll('button.suggested')].map(b => b.id)")

        def is_press(response) -> bool:
            return '"engine"' not in (response.request.post_data or "")

        b1, b2, b3, b4, b5, b6 = EXPECTED_BEATS

        # Off camera: open the chosen pull request. One billed model call. Its spoken
        # answer ends before the cold open's first frame, so nothing on camera cuts it.
        scroll_to("#review", 8, "instant")
        page.keyboard.press("Alt+6")
        if focused() != "prUrl":
            raise SystemExit(f"Alt+6 put the focus on {focused()!r}, not the pull request URL box")
        page.keyboard.type(pr_url, delay=0)
        before = turns()
        armed["open_pull_request"] = 1
        opened = start_turn("Enter opens the pull request",
                            lambda: press_key("Enter", "prUrl", "open the pull request"),
                            "/api/review/turn", 2, timeout_seconds=BILLED_TURN_TIMEOUT_SECONDS,
                            timeline=False)
        answered(before, BILLED_TURN_TIMEOUT_SECONDS)
        if f"Opened {pr_label}" not in page.inner_text("#dialogueLog"):
            raise SystemExit(f"the dialogue did not open {pr_label}")
        wait_speech_end(int(opened["firstSpeech"]) + 1, BILLED_TURN_TIMEOUT_SECONDS)
        if cold_id not in outlined():
            raise SystemExit(f"{cold_label} is not an outlined next step: {outlined()}")
        scroll_to("#reviewConvo", 12, "instant")
        page.wait_for_timeout(1500)

        # Cold open, in the title slot: the first frame is the opened overview.
        clock["origin"] = time.monotonic()
        cold_epoch = page_epoch()
        timeline_epoch = cold_epoch + cold_seconds * 1000
        until(-cold_seconds + 0.3)
        before = turns()
        cold = start_turn(cold_label, lambda: page.click(cold_selector), "/api/review/turn", 2)
        answered(before)
        if cold_label == "Findings" and str(cold["data"].get("spoken") or "").strip() == NO_FINDING:
            raise SystemExit("Findings answered that there is no finding; the plan keeps that turn off "
                             "camera. Choose another pull request or set VOLCAN_COLD_OPEN=files")
        finish_voiced(cold, 0.0)

        # Beat 1: the Alexa+ value over the top of the page, then the focus ring.
        until(beat_start(b1))
        act("scroll to the top of the page", lambda: page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})"))
        until(sentence(b1, len(by_id[b1]["sentences"]) - 1, 0.6))
        act("Alt+1 focuses Hear this code review", lambda: page.keyboard.press("Alt+1"))
        if focused() != "runReview":
            raise SystemExit(f"Alt+1 put the focus on {focused()!r}, not Hear this code review")

        # Beat 2: press at the first frame; the narrator covers the model wait. One billed call.
        until(beat_start(b2))
        armed["digest"] = 1
        press = start_turn("Enter presses Hear this code review",
                           lambda: press_key("Enter", "runReview", "Hear this code review"),
                           "/api/digest_semantic_diff", 1, is_press,
                           timeout_seconds=BILLED_TURN_TIMEOUT_SECONDS)
        if press["data"].get("synthesis_mode") != "bedrock" or press["data"].get("synthesis_fallback_reason"):
            raise SystemExit("the press was not answered by Amazon Bedrock: synthesis_mode "
                             f"{press['data'].get('synthesis_mode')!r}, fallback reason "
                             f"{press['data'].get('synthesis_fallback_reason')!r}; record again")
        page.wait_for_function(
            "(from) => window.__volcanCaptureLog.slice(from).some(e => e.kind === 'speech.start')",
            arg=press["logFrom"], timeout=max(0.5, beat_start(b3) - now()) * 1000)
        act("scroll so the earcon, the sentence and the Braille share the frame",
            lambda: scroll_to(".r-earcon", 16))
        finish_voiced(press, beat_start(b3))

        # Beat 3: the meter, the coverage line as printed, and the model's full answer.
        until(beat_start(b3))
        if not page.inner_text("#meterEngine").strip().startswith("Amazon Bedrock"):
            raise SystemExit("the engine meter does not read Amazon Bedrock")
        if not page.inner_text("#modelCoverage").strip().startswith("The model read"):
            raise SystemExit("the page printed no model coverage line")
        act("scroll to the engine meter", lambda: scroll_to("#meters", 120))
        until(sentence(b3, 0, 0.35))
        act("scroll to the coverage line", lambda: scroll_to("#modelCoverage", 260))
        until(sentence(b3, 0, 0.7))
        act("open The model's full answer", lambda: page.click("#modelProseWrap summary"))
        act("scroll to the model's full answer", lambda: scroll_to("#modelProseWrap", 80))

        # Beat 4: back on the pull request; Request changes after the narrator, voiced.
        until(beat_start(b4))
        act("scroll to Talk through a real pull request", lambda: scroll_to("#review", 8))
        until(sentence(b4, 0, 0.5))
        act("scroll to the dialogue and the comment box", lambda: scroll_to("#reviewConvo", 12))
        page.click("#reviewComment")
        if focused() != "reviewComment":
            raise SystemExit(f"the comment box did not take the focus: {focused()!r}")
        act("type the review comment", lambda: page.keyboard.type(REVIEW_COMMENT, delay=12))
        until(window_opens(b4))
        before = turns()
        staged = start_turn("Request changes", lambda: page.click("#cmdRequestChanges"), "/api/review/turn", 2)
        answered(before)
        if "cmdConfirm" not in outlined():
            raise SystemExit(f"Confirm is not an outlined next step: {outlined()}")
        finish_voiced(staged, beat_start(b5))

        # Beat 5: Confirm after the narrator, voiced; the review pane shows it unsent.
        until(window_opens(b5))
        before = turns()
        confirm = start_turn("Confirm", lambda: page.click("#cmdConfirm"), "/api/review/turn", 2)
        answered(before)
        if "recorded and not sent" not in page.inner_text("#reviewPane"):
            raise SystemExit("the review pane does not show a recorded, unsent review")
        until(window_opens(b5) + 0.5 * float(by_id[b5]["productSoundSeconds"]))
        act("scroll to the recorded request", lambda: scroll_to("#reviewPane", 150))
        finish_voiced(confirm, beat_start(b6))

        # Beat 6: Server and MCP, a real handshake, then the Alexa+ box. No replay press.
        until(beat_start(b6))
        act("Server and MCP tab", lambda: page.click("#tabServer"))
        act("scroll to Evidence", lambda: scroll_to("#evidence"))
        until(sentence(b6, 0, 0.3))
        act("scroll to the MCP handshake", lambda: scroll_to("#mcp", 16))
        act("Run a real MCP handshake", lambda: page.click("#runMcp"))
        page.wait_for_selector("#mcpPane details", timeout=10_000)
        act("scroll to the handshake facts", lambda: scroll_to("#mcp .row-actions", 24))
        until(sentence(b6, len(by_id[b6]["sentences"]) - 1))
        act("jump to the connection strip and the Alexa+ box",
            lambda: scroll_to("#evidenceTabs", 24, "instant"))
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
    if refused:
        raise SystemExit(f"the page asked for model calls the take did not plan, and they were aborted: {refused}")
    if [item["kind"] for item in billed] != [kind for kind, _ in BILLED_PRESSES]:
        raise SystemExit(f"the billed calls were {billed}, not the planned {[kind for kind, _ in BILLED_PRESSES]}")
    if errors:
        raise SystemExit("the page logged errors during the take: " + "; ".join(errors[:5]))

    flips = marker_times(final, capture)
    if len(flips) != 2:
        raise SystemExit(f"expected two marker flips in the recording, found {len(flips)}: {flips}")
    scale = (flips[1] - flips[0]) / ((end_marker - start_marker) / 1000)

    def video_time(epoch_ms: float) -> float:
        return flips[0] + (epoch_ms - start_marker) / 1000 * scale

    trim_lead = video_time(timeline_epoch)
    cold_trim_lead = video_time(cold_epoch)

    # Timeline times are page-clock seconds from the start of beat 1; the cold open's
    # are negative. The recording can run slower or faster than the page clock when
    # the machine is loaded; the build retimes it by videoPerPageSecond so both agree.
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

    def first_sound(turn: dict[str, object]) -> tuple[float | None, float | None]:
        """Page epochs of a turn's first sound (its cue, or its first word) and first word."""
        earcon = turn_earcon(turn)
        word = speech_events(int(turn["firstSpeech"])).get("speech.start")
        word_epoch = word["epoch"] if word else None
        candidates = [value for value in (earcon["epoch"] if earcon else None, word_epoch) if value is not None]
        return (min(candidates) if candidates else None), word_epoch

    cold_sound, cold_word = first_sound(cold)
    cold_open_gate(
        None if cold_sound is None else round((cold_sound - cold_epoch) / 1000, 3),
        None if cold_word is None else round((cold_word - cold_epoch) / 1000, 3),
    )
    press_sound, _ = first_sound(press)
    if press_sound is None or timeline_time(press_sound) < narrator_stops(b2):
        raise SystemExit("the model's answer began while the narrator was still speaking; record again")

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
        if start_timeline < 0:
            beat, closes = "cold_open", 0.0
        else:
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
                raise SystemExit(f"{turn['label']}: the browser was still speaking when the next segment began")
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

    blanks = blank_stretches(final, capture, cold_trim_lead, trim_lead + total * scale)
    if blanks:
        raise SystemExit(f"the recording shows a blank page at video seconds {blanks}; record again")

    recorded = probe_duration(final)
    if recorded < trim_lead + total * scale:
        raise SystemExit(f"the recording is {recorded:.3f}s, shorter than {trim_lead + total * scale:.3f}s")
    receipt = {
        "schemaVersion": "volcan.video-capture/v3",
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
        "pullRequest": {
            "url": pr_url,
            "label": pr_label,
            "opened": opened["data"].get("pull_request"),
            "openedSpoken": opened["data"].get("spoken"),
            "note": "opened before the cold open, off camera; this was a billed model call",
        },
        "billedCalls": billed,
        "coldOpen": {
            "seconds": cold_seconds,
            "command": cold_label,
            "trimLeadSeconds": round(cold_trim_lead, 3),
            "firstSoundSeconds": round((cold_sound - cold_epoch) / 1000, 3),
            "firstWordSeconds": round((cold_word - cold_epoch) / 1000, 3),
            "spoken": cold["data"].get("spoken"),
            "note": "timeline seconds from -seconds to 0; the build places this footage in the title slot",
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
            "earconType": (press["data"].get("earcon") or {}).get("type"),
            "sentenceOnScreen": press["data"].get("voice_summary"),
            "firstSoundTimelineSeconds": timeline_time(press_sound),
            "narratorStopsTimelineSeconds": round(narrator_stops(b2), 3),
        },
        "productAudio": product_audio,
        "unrecordedProductVoice": [],
        "blankStretches": blanks,
        "pageErrors": errors,
        "bytes": final.stat().st_size,
        "sha256": sha256(final),
    }
    (capture / "capture-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: receipt[key] for key in ("trimLeadSeconds", "recordedSeconds", "markers", "coldOpen")}))
    for item in product_audio:
        print(item["kind"], item["turn"], item["timelineSeconds"], "to", item["pageEndedTimelineSeconds"],
              "rendered", item["seconds"])


if __name__ == "__main__":
    main()
