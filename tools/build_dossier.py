#!/usr/bin/env python3
"""Rebuild the four-page dossier from shipped stills, or retained native frames."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from PIL import Image
import math
import json
from io import BytesIO

ROOT = Path(__file__).resolve().parents[1]
W, H = 595.28, 841.89
pdfmetrics.registerFont(TTFont("Grotesk", str(ROOT / "assets/fonts/SpaceGrotesk.ttf")))
C = canvas.Canvas(str(ROOT / "production-dossier.pdf"), pagesize=(W, H))
C.setTitle("SECOND NATURE | Production dossier")
C.setAuthor("Shivam Gupta")
NAVY = "#071E29"
TEAL = "#154D58"
CORAL = "#E98058"
PAPER = "#F4EFE5"
MUTED = "#557079"
GOLD = "#CFA77C"
style = ParagraphStyle(
    "body",
    fontName="Grotesk",
    fontSize=10.3,
    leading=14.7,
    textColor=HexColor(NAVY),
    spaceAfter=0,
)
small = ParagraphStyle("small", parent=style, fontSize=8.3, leading=11.5)


def rect(x, y, w, h, col):
    C.setFillColor(HexColor(col))
    C.rect(x, y, w, h, fill=1, stroke=0)


def txt(x, y, s, size=12, color=NAVY):
    C.setFillColor(HexColor(color))
    C.setFont("Grotesk", size)
    C.drawString(x, y, s)


def para(x, y, s, w=499, sty=None):
    p = Paragraph(s, sty or style)
    _, h = p.wrap(w, H)
    p.drawOn(C, x, y - h)
    return y - h


def image(path, x, y, w, h):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    im = Image.open(p)
    iw, ih = im.size
    factor = max(w / iw, h / ih)
    rw, rh = iw * factor, ih * factor
    encoded = BytesIO()
    im.convert("RGB").save(encoded, format="JPEG", quality=94, optimize=True)
    encoded.seek(0)
    C.saveState()
    clip = C.beginPath()
    clip.rect(x, y, w, h)
    C.clipPath(clip, stroke=0)
    C.drawImage(ImageReader(encoded), x + (w - rw) / 2, y + (h - rh) / 2, rw, rh)
    C.restoreState()


def base(page, kicker):
    rect(0, 0, W, H, PAPER)
    txt(48, H - 42, "SECOND NATURE", 10, TEAL)
    txt(W - 126, H - 42, "SHIVAM GUPTA", 8, TEAL)
    rect(48, H - 61, 32, 2, CORAL)
    txt(48, 31, kicker, 8, MUTED)
    txt(W - 62, 31, f"{page:02d}", 8, MUTED)


def line(y):
    rect(48, y, 499, 0.6, "#CECFC5")


def renderframe(n):
    p = ROOT / "film/frames" / f"frame_{n:04d}.png"
    stills = {
        1: "seed.jpg",
        95: "drop-chase.jpg",
        200: "loop.jpg",
        355: "suspension.jpg",
        530: "bloom.jpg",
    }
    return p if p.exists() else ROOT / "stills" / stills[n]


base(1, "FILM / CREATIVE DIRECTION")
txt(48, 734, "Make every", 38)
txt(48, 689, "second grow.", 38)
para(48, 651, "One drop. A world in motion. A reason to arrive.", 499)
image(renderframe(530), 48, 313, 499, 281)
rect(48, 281, 499, 31, TEAL)
txt(61, 292, "24 SECONDS  /  BLENDER  /  ORIGINAL PROCEDURAL FILM", 8.5, "#F4EFE5")
y = para(
    48,
    248,
    "A dry seed waits. A luminous amber drop accelerates through precision gates and a vertical loop. The machine finally gives way to stillness: a held drop, a fall, then an unfolding flower.",
)
y = para(
    48,
    y - 16,
    "The interpretation of Speed is purposeful motion. The race matters because of what it makes possible. A restrained palette, physical lighting and a deliberate pause let the ending feel earned.",
)
line(118)
para(
    48,
    98,
    "<b>Entrant and project lead:</b> Shivam Gupta<br/><b>AI-assisted production:</b> OpenAI Codex, with full workflow and asset disclosure included.",
    499,
    small,
)
C.showPage()

base(2, "CRAFT / STORY AND CONSTRUCTION")
txt(48, 744, "A race. A breath. A bloom.", 27)
beats = [
    (1, "00:00-00:02", "A seed establishes the need."),
    (95, "00:02-00:06", "A following camera sells acceleration."),
    (200, "00:06-00:11", "The route opens into a full loop."),
    (355, "00:11-00:15.25", "Braking, suspension and release."),
    (530, "00:15.25-00:24", "Growth replaces the machine's urgency."),
]
for i, (f, time, cap) in enumerate(beats):
    x = 48 + (i % 2) * 255
    y = 558 - (i // 2) * 149
    image(renderframe(f), x, y, 244, 104)
    txt(x, y - 17, time, 9, TEAL)
    para(x, y - 24, cap, 244, small)
image(ROOT / "stills/blender-wip.png", 303, 260, 244, 104)
txt(303, 243, "AUTHENTIC BLENDER WIP", 9, TEAL)
para(303, 236, "Editable geometry, rigs and baked keys.", 244, small)
line(193)
para(
    48,
    175,
    "<b>Procedural control:</b> bpy constructs the drop, rails, machined planter, soil, petals, leaves and Fibonacci pollen. Separate petal hinges unfold in staggered whorls. Five independent shot cameras avoid cut interpolation during motion blur.",
    499,
    small,
)
para(
    48,
    111,
    "<b>Sound and image:</b> original mathematical audio synthesis, Blender Cycles rendering, and pixel-precise title assembly. All motion is scripted and baked. No physics simulation, stock models, stock textures, recorded music or generative video is claimed.",
    499,
    small,
)
C.showPage()

base(3, "PRODUCT / A NARROW COMMERCIAL HYPOTHESIS")
txt(48, 744, "One film, repeatable craft.", 27)
para(
    48,
    712,
    "A hosted production studio for creators making polished variants of one approved visual direction.",
)
shot = ROOT / "stills/studio.png"
image(shot, 48, 414, 499, 250)
rect(48, 382, 499, 31, TEAL)
txt(61, 393, "FIREBASE WORKSPACES  /  PALETTE + SEED  /  REAL BLENDER JOBS", 8.2, PAPER)
y = para(
    48,
    352,
    "<b>Customer:</b> freelance motion designers and small studios producing launch films or sustainability campaigns. The hypothesis is that repeat variations and recovery from interruptions consume billable creative time.",
)
y = para(
    48,
    y - 13,
    "<b>Working today:</b> guest and email workspaces, isolated productions, palette/seed controls, real Cloud Run jobs, saved frames, cancellation, recovery and private exports. The original film and complete local production source are included.",
)
y = para(
    48,
    y - 13,
    "<b>Commercial experiment:</b> test a US$250 assisted variant service or US$79 editable-template license. These are proposed prices. There are no claimed customers, revenue or measured market demand.",
)
y = para(
    48,
    y - 13,
    "<b>What would earn a business:</b> ten customer interviews, three paid pilots and measured revision/support time. The current code is not a moat; a distinctive film library and reliable delivery may become one.",
)
line(108)
para(
    48,
    91,
    "Hosted studio: second-nature-studio.web.app. Cloud previews are 540p, with shared daily capacity and seven-day file retention. The local source supports final 1080p production. Pricing, alternatives and assumptions: docs/COMMERCIAL.md.",
    499,
    small,
)
C.showPage()

receipt = json.loads((ROOT / "submission/receipt.json").read_text())
if receipt.get("status") != "submitted":
    raise ValueError("The final dossier requires an actual submitted receipt.")
original_url = receipt["youtube"]["original"]["url"]
demo_url = receipt["youtube"]["studio_demo"]["url"]
discord_url = receipt["official_entry"]["url"]
devpost_url = receipt["devpost"]["url"]

base(4, "DELIVERY / PUBLICATION AND ENTRY RECEIPTS")
txt(48, 744, "Published. Submitted. Recorded.", 27)
para(
    48,
    711,
    "The original film and studio guide are public. The official Discord entry and Devpost mirror are submitted. Receipts confirm these actions, not organizer acceptance, eligibility adjudication or an award.",
)
rect(48, 599, 499, 64, TEAL)
txt(64, 639, "SUBMISSION RECEIPTS  /  21 OCTOBER 2026", 10, PAPER)
txt(64, 614, "ORIGINAL 24s  /  STUDIO GUIDE 80s", 21, PAPER)
y = 570
for i, (title, body) in enumerate(
    [
        (
            "Original film / public on YouTube",
            f'<link href="{original_url}" color="#154D58">youtube.com/watch?v=folQG-XiqTY</link><br/>'
            "24 seconds, 1080p. Initial checks: No issues found. English SRT published: six cues.",
        ),
        (
            "Studio guide / public on YouTube",
            f'<link href="{demo_url}" color="#154D58">youtube.com/watch?v=EePedJF-2lA</link><br/>'
            "80 seconds, 1080p. English SRT published: 28 cues. Stock synthetic narrator disclosed.",
        ),
        (
            "Official Discord entry / posted",
            f'<link href="{discord_url}" color="#154D58">Open the official entry and attached Blender WIP</link><br/>'
            "RenderJuice account and private registration confirmed. Three entry tags; poster and Blender WIP attached.",
        ),
        (
            "Devpost mirror / Project submitted!",
            f'<link href="{devpost_url}" color="#154D58">devpost.com/software/second-nature-jrqu9v</link><br/>'
            "Original film primary video, nine gallery images, a cover, supporting guide and testing links.",
        ),
    ]
):
    txt(48, y, f"0{i+1}", 18, CORAL)
    txt(85, y, title, 12, TEAL)
    end = para(85, y - 10, body, 462, small)
    y = end - 27
line(y + 7)
y = para(
    48,
    y - 12,
    "<b>Disclosure:</b> Shivam Gupta is entrant and project lead. OpenAI Codex assisted with concept, code, automation, documentation and review. Original geometry, materials and synthesized audio were created for this project. Space Grotesk: SIL OFL 1.1. The guide uses stock Kokoro af_heart narration, not a clone of Shivam. No RenderJuice rendering or physical simulation is claimed.",
    499,
    small,
)
y = para(
    48,
    y - 16,
    "<b>Evidence:</b> submission/receipt.json records exact URLs, confirmations and screenshot paths. Keep the original verified media and editable scene available. Publication and submitted status do not establish an official contest result.",
    499,
    small,
)
y = para(
    48,
    y - 18,
    '<b>Studio and source:</b><br/><link href="https://second-nature-studio.web.app" color="#154D58">second-nature-studio.web.app</link><br/><link href="https://github.com/shi1720/second-nature" color="#154D58">github.com/shi1720/second-nature</link>',
    499,
    small,
)
C.save()
print(ROOT / "production-dossier.pdf")
