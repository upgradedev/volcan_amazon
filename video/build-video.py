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

  1. A title slot and an outro card, whose lines come from video/narration.json with
     {sha7} replaced by the recorded commit. What fills the title slot depends on
     cards.title_slot:
       * absent (the 2026-09-29 take at fc10e7d): a text card with the title lines.
       * starting with "cold_open" (the re-take in video/SHOT_LIST.md): the cold-open
         footage the capture recorded before beat 1, on timeline seconds from minus
         title_seconds to 0, with the title lines in the band under the page and no
         card. The capture receipt's coldOpen block must match title_seconds.
     The outro repeats the provenance. Long card lines are wrapped so none runs off
     the frame. The build writes the video_manifest.json and caption_windows.json that
     scripts/verify_video_sync.py reads, computed from timing.json and the capture
     receipt and nothing else. That gate samples the middle of the title slot and of
     the outro and expects a card in both. With cold-open footage in the title slot the
     unchanged gate fails its order-pixels check there. A closing card with more rows
     than OUTRO_ROWS_MEASURED_AS_CARD fails it too, whatever the title slot holds: the
     plan's outro is 9 rows and measured an edge mean of 7.59 against the gate's 4.5
     (video/README.md, section 4, has the command). The manifest notes both, and the
     build prints them.
  2. A caption band. The page is scaled to 1632x918 at the top of the frame, and
     everything the build adds sits in the 162 pixel band under it: the captions, a
     small tag naming the build and the commit (a local run, or the live build when
     the capture's appUrl is not a local address), and the labels below. Nothing the build adds
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
  7. When the product's sentences were re-rendered in a system voice, the outro line
     "Product voice: the page's own speech." is replaced by one naming that voice.
  8. The receipt records the recorded commit, whether src/ and docs/ are unchanged
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
import urllib.parse

REPO = pathlib.Path(__file__).resolve().parents[1]
SPEC = pathlib.Path(__file__).with_name("narration.json")
ROOT = pathlib.Path(os.environ.get("VOLCAN_VIDEO_ROOT", "").strip() or "VOLCAN_VIDEO_ROOT-is-not-set")
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
# Card lines longer than this are wrapped: about 1,800 pixels at each size in Segoe UI.
CARD_HEADLINE_CHARACTERS = 30
CARD_LINE_CHARACTERS = 90
PAGE_OWN_SPEECH = "Product voice: the page's own speech."
# The 2026-09-29 outro was 5 rows and measured an edge mean of 3.70; the re-take plan's
# outro is 9 rows and measured 7.59 (video/README.md, section 4). The sync gate reads a
# frame above 4.5 as content, so a longer card is reported before the gate is run.
OUTRO_ROWS_MEASURED_AS_CARD = 5
MAX_TRIM_LEAD_SECONDS = 30.0
MAX_COLD_OPEN_LEAD_SECONDS = 180.0
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


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


def wrap(text: str, width: int) -> list[str]:
    rows: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > width:
            rows.append(current)
            current = word
        else:
            current = candidate
    if current:
        rows.append(current)
    return rows or [""]


def card_rows(lines: list[str]) -> list[tuple[str, bool]]:
    """Each card line as the rows it is drawn in, and whether a row is the headline."""
    rows: list[tuple[str, bool]] = []
    for index, line in enumerate(lines):
        width = CARD_HEADLINE_CHARACTERS if index == 0 else CARD_LINE_CHARACTERS
        rows.extend((row, index == 0) for row in wrap(line, width))
    return rows


def card(lines: list[str], seconds: float, name: str) -> str:
    """A flat card: one large line, then smaller ones. Sparse on purpose, because the
    sync gate tells a card from content by how few edges it has."""
    parts = [f"color=c={CARD_COLOUR}:s=1920x1080:r={FPS}:d={seconds}"]
    rows = card_rows(lines)
    y = 400 - 38 * max(0, len(rows) - 3)
    for index, (row, headline) in enumerate(rows):
        size = 110 if headline else 40
        font = FONT_BOLD if headline else FONT
        parts.append(
            f"drawtext=fontfile='{font}':textfile='{text_file(f'{name}-{index}.txt', row)}':"
            f"fontcolor=white:fontsize={size}:x=(w-text_w)/2:y={y}"
        )
        y += 170 if headline else 76
    return ",".join(parts)


def title_slot_is_cold_open(cards: dict[str, object]) -> bool:
    """The re-take puts the cold-open footage in the title slot instead of a card."""
    return str(cards.get("title_slot", "")).startswith("cold_open")


def band_tag(app_url: str, sha7: str) -> str:
    """The grey tag in the band: which build the capture recorded, and its commit."""
    host = (urllib.parse.urlparse(app_url).hostname or "").lower()
    if host in LOCAL_HOSTS or host.endswith(".localhost"):
        return f"Local run of commit {sha7}. Not the public deployment."
    return f"Live build at {host}, commit {sha7}."


def system_voice(product_audio: list[dict[str, object]]) -> str | None:
    """The system voice the product's sentences were re-rendered in, if any."""
    for item in product_audio:
        rendered = str(item.get("renderedWith") or "")
        if item.get("kind") == "speech" and "System.Speech" in rendered:
            found = re.search(r"voice (.+?), rate", rendered)
            return found.group(1) if found else "Windows System.Speech"
    return None


def outro_lines_for(lines: list[str], sha7: str, product_audio: list[dict[str, object]]) -> list[str]:
    """The outro lines with the commit filled in. A line that says the product voice is
    the page's own speech is replaced when the capture re-rendered it in a system voice."""
    filled = [line.replace("{sha7}", sha7) for line in lines]
    voice = system_voice(product_audio)
    if voice is None:
        return filled
    named = (f"Product voice: the page's own sentences, re-rendered in the {voice} system voice "
             "because the capture records no audio.")
    if any(PAGE_OWN_SPEECH in line for line in filled):
        return [line.replace(PAGE_OWN_SPEECH, named) for line in filled]
    if any("system voice" in line or "System.Speech" in line for line in filled):
        return filled
    return [*filled, named]


def video_graph(*, cold_open: bool, title_seconds: float, total: float, trim_lead: float,
                cold_trim_lead: float | None, video_per_page: float, captions: str, style: str,
                tag: str, unrecorded_label: str, muted: str, title_band: str | None,
                title_card: str | None, outro_card: str) -> list[str]:
    """The video filters: the page with its band, the title slot and the outro, in order.

    With a title card, the content is the narration's timeline from trim_lead and the
    card goes before it. With the cold open, the content starts title_seconds earlier,
    at cold_trim_lead, so the footage of the cold open fills the title slot; the title
    lines sit in the band while it plays, and the commit tag takes their place after."""
    if cold_open:
        if cold_trim_lead is None or title_band is None:
            raise SystemExit("the cold open needs its trim lead and the title lines for the band")
        start = cold_trim_lead
        length = title_seconds + total
        tag_enable = f":enable='gte(t,{title_seconds:.3f})'"
        band = (f"drawtext=fontfile='{FONT}':textfile='{title_band}':fontcolor=0xe6eaf0:fontsize=22:"
                f"x=24:y=h-text_h-10:enable='lt(t,{title_seconds:.3f})',")
    else:
        if title_card is None:
            raise SystemExit("the title slot needs a card")
        start = trim_lead
        length = total
        tag_enable = ""
        band = ""
    content = (
        f"[0:v]trim=start={start}:end={start + length * video_per_page + 0.2},"
        f"setpts=(PTS-STARTPTS)/{video_per_page:.6f},trim=end={length},"
        f"fps={FPS},scale={PAGE_WIDTH}:{PAGE_HEIGHT}:flags=lanczos,"
        f"pad=1920:1080:{PAGE_X}:0:color={CARD_COLOUR},"
        f"subtitles='{captions}':force_style='{style}',"
        f"drawtext=fontfile='{FONT}':textfile='{tag}':fontcolor=0x9aa4b2:fontsize=20:"
        f"x=w-text_w-24:y=h-text_h-10{tag_enable},"
        f"{band}"
        f"drawtext=fontfile='{FONT}':textfile='{unrecorded_label}':fontcolor=0xffc857:fontsize=20:"
        f"x=24:y=h-text_h-10:enable='{muted}',"
        f"format=yuv420p[content]"
    )
    outro = outro_card + ",format=yuv420p[outro]"
    if cold_open:
        return [content, outro, "[content][outro]concat=n=2:v=1:a=0[v]"]
    return [content, title_card + ",format=yuv420p[title]", outro,
            "[title][content][outro]concat=n=3:v=1:a=0[v]"]


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


def check_cold_open(cold_open: bool, title_seconds: float, trim_lead: float, video_per_page: float,
                    receipt_in: dict[str, object]) -> float | None:
    """The title slot and the capture must agree: a cold open needs one recorded at the
    same length, and a card slot must not drop a cold open the capture recorded.

    Returns where the cold open starts in the recording, or None for a card slot. The
    lead before beat 1 is bounded: 30 s for a take that starts on its first beat, and
    for the cold open the page load plus the off-camera pull request open, a model call
    the capture waits up to 60 s for, and its spoken answer."""
    recorded = receipt_in.get("coldOpen")
    if not cold_open:
        if not 0 <= trim_lead <= MAX_TRIM_LEAD_SECONDS:
            raise SystemExit("capture trim lead is outside the bounded contract")
        if recorded:
            raise SystemExit("the capture recorded a cold open, but narration.json cards.title_slot "
                             "asks for a title card; the footage would be dropped")
        return None
    if not isinstance(recorded, dict):
        raise SystemExit("narration.json puts the cold open in the title slot, but the capture "
                         "receipt has no coldOpen block; capture the re-take journey first")
    if abs(float(recorded["seconds"]) - title_seconds) > FRAME_SECONDS:
        raise SystemExit(f"the capture recorded a {recorded['seconds']} s cold open, and "
                         f"cards.title_seconds is {title_seconds} s; they must match")
    lead = float(recorded["trimLeadSeconds"])
    if not 0 <= lead <= MAX_COLD_OPEN_LEAD_SECONDS:
        raise SystemExit("the cold open's trim lead is outside the bounded contract")
    if abs(trim_lead - lead - title_seconds * video_per_page) > 0.5:
        raise SystemExit(f"the cold open starts at {lead} s and beat 1 at {trim_lead} s of the recording, "
                         f"which is not {title_seconds} s of page time apart")
    return lead


def main() -> None:
    if not os.environ.get("VOLCAN_VIDEO_ROOT", "").strip():
        raise SystemExit("set VOLCAN_VIDEO_ROOT to the media root the capture wrote")
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
    # The capture measures how many recorded seconds pass per page-clock second
    # between its two marker flips; the picture is retimed by it so an action the
    # page logged at a timeline second is shown at that second.
    video_per_page = float(receipt_in["markers"].get("videoPerPageSecond", 1.0))
    if not 0.95 <= video_per_page <= 1.05:
        raise SystemExit(f"the recording drifted {video_per_page:.6f}x against the page clock; record again")
    cold_open = title_slot_is_cold_open(cards)
    cold_trim_lead = check_cold_open(cold_open, title_seconds, trim_lead, video_per_page, receipt_in)
    # Timeline seconds become seconds of the content stream: with the cold open the
    # stream starts title_seconds before beat 1, so every time moves by that much.
    content_offset = title_seconds if cold_open else 0.0
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
        if item["beat"] == "cold_open":
            closes = 0.0
        else:
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
    write_srt(burn, [(content_offset + start, content_offset + end, burned(text))
                     for start, end, text in all_cues])
    captions = escaped(burn)
    # libass lays SRT out on a 384x288 canvas; 11 there is about 41 pixels here, and a
    # bottom margin of 12 keeps two lines inside the band under the page.
    style = (
        "FontName=Segoe UI,FontSize=11,PrimaryColour=&H00FFFFFF,"
        "BorderStyle=1,Outline=0,Shadow=0,MarginV=12,Alignment=2"
    )
    tag = text_file("tag.txt", band_tag(str(receipt_in.get("appUrl") or ""), sha7))
    unrecorded_label = text_file(
        "unrecorded.txt",
        "Not in this recording: the page's own cue and voice for this turn",
    )
    unrecorded = receipt_in.get("unrecordedProductVoice", [])
    muted = "+".join(
        f"between(t,{content_offset + float(item['fromTimelineSeconds']):.3f},"
        f"{content_offset + float(item['toTimelineSeconds']):.3f})"
        for item in unrecorded
    ) or "0"
    title_lines = [line.replace("{sha7}", sha7) for line in cards["title_lines"]]
    outro_lines = outro_lines_for(list(cards["outro_lines"]), sha7, receipt_in["productAudio"])
    filters.extend(video_graph(
        cold_open=cold_open, title_seconds=title_seconds, total=total, trim_lead=trim_lead,
        cold_trim_lead=cold_trim_lead, video_per_page=video_per_page, captions=captions,
        style=style, tag=tag, unrecorded_label=unrecorded_label, muted=muted,
        title_band=text_file("title-band.txt", "   ".join(title_lines)) if cold_open else None,
        title_card=None if cold_open else card(title_lines, title_seconds, "title"),
        outro_card=card(outro_lines, outro_seconds, "outro"),
    ))
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
        "title_slot": "cold_open_footage" if cold_open else "card",
        "_note": "screencast is beats 1 to 5 of the browser capture, web is beat 6; a_main is where the last screencast beat's speech ends",
    }
    if cold_open:
        manifest["_title_note"] = (
            "the title segment holds the cold-open footage, not a card. "
            "scripts/verify_video_sync.py samples the middle of the title segment as a card, "
            "so its order-pixels check fails on this video until the gate learns the cold open")
    outro_rows = len(card_rows(outro_lines))
    if outro_rows > OUTRO_ROWS_MEASURED_AS_CARD:
        manifest["_outro_note"] = (
            f"the outro card is {outro_rows} rows. The 2026-09-29 outro was "
            f"{OUTRO_ROWS_MEASURED_AS_CARD} rows and measured an edge mean of 3.70; the re-take "
            "plan's 9-row outro measured 7.59. scripts/verify_video_sync.py reads a frame above 4.5 "
            "as content, so its order-pixels check is expected to fail at the outro probe too, "
            "with a title card or with the cold open. video/README.md, section 4, has the "
            "measuring command")
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
        "titleSlot": "cold_open_footage" if cold_open else "card",
        "coldOpen": receipt_in.get("coldOpen"),
        "outroLines": outro_lines,
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
    if cold_open:
        print("note: the title slot holds the cold-open footage; the unchanged sync gate samples it "
              "as a card and fails order-pixels on this video")
    if "_outro_note" in manifest:
        print("note: " + str(manifest["_outro_note"]))


def stamp(value: float) -> str:
    millis = round(max(0.0, value) * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    seconds, millis = divmod(millis, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


if __name__ == "__main__":
    main()
