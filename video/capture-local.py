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

Free rehearsal. With --rehearsal the script runs the same journey against a local
server whose /health says it cannot reach Amazon Bedrock, so the two presses are
answered by the local heuristic engine and nothing is billed. It refuses a URL that is
not a loopback address, a server that reports bedrock_model_path ready_to_attempt,
and --allow-billed-presses beside it. The request guard is armed exactly as for the
take, so an unplanned request still fails the rehearsal. It writes rehearsal/, never
capture/, and its receipt says "mode": "rehearsal" and "shippable": false; the build
refuses that receipt unless it too is run with --rehearsal. Each check that needs
Amazon Bedrock is listed under notRepresentative with what the local engine did,
instead of failing. Every other check that would fail the take after the journey is
collected under failures, so one run reports all of them, and the script exits 1 if
there are any. Without a measured narration/timing.json it uses a silent timing stub
built from the plan's ESTIMATE windows in narration.json, in rehearsal/narration-stub/.
The take and the rehearsal both press Hear this code review when beat 2's narrator
stops, after the generator's tail, so the answer can only start after the narration
however fast the model answers; the check that it did runs in both modes. Beat 2's
window holds an answer whose first sound comes within ANSWER_LATENCY_ALLOWANCE_SECONDS,
5.9 s, of the press; a later answer fails the take in both modes, so a slow answer means
a retake, never an answer that runs past the window.

What it records and what it refuses to do:

* Every state on screen is the page reacting to a real response from the running
  server. The script presses keys and buttons and scrolls; it never writes into the
  page's DOM and never answers a request itself. Before each key press it checks which
  element has the focus.
* An init script observes, and only observes, when the page starts each earcon and
  each utterance it hands to the browser's speech engine, and when it cancels speech.
  Those timestamps place the product's own sound in the mix.
* The cold open follows the title card: cold_open.seconds of narration.json, before the
  first beat, on timeline seconds from minus that length to 0. The pull request was
  opened before it, and its spoken answer has ended before the first frame. Within
  0.5 s the cold-open command is pressed: cold_open.command in narration.json, which
  VOLCAN_COLD_OPEN overrides. Findings, File by file and Summary are buttons; a
  command such as "line 26" is typed into the command box and sent with Enter. The turn must make its first sound by 2.0 s after the title card ends,
  and speak its first word by 5.0 s from the start of the video, so by 3.0 s into the
  cold open with the plan's 2.0 s card.
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
  reason, makes its first sound while the narrator is still speaking, or makes it more
  than 5.9 s after the press; if the coverage line is not the one the page prints for
  that answer, ending "Answered by <model_answered>."; if Findings
  answers that no security rule matched; if a voiced turn's speech has not ended inside its
  window or was interrupted; if the page logs an error; if the review dialogue refuses
  a turn; if a request would bill a model call the take did not plan; if the picture
  goes flat for 0.75 s; or if the recording is shorter than the cold open and the
  narration.

Environment:
  VOLCAN_VIDEO_ROOT    media root, outside git (reads narration/, writes capture/)
  VOLCAN_RELEASE_SHA   the 40 character commit /health reports as source_revision
  VOLCAN_APP_URL       default http://127.0.0.1:8801/; the live build for this take
  VOLCAN_PR_URL        required: the public pull request chosen in rehearsal
  VOLCAN_COLD_OPEN     findings, files, summary or "line N": the cold-open command,
                       overriding cold_open.command in narration.json (findings when
                       neither names one)
  FFMPEG               path to ffmpeg, for finding the marker frames
  VOLCAN_SPEECH_VOICE  default "Microsoft David Desktop", the System.Speech voice

Usage:
  python video/capture-local.py                          checks only, presses nothing billed
  python video/capture-local.py --allow-billed-presses   records the take: two Bedrock calls
  python video/capture-local.py --rehearsal              a free rehearsal on a local server
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
    "beat_06_recorded_request",
    "beat_07_mcp_handshake",
]
VIEWPORT = {"width": 1280, "height": 720}
# A real review comment about the inverted check. The readback and the staged answer
# both repeat it, so its length decides whether Request changes fits its window: on
# upgradedev/volcan-demo-service pull request 1 this comment took 25.28 to 25.45 s from
# the click to the browser's speech end, and the 69-character comment it replaces took
# 33.4 s. That the review is a dry run, recorded and not sent, is what Confirm answers
# on camera and what beat 6 says.
REVIEW_COMMENT = "is_admin is inverted."
BILLED_FLAG = "--allow-billed-presses"
REHEARSAL_FLAG = "--rehearsal"
# A rehearsal drives only a server on this machine.
REHEARSAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
TITLE_SLOT = "card_then_cold_open"
# The presses this take is allowed to bill, in order, one model call each.
BILLED_PRESSES = (
    ("open_pull_request", "opening the pull request, before the cold open, off camera"),
    ("digest", "Hear this code review, in beat 2 when the narrator stops"),
)
# Each cold-open command: the button's selector, its label, the button's id, and the
# words typed into the command box (Alt+4) for a typed command, or None for a button.
COLD_OPEN_COMMANDS = {
    "findings": ("#cmdFindings", "Findings", "cmdFindings", None),
    "files": ("#cmdFiles", "File by file", "cmdFiles", None),
    "summary": ("#cmdSummary", "Summary", "cmdSummary", None),
}
# A typed "line N" turn: the page reads new line N of the first changed file, the
# file the opened overview starts on. It reads the report already built and calls no
# model, and its words come from the parsed patch, so they are the same whichever
# engine digested the pull request.
COLD_OPEN_LINE = re.compile(r"line (\d{1,4})")
# The start of the page's answer when no rule matched (CLEAN_FINDINGS_TEXT in
# src/domain/review_dialogue.py). The plan keeps that turn off camera.
NO_FINDING_PREFIX = "No security rule matched this change."
# The cold open's first product sound, in seconds after the title card ends, and its
# first spoken word, in seconds from the start of the video.
COLD_OPEN_FIRST_SOUND_SECONDS = 2.0
VIDEO_FIRST_WORD_SECONDS = 5.0
NARRATION_TAIL_SECONDS = 0.65
# How long the script waits for a billed turn's response. It is not the beat 2 budget:
# a Bedrock call can run to its 25 s timeout before the server falls back, and the script
# waits longer than that so a slow answer is named as one instead of timing out.
BILLED_TURN_TIMEOUT_SECONDS = 60.0
# Beat 2's latency allowance (ESTIMATE): the answer's first sound, its earcon, must come
# within this many seconds of the planned press, where the window opens. On the live
# build of 716b0f3 at 1769 MB one press answered in 3.44 s at the client (Lambda 3071 ms,
# model 1266 ms); at 256 MB the same press took 17.88 s. The window is this allowance, the
# earcon's lead and the longest answer the page can speak at the slowest measured rate
# plus 1 s (video/SHOT_LIST.md). It was 10 s, which left about 7 s of silent page after a
# fast answer. 41.0 s is the longest window, on the half second, that leaves at most 5 s
# of silent page after the measured 3.44 s press with a full headline, and 5.9 s is what
# that window leaves for the answer to start, rounded down to a tenth. An answer that
# starts later could overrun the window, and the take is recorded again.
ANSWER_LATENCY_ALLOWANCE_SECONDS = 5.9
# The model the narration names: beat 3 says Claude on Amazon Bedrock answered.
CLAUDE_MODEL_PREFIX = "anthropic.claude"


def press_timeline_seconds(beat_start: float, narration_seconds: float, tail_seconds: float) -> float:
    """When beat 2 presses Hear this code review: once the narrator has stopped and the
    generator's tail has passed, in a take and in a rehearsal alike. The model call
    starts only then, so its answer, however fast, starts after the narration; the
    beat's product window, which starts here, holds an answer that starts within
    ANSWER_LATENCY_ALLOWANCE_SECONDS of it."""
    return beat_start + narration_seconds + tail_seconds


def answer_latency_problem(first_sound: float | None, window_opens: float,
                           allowance: float = ANSWER_LATENCY_ALLOWANCE_SECONDS) -> str | None:
    """Why beat 2's answer started too late for its window, or None.

    first_sound and window_opens are timeline seconds. The window is sized for an answer
    whose first sound comes within the allowance of the planned press; one that comes later
    may still be speaking when beat 3 begins, so the take is recorded again."""
    if first_sound is None:
        return "beat 2's answer made no sound; record again"
    late = round(first_sound - window_opens, 3)
    if late > allowance:
        return (f"beat 2's answer made its first sound {late} s after the press, past the "
                f"{allowance} s latency allowance its window is sized for; record again")
    return None


def expected_coverage_line(data: dict[str, object]) -> str | None:
    """The coverage line the page prints for this answer (renderModelProvenance in
    docs/index.html), or None when the answer names no model or not what it read."""
    model = data.get("model_answered")
    sent = data.get("model_input_chars_sent")
    total = data.get("model_input_chars_total")

    def number(value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool)

    if not isinstance(model, str) or not model or not number(total):
        return None
    if number(sent) and total > sent:
        read = (f"The model read the first {sent} of {total} patch characters; "
                "the local rules still read the whole patch.")
    else:
        read = f"The model read the whole {total}-character patch."
    return f"{read} Answered by {model}."


def coverage_line_problem(coverage: str, data: dict[str, object], health_model: object) -> str | None:
    """Why the coverage line on screen is not the one beat 3 talks about, or None. It must
    be exactly the line the page prints for this answer, naming a Claude model, the one
    /health reports."""
    model = data.get("model_answered")
    if not isinstance(model, str) or not model.startswith(CLAUDE_MODEL_PREFIX):
        return f"the answer names model_answered {model!r}, not a Claude model; beat 3 says Claude answered"
    if model != health_model:
        return f"the answer names {model!r}, but /health reports model_id {health_model!r}"
    expected = expected_coverage_line(data)
    if expected is None:
        return "the answer does not report how much of the patch the model read"
    if coverage != expected:
        return f"the coverage line reads {coverage[:200]!r}, not {expected!r}"
    return None


def check_beats(scene_ids: list[str]) -> None:
    """The measured narration must be this journey's beats, in this order."""
    if list(scene_ids) != EXPECTED_BEATS:
        raise SystemExit(
            "the narration beats and this journey differ; update both together. "
            f"narration: {list(scene_ids)}; journey: {EXPECTED_BEATS}")


def check_title_slot(spec: dict[str, object]) -> tuple[float, float]:
    """This journey records a cold open that plays after a title card, so the plan must
    say so. Returns the title card's length and the cold open's."""
    cards = spec.get("cards") or {}
    slot = str(cards.get("title_slot", ""))
    if not slot.startswith(TITLE_SLOT):
        raise SystemExit(f"narration.json cards.title_slot does not start with {TITLE_SLOT!r}; "
                         "this journey records a cold open after a title card")
    title = float(cards.get("title_seconds", 0))
    if not 1.5 <= title <= 3.0:
        raise SystemExit(f"cards.title_seconds is {title}; the title card before the cold open needs 1.5 to 3 s")
    cold = float((spec.get("cold_open") or {}).get("seconds", 0))
    if not 3.0 <= cold <= 20.0:
        raise SystemExit(f"cold_open.seconds is {cold}; the cold open needs 3 to 20 s")
    return title, cold


def billed_presses_allowed(argv: list[str]) -> bool:
    """Billed presses happen only when the owner passes the flag. The default is off."""
    return BILLED_FLAG in argv


def rehearsal_requested(argv: list[str]) -> bool:
    """A free rehearsal, never together with the flag that allows billed presses."""
    if REHEARSAL_FLAG in argv and BILLED_FLAG in argv:
        raise SystemExit(f"{REHEARSAL_FLAG} and {BILLED_FLAG} cannot be used together: "
                         "a rehearsal bills nothing")
    return REHEARSAL_FLAG in argv


def check_local_url(url: str) -> None:
    """A rehearsal drives only a server on this machine, reached over plain loopback."""
    parsed = urllib.parse.urlparse(url.strip())
    try:
        host = (parsed.hostname or "").lower()
    except ValueError:
        host = ""
    if parsed.scheme not in ("http", "https") or parsed.username or parsed.password \
            or host not in REHEARSAL_HOSTS:
        raise SystemExit(f"{REHEARSAL_FLAG} runs only against a local server, such as "
                         f"http://127.0.0.1:8801/; VOLCAN_APP_URL names {host or url!r}")


def check_rehearsal_health(health: dict[str, object], release_sha: str) -> list[dict[str, object]]:
    """Refuse a server that could bill a model call or post a review; list what differs
    from the live build, because those beats are not representative of the take."""
    if health.get("source_revision") != release_sha:
        raise SystemExit("the server reports a different commit than VOLCAN_RELEASE_SHA; restart it")
    model = (health.get("bedrock_model_path") or {}).get("resolved_capability")
    if model == "ready_to_attempt":
        raise SystemExit("/health reports bedrock_model_path ready_to_attempt, so a press could bill an "
                         "Amazon Bedrock call. Start the rehearsal server without cloud credentials")
    review = (health.get("github_review_path") or {}).get("resolved_capability")
    if review != "dry_run_no_token":
        raise SystemExit(f"/health reports github_review_path {review!r}; a rehearsal needs "
                         "dry_run_no_token, so Confirm cannot post a review. Start it without a token")
    notes = [{"check": "bedrock_model_path", "take": "ready_to_attempt", "rehearsal": model,
              "why": "the local server has no cloud credentials, so the local heuristic engine answers"}]
    durable = (health.get("durable_state") or {}).get("resolved_capability")
    if durable != "configured_reachable":
        notes.append({"check": "durable_state", "take": "configured_reachable", "rehearsal": durable,
                      "why": "beat 3 names DynamoDB; the local server keeps its review state in memory"})
    return notes


def silent_timing_stub(spec: dict[str, object]) -> dict[str, object]:
    """A timing.json built from the plan's ESTIMATE windows, for a rehearsal only.

    Each beat holds for its planned window. Its narration is the window less the
    generator's tail and the product window, and its caption sentences share that time
    by character count, the generator's rule. No audio was synthesized: the stub's
    narration is silence of that length."""
    lead = float((spec.get("cards") or {}).get("title_seconds", 0)) + float(
        (spec.get("cold_open") or {}).get("seconds", 0))
    scenes: list[dict[str, object]] = []
    offset = 0.0
    for index, beat in enumerate(spec["beats"], start=1):
        hold = float(beat["timestamp_end"]) - float(beat["timestamp_start"])
        extra = float(beat.get("product_sound_seconds") or 0.0)
        seconds = hold - NARRATION_TAIL_SECONDS - extra
        if seconds < 3:
            raise SystemExit(f"{beat['beat_id']}: the planned window leaves {seconds:.3f} s of narration")
        if abs(float(beat["timestamp_start"]) - lead - offset) > 0.01:
            raise SystemExit(f"{beat['beat_id']}: the planned timestamps do not follow the title card, "
                             "the cold open and the beat before")
        caption = str(beat["narration_text"])
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", caption) if part.strip()]
        weight = sum(len(part) for part in sentences) or 1
        cursor = 0.0
        windows = []
        for sentence in sentences:
            share = seconds * len(sentence) / weight
            windows.append({"start": round(cursor, 3), "end": round(cursor + share, 3), "text": sentence})
            cursor += share
        scenes.append({
            "id": beat["beat_id"], "audio": f"{index:02d}-{beat['beat_id']}.wav",
            "durationSeconds": round(seconds, 3), "productSoundSeconds": round(extra, 3),
            "holdSeconds": round(hold, 3), "startSeconds": round(offset, 3),
            "speechCharacters": len(str(beat.get("speech_text") or caption)), "sentences": windows,
        })
        offset += hold
    return {
        "schemaVersion": "volcan.video-timing/v1",
        "stub": True,
        "basis": ("ESTIMATE: a silent timing stub for a rehearsal, built from the planned windows in "
                  "video/narration.json. No narration was synthesized and nothing was sent to ElevenLabs."),
        "voice": dict((spec.get("tts") or {}).get("elevenLabs") or {}),
        "tailSeconds": NARRATION_TAIL_SECONDS,
        "totalSeconds": round(offset, 3),
        "charactersSentThisRun": 0,
        "scenes": scenes,
    }


def write_silent_stub(timing: dict[str, object], folder: pathlib.Path) -> None:
    """The stub's timing.json, its captions and one silent WAV per beat."""
    import wave

    folder.mkdir(parents=True, exist_ok=True)
    (folder / "timing.json").write_text(json.dumps(timing, indent=2) + "\n", encoding="utf-8")
    cues = []
    for scene in timing["scenes"]:
        for window in scene["sentences"]:
            start = float(scene["startSeconds"]) + float(window["start"])
            cues.append((start, float(scene["startSeconds"]) + float(window["end"]), window["text"]))
        with wave.open(str(folder / scene["audio"]), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(16000)
            out.writeframes(b"\x00\x00" * round(16000 * float(scene["durationSeconds"])))
    (folder / "captions.en.srt").write_text("\n".join(
        f"{number}\n{srt_stamp(start)} --> {srt_stamp(end)}\n{text}\n"
        for number, (start, end, text) in enumerate(cues, start=1)), encoding="utf-8")


def srt_stamp(value: float) -> str:
    millis = round(max(0.0, value) * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    seconds, millis = divmod(millis, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


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
        raise SystemExit(f"/health reports durable_state {durable!r}; beat 3 names DynamoDB, "
                         "so it needs configured_reachable")
    review = (health.get("github_review_path") or {}).get("resolved_capability")
    if review != "dry_run_no_token":
        raise SystemExit(f"/health reports github_review_path {review!r}; beat 6 says the build has "
                         "no GitHub token, so it needs dry_run_no_token")
    model_id = (health.get("bedrock_model_path") or {}).get("model_id")
    if not str(model_id or "").startswith(CLAUDE_MODEL_PREFIX):
        raise SystemExit(f"/health reports model_id {model_id!r}; beat 3 says Claude on Amazon Bedrock "
                         "answered, so it needs a Claude model")


def pull_request_label(url: str) -> str:
    """The words the dialogue uses for a GitHub pull request URL."""
    found = re.fullmatch(r"https://github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)/?", url.strip())
    if not found:
        raise SystemExit("VOLCAN_PR_URL must be https://github.com/<owner>/<repo>/pull/<number>")
    owner, repo, number = found.groups()
    return f"{owner}/{repo} pull request {number}"


def cold_open_command(value: str | None) -> tuple[str, str, str, str | None]:
    """The cold-open command: findings (the default), files, summary, or "line N"."""
    key = " ".join((value or "findings").strip().lower().split())
    if key in COLD_OPEN_COMMANDS:
        return COLD_OPEN_COMMANDS[key]
    found = COLD_OPEN_LINE.fullmatch(key)
    if found and int(found.group(1)) > 0:
        words = f"line {int(found.group(1))}"
        return ("#commandInput", words, "commandInput", words)
    raise SystemExit("VOLCAN_COLD_OPEN must be findings, files, summary, or line and a number, such as line 26")


def cold_open_line_problem(words: str, data: dict[str, object]) -> str | None:
    """Why a typed "line N" cold open does not show the finding it was chosen for, or None.

    A button command is checked against the outlined next steps before the press; a
    typed line is checked on its answer: no refusal, the line it asked for, and a file
    whose review card names a security finding, because the cold open is for a finding."""
    wanted = int(words.split()[1])
    if data.get("error"):
        return f"{words}: the page refused the turn: {str(data.get('spoken') or '')[:120]}"
    line = data.get("line") or {}
    if line.get("new_no") != wanted:
        return f"{words}: the page read new line {line.get('new_no')!r}, not {wanted}"
    if not (data.get("review_card") or {}).get("finding"):
        return f"{words}: the review card names no security finding for this file; the cold open is for a finding"
    return None


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


def cold_open_gate(first_sound: float | None, first_word: float | None, title_seconds: float) -> None:
    """first_sound and first_word are seconds from the cold open's first frame, which
    comes title_seconds into the video, after the title card."""
    if first_sound is None or first_sound > COLD_OPEN_FIRST_SOUND_SECONDS:
        raise SystemExit(f"the cold open made its first sound {first_sound} s after the title card; "
                         f"the plan needs it by {COLD_OPEN_FIRST_SOUND_SECONDS} s. Record again")
    video_word = None if first_word is None else round(title_seconds + first_word, 3)
    if video_word is None or video_word > VIDEO_FIRST_WORD_SECONDS:
        raise SystemExit(f"the cold open spoke its first word {video_word} s into the video, after the "
                         f"{title_seconds} s title card; the plan needs it by {VIDEO_FIRST_WORD_SECONDS} s. "
                         "Record again")


def no_finding(spoken: str) -> bool:
    """Whether a Findings answer says that no rule matched."""
    return str(spoken or "").strip().startswith(NO_FINDING_PREFIX)


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
    rehearsal = rehearsal_requested(sys.argv[1:])
    allow_billed = billed_presses_allowed(sys.argv[1:])
    root = pathlib.Path(env("VOLCAN_VIDEO_ROOT"))
    release_sha = env("VOLCAN_RELEASE_SHA")
    if not re.fullmatch(r"[0-9a-f]{40}", release_sha):
        raise SystemExit("VOLCAN_RELEASE_SHA must be a full 40 character commit")
    app_url = os.environ.get("VOLCAN_APP_URL", "http://127.0.0.1:8801/").strip()
    if rehearsal:
        check_local_url(app_url)
    pr_url = env("VOLCAN_PR_URL")
    pr_label = pull_request_label(pr_url)
    voice = os.environ.get("VOLCAN_SPEECH_VOICE", "Microsoft David Desktop").strip()
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    # VOLCAN_COLD_OPEN overrides the plan's cold_open.command.
    cold_selector, cold_label, cold_id, cold_typed = cold_open_command(
        os.environ.get("VOLCAN_COLD_OPEN") or (spec.get("cold_open") or {}).get("command"))
    title_seconds, cold_seconds = check_title_slot(spec)
    measured = root / "narration" / "timing.json"
    narration_dir = "narration"
    if rehearsal and not measured.is_file():
        timing = silent_timing_stub(spec)
        narration_dir = "rehearsal/narration-stub"
    else:
        timing = json.loads(measured.read_text(encoding="utf-8"))
    scenes = timing["scenes"]
    check_beats([scene["id"] for scene in scenes])
    by_id = {scene["id"]: scene for scene in scenes}
    total = float(timing["totalSeconds"])

    with urllib.request.urlopen(app_url.rstrip("/") + "/health", timeout=10) as response:
        health = json.load(response)
    # What a rehearsal cannot show as the take would, and what would fail the take.
    not_representative: list[dict[str, object]] = []
    failures: list[str] = []
    if rehearsal:
        not_representative.extend(check_rehearsal_health(health, release_sha))
    else:
        check_health(health, release_sha)
        if not allow_billed:
            raise SystemExit(billed_plan())

    def fail(message: str) -> None:
        """A take stops at the first failure; a rehearsal records it and goes on."""
        if not rehearsal:
            raise SystemExit(message)
        failures.append(message)

    def differs(check: str, take: object, observed: object, why: str) -> None:
        """A check that needs Amazon Bedrock: it fails the take, and a rehearsal notes it."""
        if not rehearsal:
            raise SystemExit(f"{check}: {why}; record again")
        not_representative.append({"check": check, "take": take, "rehearsal": observed,
                                   "why": "answered by the local heuristic engine in a rehearsal"})

    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright

    capture = root / ("rehearsal" if rehearsal else "capture")
    if capture.exists():
        shutil.rmtree(capture)
    (capture / "raw").mkdir(parents=True)
    if narration_dir != "narration":
        write_silent_stub(timing, capture / "narration-stub")

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
            return press_timeline_seconds(beat_start(beat), float(by_id[beat]["durationSeconds"]),
                                          float(timing["tailSeconds"]))

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
            """Wait for the last sentence of a voiced turn to end, inside its window. A
            rehearsal records a turn that overruns its window and goes on, so the rest of
            the journey is still measured; the speech checks after it name the overrun."""
            try:
                wait_speech_end(int(turn["firstSpeech"]) + int(turn["utterances"]) - 1, deadline - now())
                actions.append({"at": round(now(), 3), "action": f"{turn['label']}: speech ended"})
            except PlaywrightTimeout:
                if not rehearsal:
                    raise
                failures.append(f"{turn['label']}: the page was still speaking when its window closed "
                                f"at {round(deadline, 3)} s")
                actions.append({"at": round(now(), 3), "action": f"{turn['label']}: window closed, still speaking"})
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

        b1, b2, b3, b4, b5, b6, b7 = EXPECTED_BEATS

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
        if cold_typed is None and cold_id not in outlined():
            raise SystemExit(f"{cold_label} is not an outlined next step: {outlined()}")
        scroll_to("#reviewConvo", 12, "instant")
        page.wait_for_timeout(1500)

        # Cold open, after the title card: the first frame is the opened overview.
        clock["origin"] = time.monotonic()
        cold_epoch = page_epoch()
        timeline_epoch = cold_epoch + cold_seconds * 1000
        if cold_typed is None:
            until(-cold_seconds + 0.3)

            def press_cold() -> None:
                page.click(cold_selector)
        else:
            # Typed on camera into the command box (Alt+4), then sent with Enter.
            until(-cold_seconds + 0.1)
            page.keyboard.press("Alt+4")
            if focused() != cold_id:
                raise SystemExit(f"Alt+4 put the focus on {focused()!r}, not the command box")
            act(f"type {cold_typed}", lambda: page.keyboard.type(cold_typed, delay=25))

            def press_cold() -> None:
                press_key("Enter", cold_id, cold_label)
        before = turns()
        cold = start_turn(cold_label, press_cold, "/api/review/turn", 2)
        answered(before)
        if cold_label == "Findings" and no_finding(str(cold["data"].get("spoken") or "")):
            fail("Findings answered that no security rule matched; the plan wants a finding in the cold "
                 "open. Choose another pull request or set VOLCAN_COLD_OPEN=files")
        if cold_typed is not None:
            problem = cold_open_line_problem(cold_typed, cold["data"])
            if problem:
                fail(problem)
        finish_voiced(cold, 0.0)

        # Beat 1: the Alexa+ value over the top of the page, then the focus ring.
        until(beat_start(b1))
        act("scroll to the top of the page", lambda: page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})"))
        until(sentence(b1, len(by_id[b1]["sentences"]) - 1, 0.6))
        act("Alt+1 focuses Hear this code review", lambda: page.keyboard.press("Alt+1"))
        if focused() != "runReview":
            raise SystemExit(f"Alt+1 put the focus on {focused()!r}, not Hear this code review")

        # Beat 2: one short line from the narrator, then the press. One billed call. The
        # press waits for the narrator to stop, in a take as in a rehearsal, so the answer
        # starts after the narration whatever the model's latency: take 3 pressed at the
        # first frame and Amazon Bedrock answered in about 5 s, under the narration. The
        # product window that opens here holds an answer that starts within the latency
        # allowance; a later one fails the take.
        until(window_opens(b2))
        armed["digest"] = 1
        press = start_turn("Enter presses Hear this code review",
                           lambda: press_key("Enter", "runReview", "Hear this code review"),
                           "/api/digest_semantic_diff", 1, is_press,
                           timeout_seconds=BILLED_TURN_TIMEOUT_SECONDS)
        mode = press["data"].get("synthesis_mode")
        reason = press["data"].get("synthesis_fallback_reason")
        if rehearsal and mode == "bedrock":
            raise SystemExit("a rehearsal press was answered by Amazon Bedrock, which bills; stop the "
                             "server and start it without cloud credentials")
        if mode != "bedrock" or reason:
            differs("the press is answered by Amazon Bedrock", "synthesis_mode bedrock, no fallback reason",
                    {"synthesis_mode": mode, "fallback_reason": reason},
                    f"the press was not answered by Amazon Bedrock: synthesis_mode {mode!r}, "
                    f"fallback reason {reason!r}")
        # An answer that arrives after the allowance cannot start inside the window's
        # budget. It is named here, at once, rather than as a timeout later; the precise
        # check on the first sound runs after the journey, in both modes.
        if now() > window_opens(b2) + ANSWER_LATENCY_ALLOWANCE_SECONDS:
            fail(f"beat 2's answer arrived {round(now() - window_opens(b2), 3)} s after the press, past "
                 f"the {ANSWER_LATENCY_ALLOWANCE_SECONDS} s latency allowance its window is sized for; "
                 "record again")
        page.wait_for_function(
            "(from) => window.__volcanCaptureLog.slice(from).some(e => e.kind === 'speech.start')",
            arg=press["logFrom"], timeout=max(0.5, beat_start(b3) - now()) * 1000)
        act("scroll so the earcon, the sentence and the Braille share the frame",
            lambda: scroll_to(".r-earcon", 16))
        finish_voiced(press, beat_start(b3))

        # Beat 3: the meter while the narrator names Amazon Bedrock, AWS Lambda and
        # DynamoDB; the coverage line as printed on the sentence about it; the full answer.
        until(beat_start(b3))
        meter = page.inner_text("#meterEngine").strip()
        if not meter.startswith("Amazon Bedrock"):
            differs("the engine meter reads Amazon Bedrock", "Amazon Bedrock", meter[:80],
                    "the engine meter does not read Amazon Bedrock")
        coverage = page.inner_text("#modelCoverage").strip()
        health_model = (health.get("bedrock_model_path") or {}).get("model_id")
        coverage_problem = coverage_line_problem(coverage, press["data"], health_model)
        if coverage_problem:
            differs("the page prints the answer's coverage line, ending Answered by <model_answered>.",
                    expected_coverage_line(press["data"]) or "The model read ... Answered by anthropic.claude-...",
                    coverage[:200] or None, coverage_problem)
        act("scroll to the engine meter", lambda: scroll_to("#meters", 120))
        coverage_sentence = len(by_id[b3]["sentences"]) - 1
        until(sentence(b3, coverage_sentence))
        act("scroll to the coverage line", lambda: scroll_to("#modelCoverage", 260))
        until(sentence(b3, coverage_sentence, 0.6))
        if page.is_visible("#modelProseWrap summary"):
            act("open The model's full answer", lambda: page.click("#modelProseWrap summary"))
            act("scroll to the model's full answer", lambda: scroll_to("#modelProseWrap", 80))
        else:
            differs("The model's full answer can be opened", "a model answer to open", "hidden",
                    "the page shows no model answer to open")

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

        # Beat 6: the narrator, over the recorded request, once the page has stopped
        # speaking. The screencast then ends on narration, so the main audio covers it
        # to within the generator's tail of its end.
        until(beat_start(b6))
        if "recorded and not sent" not in page.inner_text("#reviewPane"):
            raise SystemExit("the review pane no longer shows a recorded, unsent review")

        # Beat 7: Server and MCP, a real handshake, then the Alexa+ box. No replay press.
        until(beat_start(b7))
        act("Server and MCP tab", lambda: page.click("#tabServer"))
        act("scroll to Evidence", lambda: scroll_to("#evidence"))
        until(sentence(b7, 0, 0.3))
        act("scroll to the MCP handshake", lambda: scroll_to("#mcp", 16))
        act("Run a real MCP handshake", lambda: page.click("#runMcp"))
        page.wait_for_selector("#mcpPane details", timeout=10_000)
        act("scroll to the handshake facts", lambda: scroll_to("#mcp .row-actions", 24))
        until(sentence(b7, len(by_id[b7]["sentences"]) - 1))
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
        fail(f"the page asked for model calls the take did not plan, and they were aborted: {refused}")
    if [item["kind"] for item in billed] != [kind for kind, _ in BILLED_PRESSES]:
        fail(f"the model-path calls were {billed}, not the planned {[kind for kind, _ in BILLED_PRESSES]}")
    if errors:
        fail("the page logged errors during the take: " + "; ".join(errors[:5]))

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

    def turn_log_end(turn: dict[str, object]) -> int:
        """Where this turn's stretch of the log ends: the next voiced turn's press."""
        later = [int(other["logFrom"]) for other in voiced if int(other["logFrom"]) > int(turn["logFrom"])]
        return min(later) if later else len(log)

    def turn_earcon(turn: dict[str, object]) -> dict[str, object] | None:
        """Where the page's own playback clock says this turn's cue started.

        Each timeupdate reports how far into the WAV the element is, so its wall time
        minus that position is the start. Headless Chromium fires "playing" a few
        hundred milliseconds before the clock moves, and the waveform's playhead
        follows the clock, so this is the moment the picture shows the cue sounding."""
        # Only this turn's own stretch of the log, up to the next voiced turn's press: a
        # turn the server answered without a cue (a typed "line N") must not be credited
        # with the next turn's cue, and a cue it did play is still found and checked.
        entries = log[int(turn["logFrom"]):turn_log_end(turn)]
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
    cold_sound_seconds = None if cold_sound is None else round((cold_sound - cold_epoch) / 1000, 3)
    cold_word_seconds = None if cold_word is None else round((cold_word - cold_epoch) / 1000, 3)
    try:
        cold_open_gate(cold_sound_seconds, cold_word_seconds, title_seconds)
    except SystemExit as exc:
        fail(str(exc))
    press_sound, _ = first_sound(press)
    # The take and the rehearsal press at the same moment, so this check is the take's in
    # both: a rehearsal that fails it has a failure, not a note.
    if rehearsal:
        if press_sound is None or timeline_time(press_sound) < narrator_stops(b2):
            fail("the answer starts after beat 2's narration: the answer began while the narrator was "
                 f"still speaking, or made no sound (after {round(narrator_stops(b2), 3)} s)")
    elif press_sound is None or timeline_time(press_sound) < narrator_stops(b2):
        differs("the answer starts after beat 2's narration", f"after {round(narrator_stops(b2), 3)} s",
                None if press_sound is None else timeline_time(press_sound),
                "the model's answer began while the narrator was still speaking")
    # The window is sized for an answer that starts within the latency allowance, so a
    # later one fails the take, and a rehearsal, rather than run past the window.
    latency_problem = answer_latency_problem(
        None if press_sound is None else timeline_time(press_sound), window_opens(b2))
    if latency_problem:
        fail(latency_problem)

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
            fail(f"{turn['label']}: expected {turn['utterances']} sentences, the server returned {len(sentences)}")
            continue
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
                fail(f"{turn['label']}: sentence {offset + 1} was interrupted "
                     f"({events['speech.error']['detail'].get('error')}); record again")
                continue
            if not {"speech.speak", "speech.start", "speech.end"} <= set(events):
                fail(f"{turn['label']}: sentence {offset + 1} has no start and end events")
                continue
            text = events["speech.speak"]["detail"]["text"]
            if text != expected:
                fail(f"{turn['label']}: the page spoke a sentence other than the one the server returned")
            ended_at = timeline_time(events["speech.end"]["epoch"])
            if ended_at > closes:
                fail(f"{turn['label']}: the browser was still speaking {round(ended_at - closes, 3)} s after "
                     f"the next segment began at {round(closes, 3)} s")
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
        fail(f"the recording shows a blank page at video seconds {blanks}; record again")

    recorded = probe_duration(final)
    if recorded < trim_lead + total * scale:
        fail(f"the recording is {recorded:.3f}s, shorter than {trim_lead + total * scale:.3f}s")
    receipt = {
        "schemaVersion": "volcan.video-capture/v3",
        "mode": "rehearsal" if rehearsal else "take",
        "shippable": not rehearsal,
        "releaseSha": release_sha,
        "appUrl": app_url,
        "narrationDir": narration_dir,
        "timingBasis": timing.get("basis") or "measured by video/generate-narration.py",
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
            "note": ("opened before the cold open, off camera; in a rehearsal the local engine digested it"
                 if rehearsal else "opened before the cold open, off camera; this was a billed model call"),
        },
        "billedCalls": [] if rehearsal else billed,
        "coldOpen": {
            "seconds": cold_seconds,
            "command": cold_label,
            "trimLeadSeconds": round(cold_trim_lead, 3),
            "firstSoundSeconds": cold_sound_seconds,
            "firstWordSeconds": cold_word_seconds,
            "titleCardSeconds": title_seconds,
            "firstWordVideoSeconds": None if cold_word_seconds is None else round(title_seconds + cold_word_seconds, 3),
            "spoken": cold["data"].get("spoken"),
            "note": "timeline seconds from -seconds to 0; the build plays this footage after the title card",
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
            "firstSoundTimelineSeconds": None if press_sound is None else timeline_time(press_sound),
            "narratorStopsTimelineSeconds": round(narrator_stops(b2), 3),
            "pressTimelineSeconds": press["timelineAction"],
            "windowOpensTimelineSeconds": round(window_opens(b2), 3),
            "latencyAllowanceSeconds": ANSWER_LATENCY_ALLOWANCE_SECONDS,
            "firstSoundAfterWindowOpensSeconds": None if press_sound is None
            else round(timeline_time(press_sound) - window_opens(b2), 3),
            "windowClosesTimelineSeconds": round(beat_end(b2), 3),
            "modelAnswered": press["data"].get("model_answered"),
            "coverageLine": coverage,
            "expectedCoverageLine": expected_coverage_line(press["data"]),
        },
        "productAudio": product_audio,
        "unrecordedProductVoice": [],
        "blankStretches": blanks,
        "pageErrors": errors,
        "bytes": final.stat().st_size,
        "sha256": sha256(final),
    }
    if rehearsal:
        receipt["rehearsal"] = {
            "note": ("A free rehearsal against a local server, answered by the local heuristic engine. "
                     "Nothing was billed. It is not shippable, and the checks under notRepresentative "
                     "say what the billed take does differently."),
            "modelPathRequests": billed,
            "notRepresentative": not_representative,
            "failures": failures,
        }
    (capture / "capture-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: receipt[key] for key in ("trimLeadSeconds", "recordedSeconds", "markers", "coldOpen")}))
    for item in product_audio:
        print(item["kind"], item["turn"], item["timelineSeconds"], "to", item["pageEndedTimelineSeconds"],
              "rendered", item["seconds"])
    if rehearsal:
        for item in not_representative:
            print("not representative:", item["check"], "->", item["rehearsal"])
        for message in failures:
            print("FAIL:", message)
        if failures:
            raise SystemExit(f"the rehearsal found {len(failures)} failures; see {capture / 'capture-receipt.json'}")


if __name__ == "__main__":
    main()
