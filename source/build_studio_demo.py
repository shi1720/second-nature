#!/usr/bin/env python3
"""Assemble the actual 80-second Second Nature product demonstration.

Default: validate required inputs only. --layout-preview produces a work-only
contact sheet from available evidence. --render is the explicit publication
step and requires completed cloud QA, the real completed UI and Blue hour movie.
No UI, cursor, worker result or browser action is simulated.
"""
from __future__ import annotations
import argparse
import bisect
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import textwrap
import wave

HERE = Path(__file__).resolve()
ROOT = (
    HERE.parents[1]
    if HERE.parent.name == "source"
    else HERE.parent.parent / "outputs/second-nature"
)
WORK = (
    ROOT / ".demo-build"
    if HERE.parent.name == "source"
    else HERE.parent / "studio-demo-edit"
)
WIDTH, HEIGHT, FPS, SECONDS = 1920, 1080, 24, 80
NAVY, INK, CREAM, CORAL, MUTED = "#0C252E", "#071E29", "#F5F0E6", "#E7926D", "#ABC3BF"
CAPTION_TOP = 930
FONT = ROOT / "assets/fonts/SpaceGrotesk.ttf"
VOICE = ROOT / "film/studio-demo-narration.wav"
CAPTIONS = ROOT / "film/studio-demo-narration.srt"
CHAPTERS = ROOT / "film/studio-demo-narration.chapters.json"


@dataclass(frozen=True)
class Shot:
    start: float
    end: float
    key: str
    source: str
    layout: str
    kicker: str
    title: str
    body: str = ""
    source_start: float = 0
    capture: bool = False

    @property
    def frames(self):
        return round(self.end * FPS) - round(self.start * FPS)

    @property
    def duration(self):
        return self.frames / FPS

    @property
    def path(self):
        return ROOT / self.source


def read_chapters():
    chapters = json.loads(CHAPTERS.read_text())
    expected = [
        "Introduction",
        "Featured film",
        "Guest and palette",
        "Create film",
        "Progress and resume",
        "Playback and downloads",
        "Credits",
        "Closing",
    ]
    if [c["title"] for c in chapters] != expected:
        raise ValueError(
            "The narrator chapter map changed. Review the picture edit before rendering."
        )
    if abs(chapters[-1]["end"] - SECONDS) > 0.001:
        raise ValueError("The narration must cover exactly 80 seconds.")
    for a, b in zip(chapters, chapters[1:]):
        if abs(a["end"] - b["start"]) > 0.001:
            raise ValueError("Narration chapters must be contiguous.")
    return {c["title"]: c["start"] for c in chapters}


def timeline():
    c = read_chapters()
    still = "stills/"
    film = "film/"
    return [
        Shot(
            0,
            c["Featured film"],
            "intro",
            still + "studio.png",
            "ui",
            "01 / THE STUDIO",
            "One idea.\nA whole workflow.",
            "A directed visual story, with a repeatable production process.",
        ),
        Shot(
            c["Featured film"],
            11.099,
            "seed",
            film + "second-nature.mp4",
            "film",
            "THE ORIGINAL / LOCALLY RENDERED",
            "A reason to arrive.",
            source_start=0,
        ),
        Shot(
            11.099,
            12.35,
            "chase",
            film + "second-nature.mp4",
            "film",
            "THE ORIGINAL / 1080P",
            "One drop. A world in motion.",
            source_start=3.1,
        ),
        Shot(
            12.35,
            13.599,
            "loop",
            film + "second-nature.mp4",
            "film",
            "THE ORIGINAL / 1080P",
            "Purposeful speed.",
            source_start=7.1,
        ),
        Shot(
            13.599,
            17.04,
            "arrival",
            film + "second-nature.mp4",
            "film",
            "THE ORIGINAL / 1080P",
            "A breath of stillness.",
            source_start=11.65,
        ),
        Shot(
            17.04,
            c["Guest and palette"],
            "bloom",
            film + "second-nature.mp4",
            "film",
            "THE ORIGINAL / 1080P",
            "Then, growth.",
            source_start=17.05,
        ),
        Shot(
            c["Guest and palette"],
            22.2,
            "account",
            still + "studio-account.png",
            "ui",
            "02 / KEEP YOUR WORKSPACE",
            "Begin as a guest.\nKeep the idea.",
            "Link an account to retain access across devices.",
        ),
        Shot(
            22.2,
            24.719,
            "guest",
            still + "studio-mobile.png",
            "mobile",
            "YOUR WORKSPACE / ACROSS DEVICES",
            "Start in\nyour browser.",
            "Guest access to explore.\nAn account to keep access across devices.",
        ),
        Shot(
            24.719,
            29.4,
            "palette",
            "assets/demo/palette.mp4",
            "ui-video",
            "ACTUAL BROWSER CAPTURE",
            "A palette.\nA consistent seed.",
            "Drop and enamel colors.\nA detail seed for the soil.",
            capture=True,
        ),
        Shot(
            29.4,
            35.85,
            "save",
            still + "studio-running.png",
            "ui",
            "SAVED PRODUCTION / BLUE HOUR",
            "Save the idea.\nCreate the film.",
            "Blue hour follows the saved palette and seed.\nProduction stages are edited for time.",
        ),
        Shot(
            35.85,
            39.304,
            "blender",
            still + "blender-wip.png",
            "ui",
            "03 / EDITABLE BLENDER SCENE",
            "Built with\nintention.",
            "Procedural geometry.\nBaked motion.\nAn editable Blender file.",
        ),
        Shot(
            39.304,
            c["Progress and resume"],
            "running",
            still + "studio-running.png",
            "ui",
            "ACTUAL CLOUD WORKBENCH",
            "Every frame\nhas a record.",
            "Real worker progress and production logs.",
        ),
        Shot(
            c["Progress and resume"],
            46.738,
            "progress",
            "assets/demo/progress.mp4",
            "ui-video",
            "ACTUAL BROWSER CAPTURE",
            "Follow the\nproduction.",
            "The worker continues when the page is closed.",
            capture=True,
        ),
        Shot(
            46.738,
            49.883,
            "cancelled",
            still + "studio-cancelled.png",
            "ui",
            "EARLIER CANCELLATION TEST / 17 FRAMES SAVED",
            "Stop safely.",
            "This genuine cancellation test preserved its completed frames.",
        ),
        Shot(
            49.883,
            c["Playback and downloads"],
            "resumed",
            still + "studio-running.png",
            "ui",
            "ACTUAL RESUMED PRODUCTION",
            "Keep the\ncompleted work.",
            "The acceptance run restored 17 frames and resumed at frame 18.",
        ),
        Shot(
            c["Playback and downloads"],
            58.6,
            "complete",
            still + "studio-complete.png",
            "ui",
            "04 / VERIFIED CLOUD DELIVERY",
            "Watch it.\nKeep creating.",
            "Play the actual variant.\nDownload the movie or Blender scene.",
        ),
        Shot(
            58.6,
            63.7,
            "blue-hour",
            film + "blue-hour-preview.mp4",
            "film",
            "BLUE HOUR / ACTUAL CLOUD EXPORT / 540P",
            "Your palette, in motion.",
            source_start=2.2,
        ),
        Shot(
            63.7,
            c["Credits"],
            "retention",
            still + "studio-complete.png",
            "ui",
            "GENERATED EXPORTS / SEVEN-DAY LIFECYCLE",
            "Keep the files\nyou value.",
            "Download the movie and editable scene.\nGenerated exports and frames expire.",
        ),
        Shot(
            c["Credits"],
            c["Closing"],
            "credits",
            still + "bloom.jpg",
            "credits",
            "CREATED FOR SECOND NATURE",
            "Shivam Gupta",
            "Project lead\n\nAI assistance: OpenAI Codex\nStock synthetic narrator: Kokoro af_heart\nOriginal procedural film and synthesized soundtrack",
        ),
        Shot(
            c["Closing"],
            80,
            "closing",
            still + "poster.jpg",
            "closing",
            "SECOND NATURE STUDIO",
            "Make every\nsecond grow.",
            "second-nature-studio.web.app",
        ),
    ]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def local_name(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return Path(path).name


def probe(path, count=False):
    command = ["ffprobe", "-v", "error"]
    if count:
        command += ["-count_frames"]
    command += [
        "-show_entries",
        "stream=codec_type,codec_name,width,height,r_frame_rate,nb_read_frames,sample_rate,channels,pix_fmt:format=duration",
        "-of",
        "json",
        str(path),
    ]
    return json.loads(subprocess.check_output(command, text=True))


def validate(shots, full=False):
    from PIL import Image

    missing = []
    required = [
        FONT,
        VOICE,
        CAPTIONS,
        CHAPTERS,
        ROOT / "film/studio-demo-narration.vtt",
        ROOT / "film/studio-demo-narration.narration.json",
        ROOT / "film/studio-demo-narration.verification.json",
        ROOT / "docs/studio-demo-script.txt",
    ]
    for p in dict.fromkeys(required + [s.path for s in shots]):
        if not p.is_file():
            missing.append(local_name(p))
    checks = {
        "timeline_frames_1920": sum(s.frames for s in shots) == 1920,
        "contiguous_timeline": all(
            abs(a.end - b.start) < 1e-6 for a, b in zip(shots, shots[1:])
        ),
        "positive_shots": all(s.frames > 0 for s in shots),
        "required_assets_present": not missing,
    }
    for s in shots:
        if not s.path.is_file():
            continue
        if s.capture:
            media = probe(s.path, count=full)
            video = next(
                (x for x in media.get("streams", []) if x.get("codec_type") == "video"),
                {},
            )
            if video.get("r_frame_rate") != "24/1":
                raise ValueError(
                    f"Capture must retain the packaged 24fps clock: {s.key}"
                )
            metadata = s.path.with_suffix(".provenance.json")
            if not metadata.is_file():
                missing.append(local_name(metadata))
            elif json.loads(metadata.read_text()).get("video_sha256") != sha(s.path):
                raise ValueError(f"Capture asset hash differs from provenance: {s.key}")
        elif s.path.suffix.lower() in (".png", ".jpg", ".jpeg"):
            with Image.open(s.path) as im:
                im.verify()
    checks["required_assets_present"] = not missing
    if VOICE.is_file():
        with wave.open(str(VOICE), "rb") as voice:
            checks["voice_80s_stereo_48khz"] = (
                voice.getnframes() == 80 * 48000
                and voice.getframerate() == 48000
                and voice.getnchannels() == 2
            )
        metadata_path = VOICE.with_suffix(".narration.json")
        if metadata_path.is_file():
            narration = json.loads(metadata_path.read_text())
            checks["approved_voice_hash"] = narration.get("audio_sha256") == sha(VOICE)
            verification_path = VOICE.with_suffix(".verification.json")
            if verification_path.is_file():
                verified = json.loads(verification_path.read_text())
                checks["voice_verification_matches"] = verified.get(
                    "passed"
                ) is True and verified.get("audio_sha256") == sha(VOICE)
    if CAPTIONS.is_file():
        srt = CAPTIONS.read_text()
        checks["caption_copy_clean"] = (
            "\u2014" not in srt and "hackathon" not in srt.lower()
        )
        checks["readable_caption_lines"] = all(
            len(line) <= 38
            for block in srt.strip().split("\n\n")
            for line in block.splitlines()[2:]
        )
        cues = read_captions(CAPTIONS)
        normalize = lambda value: re.findall(r"[a-z0-9]+", value.casefold())
        script_path = ROOT / "docs/studio-demo-script.txt"
        if script_path.is_file():
            checks["captions_match_script"] = normalize(
                " ".join(cue["text"] for cue in cues)
            ) == normalize(script_path.read_text())
        checks["approved_caption_count"] = len(cues) == 28
    qa_path = ROOT / "cloud/qa-report.json"
    qa = json.loads(qa_path.read_text()) if qa_path.is_file() else {}
    checks["full_cloud_delivery_verified"] = qa.get("full_verified") is True
    for s in shots:
        if s.layout == "film" and s.path.is_file():
            data = probe(s.path, count=full and s.key == "blue-hour")
            duration = float(data["format"]["duration"])
            if duration + 1 / FPS < s.source_start + s.duration:
                raise ValueError(f"Video excerpt exceeds source duration: {s.key}")
            if s.key == "blue-hour":
                video = next(
                    (
                        x
                        for x in data.get("streams", [])
                        if x.get("codec_type") == "video"
                    ),
                    {},
                )
                checks["cloud_movie_24s_540p"] = (
                    abs(duration - 24) < 0.01
                    and video.get("width") == 960
                    and video.get("height") == 540
                )
                if full:
                    checks["cloud_movie_576_decoded_frames"] = (
                        video.get("nb_read_frames") == "576"
                    )
    return {
        "ready": all(checks.values()),
        "checks": checks,
        "missing": missing,
        "shots": len(shots),
        "frames": sum(s.frames for s in shots),
    }


def font(size):
    from PIL import ImageFont

    return ImageFont.truetype(str(FONT), size)


def text(draw, xy, body, size, color=CREAM, spacing=10):
    draw.multiline_text(xy, body, font=font(size), fill=color, spacing=spacing)


def fit(image, size):
    from PIL import Image, ImageOps

    return ImageOps.contain(image, size, method=Image.Resampling.LANCZOS)


def base(shot):
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (WIDTH, HEIGHT), NAVY)
    d = ImageDraw.Draw(im)
    # Quiet graphic structure, with space reserved for the real UI and captions.
    d.ellipse((1420, -600, 2320, 300), outline="#183B44", width=2)
    d.line((64, 87, 1856, 87), fill="#28444C", width=1)
    text(d, (64, 36), "SECOND NATURE", 23)
    text(d, (1370, 39), "A FILM. A REPEATABLE PROCESS.", 16, MUTED)
    d.rectangle((64, 112, 112, 116), fill=CORAL)
    return im


def screenshot(image, rect, crop=None):
    from PIL import Image

    im = Image.open(image).convert("RGB")
    if crop:
        im = im.crop(
            tuple(
                round(v * s)
                for v, s in zip(crop, (im.width, im.height, im.width, im.height))
            )
        )
    panel = Image.new("RGB", (rect[2], rect[3]), "#F5F0E6")
    pic = fit(im, panel.size)
    panel.paste(pic, ((panel.width - pic.width) // 2, (panel.height - pic.height) // 2))
    return panel


def compose(shot, source=None):
    from PIL import Image, ImageDraw, ImageFilter, ImageOps

    im = base(shot)
    d = ImageDraw.Draw(im)
    source = source or shot.path
    if shot.layout in ("ui", "ui-video", "mobile"):
        text(d, (64, 160), shot.kicker, 17, CORAL)
        text(d, (64, 221), shot.title, 49, spacing=8)
        body = "\n".join(
            "\n".join(textwrap.wrap(line, width=29)) for line in shot.body.splitlines()
        )
        text(d, (66, 440), body, 24, MUTED, 12)
        text(d, (66, 822), "second-nature-studio.web.app", 18, CREAM)
        if shot.layout == "mobile":
            rect = (1124, 150, 323, 700)
            # A genuine desktop companion, not a synthesized responsive view.
            desktop = screenshot(ROOT / "stills/studio.png", (0, 0, 860, 458))
            im.paste(desktop, (560, 267))
            shadow = Image.new("RGBA", (363, 740))
            ImageDraw.Draw(shadow).rounded_rectangle(
                (18, 18, 345, 721), radius=32, fill="#000000AA"
            )
            shadow = shadow.filter(ImageFilter.GaussianBlur(12))
            im.paste(shadow, (1104, 130), shadow)
        else:
            rect = (544, 157, 1312, 699)
        shadow = Image.new("RGBA", (rect[2] + 32, rect[3] + 32))
        ImageDraw.Draw(shadow).rounded_rectangle(
            (10, 10, rect[2] + 22, rect[3] + 22), radius=18, fill="#00000077"
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(8))
        im.paste(shadow, (rect[0] - 16, rect[1] - 8), shadow)
        panel = screenshot(source, rect)
        im.paste(panel, (rect[0], rect[1]))
        d = ImageDraw.Draw(im)
        d.rectangle(
            (rect[0], rect[1], rect[0] + rect[2], rect[1] + rect[3]),
            outline="#67827E",
            width=1,
        )
        text(
            d,
            (rect[0], 878),
            (
                "ACTUAL APPLICATION CAPTURE"
                if shot.key != "blender"
                else "AUTHENTIC BLENDER WORK IN PROGRESS"
            ),
            15,
            MUTED,
        )
        text(d, (1178, 900), "Production stages edited for time", 17, CREAM)
    elif shot.layout == "credits":
        pic = ImageOps.fit(
            Image.open(source).convert("RGB"), (970, 795), centering=(0.69, 0.45)
        )
        im.paste(pic, (886, 120))
        d = ImageDraw.Draw(im)
        # A local gradient protects typography without manufacturing scene content.
        fade = Image.new("RGBA", (WIDTH, HEIGHT))
        for x in range(1030):
            ImageDraw.Draw(fade).line(
                (x, 120, x, 920),
                fill=(
                    *tuple(int(NAVY[i : i + 2], 16) for i in (1, 3, 5)),
                    max(0, 255 - int(x / 1030 * 255)),
                ),
            )
        im = Image.alpha_composite(im.convert("RGBA"), fade).convert("RGB")
        d = ImageDraw.Draw(im)
        text(d, (64, 164), shot.kicker, 17, CORAL)
        text(d, (64, 242), shot.title, 64)
        text(d, (68, 350), shot.body, 25, MUTED, 15)
        text(d, (68, 828), "Original direction. Transparent assistance.", 20, CREAM)
    elif shot.layout == "closing":
        im = (
            Image.open(source)
            .convert("RGB")
            .resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        )
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, WIDTH, 148), fill=NAVY)
        text(d, (64, 36), "SECOND NATURE STUDIO", 23)
        text(d, (1120, 39), "second-nature-studio.web.app", 24)
        d.rectangle((64, 112, 112, 116), fill=CORAL)
    return im


def run(args):
    subprocess.run([str(x) for x in args], check=True)


def encode_static(shot, index, directory):
    image = directory / f"{index:02d}-{shot.key}.png"
    compose(shot).save(image)
    output = directory / f"{index:02d}-{shot.key}.mp4"
    # Restrain the zoom to 1.2 percent; no cursor, clicks or UI state are animated.
    motion = f"zoompan=z='1+0.012*on/{max(1,shot.frames-1)}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={shot.frames}:s={WIDTH}x{HEIGHT}:fps={FPS},format=yuv420p"
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            image,
            "-vf",
            motion,
            "-frames:v",
            shot.frames,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "17",
            "-threads",
            "4",
            output,
        ]
    )
    return output


def first_capture_frame(path, directory):
    # A capture can be replaced under the same filename during an edit. Key the
    # cached still by its actual bytes so the matte and layout proof stay current.
    capture_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    target = directory / (path.stem + "-" + capture_hash[:16] + "-first-frame.png")
    if not target.is_file():
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                path,
                "-frames:v",
                "1",
                target,
            ]
        )
    return target


def encode_capture(shot, index, directory):
    image = directory / f"{index:02d}-{shot.key}-matte.png"
    compose(shot, first_capture_frame(shot.path, directory)).save(image)
    output = directory / f"{index:02d}-{shot.key}.mp4"
    # Native recording plays once at its original clock; only its final real
    # frame is held when the narration allocates more time. No looping actions.
    filters = f"[1:v]format=rgb24,scale=1312:699:force_original_aspect_ratio=decrease,pad=1312:699:(ow-iw)/2:(oh-ih)/2:color=0xf5f0e6,tpad=stop_mode=clone:stop_duration={shot.duration+1}[ui];[0:v][ui]overlay=544:157,format=yuv420p[v]"
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-loop",
            "1",
            "-framerate",
            FPS,
            "-i",
            image,
            "-i",
            shot.path,
            "-filter_complex",
            filters,
            "-map",
            "[v]",
            "-frames:v",
            shot.frames,
            "-r",
            FPS,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "17",
            "-threads",
            "4",
            output,
        ]
    )
    return output


def encode_movie(shot, index, directory):
    from PIL import Image, ImageDraw

    overlay = Image.new("RGBA", (WIDTH, HEIGHT))
    d = ImageDraw.Draw(overlay)
    # Only the presentation chrome is added; the film image is genuine footage.
    d.rectangle(
        (0, 0, WIDTH, 115),
        fill=(*tuple(int(INK[i : i + 2], 16) for i in (1, 3, 5)), 225),
    )
    text(d, (64, 30), shot.kicker, 19, CORAL)
    text(d, (64, 65), shot.title, 25)
    watermark = directory / f"{index:02d}-{shot.key}-overlay.png"
    overlay.save(watermark)
    output = directory / f"{index:02d}-{shot.key}.mp4"
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            shot.source_start,
            "-i",
            shot.path,
            "-loop",
            "1",
            "-i",
            watermark,
            "-filter_complex",
            f"[0:v]scale={WIDTH}:{HEIGHT},setsar=1[film];[film][1:v]overlay=0:0,format=yuv420p[v]",
            "-map",
            "[v]",
            "-frames:v",
            shot.frames,
            "-r",
            FPS,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "17",
            "-threads",
            "4",
            output,
        ]
    )
    return output


def atom_order(movie):
    atoms = []
    with movie.open("rb") as f:
        size = movie.stat().st_size
        while f.tell() < size:
            head = f.read(8)
            if len(head) != 8:
                break
            length, kind = struct.unpack(">I4s", head)
            header = 8
            if length == 1:
                length = struct.unpack(">Q", f.read(8))[0]
                header = 16
            elif length == 0:
                length = size - f.tell() + 8
            if length < header:
                break
            atoms.append(kind.decode("ascii", "replace"))
            f.seek(length - header, 1)
    return atoms


def verify_movie(movie):
    data = probe(movie, count=True)
    streams = data.get("streams", [])
    video = next((x for x in streams if x["codec_type"] == "video"), {})
    audio = next((x for x in streams if x["codec_type"] == "audio"), {})
    atoms = atom_order(movie)
    decode = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-xerror",
            "-i",
            str(movie),
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    checks = {
        "duration_80s": abs(float(data["format"]["duration"]) - 80) < 0.01,
        "frames_1920": video.get("nb_read_frames") == "1920",
        "fps24": video.get("r_frame_rate") == "24/1",
        "1080p": (video.get("width"), video.get("height")) == (1920, 1080),
        "h264_yuv420p": video.get("codec_name") == "h264"
        and video.get("pix_fmt") == "yuv420p",
        "aac_stereo_48khz": audio.get("codec_name") == "aac"
        and audio.get("channels") == 2
        and audio.get("sample_rate") == "48000",
        "fast_start": "moov" in atoms
        and "mdat" in atoms
        and atoms.index("moov") < atoms.index("mdat"),
        "full_decode": decode.returncode == 0,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "media": data,
        "sha256": sha(movie),
        "decode_error": decode.stderr[-1000:] if decode.returncode else None,
    }


def provenance(shots, output):
    sources = []
    for shot in shots:
        entry = {
            "shot": shot.key,
            "start_frame": round(shot.start * FPS),
            "end_frame_exclusive": round(shot.end * FPS),
            "source": local_name(shot.path),
            "source_sha256": sha(shot.path),
            "layout": shot.layout,
            "context": shot.kicker,
            "source_start_seconds": shot.source_start,
        }
        if shot.capture:
            metadata = shot.path.with_suffix(".provenance.json")
            entry.update(
                capture_provenance=local_name(metadata),
                capture_provenance_sha256=sha(metadata),
                capture_timing="Included actual capture MP4 plays at original timing once; final real frame held if needed, no repeated actions",
            )
        sources.append(entry)
    return {
        "title": "Second Nature Studio",
        "duration_seconds": 80,
        "fps": 24,
        "width": WIDTH,
        "height": HEIGHT,
        "video_sha256": sha(output),
        "voice": local_name(VOICE),
        "voice_sha256": sha(VOICE),
        "synthetic_narrator": "Kokoro af_heart, stock synthetic voice, no cloning or impersonation",
        "captions": local_name(CAPTIONS),
        "caption_sha256": sha(CAPTIONS),
        "edit_type": "Programmatically composed picture edit, not a continuous screen recording",
        "edit_disclosure": "Production stages edited for time. Actual UI captures and film excerpts; no simulated cursor or fabricated completed jobs. Capture stages come from separate real moments.",
        "audio": "Narration only. Source film audio is not mixed into the product demonstration.",
        "sources": sources,
    }


def read_captions(source):
    def seconds(value):
        h, m, sms = value.split(":")
        s, ms = sms.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    result = []
    for block in source.read_text().strip().split("\n\n"):
        rows = block.splitlines()
        start, end = rows[1].split(" --> ")
        lines = rows[2:]
        if not 1 <= len(lines) <= 2 or any(len(line) > 38 for line in lines):
            raise ValueError(
                "Caption exceeds the reviewed two-line, 38-character limit."
            )
        start, end = seconds(start), seconds(end)
        if not 0 <= start < end <= SECONDS:
            raise ValueError("Caption timing is outside the narration.")
        if result and start < result[-1]["end"] - 0.001:
            raise ValueError("Caption cues overlap.")
        result.append(dict(start=start, end=end, text="\n".join(lines)))
    return result


def caption_band(body):
    from PIL import Image, ImageDraw

    band = Image.new("RGB", (WIDTH, HEIGHT - CAPTION_TOP), INK)
    d = ImageDraw.Draw(band)
    d.rectangle((64, 0, 1856, 2), fill=CORAL)
    if body:
        words = body.split()
        joined = " ".join(words)
        if len(joined) <= 38:
            body = joined
        else:
            choices = [
                (" ".join(words[:i]), " ".join(words[i:])) for i in range(1, len(words))
            ]
            choices = [pair for pair in choices if max(map(len, pair)) <= 38]
            if choices:
                pair = min(
                    choices,
                    key=lambda p: abs(
                        d.textlength(p[0], font=font(42))
                        - d.textlength(p[1], font=font(42))
                    ),
                )
                body = "\n".join(pair)
        bounds = d.multiline_textbbox(
            (0, 0), body, font=font(42), spacing=7, align="center"
        )
        x = (WIDTH - (bounds[2] - bounds[0])) / 2 - bounds[0]
        y = (band.height - (bounds[3] - bounds[1])) / 2 - bounds[1]
        d.multiline_text(
            (x, y), body, font=font(42), spacing=7, align="center", fill=CREAM
        )
    return band


def encode_captions(source, directory):
    # Pixel-rendered lossless captions work even when FFmpeg lacks libass.
    cues = read_captions(source)
    starts = [c["start"] for c in cues]
    pixels = {"": caption_band("").tobytes()}
    for cue in cues:
        pixels[cue["text"]] = caption_band(cue["text"]).tobytes()
    output = directory / "caption-band.mkv"
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pixel_format",
        "rgb24",
        "-video_size",
        f"{WIDTH}x{HEIGHT-CAPTION_TOP}",
        "-framerate",
        str(FPS),
        "-i",
        "pipe:0",
        "-frames:v",
        "1920",
        "-an",
        "-c:v",
        "ffv1",
        "-level",
        "3",
        "-pix_fmt",
        "bgr0",
        "-threads",
        "4",
        str(output),
    ]
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for frame in range(SECONDS * FPS):
            t = frame / FPS
            index = bisect.bisect_right(starts, t) - 1
            body = cues[index]["text"] if index >= 0 and t < cues[index]["end"] else ""
            proc.stdin.write(pixels[body])
        proc.stdin.close()
        error = proc.stderr.read().decode(errors="replace")
        code = proc.wait()
        if code:
            raise RuntimeError("Caption encoding failed: " + error[-1200:])
    except BaseException:
        if proc.poll() is None:
            proc.terminate()
            proc.wait()
        raise
    finally:
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.close()
        proc.stderr.close()
    return output


def render(shots, output):
    output = output.resolve()
    if output.suffix.lower() != ".mp4":
        raise ValueError("Use an .mp4 demo output filename.")
    if output in {s.path.resolve() for s in shots} | {VOICE.resolve()}:
        raise ValueError("Keep every genuine source capture and film intact.")
    report = validate(shots, full=True)
    if not report["ready"]:
        raise ValueError(
            "Full render is gated by verified cloud delivery and complete assets: "
            + json.dumps(report)
        )
    WORK.mkdir(parents=True, exist_ok=True)
    parts = []
    for index, shot in enumerate(shots):
        print(
            json.dumps(
                {
                    "event": "demo_shot",
                    "index": index,
                    "key": shot.key,
                    "frames": shot.frames,
                }
            ),
            flush=True,
        )
        part = (
            encode_capture(shot, index, WORK)
            if shot.capture
            else (
                encode_movie(shot, index, WORK)
                if shot.layout == "film"
                else encode_static(shot, index, WORK)
            )
        )
        parts.append(part)
    listing = WORK / "picture.ffconcat"
    listing.write_text("".join(f"file '{p.name}'\n" for p in parts))
    picture = WORK / "picture-no-voice.mp4"
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            listing,
            "-c",
            "copy",
            picture,
        ]
    )
    caption_video = encode_captions(CAPTIONS, WORK)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.stem + ".partial.mp4")
    # A permanent opaque band keeps every caption readable across cream UI and film.
    filter_video = f"[0:v][2:v]overlay=0:{CAPTION_TOP},format=yuv420p[v]"
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        picture,
        "-i",
        VOICE,
        "-i",
        caption_video,
        "-map",
        "[v]",
        "-map",
        "1:a:0",
        "-filter_complex",
        filter_video,
        "-frames:v",
        1920,
        "-r",
        FPS,
        "-t",
        80,
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "16",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "256k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        "-metadata",
        "title=Second Nature Studio - From Palette to Blender Film",
        "-metadata",
        "artist=Shivam Gupta",
        "-metadata",
        "comment=Edited actual application captures. Stock synthetic narrator: Kokoro af_heart. No voice cloning. Production stages edited for time.",
        "-threads",
        "4",
        partial,
    ]
    subprocess.run([str(a) for a in command], cwd=WORK, check=True)
    verification = verify_movie(partial)
    if not verification["passed"]:
        (WORK / "failed-verification.json").write_text(
            json.dumps(verification, indent=2) + "\n"
        )
        raise RuntimeError(
            "The demonstration failed independent delivery validation; partial output retained in work."
        )
    partial.replace(output)
    for extension in ("srt", "vtt"):
        shutil.copy2(
            VOICE.with_suffix("." + extension), output.with_suffix("." + extension)
        )
    output.with_suffix(".verification.json").write_text(
        json.dumps(verification, indent=2) + "\n"
    )
    output.with_suffix(".provenance.json").write_text(
        json.dumps(provenance(shots, output), indent=2) + "\n"
    )
    print(
        json.dumps({"event": "demo_complete", "file": str(output), "verified": True}),
        flush=True,
    )


def layout_preview(shots):
    from PIL import Image, ImageDraw

    WORK.mkdir(parents=True, exist_ok=True)
    chosen = [
        s
        for s in shots
        if s.key
        in (
            "intro",
            "account",
            "palette",
            "blender",
            "cancelled",
            "resumed",
            "credits",
            "closing",
        )
    ]
    sheet = Image.new("RGB", (1280, 4 * 390), INK)
    draw = ImageDraw.Draw(sheet)
    for index, shot in enumerate(chosen):
        source = first_capture_frame(shot.path, WORK) if shot.capture else shot.path
        if not source.is_file():
            continue
        im = compose(shot, source)
        d = ImageDraw.Draw(im)
        d.rectangle((0, CAPTION_TOP, WIDTH, HEIGHT), fill=INK)
        text(d, (370, 970), "Actual narration captions occupy this band.", 34)
        im.save(WORK / f"layout-{shot.key}.png")
        x = (index % 2) * 640
        y = (index // 2) * 390
        sheet.paste(im.resize((640, 360)), (x, y))
        draw.text(
            (x + 16, y + 365),
            f"{shot.key}: work-only layout proof",
            fill=CREAM,
            font=font(15),
        )
    sheet.save(WORK / "layout-contactsheet.jpg", quality=93)
    print(WORK / "layout-contactsheet.jpg")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--render",
        action="store_true",
        help="Explicitly assemble the final movie after full cloud QA passes",
    )
    parser.add_argument(
        "--layout-preview",
        action="store_true",
        help="Create only a contact sheet from available genuine evidence",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "film/studio-demo.mp4")
    args = parser.parse_args(argv)
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        parser.error("FFmpeg and FFprobe are required")
    shots = timeline()
    if args.layout_preview:
        layout_preview(shots)
        return 0
    report = validate(shots, full=args.render)
    print(json.dumps(report, indent=2))
    if args.render:
        if not report["ready"]:
            return 2
        render(shots, args.output)
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(
            json.dumps({"event": "demo_error", "message": str(error)}), file=sys.stderr
        )
        raise SystemExit(1)
