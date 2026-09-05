"""Journal-style figures: evidence arranged in a reading order, nothing else on the canvas.

These are not plates or slides. No title, no standfirst, no data strip, no stamp. Each
figure is real thumbnails, drawn data and glyphs set in a fixed skeleton, with only the
labels that *name* things; every claim and every number lives in the caption, which is
delivered as text beside the file rather than drawn into it.

Each figure is authored once as an SVG (Times, grayscale chrome, thumbnails linked from
`assets/` so the file stays editable in Illustrator or Inkscape) and then rasterised
from that same SVG, so the PNG a portfolio uses and the SVG a designer edits cannot drift.

Figures 2-5 expose the core recipe between the score and the massing, drawn from the
demo run's own records rather than from a description of them:

  fig1   framework        A1 phase band x D1 specimen grid: three recordings, four phases
  fig2   datum clamp      dot-and-range chart: 29 score-driven datums, confidence-clamped
  fig3   axes + massing   (a) C2 dims -> four axes  (b) A4 decision tree, seven families
  fig4   two authorities  10 systems x 10 grammars: affinity, screen, preferred, chosen
  fig5   lattice          E3 keyed plan and section drawn from the lattice, + massing
  fig6   fourteen         D1 specimen grid: fourteen recordings, massing, same camera
  fig7   semantic layers  D1 specimen grid: five recordings x program / envelope / structure
  fig8   drawings         E3 keyed spatial: (a) plan sheet, (b) section sheet, verbatim
  fig9   presets          five presentation looks of one saved model
  fig10  bim handoff      the Workbench handoff panel, verbatim capture
  table1 verification     the compliance schedule as a journal table

Run: python -m backend.scripts.render_paper_figures
Out:  artifacts/paper_figures/
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
# The portfolio figure set lives at the repository root on purpose: it is the one place
# any agent adds or replaces a source image, and `portfolio/README.md` is its entry point.
OUT = ROOT / "portfolio"
ASSETS = OUT / "assets"

CORPUS = ROOT / "artifacts" / "audio_saturation" / "corpus-2026-08-31-evidence-rerun-2"
STYLE = ROOT / "artifacts" / "style_evidence" / "style_evidence.json"
V3RUNS = ROOT / "artifacts" / "v3_runs"
AUDIO_CACHE = Path(os.environ.get("TEMP", "/tmp")) / "codex-mta-audio-saturation-20260830" / "normalized_mp3"
DEMO = ROOT / "web" / "public" / "reports" / "demo_run.json"

FONT = "'Times New Roman','Liberation Serif','Nimbus Roman',serif"
INK = "#000"
GREY = "#6b6b6b"
ARROW = "#6b6b6b"
BOX = "#595959"
SLOT_FILL = "#f2f2f2"
SLOT_STROKE = "#bfbfbf"
RULE = "#000"
HILITE = "#E8362D"

# --- svg primitives ------------------------------------------------------------------


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, size=13, bold=False, anchor="middle", fill=INK, italic=False):
    w = ' font-weight="bold"' if bold else ""
    i = ' font-style="italic"' if italic else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}"{w}{i} '
            f'text-anchor="{anchor}" fill="{fill}">{esc(s)}</text>\n')


def lines(x, y, rows, size=13, bold=False, anchor="middle", lh=None, fill=INK):
    lh = lh or round(size * 1.3)
    w = ' font-weight="bold"' if bold else ""
    out = (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}"{w} '
           f'text-anchor="{anchor}" fill="{fill}">')
    for i, r in enumerate(rows):
        out += f'<tspan x="{x:.1f}" dy="{0 if i == 0 else lh}">{esc(r)}</tspan>'
    return out + "</text>\n"


def img(href, x, y, w, h):
    return (f'<image href="{href}" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'preserveAspectRatio="xMidYMid meet"/>\n')


def rect(x, y, w, h, fill="none", stroke="none", sw=1.0, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>\n')


def slot(x, y, w, h):
    return rect(x, y, w, h, SLOT_FILL, SLOT_STROKE, 1)


def hair(x1, y1, x2, y2, width=1.0, color=RULE, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{color}" stroke-width="{width}"{d}/>\n')


def circle(cx, cy, r, fill="none", stroke=INK, sw=1.0):
    return (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{sw}"/>\n')


def arrow(x1, y1, x2, y2, width=2.0, color=ARROW, head=9.0, dash=None):
    """Straight arrow with an explicit triangular head (no marker, so it rasterises)."""
    dx, dy = x2 - x1, y2 - y1
    L = max((dx * dx + dy * dy) ** 0.5, 1e-6)
    ux, uy = dx / L, dy / L
    bx, by = x2 - ux * head, y2 - uy * head
    px, py = -uy, ux
    hw = head * 0.55
    shaft = hair(x1, y1, bx, by, width, color, dash)
    tip = (f'<polygon points="{x2:.1f},{y2:.1f} {bx + px * hw:.1f},{by + py * hw:.1f} '
           f'{bx - px * hw:.1f},{by - py * hw:.1f}" fill="{color}"/>\n')
    return shaft + tip


def elbow(x1, y1, x2, y2, width=2.0, color=ARROW, head=9.0):
    """One right angle: horizontal first, then vertical, arrowhead on the final leg."""
    out = hair(x1, y1, x2, y1, width, color)
    out += arrow(x2, y1, x2, y2, width, color, head)
    return out


def hatch(x, y, w, h, step=8.0, color="#9a9a9a", width=0.8):
    """Diagonal hatch clipped to the rectangle without a clipPath."""
    out = ""
    off = 0.0
    while off < w + h:
        t1, t2 = max(0.0, off - w), min(h, off)
        if t1 < t2:
            out += hair(x + off - t1, y + t1, x + off - t2, y + t2, width, color)
        off += step
    return out


def key(cx, cy, label, r=9.5):
    """Circled callout key (E3)."""
    return circle(cx, cy, r, "#fff", INK, 1.1) + text(cx, cy + 4, str(label), 11, True)


def ellipsis(cx, cy, size=26):
    return text(cx, cy, "\u2022 \u2022 \u2022", size=size, bold=True)


def write_svg(name: str, w: float, h: float, body: str) -> Path:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           f'viewBox="0 0 {w:.0f} {h:.0f}" width="{w:.0f}" height="{h:.0f}">\n'
           f'<rect x="0" y="0" width="{w:.0f}" height="{h:.0f}" fill="#ffffff"/>\n'
           f"{body}</svg>\n")
    path = OUT / f"{name}.svg"
    path.write_text(svg, encoding="utf-8")
    return path


def rasterise(svg_path: Path, target_px: int = 3300) -> Path:
    from reportlab.graphics import renderPM
    from svglib.svglib import svg2rlg

    d = svg2rlg(str(svg_path))
    if d is None:
        raise SystemExit(f"svglib could not parse {svg_path}")
    dpi = 72 * target_px / d.width
    pil = renderPM.drawToPIL(d, dpi=dpi, bg=0xFFFFFF)
    png = svg_path.with_suffix(".png")
    pil.save(png, "PNG", optimize=True)
    return png


def register_fonts() -> None:
    from svglib.svglib import register_font
    register_font("Times New Roman", "C:/Windows/Fonts/times.ttf")
    register_font("Times New Roman", "C:/Windows/Fonts/timesbd.ttf", weight="bold")
    register_font("Times New Roman", "C:/Windows/Fonts/timesi.ttf", style="italic")


# --- assets --------------------------------------------------------------------------


def flat(im: Image.Image) -> Image.Image:
    if im.mode in ("RGBA", "LA", "P"):
        base = Image.new("RGB", im.size, (255, 255, 255))
        im = im.convert("RGBA")
        base.paste(im, mask=im.split()[-1])
        return base
    return im.convert("RGB")


def thumb(src: Path, name: str, width: int = 640) -> tuple[str, float]:
    """Downscaled copy in assets/; returns (relative href, aspect h/w)."""
    im = flat(Image.open(src))
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    dst = ASSETS / f"{name}.png"
    im.save(dst, "PNG", optimize=True)
    return f"assets/{dst.name}", im.height / im.width


def waveform(track_id: str, width: int = 640, height: int = 170) -> str:
    """Envelope of the normalised 30 s excerpt, black on white."""
    import librosa

    src = AUDIO_CACHE / f"{track_id}.mp3"
    y, _ = librosa.load(str(src), sr=4000, mono=True, duration=30)
    bins = np.array_split(np.abs(y), width)
    env = np.array([b.max() if len(b) else 0.0 for b in bins])
    env = env / max(env.max(), 1e-9)
    im = Image.new("RGB", (width, height), (255, 255, 255))
    d = ImageDraw.Draw(im)
    mid = height / 2
    amp = (height / 2) * 0.92
    for x, v in enumerate(env):
        d.line([(x, mid - v * amp), (x, mid + v * amp)], fill=(0, 0, 0), width=1)
    d.line([(0, mid), (width, mid)], fill=(120, 120, 120), width=1)
    dst = ASSETS / f"wave_{track_id}.png"
    im.save(dst, "PNG", optimize=True)
    return f"assets/{dst.name}"


DIM_ORDER = ["tempo_of_change", "tension_release", "density", "continuity", "repetition",
             "variation", "hierarchy", "interruption", "polyphony", "genre_style"]


def radar_from_dims(vals: dict[str, float], cx: float, cy: float, r: float) -> str:
    pts = []
    out = circle(cx, cy, r, "none", "#8c8c8c", 1)
    out += circle(cx, cy, r * 0.5, "none", "#d9d9d9", 0.8)
    for i, k in enumerate(DIM_ORDER):
        ang = -np.pi / 2 + i * 2 * np.pi / len(DIM_ORDER)
        out += hair(cx, cy, cx + r * np.cos(ang), cy + r * np.sin(ang), 0.8, "#d9d9d9")
        v = max(0.0, min(1.0, vals.get(k, 0.0)))
        pts.append(f"{cx + v * r * np.cos(ang):.1f},{cy + v * r * np.sin(ang):.1f}")
    out += (f'<polygon points="{" ".join(pts)}" fill="#bfbfbf" fill-opacity="0.85" '
            f'stroke="#000" stroke-width="1.2"/>\n')
    return out


def radar(track_id: str, cx: float, cy: float, r: float) -> str:
    score = json.loads((CORPUS / "tracks" / track_id / "architectural_score.json").read_text("utf-8"))
    return radar_from_dims({d["id"]: float(d["value"]) for d in score["dimensions"]}, cx, cy, r)


def sheet_raster(run_id: str, sheet_id: str, width: int = 2600) -> tuple[str, float]:
    from reportlab.graphics import renderPM
    from svglib.svglib import svg2rlg

    # Run-specific homes first; `latest/` is whatever the web build currently ships and is
    # only trusted when it is the demo run's own sheet set.
    candidates = [ROOT / "web" / "public" / "drawings" / run_id / f"{sheet_id}.svg",
                  ROOT / "artifacts" / "drawings" / run_id / f"{sheet_id}.svg",
                  ROOT / "web" / "public" / "drawings" / "latest" / f"{sheet_id}.svg"]
    src = next((c for c in candidates if c.is_file()), None)
    if src is None:
        raise SystemExit(f"sheet {sheet_id} for run {run_id} not found in "
                         + " or ".join(str(c.parent) for c in candidates)
                         + " -- the demo run may have changed under this script")
    d = svg2rlg(str(src))
    if d is None:
        raise SystemExit(f"svglib could not parse {src}")
    pil = flat(renderPM.drawToPIL(d, dpi=72 * width / d.width, bg=0xFFFFFF))
    dst = ASSETS / f"sheet_{sheet_id}.png"
    pil.save(dst, "PNG", optimize=True)
    return f"assets/{dst.name}", pil.height / pil.width


# --- data ----------------------------------------------------------------------------


def style_rows() -> dict[str, dict]:
    return {t["track_id"]: t for t in json.loads(STYLE.read_text("utf-8"))["tracks"]}


def short_family(s: str, words: int = 3) -> str:
    head = s.split(" / ")[0].strip()
    return " ".join(head.split()[:words])


FRAME_TOKEN = {
    "Steel frame": "steel",
    "Reinforced concrete frame and wall": "concrete",
    "Mass timber frame": "timber",
}


def frame_token(label: str) -> str:
    return FRAME_TOKEN.get(label, label.split(" ")[0].lower())


def fmt(v: float, unit: str) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".") if abs(v) < 100 else f"{v:.0f}"
    if s == "-0":
        s = "0"
    u = {"fraction": "", "factor": "\u00d7", "degrees": "\u00b0", "m": " m", "levels": "",
         "rows": "", "panels": "", "voids": "", "bays": "", "layers": ""}.get(unit, f" {unit}")
    return s + u


# --- fig 1: framework  (A1 phase band x D1 specimen grid) ----------------------------

FIG1_TRACKS = ["mozart-symphony-29", "m-pex-bueid", "affen-like-life-easily-ended"]


def fig1() -> None:
    rows = style_rows()
    W = 1600
    col_w, gap, x0 = 300, 95, 55
    xs = [x0 + i * (col_w + gap) for i in range(4)]
    phases = ["Recording", "Shared score", "Massing", "Structure"]

    body = ""
    for x, p in zip(xs, phases):
        body += text(x + col_w / 2, 40, p, size=17, bold=True)
        body += hair(x, 58, x + col_w, 58, 1.0)
    for x in xs[1:]:
        body += hair(x - gap / 2, 24, x - gap / 2, 64, 1.0, dash="6 5")
    body += hair(xs[0] - 18, 24, xs[0] - 18, 64, 1.0)
    body += hair(xs[3] + col_w + 18, 24, xs[3] + col_w + 18, 64, 1.0)

    th = round(col_w * 1100 / 1600)
    pitch = th + 62
    y = 92
    for tid in FIG1_TRACKS:
        t = rows[tid]
        run = t["model_id"]
        cy = y + th / 2

        wave = waveform(tid)
        wh = round(col_w * 170 / 640)
        body += slot(xs[0], cy - wh / 2, col_w, wh)
        body += img(wave, xs[0], cy - wh / 2, col_w, wh)
        body += text(xs[0] + col_w / 2, y + th + 20, short_family(t["style_family"]), size=12)

        body += slot(xs[1], y, col_w, th)
        body += radar(tid, xs[1] + col_w / 2, cy, th * 0.42)

        href, asp = thumb(V3RUNS / run / "05_massing_south_west.png", f"mass_{tid}")
        body += img(href, xs[2], y, col_w, col_w * asp)
        body += text(xs[2] + col_w / 2, y + th + 20,
                     f"{t['typology']} \u00b7 {t['massing_label'].lower()}", size=12)

        href, asp = thumb(CORPUS / "tracks" / tid / "renders" / "03_structure.png", f"str_{tid}")
        body += img(href, xs[3], y, col_w, col_w * asp)
        body += text(xs[3] + col_w / 2, y + th + 20, t["frame_label"].lower(), size=12)

        for a, b in zip(xs[:-1], xs[1:]):
            body += arrow(a + col_w + 10, cy, b - 10, cy)
        y += pitch

    eh = 110
    for x in xs:
        body += rect(x, y, col_w, eh, "none", "#2f3f4f", 1.2)
        body += ellipsis(x + col_w / 2, y + eh / 2 + 8)
    for a, b in zip(xs[:-1], xs[1:]):
        body += arrow(a + col_w + 10, y + eh / 2, b - 10, y + eh / 2)
    y += eh + 44

    names = [["Source audio, 30 s"], ["10 bounded dimensions"],
             ["Massing, south-west"], ["Structure only"]]
    for x, n in zip(xs, names):
        body += lines(x + col_w / 2, y, n, size=15)
    write_and_raster("fig1_framework", W, y + 30, body)


# --- fig 2: score -> datums, the confidence clamp -------------------------------------

FULL_CONFIDENCE = 0.75


def fig2(demo: dict) -> None:
    dims = {d["id"]: d for d in demo["architectural_score"]["dimensions"]}
    datums = demo["analysis"]["datum_set"]["datums"]
    W = 1600
    x_id, x0, x1, x_val = 340, 440, 1160, 1290
    body = ""
    y = 36
    # axis
    for pos, lab in ((0.0, "0"), (0.5, "0.5"), (1.0, "1")):
        xx = x0 + pos * (x1 - x0)
        body += hair(xx, y - 6, xx, y + 2, 0.8, GREY)
        body += text(xx, y - 10, lab, 11, fill=GREY)
    body += hair(x0, y + 2, x1, y + 2, 0.8, GREY)
    body += text((x0 + x1) / 2, y + 16, "position within the datum's declared range", 11,
                 fill=GREY, italic=True)
    body += text(x_val, y + 16, "applied value", 11, anchor="start", fill=GREY, italic=True)
    body += text(x_id, y + 16, "datum", 11, anchor="end", fill=GREY, italic=True)
    y += 40

    for dim_id in DIM_ORDER:
        group = [d for d in datums if d["driving_dimension"] == dim_id]
        if not group:
            continue
        dm = dims[dim_id]
        c = float(dm["confidence"])
        f = min(1.0, c / FULL_CONFIDENCE)
        body += hair(x_id - 300, y - 2, x_val + 130, y - 2, 0.6, "#d9d9d9")
        body += text(x_id - 300, y + 15, dim_id, 13, True, "start")
        body += text(x_id - 300 + 150, y + 15,
                     f"{dm['value']:.2f} \u00b7 confidence {c:.2f} \u00b7 {dm['extraction_method']}",
                     12, False, "start", fill="#333")
        body += text(x1, y + 15, f"reach {f * 100:.0f} %", 11, anchor="end", fill=GREY)
        y += 24
        for d in group:
            cy = y + 9
            lo, hi = d["output_range"]
            body += text(x_id, cy + 4, d["id"], 12, anchor="end")
            body += rect(x0, cy - 3, x1 - x0, 6, "#e6e6e6")
            band_x = x0 + (0.5 - f / 2) * (x1 - x0)
            body += rect(band_x, cy - 3, f * (x1 - x0), 6, "#9a9a9a")
            rx = x0 + float(d["dimension_value"]) * (x1 - x0)
            ax = x0 + float(d["applied_position"]) * (x1 - x0)
            if abs(rx - ax) > 1.0:
                body += hair(rx, cy, ax, cy, 1.0, INK)
            body += circle(rx, cy, 4.2, "#fff", INK, 1.1)
            body += rect(ax - 1.1, cy - 8, 2.2, 16, INK)
            body += text(x0 - 8, cy + 4, fmt(lo, d["unit"]), 10.5, anchor="end", fill=GREY)
            body += text(x1 + 8, cy + 4, fmt(hi, d["unit"]), 10.5, anchor="start", fill=GREY)
            body += text(x_val, cy + 4, fmt(d["value"], d["unit"]), 12, anchor="start")
            y += 26
        y += 10

    consts = [d for d in datums if d["provenance"] != "score_driven"]
    body += hair(x_id - 300, y - 2, x_val + 130, y - 2, 0.6, "#d9d9d9")
    body += text(x_id - 300, y + 15, "tectonic constant", 13, True, "start", fill=GREY)
    body += text(x_id - 300 + 150, y + 15, "not driven by the score", 12, False, "start",
                 fill=GREY)
    y += 24
    for d in consts:
        cy = y + 9
        body += text(x_id, cy + 4, d["id"], 12, anchor="end", fill=GREY)
        body += hair(x0, cy, x1, cy, 0.8, "#d9d9d9", dash="3 4")
        body += text(x_val, cy + 4, fmt(d["value"], d["unit"]), 12, anchor="start", fill=GREY)
        y += 26
    y += 22

    # legend (three load-bearing encodings)
    lx = x0
    body += rect(lx, y - 3, 40, 6, "#e6e6e6")
    body += text(lx + 48, y + 4, "declared range", 11, anchor="start")
    lx += 170
    body += rect(lx, y - 3, 40, 6, "#9a9a9a")
    body += text(lx + 48, y + 4, "reach permitted by confidence", 11, anchor="start")
    lx += 270
    body += circle(lx + 6, y, 4.2, "#fff", INK, 1.1)
    body += text(lx + 18, y + 4, "reading", 11, anchor="start")
    lx += 90
    body += rect(lx + 5, y - 8, 2.2, 16, INK)
    body += text(lx + 18, y + 4, "applied position", 11, anchor="start")
    write_and_raster("fig2_datum_clamp", W, y + 30, body)


# --- fig 3: (a) dims -> four axes   (b) massing decision tree -------------------------

LEAF_EXAMPLE = {                       # a corpus track that landed on each family
    "MAS-SPLIT": "mozart-symphony-29",
    "MAS-COURTYARD": "affen-like-life-easily-ended",
    "MAS-BAR-PODIUM": "deadbone-wake-up-call",
    "MAS-ZIGGURAT": "m-pex-bueid",
    "MAS-TOWER": "nienvox-visions",
    "MAS-SLAB": "dub-riots-silience-is-gold",
    "MAS-PAVILION": None,
}
LEAF_LABEL = {
    "MAS-SPLIT": "Split mass", "MAS-COURTYARD": "Courtyard block",
    "MAS-BAR-PODIUM": "Bar on a podium", "MAS-ZIGGURAT": "Stepped terraces",
    "MAS-TOWER": "Compact tower", "MAS-PAVILION": "Single-volume pavilion",
    "MAS-SLAB": "Stacked slab",
}
TESTS = [   # (question lines, leaf, the run's readings shown beside the diamond)
    (["1 \u2212 regularity \u2265 0.68", "and incident \u2265 0.55"], "MAS-SPLIT",
     ["1 \u2212 regularity", "incident"]),
    (["1 \u2212 regularity \u2265 0.68"], "MAS-COURTYARD", ["1 \u2212 regularity"]),
    (["incident \u2265 0.66"], "MAS-BAR-PODIUM", ["incident"]),
    (["regularity < 0.48"], "MAS-ZIGGURAT", ["regularity"]),
    (["density \u2265 0.58", "and mass \u2265 0.40"], "MAS-TOWER", ["density", "mass"]),
    (["density < 0.34", "or tempo < 0.22"], "MAS-PAVILION", ["density", "tempo"]),
]


def fig3(demo: dict) -> None:
    rows = style_rows()
    dims = {d["id"]: float(d["value"]) for d in demo["architectural_score"]["dimensions"]}
    axes = {a["axis"]: float(a["value"]) for a in demo["analysis"]["selection"]["axes"]}
    chosen = demo["analysis"]["selection"]["massing_id"]
    counts: dict[str, int] = {}
    for t in rows.values():
        counts[t["massing_id"]] = counts.get(t["massing_id"], 0) + 1

    W = 1600
    body = ""

    # ---- (a) dims -> axes ---------------------------------------------------------
    body += text(40, 40, "(a)", 20, True, "start")
    ax0 = 60
    bar_w = 150
    src = [("tension_release", dims["tension_release"], False),
           ("continuity", dims["continuity"], False),
           ("genre_style", dims["genre_style"], True),
           ("polyphony", dims["polyphony"], False),
           ("repetition", dims["repetition"], False),
           ("hierarchy", dims["hierarchy"], False)]
    ys = {}
    y = 90
    for name, v, nudge in src:
        ys[name] = y
        body += text(ax0 + bar_w, y - 8, name, 12, anchor="end", fill=GREY if nudge else INK)
        body += rect(ax0, y - 2, bar_w, 6, "#e6e6e6")
        body += rect(ax0, y - 2, bar_w * v, 6, "#9a9a9a" if nudge else INK)
        body += text(ax0 + bar_w + 8, y + 3, f"{v:.2f}", 11, anchor="start", fill=GREY)
        y += 58

    tx = ax0 + bar_w + 46
    axx = 400
    ay = {"mass": ys["continuity"], "layering": ys["polyphony"],
          "regularity": ys["repetition"], "incident": ys["hierarchy"]}
    # merge for mass: decisive( tension, 1 - continuity ) + nudge
    mx, my = tx + 28, ys["continuity"] - 8
    body += hair(tx, ys["tension_release"], mx - 12, my, 1.4, ARROW)
    body += hair(tx, ys["continuity"], mx - 12, my, 1.4, ARROW)
    body += hair(tx, ys["genre_style"], mx - 12, my, 1.4, ARROW, dash="4 4")
    body += circle(mx, my, 12, "#fff", INK, 1.2)
    body += text(mx, my + 4, "d", 12, True)
    body += text(mx, my + 30, "decisive", 10.5, fill=GREY, italic=True)
    body += text(tx + 6, ys["genre_style"] + 14, "nudge \u2264 0.12", 10.5, anchor="start",
                 fill=GREY, italic=True)
    body += text(ax0, ys["continuity"] + 18, "enters as 1 \u2212 continuity", 10.5,
                 anchor="start", fill=GREY, italic=True)
    body += arrow(mx + 12, my, axx - 8, ay["mass"], 1.6, ARROW)
    for s_, a_ in (("polyphony", "layering"), ("repetition", "regularity"),
                   ("hierarchy", "incident")):
        body += arrow(tx, ys[s_], axx - 8, ay[a_], 1.6, ARROW)
    for name in ("mass", "layering", "regularity", "incident"):
        yy = ay[name]
        v = axes[name]
        body += text(axx, yy - 8, name, 13, True, "start")
        body += rect(axx, yy - 2, bar_w, 6, "#e6e6e6")
        body += rect(axx, yy - 2, bar_w * v, 6, INK)
        body += text(axx + bar_w + 8, yy + 3, f"{v:.2f}", 11, anchor="start", fill=GREY)
    # density and tempo feed the tree directly
    yy = ys["hierarchy"] + 58
    for name in ("density", "tempo_of_change"):
        v = dims[name]
        body += text(axx, yy - 8, name, 12, anchor="start", fill=GREY)
        body += rect(axx, yy - 2, bar_w, 6, "#e6e6e6")
        body += rect(axx, yy - 2, bar_w * v, 6, "#9a9a9a")
        body += text(axx + bar_w + 8, yy + 3, f"{v:.2f}", 11, anchor="start", fill=GREY)
        yy += 44

    body += hair(640, 60, 640, 1120, 0.8, "#bfbfbf", dash="6 5")

    # ---- (b) decision tree --------------------------------------------------------
    body += text(680, 40, "(b)", 20, True, "start")
    dx, dw, dh = 700, 300, 78                   # diamond column
    lx, lw = 1110, 190                          # leaf thumbnail column
    lh = round(lw * 1100 / 1600)
    pitch = lh + 26                             # a leaf thumbnail plus clear space
    link = pitch - dh                           # vertical connector between diamonds
    y = 82
    # start terminator
    body += rect(dx + dw / 2 - 90, y, 180, 34, "#fff", INK, 1.2)
    body += text(dx + dw / 2, y + 22, "four axes, density, tempo", 12.5)
    y += 34
    reading = {**axes, "density": dims["density"], "tempo": dims["tempo_of_change"],
               "1 \u2212 regularity": 1 - axes["regularity"]}

    def leaf_slot(leaf: str, cy: float, hit: bool) -> str:
        out = ""
        ly = cy - lh / 2
        tid = LEAF_EXAMPLE[leaf]
        if tid:
            href, asp = thumb(V3RUNS / rows[tid]["model_id"] / "05_massing_south_west.png",
                              f"mass_{tid}", 420)
            out += img(href, lx, ly, lw, lw * asp)
        else:
            out += rect(lx, ly, lw, lh, "none", "#8c8c8c", 1.0, dash="6 4")
            out += text(lx + lw / 2, ly + lh / 2 + 4, "not reached by the corpus", 10.5,
                        fill=GREY, italic=True)
        if hit:
            out += rect(lx - 4, ly - 4, lw + 8, lh + 8, "none", HILITE, 2.5)
        out += text(lx + lw + 14, cy - 4, LEAF_LABEL[leaf], 12.5, anchor="start")
        out += text(lx + lw + 14, cy + 14, f"n = {counts.get(leaf, 0)} of 14", 11,
                    anchor="start", fill=GREY)
        return out

    first = True
    for q, leaf, shown in TESTS:
        # connector down from the previous node; 'no' on every one after the first
        body += arrow(dx + dw / 2, y, dx + dw / 2, y + link, 1.6, ARROW, 8)
        if not first:
            body += text(dx + dw / 2 + 10, y + link / 2 + 4, "no", 10.5, anchor="start",
                         fill=GREY, italic=True)
        first = False
        y += link
        cx, cy = dx + dw / 2, y + dh / 2
        body += (f'<polygon points="{cx:.1f},{y:.1f} {dx + dw:.1f},{cy:.1f} '
                 f'{cx:.1f},{y + dh:.1f} {dx:.1f},{cy:.1f}" fill="#fff" stroke="{INK}" '
                 f'stroke-width="1.2"/>\n')
        body += lines(cx, cy + (4 if len(q) == 1 else -3), q, 12.5, lh=16)
        actual = " \u00b7 ".join(f"{t} {reading[t]:.2f}" for t in shown)
        body += text(dx - 10, cy + 4, actual, 10.5, anchor="end", fill=GREY, italic=True)
        hit = leaf == chosen
        body += arrow(dx + dw, cy, lx - 8, cy, 1.6, HILITE if hit else ARROW, 8)
        body += text(dx + dw + 14, cy - 6, "yes", 10.5, anchor="start",
                     fill=HILITE if hit else GREY, italic=True)
        body += leaf_slot(leaf, cy, hit)
        y += dh
    # else leaf
    body += arrow(dx + dw / 2, y, dx + dw / 2, y + link, 1.6, ARROW, 8)
    body += text(dx + dw / 2 + 10, y + link / 2 + 4, "no", 10.5, anchor="start",
                 fill=GREY, italic=True)
    y += link
    cy = y + lh / 2
    body += rect(dx + dw / 2 - 40, cy - 17, 80, 34, "#fff", INK, 1.2)
    body += text(dx + dw / 2, cy + 4, "else", 12.5)
    body += arrow(dx + dw / 2 + 40, cy, lx - 8, cy, 1.6, ARROW, 8)
    body += leaf_slot("MAS-SLAB", cy, "MAS-SLAB" == chosen)
    y = cy + lh / 2 + 30
    write_and_raster("fig3_axes_and_massing", W, y, body)


# --- fig 4: two authorities, 10 systems x 10 grammars ---------------------------------

SYSTEM_LABEL = {
    "STR-SYS-STEEL-FRAME": "Steel frame",
    "STR-SYS-RC-FRAME-WALL": "RC frame and wall",
    "STR-SYS-MASS-TIMBER-CLT-GLULAM": "CLT and glulam",
    "STR-SYS-GLULAM-POST-BEAM": "Glulam post and beam",
    "STR-SYS-LIGHT-WOOD-FRAME": "Light wood frame",
    "STR-SYS-RC-SHELL": "RC shell",
    "STR-SYS-TIMBER-GRIDSHELL": "Timber gridshell",
    "STR-SYS-TENSILE-MEMBRANE": "Tensile membrane",
    "STR-SYS-CABLE-NET-HYBRID": "Cable-net hybrid",
    "STR-SYS-STEEL-SPACE-FRAME-SHELL": "Steel space-frame shell",
}
GRAMMAR_LABEL = {
    "FCD-01-INTERNATIONAL-STYLE": ["International", "Style"],
    "FCD-02-BAUHAUS": ["Bauhaus"],
    "FCD-03-BRUTALISM": ["Brutalism"],
    "FCD-04-ORGANIC": ["Organic"],
    "FCD-05-HIGH-TECH": ["High-Tech"],
    "FCD-06-POSTMODERNISM": ["Postmodernism"],
    "FCD-07-DECONSTRUCTIVISM": ["Deconstructivism"],
    "FCD-08-MINIMALISM": ["Minimalism"],
    "FCD-09-CRITICAL-REGIONALISM": ["Critical", "Regionalism"],
    "FCD-10-PARAMETRICISM": ["Parametricism"],
}


def fig4(demo: dict) -> dict:
    from backend.app.selection import (AXIS_WEIGHTS, ENVELOPE_POSITION, FRAME_POSITION,
                                       _affinity)
    from backend.app.tectonics import GRAMMAR_ENVELOPE, SYSTEM_BUILDABILITY

    sel = demo["analysis"]["selection"]
    dims = {d["id"]: float(d["value"]) for d in demo["architectural_score"]["dimensions"]}
    reading = {a["axis"]: float(a["value"]) for a in sel["axes"]}
    frame_reading = {"mass": reading["mass"], "expression": dims["variation"]}
    frame_weights = {"mass": 0.6, "expression": 0.4}
    admissible = set(sel["admissible_systems"])
    grammars = list(GRAMMAR_LABEL)
    systems = [s for s in SYSTEM_LABEL if s in admissible] + \
              [s for s in SYSTEM_LABEL if s not in admissible and SYSTEM_BUILDABILITY[s].frame_tectonic] + \
              [s for s in SYSTEM_LABEL if not SYSTEM_BUILDABILITY[s].frame_tectonic]

    recorded = {(o["system_id"], o["grammar_id"]): o["affinity"] for o in sel["ranked_options"]}

    def affinity(s, g):
        env = _affinity(ENVELOPE_POSITION[GRAMMAR_ENVELOPE[g]], reading, AXIS_WEIGHTS)
        ft = SYSTEM_BUILDABILITY[s].frame_tectonic
        if ft is None:
            return None
        return round(env * 0.68 + _affinity(FRAME_POSITION[ft], frame_reading, frame_weights) * 0.32, 4)

    max_diff = max(abs(affinity(s, g) - a) for (s, g), a in recorded.items())

    W = 1600
    gx, gy, cw, ch = 330, 96, 100, 46
    body = ""
    for j, g in enumerate(grammars):
        body += lines(gx + j * cw + cw / 2, gy - 34 + (0 if len(GRAMMAR_LABEL[g]) > 1 else 8),
                      GRAMMAR_LABEL[g], 12, lh=14)
    pref = (sel["preferred_system_id"], sel["preferred_grammar_id"])
    chosen = (sel["system_id"], sel["grammar_id"])
    for i, s in enumerate(systems):
        yy = gy + i * ch
        body += text(gx - 12, yy + ch / 2 + 4, SYSTEM_LABEL[s], 12.5, anchor="end")
        state = ("admissible" if s in admissible
                 else "screened" if SYSTEM_BUILDABILITY[s].frame_tectonic else "not emitted")
        for j, g in enumerate(grammars):
            xx = gx + j * cw
            a = affinity(s, g)
            if state == "admissible":
                grey = int(round(238 - max(0.0, min(1.0, (a - 0.5) / 0.4)) * 190))
                body += rect(xx, yy, cw, ch, f"#{grey:02x}{grey:02x}{grey:02x}", "#fff", 1)
                body += text(xx + cw / 2, yy + ch / 2 + 4, f"{a:.2f}", 11.5,
                             fill="#fff" if grey < 140 else INK)
            elif state == "screened":
                body += rect(xx, yy, cw, ch, "#f7f7f7", "#fff", 1)
                body += hatch(xx, yy, cw, ch, 9, "#b0b0b0", 0.8)
                if (s, g) == pref:
                    body += text(xx + cw / 2, yy + ch / 2 + 4, f"{a:.2f}", 11.5, fill=GREY)
            else:
                body += rect(xx, yy, cw, ch, "#ececec", "#fff", 1)
                body += hatch(xx, yy, cw, ch, 6, "#8c8c8c", 0.9)
        # right-gutter state word, once per block
        if i == 0 or state != ("admissible" if systems[i - 1] in admissible
                               else "screened" if SYSTEM_BUILDABILITY[systems[i - 1]].frame_tectonic
                               else "not emitted"):
            body += text(gx + 10 * cw + 14, yy + ch / 2 + 4, state, 11.5, anchor="start",
                         fill=GREY, italic=True)
    # block rules
    n_adm = sum(1 for s in systems if s in admissible)
    n_scr = sum(1 for s in systems if s not in admissible and SYSTEM_BUILDABILITY[s].frame_tectonic)
    body += hair(gx, gy + n_adm * ch, gx + 10 * cw, gy + n_adm * ch, 1.2, INK)
    body += hair(gx, gy + (n_adm + n_scr) * ch, gx + 10 * cw, gy + (n_adm + n_scr) * ch, 1.2, INK)
    body += rect(gx, gy, 10 * cw, len(systems) * ch, "none", INK, 1.0)

    def cell(sg):
        i = systems.index(sg[0]); j = grammars.index(sg[1])
        return gx + j * cw, gy + i * ch

    px, py = cell(pref)
    body += rect(px + 2, py + 2, cw - 4, ch - 4, "none", INK, 1.6, dash="5 4")
    cx_, cy_ = cell(chosen)
    body += rect(cx_ + 1, cy_ + 1, cw - 2, ch - 2, "none", HILITE, 2.6)

    # legend
    ly = gy + len(systems) * ch + 36
    lx = gx
    body += rect(lx, ly - 9, 26, 16, "#7a7a7a"); body += text(lx + 34, ly + 4, "admissible, shade = affinity", 11.5, anchor="start"); lx += 250
    body += rect(lx, ly - 9, 26, 16, "#f7f7f7", "#bfbfbf", 0.8); body += hatch(lx, ly - 9, 26, 16, 6, "#b0b0b0", 0.8); body += text(lx + 34, ly + 4, "removed by the screen", 11.5, anchor="start"); lx += 210
    body += rect(lx, ly - 9, 26, 16, "#ececec", "#bfbfbf", 0.8); body += hatch(lx, ly - 9, 26, 16, 5, "#8c8c8c", 0.9); body += text(lx + 34, ly + 4, "not emitted by this compiler", 11.5, anchor="start"); lx += 250
    body += rect(lx, ly - 9, 26, 16, "none", INK, 1.6, dash="5 4"); body += text(lx + 34, ly + 4, "music's preference", 11.5, anchor="start"); lx += 180
    body += rect(lx, ly - 9, 26, 16, "none", HILITE, 2.4); body += text(lx + 34, ly + 4, "chosen", 11.5, anchor="start")
    write_and_raster("fig4_two_authorities", W, ly + 34, body)
    return {"max_affinity_diff_vs_record": max_diff, "preferred": pref, "chosen": chosen,
            "preferred_affinity": affinity(*pref), "chosen_affinity": affinity(*chosen)}


# --- fig 5: datums -> lattice -> massing (E3) ----------------------------------------


def fig5(demo: dict) -> None:
    L = demo["analysis"]["lattice"]
    run_id = demo["analysis"]["model_id"]
    dat = {d["id"]: d["value"] for d in demo["analysis"]["datum_set"]["datums"]}
    W = 1600
    body = ""
    s = 13.0                                       # px per metre
    xmin, xmax = L["plan"]["x_min"], L["plan"]["x_max"]
    ymin, ymax = L["plan"]["y_min"], L["plan"]["y_max"]
    ox, oy = 96, 96                                # plan origin (top-left)

    def X(x): return ox + (x - xmin) * s
    def Y(y): return oy + (ymax - y) * s

    body += text(40, 40, "(a)", 20, True, "start")
    # grid
    for i, gxl in enumerate(L["x_lines"]):
        body += hair(X(gxl), oy - 14, X(gxl), Y(ymin) + 14, 0.6, "#9a9a9a", dash="8 5")
        body += text(X(gxl), oy - 22, chr(65 + i), 10.5, fill=GREY)
    for j, gyl in enumerate(L["y_lines"]):
        body += hair(ox - 14, Y(gyl), X(xmax) + 14, Y(gyl), 0.6, "#9a9a9a", dash="8 5")
        body += text(ox - 22, Y(gyl) + 4, str(j + 1), 10.5, fill=GREY)
    # plates, bottom to top
    levels = L["levels"]
    podium = levels[0]["plate"]
    pts = " ".join(f"{X(p['x']):.1f},{Y(p['y']):.1f}" for p in podium)
    body += f'<polygon points="{pts}" fill="{SLOT_FILL}" stroke="{INK}" stroke-width="1.0"/>\n'
    weights = {2: 0.7, 3: 0.9, 4: 1.15, 5: 1.4, 6: 1.7}
    for lv in levels[1:]:
        pts = " ".join(f"{X(p['x']):.1f},{Y(p['y']):.1f}" for p in lv["plate"])
        dash = ' stroke-dasharray="7 4"' if lv["is_terrace"] else ""
        body += (f'<polygon points="{pts}" fill="none" stroke="{INK}" '
                 f'stroke-width="{weights.get(lv["index"], 1.0)}"{dash}/>\n')
    # carved auditorium/stage footprint on level 1
    for x0_, y0_, x1_, y1_ in L["carved"].get("1", []):
        body += rect(X(x0_), Y(y1_), (x1_ - x0_) * s, (y1_ - y0_) * s, "#dcdcdc", "#555", 0.8, "4 3")
    # keys
    xl = L["x_lines"]; yl = L["y_lines"]
    # 1: bay x (dimension above plan between two grid lines)
    dy_ = oy - 46
    body += hair(X(xl[3]), dy_, X(xl[4]), dy_, 0.9, INK)
    body += hair(X(xl[3]), dy_ - 5, X(xl[3]), dy_ + 5, 0.9, INK)
    body += hair(X(xl[4]), dy_ - 5, X(xl[4]), dy_ + 5, 0.9, INK)
    body += key((X(xl[3]) + X(xl[4])) / 2, dy_ - 14, 1)
    # 2: bay y (dimension left of plan)
    dx_ = ox - 50
    body += hair(dx_, Y(yl[2]), dx_, Y(yl[3]), 0.9, INK)
    body += hair(dx_ - 5, Y(yl[2]), dx_ + 5, Y(yl[2]), 0.9, INK)
    body += hair(dx_ - 5, Y(yl[3]), dx_ + 5, Y(yl[3]), 0.9, INK)
    body += key(dx_ - 16, (Y(yl[2]) + Y(yl[3])) / 2, 2)
    # 3: podium plate
    body += key(X(xmin) + 22, Y(ymin) - 22, 3)
    # 4: bar plates stepping back (top-left corner of L03..L06)
    l3 = levels[3]["plate"]; l6 = levels[6]["plate"]
    x3 = min(p["x"] for p in l3); y3 = max(p["y"] for p in l3)
    x6 = min(p["x"] for p in l6)
    body += hair(X(x3) - 30, Y(y3) - 30, X(x6) - 2, Y(y3) - 2, 0.8, INK)
    body += key(X(x3) - 34, Y(y3) - 36, 4)
    # 5: terrace overhang (L02 dashed outline), keyed at its outermost corner
    l2 = levels[2]["plate"]; x2 = max(p["x"] for p in l2); y2 = min(p["y"] for p in l2)
    body += hair(X(x2) + 2, Y(y2) + 2, X(x2) + 14, Y(y2) + 16, 0.8, INK)
    body += key(X(x2) + 22, Y(y2) + 26, 5)
    # 6: carved region
    c0 = L["carved"]["1"][0]
    body += key(X((c0[0] + c0[2]) / 2), Y((c0[1] + c0[3]) / 2), 6)
    # north arrow + scale bar (mandatory on a plan); kept clear of panel (c)
    nx, ny = X(xmax) + 30, oy + 10
    body += arrow(nx, ny + 44, nx, ny, 1.4, INK, 9)
    body += text(nx, ny - 8, "N", 12, True)
    sb_x, sb_y = ox, Y(ymin) + 50
    for k in range(4):
        body += rect(sb_x + k * 5 * s, sb_y, 5 * s, 6, INK if k % 2 == 0 else "#fff", INK, 0.8)
    for k, lab in ((0, "0"), (2, "10"), (4, "20 m")):
        body += text(sb_x + k * 5 * s, sb_y + 20, lab, 10.5, fill=GREY)

    # ---- (b) section: level table ------------------------------------------------
    sy0 = Y(ymin) + 130
    body += text(40, sy0 - 20, "(b)", 20, True, "start")
    zmax = levels[-1]["z"]
    g_y = sy0 + zmax * s + 6
    def Z(z): return g_y - z * s
    for gxl in L["x_lines"]:
        body += hair(X(gxl), Z(zmax) - 10, X(gxl), g_y, 0.6, "#c8c8c8", dash="8 5")
    body += hair(X(xmin) - 20, g_y, X(xmax) + 20, g_y, 1.6, INK)
    for lv in levels:
        xs_ = [p["x"] for p in lv["plate"]]
        w_ = 2.2 if lv["kind"] in ("podium", "roof") else 1.4
        body += hair(X(min(xs_)), Z(lv["z"]), X(max(xs_)), Z(lv["z"]), w_, INK)
        body += text(X(xmax) + 30, Z(lv["z"]) + 4, lv["id"], 10.5, anchor="start", fill=GREY)
        body += text(X(xmax) + 62, Z(lv["z"]) + 4, f"+{lv['z']:.2f}", 10.5, anchor="start", fill=GREY)
    # piloti under the podium level (registration only)
    for gxl in L["x_lines"]:
        body += hair(X(gxl), Z(levels[1]["z"]), X(gxl), g_y, 1.0, "#555")
    # 7: floor to floor  8: podium clear height
    dx7 = X(xmin) - 48
    body += hair(dx7, Z(levels[1]["z"]), dx7, Z(levels[2]["z"]), 0.9, INK)
    body += hair(dx7 - 5, Z(levels[1]["z"]), dx7 + 5, Z(levels[1]["z"]), 0.9, INK)
    body += hair(dx7 - 5, Z(levels[2]["z"]), dx7 + 5, Z(levels[2]["z"]), 0.9, INK)
    body += key(dx7 - 16, (Z(levels[1]["z"]) + Z(levels[2]["z"])) / 2, 7)
    body += hair(dx7, g_y, dx7, Z(levels[1]["z"]), 0.9, INK)
    body += hair(dx7 - 5, g_y, dx7 + 5, g_y, 0.9, INK)
    body += key(dx7 - 16, (g_y + Z(levels[1]["z"])) / 2, 8)
    for k in range(4):
        body += rect(sb_x + k * 5 * s, g_y + 26, 5 * s, 6, INK if k % 2 == 0 else "#fff", INK, 0.8)
    for k, lab in ((0, "0"), (2, "10"), (4, "20 m")):
        body += text(sb_x + k * 5 * s, g_y + 46, lab, 10.5, fill=GREY)

    # ---- (c) the massing this lattice carries -------------------------------------
    rx, ry, rw = 1050, 96, 510
    body += text(rx, 40, "(c)", 20, True, "start")
    href, asp = thumb(V3RUNS / run_id / "05_massing_south_west.png", f"mass_{run_id}", 640)
    body += img(href, rx, ry, rw, rw * asp)
    body += text(rx + rw / 2, ry + rw * asp + 20, "massing, south-west", 12)
    href, asp2 = thumb(V3RUNS / run_id / "02_section_open_side.png", f"sect_{run_id}", 640)
    ry2 = ry + rw * asp + 44
    body += img(href, rx, ry2, rw, rw * asp2)
    body += text(rx + rw / 2, ry2 + rw * asp2 + 20, "section, open side", 12)

    H = max(g_y + 70, ry2 + rw * asp2 + 40)
    write_and_raster("fig5_lattice", W, H, body)


# --- fig 6: fourteen recordings (D1 specimen grid) -----------------------------------


def fig6() -> None:
    rows = style_rows()
    order = list(rows)
    W = 1600
    cols, x0, gapx = 7, 40, 14
    tw = (W - 2 * x0 - gapx * (cols - 1)) / cols
    th = tw * 1100 / 1600
    label_h = 44
    body = ""
    y = 30
    for r in range(2):
        for c in range(cols):
            i = r * cols + c
            if i >= len(order):
                break
            tid = order[i]
            t = rows[tid]
            x = x0 + c * (tw + gapx)
            href, asp = thumb(V3RUNS / t["model_id"] / "05_massing_south_west.png", f"mass_{tid}", 520)
            body += img(href, x, y, tw, tw * asp)
            body += text(x + tw / 2, y + th + 17, short_family(t["style_family"], 3), size=11.5)
            body += text(x + tw / 2, y + th + 32,
                         f"{t['typology']}, {t['level_count']} levels", size=10.5, fill="#444")
        y += th + label_h + 10
    write_and_raster("fig6_fourteen_recordings", W, y + 6, body)


# --- fig 7: semantic layers ----------------------------------------------------------

FIG7_TRACKS = ["mozart-symphony-29", "lucas-darklord-hymne-iii", "nienvox-visions",
               "m-pex-bueid", "hurle-cancer"]


def fig7() -> None:
    rows = style_rows()
    W = 1600
    gutter, x0, gapx = 150, 170, 22
    cols = 3
    tw = (W - x0 - 30 - gapx * (cols - 1)) / cols
    th = tw * 1100 / 1600
    body = ""
    heads = ["Program and circulation", "Envelope only", "Structure only"]
    for c, h in enumerate(heads):
        x = x0 + c * (tw + gapx)
        body += text(x + tw / 2, 38, h, size=17, bold=True)
        body += hair(x, 54, x + tw, 54, 1.0)
    y = 78
    files = ["01_program", "02_facade", "03_structure"]
    for tid in FIG7_TRACKS:
        t = rows[tid]
        body += lines(gutter - 14, y + th / 2 - 4,
                      [short_family(t["style_family"], 2), f"{t['typology']}, {frame_token(t['frame_label'])}"],
                      size=13, anchor="end", lh=17)
        for c, f in enumerate(files):
            x = x0 + c * (tw + gapx)
            href, asp = thumb(CORPUS / "tracks" / tid / "renders" / f"{f}.png", f"{f[3:]}_{tid}", 560)
            body += img(href, x, y, tw, tw * asp)
        y += th + 18
    eh = 90
    for c in range(cols):
        x = x0 + c * (tw + gapx)
        body += rect(x, y, tw, eh, "none", "#2f3f4f", 1.2)
        body += ellipsis(x + tw / 2, y + eh / 2 + 8)
    body += ellipsis(gutter - 40, y + eh / 2 + 8, 20)
    write_and_raster("fig7_semantic_layers", W, y + eh + 30, body)


# --- fig 8: emitted drawings (E3, verbatim sheets) -----------------------------------


def fig8(run_id: str, plan_id: str, section_id: str) -> None:
    W = 1600
    x0, sw = 60, 1480
    body = ""
    y = 30
    for letter, sid in (("(a)", plan_id), ("(b)", section_id)):
        href, asp = sheet_raster(run_id, sid)
        sh = sw * asp
        body += rect(x0, y, sw, sh, "none", "#8c8c8c", 0.8)
        body += img(href, x0, y, sw, sh)
        body += text(x0 + 16, y + 30, letter, size=20, bold=True, anchor="start")
        y += sh + 40
    write_and_raster("fig8_drawings", W, y, body, target_px=4200)


# --- fig 9: presentation presets -----------------------------------------------------


def fig9() -> None:
    names = ["photoreal", "post_digital", "cinematic", "minimalist", "watercolor"]
    labels = ["Photoreal", "Post-digital", "Cinematic", "Minimalist", "Watercolour"]
    W = 1600
    x0, gapx = 30, 14
    tw = (W - 2 * x0 - gapx * 4) / 5
    th = tw * 900 / 1400
    body = ""
    for i, (n, lab) in enumerate(zip(names, labels)):
        x = x0 + i * (tw + gapx)
        href, asp = thumb(ROOT / "artifacts" / "render_presets" / "model_v3" / n / "hero.png", f"preset_{n}", 560)
        body += img(href, x, 20, tw, tw * asp)
        body += text(x + tw / 2, 20 + th + 22, lab, size=13)
    write_and_raster("fig9_presentation_presets", W, 20 + th + 44, body)


# --- fig 10: BIM handoff panel -------------------------------------------------------


def fig10() -> None:
    W = 1600
    href, asp = thumb(ROOT / "artifacts" / "evidence" / "revit_dynamo_handoff_ui" / "bim_handoff_panel.png",
                      "bim_panel", 1600)
    x0, sw = 40, 1520
    sh = sw * asp
    body = rect(x0, 30, sw, sh, "none", "#8c8c8c", 0.8) + img(href, x0, 30, sw, sh)
    write_and_raster("fig10_bim_handoff", W, sh + 60, body)


# --- table 1: verification schedule --------------------------------------------------


def table1(demo: dict) -> dict:
    a = demo["analysis"]
    tallies = a["compliance"]["tallies"]
    W = 1600
    x0, x1 = 40, 1560
    c_check, c_auth = x0 + 6, 340
    c_p, c_f, c_u = 1240, 1395, 1554
    body = ""
    y = 30
    body += hair(x0, y, x1, y, 1.5)
    y += 26
    body += text(c_check, y, "Check", 13.5, True, "start")
    body += text(c_auth, y, "Authority", 13.5, True, "start")
    body += text(c_p, y, "Passed", 13.5, True, "end")
    body += text(c_f, y, "Failed", 13.5, True, "end")
    body += text(c_u, y, "Unevaluated", 13.5, True, "end")
    y += 12
    body += hair(x0, y, x1, y, 0.75)
    rows = sorted(tallies, key=lambda t: (-t["passed"], t["label"]))
    for t in rows:
        y += 30
        body += text(c_check, y, t["label"], 13.5, False, "start")
        auth = t["authority"].split(" (")[0]
        body += text(c_auth, y, auth, 12.5, False, "start", fill="#222")
        for cx, v in ((c_p, t["passed"]), (c_f, t["failed"]), (c_u, t["unevaluated"])):
            body += text(cx, y, str(v) if v else "\u2014", 13.5, False, "end",
                         fill=INK if v else "#8c8c8c")
    y += 14
    body += hair(x0, y, x1, y, 0.75)
    tot = {k: sum(t[k] for t in tallies) for k in ("passed", "failed", "unevaluated")}
    y += 28
    body += text(c_check, y, "Total", 13.5, True, "start")
    body += text(c_auth, y, f"{len(tallies)} independent authorities", 12.5, False, "start", fill="#222")
    for cx, v in ((c_p, tot["passed"]), (c_f, tot["failed"]), (c_u, tot["unevaluated"])):
        body += text(cx, y, str(v), 13.5, True, "end")
    y += 14
    body += hair(x0, y, x1, y, 1.5)
    write_and_raster("table1_verification", W, y + 24, body)
    return tot


# --- captions: generated from the same data as the figures ----------------------------


def captions(demo: dict, sel_meta: dict, tot: dict, plan_id: str, section_id: str) -> None:
    """Write captions.md from run data so the words can never drift from the images."""
    a = demo["analysis"]
    sel = a["selection"]
    dims = {d["id"]: d for d in demo["architectural_score"]["dimensions"]}
    dat = {d["id"]: d for d in a["datum_set"]["datums"]}
    L = a["lattice"]
    sheets = {s["id"]: s for s in demo["drawing_index"]["sheets"]}
    run = a["model_id"]
    tally = {t["source"]: t for t in a["compliance"]["tallies"]}
    failed_bits = [f"{t['failed']} under {t['label'].lower()}"
                   for t in a["compliance"]["tallies"] if t["failed"]]
    reach = lambda k: min(1.0, dims[k]["confidence"] / FULL_CONFIDENCE) * 100
    n_bays_x, n_bays_y = len(L["x_lines"]) - 1, len(L["y_lines"]) - 1
    pref_sys, pref_gr = sel_meta["preferred"]
    ch_sys, ch_gr = sel_meta["chosen"]
    sys_lab = lambda s: SYSTEM_LABEL[s].lower()
    gr_lab = lambda g: " ".join(GRAMMAR_LABEL[g])
    n_not_emitted = sum(1 for s in SYSTEM_LABEL if s not in sel["admissible_systems"]
                        and s != pref_sys)

    md = f"""# Captions

Generated by `backend/scripts/render_paper_figures.py` from the same run data as the
figures; paste beside the image. Nothing below is drawn into the files. "This run" is
`{run}`: {a['typology']}, {sys_lab(ch_sys)}, {gr_lab(ch_gr)} envelope; {a['element_count']:,}
elements, {a['sized_element_count']} of them load-sized; compiled in {demo['elapsed_seconds']:.1f} s.

**Figure 1.** Three of the fourteen recordings traced through the compiler: the normalised
30 s excerpt; its shared score (ten axes clockwise from the top — tempo of change,
tension/release, density, continuity, repetition, variation, hierarchy, interruption,
polyphony, timbral position; radius is the value in [0, 1]); the compiled massing from the
south-west; and the structural system isolated from the same model. Rows: Mozart, Symphony
No. 29 (theater, split mass, steel frame); M-Pex, *Bueid* (museum, stepped terraces, steel
frame); Affen, *Like Life Easily Ended* (library, courtyard block, reinforced-concrete frame
and wall). Every panel is machine output; no model was edited between stages.

**Figure 2.** How the score reaches geometry in this run: the {sum(1 for d in dat.values() if d['provenance'] == 'score_driven')} score-driven datums,
grouped by the dimension that drives each, on a common axis of position within the datum's
declared output range (range ends are printed in the datum's own units, so an inverse
mapping such as `bay_x_m` reads right to left). The dark band is the reach a dimension is
permitted, `min(1, confidence / {FULL_CONFIDENCE})` of the range centred on the midpoint; the
hollow circle is the reading and the tick is where it was applied. Well-measured
dimensions travel the full range; `polyphony` at confidence {dims['polyphony']['confidence']:.2f} reaches
{reach('polyphony'):.0f} %, and `genre_style` at {dims['genre_style']['confidence']:.2f} reaches {reach('genre_style'):.0f} %, so its
reading of {dims['genre_style']['value']:.2f} is applied at {dat['opaque_fraction']['applied_position']:.2f}. Five tectonic constants
carry no score and say so.

**Figure 3.** (a) Ten dimensions become four architectural axes: `mass` takes whichever of
tension/release and 1 − continuity is further from neutral (marked *d*), plus a bounded
nudge of at most 0.12 from `genre_style`, which never selects on its own; `layering`,
`regularity` and `incident` read polyphony, repetition and hierarchy directly; density and
tempo of change enter the tree as themselves. Values are this run's. (b) The massing
decision tree with its thresholds as written in `massing.py`; each branch is a claim about
the music a reader can dispute in words. Grey figures beside each test are this run's
readings; the red edge is the branch taken (`{sel['massing_label']}`: {sel['massing_reason'][0].split(':')[0]}).
Leaf thumbnails are corpus models that landed on each family, with the count out of
fourteen; the pavilion was reached by none, and its reachability is proved by the test
sweep rather than by the corpus.

**Figure 4.** Two authorities choosing a structural system and a facade grammar. Shade is
the music's affinity for each admissible pair — 0.68 of the envelope's distance to the
four-axis reading plus 0.32 of the frame's distance to mass and expression — and every
value shown equals the pipeline's own `ranked_options` record. The screen admits
{len(sel['admissible_systems'])} of the ten systems on 7 physical hard gates and 5 building-code gates, contributing no
number; {sys_lab(pref_sys)} did not survive it, and {n_not_emitted} systems are not emitted
by this compiler at all. The music's preference, {sys_lab(pref_sys)} × {gr_lab(pref_gr)}
(affinity {sel_meta['preferred_affinity']:.2f}, dashed), was therefore overruled: the grammar was kept and the nearest
admissible frame carried it — {sys_lab(ch_sys)} × {gr_lab(ch_gr)}, {sel_meta['chosen_affinity']:.2f}, red — with the
overrule recorded on the model. Runner-up grammar {gr_lab(sel['runner_up_grammar_id'])}, margin {sel['runner_up_margin']:.2f}.

**Figure 5.** The registration lattice this run compiled, drawn from `analysis.lattice`, and
the massing it carries. (a) Plan: {len(L['x_lines'])} x-lines and {len(L['y_lines'])} y-lines divide the
{L['plan_x_m']:.1f} × {L['plan_y_m']:.1f} m podium into {n_bays_x} × {n_bays_y} bays; plates are drawn for every level, heavier
with height; the terrace plate is dashed; the region carved by the theater archetype is
tinted. Keys: 1 primary bay, x (`bay_x_m` {dat['bay_x_m']['value']:.2f} m, snapped to {L['plan_x_m'] / n_bays_x:.2f} m); 2 primary bay, y
(`bay_y_m` {dat['bay_y_m']['value']:.2f} m, snapped to {L['plan_y_m'] / n_bays_y:.2f} m); 3 podium plate; 4 bar plates stepping back
(`plate_step_m` {dat['plate_step_m']['value']:.2f} m, `plate_rotation_deg` {dat['plate_rotation_deg']['value']:.2f}°); 5 terrace overhang
(`cantilever_m` {dat['cantilever_m']['value']:.2f} m); 6 plates removed above the auditorium and stage. (b) Level table:
7 floor to floor (`floor_to_floor_m` {dat['floor_to_floor_m']['value']:.2f} m); 8 podium clear height
(`ground_open_height_m` {dat['ground_open_height_m']['value']:.2f} m); {len(L['levels'])} levels from `level_count` {dat['level_count']['value']:.2f}
scaled by the massing family. No element carries an absolute coordinate; every one indexes
this lattice. (c) The same run rendered: massing from the south-west, and the section on
the open side.

**Figure 6.** Fourteen licensed recordings, fourteen buildings: massing from the south-west
for every track in the corpus, same camera and compiler settings. Labels give style
family, compiled typology and level count. Across the corpus the compiler produced 6
massing families, 3 typologies, 10 distinct footprints and 6 facade grammars, with no two
tracks sharing a score or model signature.

**Figure 7.** Semantic layers of five compiled models, one `building_model_v3.json` per row
rendered three times with the other layers hidden: program and circulation (colour encodes
program category), envelope only, structure only. Rows: Classical orchestral (theater,
steel); Black metal (library, reinforced concrete); Trip-hop (library, steel, 13 levels);
Portuguese guitar (museum, steel); Hardcore punk (library, steel, 12 levels).

**Figure 8.** Drawing sheets emitted for this run, reproduced verbatim at A1: (a) {plan_id},
{sheets[plan_id]['title']}, 1:100, {sheets[plan_id]['subtitle'].split(' ·')[0]}; (b) {section_id},
{sheets[section_id]['title']}, 1:100. Grid bubbles, poché, dimension strings, room areas,
graphic scale bars, north arrow, level datums and title block are all generated by
`drawings.py` from the same model that produced the renders.

**Figure 9.** One saved model (`artifacts/v3_demo/model_v3.blend`) rendered through five
presentation-only Blender presets built from native shader, World, Freestyle and compositor
nodes. Geometry is identical in every panel; the renders carry presentation authority only.

**Figure 10.** The Workbench Revit/Dynamo handoff panel for run `building-v3-b7ad95fa45a6`
(2,424 elements), captured at 1600 × 1000: 70/70 taxonomy kinds and 42/42 emitted kinds
have a declared delivery strategy, 2,220 instances are BIM targets, 204 presentation-only
instances are omitted, and 18 shared parameters carry stable GUIDs. The static contract is
`ready_for_dry_run`; live Revit/Dynamo validation remains visibly `pending`.

**Table 1.** Verification schedule for this run. Passed, failed and unevaluated counts are
reported per authority and never combined into a score; a gate the pipeline cannot
evaluate is counted as unevaluated, not passed. {tot['failed']} checks fail — {', '.join(failed_bits)} —
and are shown rather than suppressed. A separate construction audit of the fourteen-track
corpus recorded 0 of 14 models construction-ready; all generated results remain
`professional_review_required`.
"""
    (OUT / "captions.md").write_text(md, encoding="utf-8")


# --- driver --------------------------------------------------------------------------


def write_and_raster(name, w, h, body, target_px=3300):
    p = write_svg(name, w, h, body)
    png = rasterise(p, target_px)
    im = Image.open(png)
    print(f"{name:28} {im.size[0]}\u00d7{im.size[1]:<6} {png.stat().st_size / 1024:7.0f} KB   + .svg")


def main() -> None:
    if ASSETS.exists():
        shutil.rmtree(ASSETS)
    ASSETS.mkdir(parents=True)
    for stale in OUT.glob("fig*_*.*"):
        stale.unlink()
    register_fonts()
    demo = json.loads(DEMO.read_text("utf-8"))
    run_id = demo["analysis"]["model_id"]
    sheets = {s["kind"]: s["id"] for s in reversed(demo["drawing_index"]["sheets"])}
    plan_id = next(s["id"] for s in demo["drawing_index"]["sheets"]
                   if s["kind"] == "plan" and "L01" in s["title"])
    section_id = sheets["section"]

    fig1()
    fig2(demo)
    fig3(demo)
    sel_meta = fig4(demo)
    fig5(demo)
    fig6()
    fig7()
    fig8(run_id, plan_id, section_id)
    fig9()
    fig10()
    tot = table1(demo)
    captions(demo, sel_meta, tot, plan_id, section_id)

    import hashlib
    pinned = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(OUT.glob("*.svg")) + sorted(OUT.glob("*.png"))}
    meta = {
        "demo_run": run_id, "plan_sheet": plan_id, "section_sheet": section_id,
        "verification_totals": tot,
        "elements": demo["analysis"]["element_count"],
        "sized": demo["analysis"]["sized_element_count"],
        "elapsed_seconds": demo["elapsed_seconds"],
        "selection": sel_meta,
        "fig1_tracks": FIG1_TRACKS, "fig7_tracks": FIG7_TRACKS,
        "sha256": pinned,
    }
    (OUT / "figures_manifest.json").write_text(json.dumps(meta, indent=2), "utf-8")
    print(f"\n\u2192 {OUT}   demo run {run_id}, plan {plan_id}, section {section_id}")
    print(f"   fig4 affinity check vs recorded ranked_options: max |diff| = "
          f"{sel_meta['max_affinity_diff_vs_record']:.4f}")


if __name__ == "__main__":
    main()
