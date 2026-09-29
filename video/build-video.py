#!/usr/bin/env python3
"""Compose the local capture, the measured narration, the product's own sound and captions.

Adapted from the submission kit's video pipeline (video/build-video.py in the kit).
Kept from the kit: the capture is trimmed to exactly the measured narration length
from the capture receipt's trimLeadSeconds, scaled onto a 1920x1080 canvas at 25 fps,
the SRT derived from the measured audio is burned in, each beat's audio is delayed to
its measured start, the mix is loudness normalised to -16 LUFS, and the build probes
its own output and exits non-zero when the duration, the dimensions, the stream count
or the length against the narration are wrong.

What this copy adds, so the video carries its own honesty and the product's sound:

  1. A title card and an outro card, whose lines come from video/narration.json with
     {sha7} replaced by the recorded commit. The title card names the product and says
     the video is a local run of that commit; the outro repeats the provenance. The
     cards give the four part shape (title, screencast, web, outro) that
     scripts/verify_video_sync.py checks, and the build writes the video_manifest.json
     and caption_windows.json that gate reads, computed from timing.json and the
     capture receipt and nothing else.
  2. A caption band. The page is scaled to 1632x918 at the top of the frame, and
     everything the build adds sits in the 162 pixel band under it: the captions, a
     small tag naming the local commit, and the labels below. Nothing the build adds
     covers the page, so the sentence the page shows while it speaks stays readable.
  3. The product's sound, from the capture receipt: for each voiced turn, the earcon
     WAV the server returned and each sentence the page spoke, in the system voice,
     placed at the moment the page started it. Each is captioned: the sentences as
     "Volcan (product voice):", the earcon as a sound description.
  4. Each source is brought to a measured loudness before the mix, because the earcon
     is a pure tone about 18 LU louder than the narration as delivered. Every earcon
     takes the gain measured on the longest one: EBU R128 gates on 400 ms blocks, so a
     cue shorter than that cannot be measured on its own.
  5. The composed length must equal title + narration + outro within one frame.
  6. For the turns the narrator talks over, a label in the band says, for exactly the
     stretch the page spoke, that the page's own cue and voice are not in the recording.
  7. The receipt records the recorded commit, whether src/ and docs/ are unchanged
     between that commit and the commit that built the video, the voice, and the
     characters sent to the text to speech provider.

Environment:
  VOLCAN_VIDEO_ROOT   media root (reads narration/ and capture/, writes output/)
  VOLCAN_RELEASE_SHA  the 40 character commit the capture was recorded from
  FFMPEG, FFPROBE     paths to the binaries
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import subprocess


REPO = pathlib.Path(__file__).resolve().parents[1]
SPEC = pathlib.Path(__file__).with_name("narration.json")
ROOT = pathlib.Path(os.environ["VOLCAN_VIDEO_ROOT"])
NARRATION = ROOT / "narration"
CAPTURE = ROOT / "capture"
OUTPUT = ROOT / "output"
FPS = 25
FRAME_SECONDS = 1 / FPS
OUTPUT_NAME = "volcan-demo.mp4"
CARD_COLOUR = "0x07111f"
FONT = "C\\:/Windows/Fonts/segoeui.ttf"
FONT_BOLD = "C\\:/Windows/Fonts/segoeuib.ttf"
# The page sits at the top of the frame at 1.275x; the band under it holds captions.
PAGE_WIDTH, PAGE_HEIGHT, PAGE_X = 1632, 918, 144
# Loudness each source is brought to before the mix. The final loudnorm then sets
# the programme to -16 LUFS. The earcon sits a little under the voices because a
# pure tone reads louder than speech at the same integrated level.
SOURCE_TARGET_LUFS = {"narration": -20.0, "speech": -21.0, "earcon": -22.0}
PRODUCT_SPEAKER = "Volcan (product voice)"
PRODUCT_COLOUR = "#ffc857"
PRODUCT_CUE_CHARACTERS = 72
EARCON_CUE_MIN_SECONDS = 0.4


def run(args: list[str], cwd: pathlib.Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        raise SystemExit(result.stderr[-3000:] or "media command failed")
    return result


def probe(path: pathlib.Path) -> dict[str, object]:
    return json.loads(
        run([os.environ["FFPROBE"], "-v", "error", "-show_streams", "-show_format",
             "-of", "json", str(path)]).stdout
    )


def loudness(path: pathlib.Path) -> float:
    log = run([os.environ["FFMPEG"], "-hide_banner", "-nostats", "-i", str(path),
               "-af", "ebur128", "-f", "null", "-"]).stderr
    found = re.findall(r"I:\s+(-?[0-9.]+) LUFS", log)
    if not found:
        raise SystemExit(f"could not measure the loudness of {path.name}")
    return float(found[-1])


def escaped(path: pathlib.Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:")


def text_file(name: str, text: str) -> str:
    path = OUTPUT / "overlays" / name
    path.write_text(text, encoding="utf-8")
    return escaped(path)


def card(lines: list[str], seconds: float, name: str) -> str:
    """A flat card: one large line, then smaller ones. Sparse on purpose, because the
    sync gate tells a card from content by how few edges it has."""
    parts = [f"color=c={CARD_COLOUR}:s=1920x1080:r={FPS}:d={seconds}"]
    y = 400 - 38 * max(0, len(lines) - 3)
    for index, line in enumerate(lines):
        size = 110 if index == 0 else 40
        font = FONT_BOLD if index == 0 else FONT
        parts.append(
            f"drawtext=fontfile='{font}':textfile='{text_file(f'{name}-{index}.txt', line)}':"
            f"fontcolor=white:fontsize={size}:x=(w-text_w)/2:y={y}"
        )
        y += 170 if index == 0 else 76
    return ",".join(parts)


def srt_windows(path: pathlib.Path) -> list[tuple[float, float, str]]:
    def seconds(stamp: str) -> float:
        hours, minutes, rest = stamp.split(":")
        secs, millis = rest.split(",")
        return int(hours) * 3600 + int(minutes) * 60 + int(secs) + int(millis) / 1000

    windows = []
    for block in path.read_text(encoding="utf-8").strip().split("\n\n"):
        lines = block.splitlines()
        start, end = (part.strip() for part in lines[1].split("-->"))
        windows.append((seconds(start), seconds(end), "\n".join(lines[2:])))
    return windows


def write_srt(path: pathlib.Path, windows: list[tuple[float, float, str]]) -> None:
    path.write_text(
        "\n".join(
            f"{number}\n{stamp(start)} --> {stamp(end)}\n{text}\n"
            for number, (start, end, text) in enumerate(windows, start=1)
        ),
        encoding="utf-8",
    )


def product_speech_cues(text: str, start: float, end: float) -> list[tuple[float, float, str]]:
    """One sentence the page spoke, as short cues timed by character share across the
    rendered speech, the rule the narration captions use. Each cue names the speaker."""
    chunks: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > PRODUCT_CUE_CHARACTERS:
            chunks.append(current)
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    weight = sum(len(chunk) for chunk in chunks) or 1
    cues = []
    cursor = start
    for chunk in chunks:
        share = (end - start) * len(chunk) / weight
        cues.append((round(cursor, 3), round(cursor + share, 3), f"{PRODUCT_SPEAKER}:\n{chunk}"))
        cursor += share
    return cues


def burned(text: str) -> str:
    """The burn-in copy of a cue: the product's speaker name in its own colour."""
    prefix = f"{PRODUCT_SPEAKER}:"
    if text.startswith(prefix):
        return f'<font color="{PRODUCT_COLOUR}">{prefix}</font>{text[len(prefix):]}'
    if text.startswith("[Volcan"):
        return f'<font color="{PRODUCT_COLOUR}">{text}</font>'
    return text


def product_code_unchanged(sha: str) -> bool:
    result = subprocess.run(
        ["git", "diff", "--quiet", sha, "HEAD", "--", "src", "docs"], cwd=REPO,
        capture_output=True, text=True,
    )
    return result.returncode == 0


def main() -> None:
    release_sha = os.environ["VOLCAN_RELEASE_SHA"].strip()
    if not re.fullmatch(r"[0-9a-f]{40}", release_sha):
        raise SystemExit("VOLCAN_RELEASE_SHA must be a full 40 character commit")
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    cards = spec["cards"]
    title_seconds = float(cards["title_seconds"])
    outro_seconds = float(cards["outro_seconds"])
    sha7 = release_sha[:7]
    timing = json.loads((NARRATION / "timing.json").read_text(encoding="utf-8"))
    receipt_in = json.loads((CAPTURE / "capture-receipt.json").read_text(encoding="utf-8"))
    if receipt_in["releaseSha"] != release_sha:
        raise SystemExit("the capture was recorded from a different commit than VOLCAN_RELEASE_SHA")
    if receipt_in["serverHealth"].get("sourceRevision") != release_sha:
        raise SystemExit("the server in the capture reported a different commit than VOLCAN_RELEASE_SHA")
    scenes = timing["scenes"]
    total = float(timing["totalSeconds"])
    whole = title_seconds + total + outro_seconds
    trim_lead = float(receipt_in["trimLeadSeconds"])
    if not 0 <= trim_lead <= 30:
        raise SystemExit("capture trim lead is outside the bounded contract")
    # The capture measures how many recorded seconds pass per page-clock second
    # between its two marker flips; the picture is retimed by it so an action the
    # page logged at a timeline second is shown at that second.
    video_per_page = float(receipt_in["markers"].get("videoPerPageSecond", 1.0))
    if not 0.95 <= video_per_page <= 1.05:
        raise SystemExit(f"the recording drifted {video_per_page:.6f}x against the page clock; record again")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "overlays").mkdir(exist_ok=True)

    product = sorted(receipt_in["productAudio"], key=lambda item: float(item["timelineSeconds"]))
    earcons = [item for item in product if item["kind"] == "earcon"]
    speech = [item for item in product if item["kind"] == "speech"]
    if not speech:
        raise SystemExit("the capture receipt carries no product speech")
    earcon_gain = None
    if earcons:
        longest = max(earcons, key=lambda item: float(item["seconds"]))
        earcon_gain = SOURCE_TARGET_LUFS["earcon"] - loudness(CAPTURE / longest["file"])

    args = [os.environ["FFMPEG"], "-y", "-i", str(CAPTURE / "production.webm")]
    filters: list[str] = []
    labels: list[str] = []
    gains: dict[str, float] = {}
    sources: list[tuple[pathlib.Path, float, str]] = []
    for scene in scenes:
        sources.append((NARRATION / str(scene["audio"]), float(scene["startSeconds"]), "narration"))
    for item in product:
        sources.append((CAPTURE / item["file"], float(item["timelineSeconds"]), item["kind"]))
    for index, (path, start, kind) in enumerate(sources, start=1):
        args.extend(["-i", str(path)])
        gain = earcon_gain if kind == "earcon" else SOURCE_TARGET_LUFS[kind] - loudness(path)
        gains[path.name] = round(gain, 2)
        delay = round((title_seconds + start) * 1000)
        label = f"a{index}"
        filters.append(
            f"[{index}:a]aresample=48000,aformat=channel_layouts=stereo,volume={gain:.2f}dB,"
            f"adelay={delay}:all=1[{label}]"
        )
        labels.append(f"[{label}]")

    # Each rendered sentence must end before the next one the page spoke, and before
    # its beat ends, so the product voice never runs under the narrator.
    by_id = {scene["id"]: scene for scene in scenes}
    for item in speech:
        begins = float(item["timelineSeconds"])
        ends = begins + float(item["seconds"])
        beat = by_id[item["beat"]]
        closes = float(beat["startSeconds"]) + float(beat["holdSeconds"])
        if ends > closes:
            raise SystemExit(f"{item['file']} ends at {ends:.3f}s, after its beat closes at {closes:.3f}s")
        following = [float(other["timelineSeconds"]) for other in speech if float(other["timelineSeconds"]) > begins]
        if following and ends > min(following):
            raise SystemExit(f"{item['file']} runs into the next sentence the page spoke")

    narration_cues = srt_windows(NARRATION / "captions.en.srt")
    product_cues: list[tuple[float, float, str]] = []
    for item in speech:
        begins = float(item["timelineSeconds"])
        product_cues.extend(product_speech_cues(str(item["text"]), begins, begins + float(item["seconds"])))
    earcon_cues: list[tuple[float, float, str]] = []
    for item in earcons:
        begins = float(item["timelineSeconds"])
        first_word = min((float(other["timelineSeconds"]) for other in speech
                          if other["turn"] == item["turn"] and float(other["timelineSeconds"]) >= begins),
                         default=begins + 1.5)
        ends = min(begins + max(1.2, float(item["seconds"]) + 0.6), first_word - 0.05)
        if ends - begins >= EARCON_CUE_MIN_SECONDS:
            kind = str(item.get("earconType") or "cue").replace("_", " ").lower()
            earcon_cues.append((round(begins, 3), round(ends, 3), f"[Volcan earcon: {kind}]"))
    all_cues = sorted(narration_cues + product_cues + earcon_cues)
    for (_, first_end, _), (second_start, _, second_text) in zip(all_cues, all_cues[1:]):
        if second_start < first_end - 0.001:
            raise SystemExit(f"caption overlap at {second_start:.3f}s: {second_text!r}")
    burn = OUTPUT / "overlays" / "captions.burn.srt"
    write_srt(burn, [(start, end, burned(text)) for start, end, text in all_cues])
    captions = escaped(burn)
    # libass lays SRT out on a 384x288 canvas; 11 there is about 41 pixels here, and a
    # bottom margin of 12 keeps two lines inside the band under the page.
    style = (
        "FontName=Segoe UI,FontSize=11,PrimaryColour=&H00FFFFFF,"
        "BorderStyle=1,Outline=0,Shadow=0,MarginV=12,Alignment=2"
    )
    tag = text_file("tag.txt", f"Local run of commit {sha7}. Not the public deployment.")
    unrecorded_label = text_file(
        "unrecorded.txt",
        "Not in this recording: the page's own cue and voice for this turn",
    )
    unrecorded = receipt_in.get("unrecordedProductVoice", [])
    muted = "+".join(
        f"between(t,{float(item['fromTimelineSeconds']):.3f},{float(item['toTimelineSeconds']):.3f})"
        for item in unrecorded
    ) or "0"
    filters.append(
        f"[0:v]trim=start={trim_lead}:end={trim_lead + total * video_per_page + 0.2},"
        f"setpts=(PTS-STARTPTS)/{video_per_page:.6f},trim=end={total},"
        f"fps={FPS},scale={PAGE_WIDTH}:{PAGE_HEIGHT}:flags=lanczos,"
        f"pad=1920:1080:{PAGE_X}:0:color={CARD_COLOUR},"
        f"subtitles='{captions}':force_style='{style}',"
        f"drawtext=fontfile='{FONT}':textfile='{tag}':fontcolor=0x9aa4b2:fontsize=20:"
        f"x=w-text_w-24:y=h-text_h-10,"
        f"drawtext=fontfile='{FONT}':textfile='{unrecorded_label}':fontcolor=0xffc857:fontsize=20:"
        f"x=24:y=h-text_h-10:enable='{muted}',"
        f"format=yuv420p[content]"
    )
    title_lines = [line.replace("{sha7}", sha7) for line in cards["title_lines"]]
    outro_lines = [line.replace("{sha7}", sha7) for line in cards["outro_lines"]]
    filters.append(card(title_lines, title_seconds, "title") + ",format=yuv420p[title]")
    filters.append(card(outro_lines, outro_seconds, "outro") + ",format=yuv420p[outro]")
    filters.append("[title][content][outro]concat=n=3:v=1:a=0[v]")
    filters.append(
        f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:normalize=0,"
        f"apad=whole_dur={whole},atrim=0:{whole},"
        f"loudnorm=I=-16:LRA=7:TP=-1.5,aresample=48000,atrim=0:{whole}[a]"
    )
    final = OUTPUT / OUTPUT_NAME
    args.extend(
        [
            "-filter_complex", ";".join(filters),
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            "-t", f"{whole:.3f}",
            str(final),
        ]
    )
    run(args)
    media = probe(final)
    duration = float(media["format"]["duration"])
    streams = media["streams"]
    videos = [item for item in streams if item.get("codec_type") == "video"]
    audios = [item for item in streams if item.get("codec_type") == "audio"]
    if not 90 <= duration < 175 or len(videos) != 1 or len(audios) != 1:
        raise SystemExit("final media contract failed")
    if videos[0].get("width") != 1920 or videos[0].get("height") != 1080:
        raise SystemExit("final video dimensions are not 1920x1080")
    if abs(duration - whole) > FRAME_SECONDS:
        raise SystemExit(
            f"composed {duration:.3f}s but title + narration + outro measure {whole:.3f}s. "
            "Record a longer capture. Do not widen this tolerance."
        )

    # The sync gate's inputs, computed from timing.json only.
    web = scenes[-1]
    screencast_seconds = float(web["startSeconds"])
    before_web = scenes[-2]
    manifest = {
        "fps": FPS,
        "title_dur": title_seconds,
        "screencast_dur": round(screencast_seconds, 3),
        "web_dur": float(web["holdSeconds"]),
        "outro_dur": outro_seconds,
        "a_main": round(float(before_web["startSeconds"]) + float(before_web["durationSeconds"]), 3),
        "vo_delay": title_seconds,
        "have_vo": True,
        "segments": ["title", "screencast", "web", "outro"],
        "_note": "screencast is beats 1 to 5 of the browser capture, web is beat 6; a_main is where the last screencast beat's speech ends",
    }
    (OUTPUT / "video_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    windows = [
        [round(title_seconds + start, 3), round(title_seconds + end, 3), text]
        for start, end, text in all_cues
    ]
    (OUTPUT / "caption_windows.json").write_text(json.dumps(windows, indent=2) + "\n", encoding="utf-8")
    write_srt(OUTPUT / "captions.en.srt", [(start, end, text) for start, end, text in windows])

    ledger = NARRATION / "tts-ledger.jsonl"
    billed = sum(
        json.loads(line)["characters"]
        for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()
    ) if ledger.exists() else None
    digest = hashlib.sha256(final.read_bytes()).hexdigest()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                          text=True).stdout.strip()
    receipt = {
        "schemaVersion": "volcan.video-receipt/v2",
        "file": final.name,
        "recordedSha": release_sha,
        "builtFromHead": head,
        "productCodeUnchangedSinceRecordedSha": product_code_unchanged(release_sha),
        "durationSeconds": round(duration, 3),
        "width": 1920,
        "height": 1080,
        "fps": FPS,
        "pageArea": {"x": PAGE_X, "y": 0, "width": PAGE_WIDTH, "height": PAGE_HEIGHT,
                     "note": "captions, the commit tag and the labels sit in the band under the page"},
        "sceneCount": len(scenes),
        "captionCues": {"narration": len(narration_cues), "productSpeech": len(product_cues),
                        "earcon": len(earcon_cues)},
        "voicedTurns": sorted({str(item["turn"]) for item in product}),
        "unrecordedProductVoice": unrecorded,
        "titleSeconds": title_seconds,
        "narrationSeconds": total,
        "outroSeconds": outro_seconds,
        "sha256": digest,
        "bytes": final.stat().st_size,
        "voice": {"provider": "elevenlabs", **timing["voice"]},
        "charactersInFinalBeats": sum(int(scene["speechCharacters"]) for scene in scenes),
        "charactersSentToElevenLabsTotal": billed,
        "sourceGainsDb": gains,
        "captureSha256": receipt_in["sha256"],
        "captureVideoPerPageSecond": video_per_page,
        "serverHealth": receipt_in["serverHealth"],
        "productAudio": receipt_in["productAudio"],
    }
    (OUTPUT / "video-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: receipt[key] for key in
                      ("file", "recordedSha", "durationSeconds", "sha256", "productCodeUnchangedSinceRecordedSha")}))


def stamp(value: float) -> str:
    millis = round(max(0.0, value) * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    seconds, millis = divmod(millis, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


if __name__ == "__main__":
    main()
