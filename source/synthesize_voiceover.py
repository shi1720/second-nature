#!/usr/bin/env python3
"""Optional local neural narrator with model-derived word timings and captions.

Install kokoro==0.9.4 and soundfile in a separate environment. The first run
downloads the official hexgrad/Kokoro-82M model, its stock voice and English
pronunciation resources. This does not clone or impersonate the project lead.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap


def timestamp(seconds, separator):
    milliseconds = max(0, round(seconds * 1000))
    hours, rest = divmod(milliseconds, 3600000)
    minutes, rest = divmod(rest, 60000)
    seconds, milliseconds = divmod(rest, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02}{separator}{milliseconds:03}"


def caption_groups(words):
    groups, current = [], []
    for word in words:
        if current and (
            len(current) >= 7
            or len(" ".join(w["text"] for w in current + [word])) > 64
            or word["end"] - current[0]["start"] > 3.8
        ):
            groups.append(current)
            current = []
        current.append(word)
        if word["text"].endswith((".", "!", "?", ":", ";")) and len(current) >= 3:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--voice", default="af_heart", choices=["af_heart", "af_bella", "af_sarah"]
    )
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--target-duration", type=float)
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args()
    if args.output.suffix.lower() != ".wav":
        parser.error("Use a .wav output filename")
    if not args.text.is_file():
        parser.error("The narration text file must exist")
    if args.output.resolve() == args.text.resolve():
        parser.error("Keep the transcript and output separate")
    if not math.isfinite(args.speed) or not 0.8 <= args.speed <= 1.2:
        parser.error("Choose a natural speaking speed between 0.8 and 1.2")
    if args.target_duration is not None and (
        not math.isfinite(args.target_duration) or args.target_duration <= 0
    ):
        parser.error("Target duration must be a positive number")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        parser.error("FFmpeg is required")
    if args.cache_dir:
        os.environ["HF_HOME"] = str(args.cache_dir.resolve())
    espeak = Path("/opt/homebrew/lib/libespeak-ng.dylib")
    if espeak.is_file():
        os.environ.setdefault("PHONEMIZER_ESPEAK_LIBRARY", str(espeak))
    import numpy as np
    import soundfile as sf
    import torch
    from kokoro import KPipeline

    torch.set_num_threads(4)
    text = args.text.read_text().strip()
    if not text or "\u2014" in text:
        parser.error("Use nonempty narration without em dashes")
    pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M", device="cpu")
    sample_rate = 24000
    chunks, words = [np.zeros(round(sample_rate * 0.12), dtype=np.float32)], []
    offset = 0.12
    for result in pipeline(
        text, voice=args.voice, speed=args.speed, split_pattern=r"\n+"
    ):
        audio = result.audio.detach().cpu().numpy().reshape(-1)
        active = np.flatnonzero(np.abs(audio) > 0.002)
        if not len(active):
            raise RuntimeError("The speech model produced a silent segment")
        first = max(0, int(active[0]) - round(0.045 * sample_rate))
        last = min(len(audio), int(active[-1]) + round(0.07 * sample_rate))
        trim = first / sample_rate
        audio = audio[first:last]
        segment_duration = len(audio) / sample_rate
        for token in result.tokens or []:
            start, end = getattr(token, "start_ts", None), getattr(
                token, "end_ts", None
            )
            content = token.text.strip()
            if not content:
                continue
            if not any(c.isalnum() for c in content):
                if words:
                    words[-1]["text"] += content
                continue
            if start is None or end is None:
                continue
            start = max(0, min(segment_duration, float(start) - trim))
            end = max(start, min(segment_duration, float(end) - trim))
            if end > start:
                words.append(dict(text=content, start=offset + start, end=offset + end))
        chunks.extend([audio, np.zeros(round(sample_rate * 0.12), dtype=np.float32)])
        offset += segment_duration + 0.12
        print(
            json.dumps(
                {
                    "event": "speech_segment",
                    "text": result.graphemes,
                    "seconds": round(segment_duration, 3),
                }
            ),
            flush=True,
        )
    if not words:
        raise RuntimeError("No model word timings were generated")
    audio = np.concatenate(chunks)
    original_duration = len(audio) / sample_rate
    duration = args.target_duration or original_duration
    tempo = original_duration / duration
    if not 0.85 <= tempo <= 1.18:
        parser.error(
            f"The natural reading is {original_duration:.1f}s. Revise the script or synthesis speed to fit {duration:.1f}s without a large tempo change"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="neural-voice-", dir=args.output.parent
    ) as temporary:
        raw, normalized = (
            Path(temporary) / "raw.wav",
            Path(temporary) / "normalized.wav",
        )
        sf.write(raw, audio, sample_rate, subtype="PCM_16")
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(raw),
                "-af",
                f"atempo={tempo:.9f},apad,atrim=duration={duration:.9f},loudnorm=I=-16:TP=-1.5:LRA=9",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-c:a",
                "pcm_s16le",
                "-metadata",
                f"artist=AI narrator using Kokoro {args.voice}",
                "-metadata",
                "comment=Stock synthetic narrator. No voice cloning or impersonation.",
                str(normalized),
            ],
            check=True,
        )
        normalized.replace(args.output)
    for word in words:
        word["start"] = round(word["start"] / tempo, 3)
        word["end"] = round(min(duration, word["end"] / tempo), 3)
    args.output.with_suffix(".words.json").write_text(
        json.dumps(words, indent=2) + "\n"
    )
    groups = caption_groups(words)
    for extension, separator in [("srt", ","), ("vtt", ".")]:
        lines = ["WEBVTT\n"] if extension == "vtt" else []
        for index, group in enumerate(groups, 1):
            if extension == "srt":
                lines.append(str(index))
            lines.append(
                f"{timestamp(group[0]['start'], separator)} --> {timestamp(group[-1]['end'], separator)}"
            )
            lines.extend(
                textwrap.wrap(
                    " ".join(w["text"] for w in group), width=38, break_long_words=False
                )
            )
            lines.append("")
        args.output.with_suffix("." + extension).write_text("\n".join(lines) + "\n")
    metadata = dict(
        model="hexgrad/Kokoro-82M",
        library="kokoro==0.9.4",
        voice=args.voice,
        model_license="Apache-2.0",
        synthetic_narrator=True,
        voice_cloning=False,
        transcript=text,
        transcript_sha256=hashlib.sha256(text.encode()).hexdigest(),
        duration_seconds=round(duration, 3),
        synthesis_speed=args.speed,
        tempo_adjustment=round(tempo, 6),
        timing_method="Model-predicted token durations, adjusted for silence trimming and final tempo",
        audio_sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
    )
    args.output.with_suffix(".narration.json").write_text(
        json.dumps(metadata, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "event": "speech_complete",
                "file": str(args.output),
                "duration": round(duration, 3),
                "words": len(words),
                "captions": len(groups),
            }
        )
    )


if __name__ == "__main__":
    main()
