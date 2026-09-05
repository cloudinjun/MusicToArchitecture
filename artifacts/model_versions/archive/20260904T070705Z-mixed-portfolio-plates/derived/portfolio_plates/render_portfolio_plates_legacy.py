"""Standalone evidence plates, each one readable out of context.

The contact sheets, renders and emitted drawings this repository already produces are
evidence, but they are unlabelled: dropped into a portfolio page they carry no claim and
no number, so a reader has to be told what they are looking at. This module wraps each
one in the same plate -- a number, a title, one line of what it shows, and the figures
that make it checkable -- so a single PNG can be placed on its own and still say what it
proves and what it does not.

Two plates are drawn rather than wrapped: the pipeline diagram, which has no source
image, and the verification schedule, whose whole point is that passed, failed and
unevaluated are three separate columns and never averaged into one.

Run: python -m backend.scripts.render_portfolio_plates
Out:  artifacts/portfolio_plates/
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "portfolio_plates"
RUN = "building-v3-c64269ebc1a8"

# --- design tokens -----------------------------------------------------------------

PAPER = (242, 241, 236)
SUNK = (233, 232, 225)
INK = (22, 24, 28)
GRAPHITE = (110, 112, 118)
RULE = (211, 210, 202)
RULE_STRONG = (180, 179, 169)
ACCENT = (201, 63, 25)
OK = (61, 110, 82)
OPEN = (142, 106, 24)
STEEL = (78, 104, 133)

W = 1920           # plate width
MARGIN = 100
CONTENT = W - MARGIN * 2
SS = 3             # supersampling factor for drawn plates

FONTS = Path("C:/Windows/Fonts")


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for candidate in (name, "segoeui.ttf", "arial.ttf"):
        path = FONTS / candidate
        if path.exists():
            return ImageFont.truetype(str(path), size)
    raise SystemExit(f"no usable font for {name}")


def display(size: int) -> ImageFont.FreeTypeFont:
    return font("FRAMDCN.TTF", size)


def body(size: int) -> ImageFont.FreeTypeFont:
    return font("segoeui.ttf", size)


def mono(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return font("consolab.ttf" if bold else "consola.ttf", size)


def tracked(draw: ImageDraw.ImageDraw, xy, text: str, fnt, fill, spacing: float = 0.0):
    """Draw text with extra letter-spacing; returns the advance width."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + spacing
    return x - xy[0]


def text_w(draw: ImageDraw.ImageDraw, text: str, fnt, spacing: float = 0.0) -> float:
    return draw.textlength(text, font=fnt) + spacing * max(len(text) - 1, 0)


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt, width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=fnt) <= width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


# --- plate scaffold ----------------------------------------------------------------


class Plate:
    """Header, one body block, a data strip, and a stamp -- at scale ``s``."""

    def __init__(self, number: str, title: str, standfirst: str, s: int = 1):
        self.s = s
        self.number = number
        self.title = title
        self.standfirst = standfirst
        self.blocks: list = []

    def _header_height(self, draw: ImageDraw.ImageDraw) -> int:
        s = self.s
        h = 34 * s                                        # accent rule + number
        h += int(96 * s * 1.0)                            # title line
        lines = wrap(draw, self.standfirst, body(27 * s), CONTENT * s)
        h += len(lines) * int(40 * s) + 26 * s
        return h

    def render(self, image: Image.Image | None, data_rows: list[str],
               drawer=None, drawn_height: int = 0) -> Image.Image:
        s = self.s
        probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))

        head_h = self._header_height(probe)
        if image is not None:
            scaled_h = round(image.height * (CONTENT * s) / image.width)
        else:
            scaled_h = drawn_height

        # Data rows wrap: a figure line that runs past the margin is a broken plate.
        wrapped_rows = [wrap(probe, row, mono(21 * s), CONTENT * s - 16 * s)
                        for row in data_rows]
        strip_h = 0
        if data_rows:
            strip_h = 30 * s + sum(len(r) for r in wrapped_rows) * int(38 * s) + 10 * s
        stamp_h = 74 * s

        H = MARGIN * s + head_h + 30 * s + scaled_h + strip_h + stamp_h
        canvas = Image.new("RGB", (W * s, H), PAPER)
        d = ImageDraw.Draw(canvas)

        x0 = MARGIN * s
        y = MARGIN * s

        # accent rule + plate number
        d.rectangle([x0, y, x0 + 84 * s, y + 4 * s], fill=ACCENT)
        tracked(d, (x0, y + 14 * s), self.number, mono(19 * s, True), ACCENT, 1.4 * s)
        y += 34 * s + 18 * s

        # title
        d.text((x0, y), self.title, font=display(78 * s), fill=INK)
        y += int(96 * s)

        # standfirst
        fnt = body(27 * s)
        for line in wrap(d, self.standfirst, fnt, CONTENT * s):
            d.text((x0, y), line, font=fnt, fill=GRAPHITE)
            y += int(40 * s)
        y += 26 * s + 30 * s

        # body block
        if image is not None:
            fitted = image.resize((CONTENT * s, scaled_h), Image.LANCZOS)
            canvas.paste(fitted, (x0, y))
            d.rectangle([x0, y, x0 + CONTENT * s - 1, y + scaled_h - 1],
                        outline=RULE, width=max(1, s))
        elif drawer is not None:
            drawer(canvas, d, x0, y, CONTENT * s, scaled_h)
        y += scaled_h

        # data strip
        if data_rows:
            y += 30 * s
            d.line([x0, y - 15 * s, x0 + CONTENT * s, y - 15 * s], fill=RULE, width=max(1, s))
            fnt = mono(21 * s)
            for lines in wrapped_rows:
                tick_top = y + 4 * s
                for line in lines:
                    d.text((x0 + 16 * s, y), line, font=fnt, fill=GRAPHITE)
                    y += int(38 * s)
                d.line([x0, tick_top, x0, y - 10 * s], fill=RULE_STRONG, width=max(2, 2 * s))
            y += 10 * s

        # stamp
        y = H - 52 * s
        d.line([x0, y - 20 * s, x0 + CONTENT * s, y - 20 * s], fill=RULE, width=max(1, s))
        left = "MUSIC \u2192 ARCHITECTURE   \u00b7   design-intent compiler"
        right = f"run {RUN}   \u00b7   professional_review_required"
        fnt = mono(18 * s)
        tracked(d, (x0, y), left, fnt, GRAPHITE, 0.8 * s)
        rw = text_w(d, right, fnt, 0.8 * s)
        tracked(d, (x0 + CONTENT * s - rw, y), right, fnt, GRAPHITE, 0.8 * s)

        if s > 1:
            canvas = canvas.resize((W, H // s), Image.LANCZOS)
        return canvas


def flatten(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "LA", "P"):
        base = Image.new("RGB", img.size, (255, 255, 255))
        img = img.convert("RGBA")
        base.paste(img, mask=img.split()[-1])
        return base
    return img.convert("RGB")


def load(rel: str) -> Image.Image:
    return flatten(Image.open(ROOT / rel))


# --- P-01  pipeline diagram --------------------------------------------------------

STAGES = [
    ("MP3", "44 s excerpt", ["one recording"]),
    ("AUDIO FEATURES", "audio.py", ["12 Librosa features", "6 temporal segments"]),
    ("SHARED SCORE", "10 bounded dimensions", ["6 measured, 4 declared proxy",
                                               "method + confidence + provenance"]),
    ("SELECTION", "4 compiled decisions", ["typology \u00b7 massing family",
                                           "facade grammar \u00b7 structure"]),
    ("DATUMS", "datums.py", ["34 datums", "each records what drove it"]),
    ("LATTICE", "levels \u00d7 grid \u00d7 plates", ["plate polygons + voids"]),
    ("PROGRAM", "program.py", ["area brief packed", "band by band"]),
    ("SIZING", "sizing.py", ["ASCE 7 loads", "AISC 360 selection"]),
    ("MODEL", "compiler_v3.py", ["4,095 elements", "35 kinds \u00b7 4 primitives"]),
]

OUTPUTS = [
    ("DRAWINGS", "SVG plans + sections"),
    ("BLENDER", ".blend + semantic GLB"),
    ("WEB", "filtered 3D workbench"),
    ("REVIT", "70/70 kinds mapped"),
]

AUTHORITIES = [
    ("Brief delivered", 17, 0, 0),
    ("Base-building support", 15, 0, 0),
    ("Egress \u00b7 IBC Ch.10", 11, 0, 5),
    ("Dependency topology", 8, 0, 1),
    ("Facade grammar gates", 4, 0, 0),
    ("Centre-line joints", 3, 0, 0),
    ("Spatial common sense", 3, 0, 1),
    ("Accessible route \u00b7 ADA", 1, 0, 0),
    ("Site load cases \u00b7 ASCE 7", 0, 0, 3),
]


def draw_diagram(canvas: Image.Image, d: ImageDraw.ImageDraw,
                 x0: int, y0: int, w: int, h: int) -> None:
    s = SS
    f_stage = display(30 * s)
    f_sub = mono(17 * s)
    f_note = body(19 * s)
    f_band = display(26 * s)
    f_small = mono(17 * s)

    # ---- authority band above the spine: the asymmetric rule -----------------
    band_h = 108 * s
    d.rectangle([x0, y0, x0 + w, y0 + band_h], fill=SUNK)
    d.rectangle([x0, y0, x0 + 6 * s, y0 + band_h], fill=STEEL)
    d.text((x0 + 26 * s, y0 + 18 * s), "THE SCREEN", font=f_band, fill=STEEL)
    d.text((x0 + 26 * s, y0 + 56 * s),
           "hard physical and code gates  \u00b7  eliminates what may exist, contributes no number",
           font=f_note, fill=GRAPHITE)

    mid = x0 + w // 2 + 40 * s
    d.rectangle([mid, y0, mid + 6 * s, y0 + band_h], fill=ACCENT)
    d.text((mid + 26 * s, y0 + 18 * s), "THE SCORE", font=f_band, fill=ACCENT)
    d.text((mid + 26 * s, y0 + 56 * s),
           "proposes inside what survives  \u00b7  never eliminates; overrules are recorded",
           font=f_note, fill=GRAPHITE)

    y = y0 + band_h + 54 * s

    # ---- the spine -----------------------------------------------------------
    cols = 5
    gap = 18 * s
    bw = (w - gap * (cols - 1)) // cols
    bh = 150 * s
    row_gap = 58 * s

    positions: list[tuple[int, int]] = []
    for i, (name, sub, notes) in enumerate(STAGES):
        r, c = divmod(i, cols)
        bx = x0 + c * (bw + gap)
        by = y + r * (bh + row_gap)
        positions.append((bx, by))

        accent_stage = name in ("SHARED SCORE", "SELECTION", "MODEL")
        d.rectangle([bx, by, bx + bw, by + bh], fill=PAPER,
                    outline=ACCENT if accent_stage else RULE_STRONG,
                    width=(3 * s if accent_stage else 2 * s))
        d.rectangle([bx, by, bx + bw, by + 5 * s],
                    fill=ACCENT if accent_stage else RULE_STRONG)

        d.text((bx + 18 * s, by + 22 * s), name, font=f_stage,
               fill=INK if accent_stage else INK)
        d.text((bx + 18 * s, by + 60 * s), sub, font=f_sub, fill=GRAPHITE)
        ny = by + 88 * s
        for note in notes:
            d.text((bx + 18 * s, ny), note, font=f_small, fill=GRAPHITE)
            ny += 24 * s

        # connector to the previous box
        if i and i % cols:
            ax = bx - gap
            ay = by + bh // 2
            d.line([ax - 2 * s, ay, ax + gap - 2 * s, ay], fill=RULE_STRONG, width=3 * s)
            d.polygon([(bx - 2 * s, ay), (bx - 13 * s, ay - 7 * s),
                       (bx - 13 * s, ay + 7 * s)], fill=RULE_STRONG)
        elif i == cols:  # wrap from end of row 1 to start of row 2
            px, py = positions[cols - 1]
            d.line([px + bw // 2, py + bh, px + bw // 2, py + bh + row_gap // 2],
                   fill=RULE_STRONG, width=3 * s)
            d.line([px + bw // 2, py + bh + row_gap // 2,
                    x0 + bw // 2, py + bh + row_gap // 2], fill=RULE_STRONG, width=3 * s)
            d.line([x0 + bw // 2, py + bh + row_gap // 2, x0 + bw // 2, by],
                   fill=RULE_STRONG, width=3 * s)
            d.polygon([(x0 + bw // 2, by - 2 * s), (x0 + bw // 2 - 7 * s, by - 13 * s),
                       (x0 + bw // 2 + 7 * s, by - 13 * s)], fill=RULE_STRONG)

    y = positions[-1][1] + bh + 56 * s

    # ---- outputs -------------------------------------------------------------
    d.text((x0, y), "EMITS", font=f_band, fill=INK)
    y += 40 * s
    ow = (w - gap * (len(OUTPUTS) - 1)) // len(OUTPUTS)
    for i, (name, sub) in enumerate(OUTPUTS):
        bx = x0 + i * (ow + gap)
        d.rectangle([bx, y, bx + ow, y + 86 * s], fill=SUNK, outline=RULE_STRONG, width=2 * s)
        d.text((bx + 18 * s, y + 16 * s), name, font=display(27 * s), fill=INK)
        d.text((bx + 18 * s, y + 52 * s), sub, font=f_small, fill=GRAPHITE)
    y += 86 * s + 56 * s

    # ---- verification band spanning everything -------------------------------
    total_p = sum(a[1] for a in AUTHORITIES)
    total_o = sum(a[3] for a in AUTHORITIES)
    d.rectangle([x0, y, x0 + w, y + 4 * s], fill=INK)
    y += 26 * s
    d.text((x0, y), "CHECKED ACROSS EVERY STAGE", font=f_band, fill=INK)
    label = (f"{total_p} passed   \u00b7   0 failed   \u00b7   {total_o} unevaluated"
             f"   \u2014   9 independent authorities")
    lw = text_w(d, label, mono(23 * s, True), 0.6 * s)
    tracked(d, (x0 + w - lw, y + 4 * s), label, mono(23 * s, True), INK, 0.6 * s)
    y += 48 * s

    chip_gap = 12 * s
    per_row = 5
    cw = (w - chip_gap * (per_row - 1)) // per_row
    for i, (name, p, f_, o) in enumerate(AUTHORITIES):
        r, c = divmod(i, per_row)
        bx = x0 + c * (cw + chip_gap)
        by = y + r * (74 * s + chip_gap)
        d.rectangle([bx, by, bx + cw, by + 74 * s], fill=PAPER, outline=RULE, width=2 * s)
        d.rectangle([bx, by, bx + 5 * s, by + 74 * s], fill=OPEN if o else OK)
        d.text((bx + 16 * s, by + 12 * s), name, font=body(20 * s), fill=INK)
        counts = f"{p} pass"
        if o:
            counts += f"   {o} open"
        d.text((bx + 16 * s, by + 42 * s), counts, font=mono(19 * s),
               fill=OPEN if o else OK)

    y += 2 * (74 * s + chip_gap) - chip_gap + 34 * s
    d.text((x0, y),
           "A gate the pipeline cannot evaluate reports unevaluated \u2014 never passed.",
           font=body(24 * s), fill=ACCENT)


def diagram_height() -> int:
    s = SS
    band = 108 * s + 54 * s
    spine = 2 * 150 * s + 58 * s
    outputs = 56 * s + 40 * s + 86 * s + 56 * s
    verif = 4 * s + 26 * s + 48 * s + 2 * (74 * s + 12 * s) - 12 * s + 34 * s + 40 * s
    return band + spine + outputs + verif


# --- P-06  verification schedule ---------------------------------------------------


def draw_schedule(canvas: Image.Image, d: ImageDraw.ImageDraw,
                  x0: int, y0: int, w: int, h: int) -> None:
    s = SS
    rows = [
        ("Brief delivered", "The typology brief, per space", 17, 0, 0),
        ("Base-building support", "Constitution for theater", 15, 0, 0),
        ("Egress and occupancy", "IBC Chapter 10, occupancy A-3", 11, 0, 5),
        ("Dependency topology", "Generated graph; connection capacity not checked", 8, 0, 1),
        ("Facade grammar gates", "High-Tech guide, its own written rules", 4, 0, 0),
        ("Centre-line joints", "Axis skeleton the emitters registered to", 3, 0, 0),
        ("Spatial common sense", "Constraints standing in for what a person would see", 3, 0, 1),
        ("Accessible route", "ADA \u00a7405 \u2014 slope, width, rise, landings", 1, 0, 0),
        ("Site load cases", "ASCE 7-16, from resolved site parameters", 0, 0, 3),
    ]
    head_h = 56 * s
    row_h = 62 * s
    num_w = 130 * s
    c_check = x0 + 24 * s
    c_auth = x0 + 470 * s
    c_pass = x0 + w - num_w * 3
    c_fail = x0 + w - num_w * 2
    c_open = x0 + w - num_w

    d.rectangle([x0, y0, x0 + w, y0 + head_h], fill=SUNK)
    f_h = mono(20 * s)
    tracked(d, (c_check, y0 + 18 * s), "CHECK", f_h, GRAPHITE, 2.2 * s)
    tracked(d, (c_auth, y0 + 18 * s), "AUTHORITY", f_h, GRAPHITE, 2.2 * s)
    for cx, lab in ((c_pass, "PASS"), (c_fail, "FAIL"), (c_open, "OPEN")):
        lw = text_w(d, lab, f_h, 2.2 * s)
        tracked(d, (cx + num_w - lw - 24 * s, y0 + 18 * s), lab, f_h, GRAPHITE, 2.2 * s)
    d.line([x0, y0 + head_h, x0 + w, y0 + head_h], fill=RULE_STRONG, width=3 * s)

    y = y0 + head_h
    f_check = body(25 * s)
    f_auth = mono(19 * s)
    f_num = mono(26 * s, True)
    for name, auth, p, f_, o in rows:
        d.text((c_check, y + 17 * s), name, font=f_check, fill=INK)
        d.text((c_auth, y + 21 * s), auth, font=f_auth, fill=GRAPHITE)
        for cx, val, col in ((c_pass, p, OK), (c_fail, f_, GRAPHITE), (c_open, o, OPEN)):
            txt = str(val)
            dim = (val == 0)
            tw = d.textlength(txt, font=f_num)
            d.text((cx + num_w - tw - 24 * s, y + 16 * s), txt, font=f_num,
                   fill=RULE_STRONG if dim else col)
        y += row_h
        d.line([x0, y, x0 + w, y], fill=RULE, width=max(1, s))

    d.rectangle([x0, y, x0 + w, y + 70 * s], fill=SUNK)
    d.line([x0, y, x0 + w, y], fill=RULE_STRONG, width=3 * s)
    d.text((c_check, y + 20 * s), "TOTAL \u2014 9 authorities", font=mono(24 * s, True), fill=INK)
    for cx, val, col in ((c_pass, 62, OK), (c_fail, 0, INK), (c_open, 10, OPEN)):
        txt = str(val)
        tw = d.textlength(txt, font=f_num)
        d.text((cx + num_w - tw - 24 * s, y + 18 * s), txt, font=f_num, fill=col)
    y += 70 * s + 46 * s

    d.rectangle([x0, y, x0 + 6 * s, y + 96 * s], fill=ACCENT)
    note = ("A separate construction audit judged all fourteen models against current "
            "accessibility, egress, steel, concrete and mass-timber baselines and recorded "
            "0 of 14 construction-ready. That number is published, not buried.")
    fnt = body(25 * s)
    ny = y + 6 * s
    for line in wrap(d, note, fnt, w - 34 * s):
        d.text((x0 + 26 * s, ny), line, font=fnt, fill=INK)
        ny += 34 * s


def schedule_height() -> int:
    s = SS
    return 56 * s + 9 * 62 * s + 70 * s + 46 * s + 96 * s + 10 * s


# --- the emitted drawing -----------------------------------------------------------


def raster_plan() -> Image.Image:
    from reportlab.graphics import renderPM
    from svglib.svglib import svg2rlg

    src = ROOT / "web" / "public" / "drawings" / RUN / "DWG-PLAN-L01.svg"
    drawing = svg2rlg(str(src))
    scale = (CONTENT * 2) / drawing.width
    drawing.width *= scale
    drawing.height *= scale
    drawing.scale(scale, scale)
    pil = renderPM.drawToPIL(drawing, bg=0xFFFFFF)
    return flatten(pil)


def preset_strip() -> Image.Image:
    names = ["photoreal", "post_digital", "cinematic", "minimalist", "watercolor"]
    tiles = [load(f"artifacts/render_presets/model_v3/{n}/hero.png") for n in names]
    pw, gap = 760, 10
    ph = round(tiles[0].height * pw / tiles[0].width)
    sheet = Image.new("RGB", (pw * 5 + gap * 4, ph + 46), PAPER)
    d = ImageDraw.Draw(sheet)
    for i, (tile, name) in enumerate(zip(tiles, names)):
        x = i * (pw + gap)
        sheet.paste(tile.resize((pw, ph), Image.LANCZOS), (x, 0))
        d.text((x + 4, ph + 12), name.replace("_", "-").upper(),
               font=mono(21), fill=GRAPHITE)
    return sheet


# --- build -------------------------------------------------------------------------


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    made: list[tuple[str, Image.Image]] = []

    made.append(("P-01_pipeline_diagram", Plate(
        "P-01",
        "How a recording becomes a checked building",
        "One pipeline, nine stages, four outputs. Two authorities negotiate every choice, "
        "and nine independent checks run across all of it.",
        s=SS,
    ).render(None, [
        "MP3 \u2192 12 audio features \u2192 10 score dimensions \u2192 4 compiled decisions "
        "\u2192 34 datums \u2192 4,095 elements   \u00b7   38.9 s end to end",
        "the screen eliminates and never scores   \u00b7   the score proposes and never "
        "eliminates   \u00b7   where they disagree the screen wins, and the model records it",
    ], drawer=draw_diagram, drawn_height=diagram_height())))

    made.append(("P-02_fourteen_buildings", Plate(
        "P-02",
        "Fourteen recordings, fourteen buildings",
        "The same compiler, the same site, the same brief-writing rules \u2014 and fourteen "
        "licensed recordings across genres. Nothing here was posed.",
    ).render(load("artifacts/style_evidence/contact_sheet_massing.png"), [
        "6 massing families   \u00b7   3 typologies   \u00b7   10 distinct footprints   "
        "\u00b7   6 facade grammars   \u00b7   storeys 6\u20139",
        "0 % score/model signature collisions   \u00b7   100 % minimum variable-datum "
        "coverage   \u00b7   before form was compiled, the same 14 shared 35 of 36 element kinds",
    ])))

    made.append(("P-03_structure_follows", Plate(
        "P-03",
        "The frame follows the score too",
        "The same fourteen models with everything but structure removed. The system is "
        "screened for capacity first, then chosen by the music.",
    ).render(load("artifacts/audio_saturation/corpus-2026-08-31-evidence-rerun-2/"
                  "contact_sheet_structure.png"), [
        "3 structural systems \u2014 steel frame with joists, RC frame and wall, timber core"
        "   \u00b7   bays 5.9\u20137.6 m   \u00b7   floor-to-floor 4.08\u20135.19 m",
        "62,828 element IDs   \u00b7   74,345 resolved relations   \u00b7   100 % "
        "structure-to-soil load paths   \u00b7   connection capacity explicitly not_checked",
    ])))

    made.append(("P-04_member_level", Plate(
        "P-04",
        "Members, not massing",
        "Column, girder and joist each carry the section a load calculation chose, so the "
        "member drawn is the member that was checked.",
    ).render(load("artifacts/v3_demo/03_structure_closeup.png"), [
        "ASCE 7 loads from the allocated program \u2192 AISC 360 selection   \u00b7   "
        "407 of 4,095 elements load-sized   \u00b7   hardest joist at 78 % of capacity (W16\u00d740)",
        "everything else is dimensioned by architectural convention and says so through "
        "sizing_status   \u00b7   gravity only \u2014 no wind, seismic or lateral system designed",
    ])))

    made.append(("P-05_emitted_drawing", Plate(
        "P-05",
        "It emits drawings, not screenshots",
        "A plan cut 1.20 m above finished floor with grid bubbles, poch\u00e9, dimension "
        "strings, room areas and section marks \u2014 from the same model as every other plate.",
    ).render(raster_plan(), [
        "DWG-PLAN-L01   \u00b7   1:100 @ A1   \u00b7   788 \u00d7 571 mm sheet   \u00b7   "
        "1,323 marks   \u00b7   424 elements cut, 1,314 drawn",
        "240 figures, 140 seats and 125 desks dropped by the scale rule \u2014 and the "
        "omission is counted, not silent   \u00b7   plans and sections only; no elevations issued",
    ])))

    made.append(("P-06_verification_schedule", Plate(
        "P-06",
        "What it refuses to claim",
        "Nine independent authorities check this building. Passed, failed and unevaluated "
        "stay three separate columns and are never averaged into a score.",
        s=SS,
    ).render(None, [
        "62 passed   \u00b7   0 failed   \u00b7   10 unevaluated   \u00b7   "
        "every generated object resolves to the rule and the input that produced it",
    ], drawer=draw_schedule, drawn_height=schedule_height())))

    made.append(("P-07_presentation_range", Plate(
        "P-07",
        "One model, five ways to show it",
        "A presentation-only Blender adapter self-frames any saved .blend and renders from "
        "native shader, World, Freestyle and compositor nodes.",
    ).render(preset_strip(), [
        "15 renders   \u00b7   every hash matched against render_manifest.json   \u00b7   "
        "source and template hashes unchanged   \u00b7   no geometry mutation",
        "presentation authority only \u2014 these images are not accepted geometry and carry "
        "no code-compliance claim",
    ])))

    made.append(("P-08_revit_handoff", Plate(
        "P-08",
        "And it hands off to Revit",
        "Every emitted element kind has a declared delivery path, a stable identity and "
        "conservative update semantics \u2014 planned without importing an Autodesk API.",
    ).render(load("artifacts/evidence/revit_dynamo_handoff_ui/bim_handoff_panel.png"), [
        "70/70 taxonomy kinds and 42/42 emitted kinds mapped   \u00b7   2,220 BIM targets   "
        "\u00b7   204 presentation-only omissions   \u00b7   18 stable parameter GUIDs",
        "static contract ready_for_dry_run   \u00b7   installed-host validation visibly "
        "pending \u2014 no integration claim is made",
    ])))

    manifest = []
    for name, img in made:
        path = OUT / f"{name}.png"
        img.save(path, "PNG", optimize=True)
        manifest.append({"plate": name, "size": list(img.size),
                         "bytes": path.stat().st_size})
        print(f"{name:32} {img.size[0]}\u00d7{img.size[1]:<6} "
              f"{path.stat().st_size / 1024:7.0f} KB")

    (OUT / "plates_manifest.json").write_text(
        json.dumps({"run": RUN, "plates": manifest}, indent=2), encoding="utf-8")
    print(f"\n{len(made)} plates \u2192 {OUT}")


if __name__ == "__main__":
    main()
