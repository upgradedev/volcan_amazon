#!/usr/bin/env python3
"""Synthesize each narration beat on its own, measure it, and write the timing.

Adapted from the submission kit's video pipeline (video/generate-narration.py in
the kit). The timing model is the kit's and is unchanged: every beat is
synthesized separately, its real length is measured with ffprobe, and the beat
holds for that length plus a fixed 0.65 second tail. Nothing downstream invents a
timestamp.

What this copy changes, so it reads Volcan's own video/narration.json:

  1. Beats come from the "beats" list (beat_id, narration_text, speech_text)
     instead of the kit's "segments" list. narration_text is the caption a viewer
     reads; speech_text, when present, is what the voice pronounces.
  2. The voice comes from the "tts" block. Only ElevenLabs is wired here.
  3. A beat may carry "product_sound_seconds": a silent stretch for the narrator
     after the beat's speech, in which the page itself makes its sound (the
     earcon and the browser's speech). It is added to the beat's hold, never to
     its captions, and must be backed by a "product_sound_basis" that says how it
     was measured.
  4. timing.json also records each caption sentence's window inside the beat, so
     the capture can press a button on the sentence that talks about it, and the
     number of characters sent to the text to speech provider on this run. Every
     paid call is also appended to narration/tts-ledger.jsonl in the media root,
     so re-rolls are counted too.
  5. --write-timestamps copies the measured beat windows back into
     video/narration.json, offset by the title card and, when cards.title_slot
     plays a cold open after the card, by cold_open.seconds too, so the repository's own
     scripts/synthesize_video_assets.py regenerates the cue sheet and subtitles
     from measured numbers instead of authored ones.

Kept from the kit: per-beat caching keyed on the speech text plus the voice
settings (ElevenLabs does not return identical audio for identical input, so
re-rolling unchanged beats would move every offset), NARRATION_FORCE, the 3 to 40
second beat limit and the 90 to 174 second total.

Environment:
  VOLCAN_VIDEO_ROOT   media root, outside git. narration/ is written under it.
  FFPROBE             path to ffprobe.
  ELEVENLABS_API_KEY  the key. Read, never printed, never written anywhere.
  NARRATION_FORCE     optional: comma separated beat ids to re-synthesize, or all.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request


SPEC = pathlib.Path(__file__).with_name("narration.json")
TAIL_SECONDS = 0.65
MAX_PRODUCT_SOUND_SECONDS = 30.0

ELEVENLABS_KEY_ENV_NAMES = ("ELEVENLABS_API_KEY", "XI_API_KEY", "ELEVEN_LABS_KEY")


def root() -> pathlib.Path:
    value = os.environ.get("VOLCAN_VIDEO_ROOT", "").strip()
    if not value:
        raise SystemExit("set VOLCAN_VIDEO_ROOT to a media directory outside the repository")
    return pathlib.Path(value)


def run(args: list[str]) -> str:
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def duration(path: pathlib.Path) -> float:
    return float(
        run(
            [
                os.environ["FFPROBE"],
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ]
        )
    )


def timestamp(value: float) -> str:
    millis = round(max(0.0, value) * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    seconds, millis = divmod(millis, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def wrapped(text: str, width: int = 66) -> str:
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if line and len(candidate) > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    if len(lines) <= 2:
        return "\n".join(lines)
    midpoint = max(1, len(words) // 2)
    return " ".join(words[:midpoint]) + "\n" + " ".join(words[midpoint:])


def elevenlabs_key() -> str:
    for name in ELEVENLABS_KEY_ENV_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    raise SystemExit("no ElevenLabs key: set one of " + ", ".join(ELEVENLABS_KEY_ENV_NAMES))


def elevenlabs_config(spec: dict[str, object]) -> dict[str, str]:
    tts = spec.get("tts")
    if not isinstance(tts, dict) or tts.get("provider") != "elevenlabs":
        raise SystemExit("narration.json needs a tts block with provider elevenlabs")
    config = tts.get("elevenLabs")
    if not isinstance(config, dict):
        raise SystemExit("the tts block has no elevenLabs settings")
    voice_id = str(config.get("voiceId", ""))
    model_id = str(config.get("modelId", "eleven_multilingual_v2"))
    output_format = str(config.get("outputFormat", "mp3_44100_128"))
    if not re.fullmatch(r"[A-Za-z0-9]{16,40}", voice_id):
        raise SystemExit("tts.elevenLabs.voiceId is missing or malformed")
    if not re.fullmatch(r"[a-z0-9_]{4,40}", model_id):
        raise SystemExit("tts.elevenLabs.modelId is malformed")
    if not re.fullmatch(r"[a-z0-9_]{4,32}", output_format):
        raise SystemExit("tts.elevenLabs.outputFormat is malformed")
    return {"voiceId": voice_id, "modelId": model_id, "outputFormat": output_format}


def synthesize_elevenlabs(text: str, config: dict[str, str], retries: int = 3) -> bytes:
    """The request body and retry loop are the kit's ElevenLabs provider, unchanged."""
    key = elevenlabs_key()
    url = (
        f"https://api.elevenlabs.io/v1/text-to-speech/{config['voiceId']}"
        f"?output_format={config['outputFormat']}"
    )
    body = json.dumps(
        {
            "text": text,
            "model_id": config["modelId"],
            "voice_settings": {
                "stability": 0.45,
                "similarity_boost": 0.8,
                "use_speaker_boost": True,
            },
        }
    ).encode("utf-8")
    last: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                url,
                data=body,
                headers={
                    "xi-api-key": key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
            )
            with urllib.request.urlopen(request, timeout=90) as response:
                data = response.read()
            if len(data) < 3000:
                raise RuntimeError(f"tiny audio ({len(data)} bytes)")
            return data
        except urllib.error.HTTPError as error:
            # The body names the failure; it never contains the key.
            last = RuntimeError(f"HTTP {error.code}")
        except Exception as error:  # noqa: BLE001
            last = error
        time.sleep(2 * (attempt + 1))
    raise SystemExit(f"ElevenLabs failed after {retries} tries: {last}")


def cache_key(speech: str, config: dict[str, str]) -> str:
    payload = json.dumps(
        {"provider": "elevenlabs", "speech": speech, "voice": config},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cached_key(sidecar: pathlib.Path) -> str | None:
    try:
        recorded = json.loads(sidecar.read_text(encoding="utf-8")).get("cacheKey")
    except (OSError, ValueError):
        return None
    return recorded if isinstance(recorded, str) else None


def product_sound(beat: dict[str, object], identifier: str) -> float:
    value = beat.get("product_sound_seconds")
    if value is None:
        return 0.0
    if not isinstance(value, (int, float)) or not 0 < float(value) <= MAX_PRODUCT_SOUND_SECONDS:
        raise SystemExit(f"{identifier}: product_sound_seconds must be in (0, {MAX_PRODUCT_SOUND_SECONDS}]")
    basis = beat.get("product_sound_basis")
    if not isinstance(basis, str) or len(basis) < 40:
        raise SystemExit(f"{identifier}: product_sound_seconds needs a product_sound_basis saying how it was measured")
    return float(value)


def lead_seconds(spec: dict[str, object]) -> float:
    """Video seconds before beat 1: the title card, and the cold open when one follows it."""
    cards = spec.get("cards") or {}
    lead = float(cards.get("title_seconds", 0.0))
    if str(cards.get("title_slot", "")).startswith("card_then_cold_open"):
        lead += float((spec.get("cold_open") or {}).get("seconds", 0.0))
    return lead


def main() -> None:
    write_back = "--write-timestamps" in sys.argv[1:]
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    beats = spec.get("beats")
    if not isinstance(beats, list) or not beats:
        raise SystemExit("narration.json has no beats")
    config = elevenlabs_config(spec)
    forced = {item.strip() for item in os.environ.get("NARRATION_FORCE", "").split(",") if item.strip()}
    out = root() / "narration"
    out.mkdir(parents=True, exist_ok=True)
    timing: list[dict[str, object]] = []
    cues: list[tuple[float, float, str]] = []
    offset = 0.0
    characters_sent = 0
    for index, beat in enumerate(beats, start=1):
        identifier = beat.get("beat_id")
        caption = beat.get("narration_text")
        speech = beat.get("speech_text") or caption
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-z][a-z0-9_]{2,40}", identifier):
            raise SystemExit("beat_id is invalid")
        if not all(isinstance(value, str) and 20 <= len(value) <= 800 for value in (speech, caption)):
            raise SystemExit(f"beat text is invalid: {identifier}")
        if "<" in f"{speech}{caption}" or ">" in f"{speech}{caption}":
            raise SystemExit(f"beat {identifier} still contains a <PLACEHOLDER>")
        extra = product_sound(beat, identifier)
        audio = out / f"{index:02d}-{identifier}.mp3"
        sidecar = out / f"{index:02d}-{identifier}.cache.json"
        key = cache_key(speech, config)
        reuse = (
            identifier not in forced
            and "all" not in forced
            and audio.is_file()
            and cached_key(sidecar) == key
        )
        if reuse:
            print(f"reused {audio.name}")
        else:
            audio.write_bytes(synthesize_elevenlabs(speech, config))
            characters_sent += len(speech)
            with (out / "tts-ledger.jsonl").open("a", encoding="utf-8") as ledger:
                ledger.write(json.dumps({
                    "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "beat": identifier,
                    "characters": len(speech),
                    "voiceId": config["voiceId"],
                }) + "\n")
            sidecar.write_text(
                json.dumps(
                    {"cacheKey": key, "provider": "elevenlabs", "characters": len(speech)},
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            print(f"synthesized {audio.name} ({len(speech)} characters)")
        seconds = duration(audio)
        if seconds < 3 or seconds > 40:
            raise SystemExit(f"beat audio duration is unsafe: {identifier} measured {seconds:.3f}s")
        hold = seconds + TAIL_SECONDS + extra
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", caption) if part.strip()]
        weight = sum(len(part) for part in sentences) or 1
        cursor = 0.0
        windows: list[dict[str, object]] = []
        for sentence in sentences:
            share = seconds * len(sentence) / weight
            cues.append((offset + cursor, offset + cursor + share, wrapped(sentence)))
            windows.append(
                {"start": round(cursor, 3), "end": round(cursor + share, 3), "text": sentence}
            )
            cursor += share
        timing.append(
            {
                "id": identifier,
                "audio": audio.name,
                "durationSeconds": round(seconds, 3),
                "productSoundSeconds": round(extra, 3),
                "holdSeconds": round(hold, 3),
                "startSeconds": round(offset, 3),
                "speechCharacters": len(speech),
                "sentences": windows,
            }
        )
        offset += hold
    if not 90 <= offset < 175:
        raise SystemExit(f"narration must be 90-174 seconds, observed {offset:.3f}")
    (out / "timing.json").write_text(
        json.dumps(
            {
                "schemaVersion": "volcan.video-timing/v1",
                "voice": config,
                "tailSeconds": TAIL_SECONDS,
                "totalSeconds": round(offset, 3),
                "charactersSentThisRun": characters_sent,
                "scenes": timing,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    srt: list[str] = []
    for number, (start, end, text) in enumerate(cues, start=1):
        srt.extend([str(number), f"{timestamp(start)} --> {timestamp(end)}", text, ""])
    (out / "captions.en.srt").write_text("\n".join(srt), encoding="utf-8")
    if write_back:
        cards = spec.get("cards") or {}
        title = lead_seconds(spec)
        outro = float(cards.get("outro_seconds", 0.0))
        for beat, scene in zip(beats, timing):
            beat["timestamp_start"] = round(title + float(scene["startSeconds"]), 3)
            beat["timestamp_end"] = round(
                title + float(scene["startSeconds"]) + float(scene["holdSeconds"]), 3
            )
        spec["target_duration_seconds"] = round(title + offset + outro, 3)
        SPEC.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote measured beat windows back to {SPEC.name}")
    print(f"Generated {len(timing)} scenes across {offset:.3f} seconds; "
          f"{characters_sent} characters sent to ElevenLabs on this run")


if __name__ == "__main__":
    main()
