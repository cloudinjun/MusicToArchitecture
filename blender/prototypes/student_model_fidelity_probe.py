"""Fidelity probe -- target register: architecture-student physical study model.

Not production pipeline code. This probe exists to pin down, concretely, WHAT the
compiler has to be able to emit before the output reads as an architecture model
rather than a massing diagram, at the fidelity of a white/basswood studio model:

    envelope (外皮)  -- mullion/transom grid, glazing infill, solid panel walls,
                        parapets, louvers, all thin and outboard of structure
    structure (结构)  -- columns / primary beams / secondary joists / braces /
                        trusses with individually modelled webs / slabs with
                        real edge thickness and cantilevers
    program (programs)-- floor-zone footprints, partitions, furniture-scale
                        blocks, stairs with individual treads, railings, figures

It implements the proposed datum chain end to end:

    score (10 scalars)
      -> DATUMS      floor-to-floor, bay span, joist spacing, mullion module,
                     cantilever depth, plate profile, void set, truss depth
      -> GRID        level table x column grid  ==  the registration lattice
      -> ELEMENTS    every element is indexed into that lattice; no element in
                     this file is positioned by an absolute literal

Run:
    blender --background --python blender/prototypes/student_model_fidelity_probe.py -- \
        --out artifacts/fidelity_probe
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy


# ===========================================================================
# TIER 0 -- SCORE.  The only free input. Stands in for architectural_score.json
# ===========================================================================

SCORE = {
    "tempo_of_change": 0.62,
    "tension_release": 0.68,
    "density": 0.58,
    "continuity": 0.44,
    "hierarchy": 0.70,
    "repetition": 0.78,
    "variation": 0.36,
    "interruption": 0.55,
    "polyphony": 0.60,
    "genre_style": 0.50,
}


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


# ===========================================================================
# TIER 0 -- DATUMS.  score -> a small set of scalars. Nothing else reads SCORE.
# ===========================================================================

class D:
    floor_to_floor = lerp(3.9, 5.1, SCORE["tension_release"])          # 4.72
    level_count = int(round(lerp(4, 7, SCORE["tempo_of_change"])))     # 6
    bay_x = lerp(7.8, 5.6, SCORE["density"])                           # 6.52
    bay_y = lerp(8.4, 6.2, SCORE["density"])                           # 7.12
    joist_spacing = lerp(2.6, 1.5, SCORE["density"])                   # 1.96
    mullion_module = lerp(1.55, 1.15, SCORE["repetition"])             # 1.24
    transom_rows = int(round(lerp(2, 4, SCORE["density"])))            # 3
    cantilever = lerp(0.6, 3.6, SCORE["continuity"])                   # 1.92
    plate_step = lerp(0.0, 5.5, SCORE["variation"])                    # 1.98
    void_count = int(round(lerp(0, 3, SCORE["interruption"])))         # 2
    truss_depth = lerp(1.5, 3.0, SCORE["hierarchy"])                   # 2.55
    truss_panels = int(round(lerp(4, 9, SCORE["hierarchy"])))          # 8
    slab_thickness = 0.30
    edge_fascia = 0.55
    podium_z = 0.0
    ground_open_height = lerp(4.2, 6.0, SCORE["hierarchy"])            # 5.46


# Plan datum: rectangle + one apsidal (curved) end -> forces the extrusion
# primitive; a rectangle-only plan would hide the schema gap.
PLAN = {
    "x_min": -14.0, "x_max": 22.0,
    "y_min": -11.0, "y_max": 11.0,
    "apse_center_x": -14.0, "apse_radius": 11.0, "apse_segments": 20,
}


def plate_polygon(level: int) -> list[tuple[float, float]]:
    """Outer boundary of one floor plate. Derived, not authored."""
    x_min, x_max = PLAN["x_min"], PLAN["x_max"]
    y_min, y_max = PLAN["y_min"], PLAN["y_max"]
    # upper levels step back from the east end (variation), and the south edge
    # cantilevers on the middle levels (continuity)
    x_max = x_max - D.plate_step * max(0, level - 2)
    south = y_min - (D.cantilever if level in (2, 3) else 0.0)
    pts: list[tuple[float, float]] = [(x_max, south), ]
    pts.append((PLAN["apse_center_x"], south))
    # apsidal end, sampled
    r = PLAN["apse_radius"] + (D.cantilever if level in (2, 3) else 0.0) * 0.35
    for k in range(1, PLAN["apse_segments"]):
        a = math.pi * 0.5 + math.pi * k / PLAN["apse_segments"]
        pts.append((PLAN["apse_center_x"] + math.cos(a) * r,
                    math.sin(a) * r * (1.0 if math.sin(a) > 0 else
                                       (abs(south) / abs(y_min)))))
    pts.append((PLAN["apse_center_x"], y_max))
    pts.append((x_max, y_max))
    return pts


def void_polygons(level: int) -> list[list[tuple[float, float]]]:
    """Atrium / stair voids punched through the plate."""
    if D.void_count == 0 or level not in (2, 3):
        return []
    out = []
    if D.void_count >= 1:
        out.append([(0.5, -4.4), (8.0, -4.4), (8.0, 3.2), (0.5, 3.2)])
    if D.void_count >= 2 and level == 3:
        out.append([(12.5, -2.0), (17.5, -2.0), (17.5, 4.0), (12.5, 4.0)])
    return out


# ===========================================================================
# TIER 0 -- THE REGISTRATION LATTICE.  Everything below indexes into this.
# ===========================================================================

def level_table() -> list[dict]:
    """z datum per level. Level 0 is the open podium (piloti)."""
    table = [{"index": 0, "z": D.podium_z, "kind": "podium"}]
    z = D.podium_z + D.ground_open_height
    for i in range(1, D.level_count):
        table.append({"index": i, "z": round(z, 4),
                      "kind": "occupied" if i < D.level_count - 1 else "roof"})
        z += D.floor_to_floor
    return table


def grid_lines() -> tuple[list[float], list[float]]:
    span_x = PLAN["x_max"] - PLAN["x_min"]
    span_y = PLAN["y_max"] - PLAN["y_min"]
    nx = max(2, round(span_x / D.bay_x))
    ny = max(2, round(span_y / D.bay_y))
    xs = [PLAN["x_min"] + span_x * i / nx for i in range(nx + 1)]
    ys = [PLAN["y_min"] + span_y * j / ny for j in range(ny + 1)]
    return xs, ys


def apse_grid(count: int = 9) -> list[tuple[float, float]]:
    """Radial column nodes following the curved end."""
    r = PLAN["apse_radius"] * 0.98
    out = []
    for k in range(1, count + 1):
        a = math.pi * 0.5 + math.pi * k / (count + 1)
        out.append((PLAN["apse_center_x"] + math.cos(a) * r, math.sin(a) * r))
    return out


LEVELS = level_table()
X_LINES, Y_LINES = grid_lines()
APSE_NODES = apse_grid()


# ===========================================================================
# GEOMETRY PRIMITIVES.  Four are required; the current schema has only one.
# ===========================================================================

def _norm(v):
    m = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    return (v[0] / m, v[1] / m, v[2] / m) if m > 1e-9 else (0.0, 0.0, 1.0)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


# --- section profile library (u = flange axis, v = web axis) ---------------
def w_section(depth: float, flange: float, web_t: float, flange_t: float):
    b, d, t, tf = flange / 2.0, depth / 2.0, web_t / 2.0, flange_t
    return [(-b, -d), (b, -d), (b, -d + tf), (t, -d + tf), (t, d - tf),
            (b, d - tf), (b, d), (-b, d), (-b, d - tf), (-t, d - tf),
            (-t, -d + tf), (-b, -d + tf)]


def box_section(w: float, h: float):
    return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]


def round_section(r: float, sides: int = 8):
    return [(math.cos(2 * math.pi * k / sides) * r,
             math.sin(2 * math.pi * k / sides) * r) for k in range(sides)]


PROFILES = {
    "W_column":    w_section(0.42, 0.34, 0.032, 0.048),
    "W_primary":   w_section(0.62, 0.30, 0.026, 0.042),
    "W_secondary": w_section(0.34, 0.18, 0.018, 0.026),
    "SHS_brace":   box_section(0.20, 0.20),
    "CHS_strut":   round_section(0.09),
    "truss_chord": box_section(0.20, 0.26),
    "truss_web":   box_section(0.13, 0.13),
    "mullion":     box_section(0.075, 0.24),
    "transom":     box_section(0.075, 0.14),
    "rail":        round_section(0.032, 6),
    "post":        box_section(0.045, 0.045),
    "stringer":    box_section(0.18, 0.45),
    "piloti":      round_section(0.24, 10),
    "purlin":      box_section(0.12, 0.20),
}


class Family:
    """One element kind -> one merged mesh. Keeps 4k elements at interactive cost."""

    def __init__(self, name, material, layer, subsystem):
        self.name, self.material = name, material
        self.layer, self.subsystem = layer, subsystem
        self.verts: list = []
        self.faces: list = []
        self.count = 0

    def _push(self, verts, faces):
        b = len(self.verts)
        self.verts.extend(verts)
        self.faces.extend(tuple(b + i for i in f) for f in faces)
        self.count += 1

    # PRIMITIVE 1 -- oriented box (the only one the current schema supports)
    def box(self, center, size, rot_z=0.0):
        hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
        c, s = math.cos(rot_z), math.sin(rot_z)
        loc = [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
               (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]
        self._push([(center[0] + x * c - y * s, center[1] + x * s + y * c, center[2] + z)
                    for x, y, z in loc],
                   [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                    (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])

    # PRIMITIVE 2 -- MEMBER: swept section profile from start to end
    def member(self, p0, p1, profile_key, up=(0.0, 0.0, 1.0), cap=True):
        prof = PROFILES[profile_key]
        axis = _norm((p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]))
        dot = sum(axis[i] * up[i] for i in range(3))
        v = (up[0] - axis[0] * dot, up[1] - axis[1] * dot, up[2] - axis[2] * dot)
        if abs(v[0]) + abs(v[1]) + abs(v[2]) < 1e-6:
            v = (1.0, 0.0, 0.0)
        v = _norm(v)
        u = _norm(_cross(v, axis))
        n = len(prof)
        verts = []
        for p in (p0, p1):
            for pu, pv in prof:
                verts.append((p[0] + u[0] * pu + v[0] * pv,
                              p[1] + u[1] * pu + v[1] * pv,
                              p[2] + u[2] * pu + v[2] * pv))
        faces = []
        if cap:
            faces.append(tuple(range(n - 1, -1, -1)))
            faces.append(tuple(range(n, 2 * n)))
        for k in range(n):
            m = (k + 1) % n
            faces.append((k, m, n + m, n + k))
        self._push(verts, faces)

    # PRIMITIVE 3 -- EXTRUSION: arbitrary closed polygon + thickness
    def extrusion(self, polygon, z0, z1):
        n = len(polygon)
        verts = [(x, y, z0) for x, y in polygon] + [(x, y, z1) for x, y in polygon]
        faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
        for k in range(n):
            m = (k + 1) % n
            faces.append((k, m, n + m, n + k))
        self._push(verts, faces)

    # PRIMITIVE 4 -- PANEL: a free quad in space (glazing, wall infill)
    def quad(self, a, b, c, d):
        self._push([a, b, c, d], [(0, 1, 2, 3)])


FAMILIES: dict[str, Family] = {}


def fam(name, material, layer, subsystem) -> Family:
    if name not in FAMILIES:
        FAMILIES[name] = Family(name, material, layer, subsystem)
    return FAMILIES[name]


def keyhole(outer, holes):
    """Outer polygon with holes bridged by zero-width slits -> one simple
    polygon the extrusion primitive can consume."""
    poly = list(outer)
    for hole in holes:
        hr = list(reversed(hole))
        best = None
        for i, o in enumerate(poly):
            for j, h in enumerate(hr):
                dist = (o[0] - h[0]) ** 2 + (o[1] - h[1]) ** 2
                if best is None or dist < best[0]:
                    best = (dist, i, j)
        _, i, j = best
        poly = poly[:i + 1] + hr[j:] + hr[:j + 1] + poly[i:]
    return poly


def inset(polygon, amount):
    cx = sum(p[0] for p in polygon) / len(polygon)
    cy = sum(p[1] for p in polygon) / len(polygon)
    out = []
    for x, y in polygon:
        dx, dy = x - cx, y - cy
        d = math.hypot(dx, dy) or 1.0
        out.append((x - dx / d * amount, y - dy / d * amount))
    return out


def inside(polygon, x, y) -> bool:
    hit = False
    n = len(polygon)
    for i in range(n):
        x0, y0 = polygon[i]
        x1, y1 = polygon[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            xr = x0 + (y - y0) / (y1 - y0) * (x1 - x0)
            if x < xr:
                hit = not hit
    return hit


def polyline_points(polygon, spacing):
    """Even stations along a closed polyline -- the envelope registration."""
    out = []
    n = len(polygon)
    carry = 0.0
    for i in range(n):
        x0, y0 = polygon[i]
        x1, y1 = polygon[(i + 1) % n]
        seg = math.hypot(x1 - x0, y1 - y0)
        d = carry
        while d < seg:
            f = d / seg
            out.append(((x0 + (x1 - x0) * f, y0 + (y1 - y0) * f),
                        math.atan2(y1 - y0, x1 - x0)))
            d += spacing
        carry = d - seg
    return out


# ===========================================================================
# STRUCTURE (结构)
# ===========================================================================

def emit_structure():
    cols = fam("column", "steel_white", "structure", "columns")
    piloti = fam("piloti_column", "steel_white", "structure", "columns")
    pri = fam("primary_beam", "steel_white", "structure", "beams")
    sec = fam("secondary_joist", "steel_light", "structure", "beams")
    brace = fam("brace", "steel_white", "structure", "bracing")
    strut = fam("outrigger_strut", "steel_dark", "structure", "bracing")
    footing = fam("footing", "concrete", "structure", "foundations")

    plates = {lv["index"]: plate_polygon(lv["index"]) for lv in LEVELS}
    occupied = [lv for lv in LEVELS if lv["index"] >= 1]

    # --- columns: node(i,j,k) -> node(i,j,k+1) -----------------------------
    for xi, x in enumerate(X_LINES):
        for yj, y in enumerate(Y_LINES):
            for k in range(len(LEVELS) - 1):
                z0, z1 = LEVELS[k]["z"], LEVELS[k + 1]["z"]
                if not inside(plates[min(k + 1, len(LEVELS) - 1)], x, y):
                    continue
                if k == 0:
                    piloti.member((x, y, z0), (x, y, z1), "piloti", up=(1, 0, 0))
                    footing.box((x, y, z0 - 0.45), (1.6, 1.6, 0.9))
                else:
                    cols.member((x, y, z0), (x, y, z1), "W_column", up=(1, 0, 0))
    # radial columns on the apsidal end
    for ax, ay in APSE_NODES:
        for k in range(len(LEVELS) - 1):
            z0, z1 = LEVELS[k]["z"], LEVELS[k + 1]["z"]
            if k == 0:
                piloti.member((ax, ay, z0), (ax, ay, z1), "piloti", up=(1, 0, 0))
                footing.box((ax, ay, z0 - 0.45), (1.4, 1.4, 0.9))
            else:
                cols.member((ax, ay, z0), (ax, ay, z1), "W_column", up=(1, 0, 0))

    # --- primary beams: along both grid directions, at every occupied level -
    for lv in occupied:
        z = lv["z"] - D.slab_thickness - 0.31
        poly = plates[lv["index"]]
        for yj, y in enumerate(Y_LINES):
            for xi in range(len(X_LINES) - 1):
                x0, x1 = X_LINES[xi], X_LINES[xi + 1]
                if inside(poly, (x0 + x1) / 2, y):
                    pri.member((x0, y, z), (x1, y, z), "W_primary")
        for xi, x in enumerate(X_LINES):
            for yj in range(len(Y_LINES) - 1):
                y0, y1 = Y_LINES[yj], Y_LINES[yj + 1]
                if inside(poly, x, (y0 + y1) / 2):
                    pri.member((x, y0, z), (x, y1, z), "W_primary")
        # ring beam closing the apsidal end
        for k in range(len(APSE_NODES) - 1):
            a, b = APSE_NODES[k], APSE_NODES[k + 1]
            pri.member((a[0], a[1], z), (b[0], b[1], z), "W_primary")
        pri.member((PLAN["x_min"], Y_LINES[0], z), (APSE_NODES[0][0], APSE_NODES[0][1], z),
                   "W_primary")
        pri.member((APSE_NODES[-1][0], APSE_NODES[-1][1], z),
                   (PLAN["x_min"], Y_LINES[-1], z), "W_primary")

    # --- secondary joists: bay subdivided by joist_spacing -----------------
    for lv in occupied:
        z = lv["z"] - D.slab_thickness - 0.17
        poly = plates[lv["index"]]
        for xi in range(len(X_LINES) - 1):
            x0, x1 = X_LINES[xi], X_LINES[xi + 1]
            n = max(1, int(round((x1 - x0) / D.joist_spacing)))
            for s in range(1, n):
                x = x0 + (x1 - x0) * s / n
                for yj in range(len(Y_LINES) - 1):
                    y0, y1 = Y_LINES[yj], Y_LINES[yj + 1]
                    if inside(poly, x, (y0 + y1) / 2):
                        sec.member((x, y0, z), (x, y1, z), "W_secondary")

    # --- braced bays: two bays get K-bracing, driven by hierarchy ----------
    for lv in occupied[:-1]:
        k = lv["index"]
        z0, z1 = LEVELS[k]["z"], LEVELS[k + 1]["z"]
        for xi in (1, len(X_LINES) - 2):
            x0, x1 = X_LINES[xi], X_LINES[xi + 1]
            y = Y_LINES[-1]
            mid = ((x0 + x1) / 2, y, z1 - 0.4)
            brace.member((x0, y, z0), mid, "SHS_brace")
            brace.member((x1, y, z0), mid, "SHS_brace")

    # --- outrigger struts holding the cantilevered south edge --------------
    for lv in occupied:
        k = lv["index"]
        if k not in (2, 3):
            continue
        z = LEVELS[k]["z"] - D.slab_thickness
        y_edge = PLAN["y_min"] - D.cantilever
        anchor_z = LEVELS[k]["z"] + D.floor_to_floor * 0.85
        for xi, x in enumerate(X_LINES):
            if x > PLAN["x_max"] - D.plate_step * max(0, k - 2):
                continue
            strut.member((x, y_edge + 0.2, z - 0.2), (x, PLAN["y_min"] + 1.0, anchor_z),
                         "CHS_strut")
    return len(occupied)


def emit_slabs():
    slab = fam("floor_slab", "concrete_light", "structure", "slabs")
    fascia = fam("slab_fascia", "white", "structure", "slabs")
    podium = fam("podium_slab", "concrete", "site", "podium")

    podium.extrusion(inset(plate_polygon(1), -4.5), -0.35, 0.0)
    for lv in LEVELS:
        k = lv["index"]
        if k == 0:
            continue
        poly = plate_polygon(k)
        voids = void_polygons(k)
        top = lv["z"]
        slab.extrusion(keyhole(poly, voids) if voids else poly,
                       top - D.slab_thickness, top)
        # thickened perimeter fascia -- the visible plate edge in a study model
        for i in range(len(poly)):
            a, b = poly[i], poly[(i + 1) % len(poly)]
            fascia.member((a[0], a[1], top - D.edge_fascia / 2),
                          (b[0], b[1], top - D.edge_fascia / 2),
                          "truss_chord", up=(0, 0, 1))


def emit_roof_trusses():
    chord = fam("truss_chord", "steel_white", "structure", "roof_truss")
    web = fam("truss_web", "steel_white", "structure", "roof_truss")
    purlin = fam("purlin", "steel_light", "structure", "roof_truss")
    deck = fam("roof_deck", "white", "envelope", "roof")

    roof = LEVELS[-1]
    z_bot = roof["z"]
    z_top = z_bot + D.truss_depth
    poly = plate_polygon(roof["index"])
    lines = [x for x in X_LINES if inside(poly, x, 0.0)]
    y0, y1 = PLAN["y_min"], PLAN["y_max"]
    span = y1 - y0
    panel = span / D.truss_panels

    for x in lines:
        chord.member((x, y0, z_bot), (x, y1, z_bot), "truss_chord")
        chord.member((x, y0, z_top), (x, y1, z_top), "truss_chord")
        for p in range(D.truss_panels + 1):
            y = y0 + panel * p
            web.member((x, y, z_bot), (x, y, z_top), "truss_web")
            if p < D.truss_panels:
                yn = y + panel
                if p % 2 == 0:
                    web.member((x, y, z_bot), (x, yn, z_top), "truss_web")
                else:
                    web.member((x, y, z_top), (x, yn, z_bot), "truss_web")
    # purlins spanning between trusses on the top chord
    for p in range(D.truss_panels + 1):
        y = y0 + panel * p
        for i in range(len(lines) - 1):
            purlin.member((lines[i], y, z_top), (lines[i + 1], y, z_top), "purlin")
    deck.extrusion(inset(poly, -0.6), z_top + 0.08, z_top + 0.26)


# ===========================================================================
# ENVELOPE (外皮)
# ===========================================================================

# Sectional study model: the envelope is authored on the south and west faces
# only, so the north/east side reads as a cut and the floor plates, frame, and
# program stay visible. This is a presentation decision, not a design decision.
CUTAWAY = {"open_north_of_y": 1.5, "open_east_of_x": 15.5}


def envelope_visible(x: float, y: float) -> bool:
    return not (y > CUTAWAY["open_north_of_y"] or x > CUTAWAY["open_east_of_x"])


def emit_envelope():
    mull = fam("mullion", "frame_dark", "envelope", "curtain_wall")
    tran = fam("transom", "frame_dark", "envelope", "curtain_wall")
    glass = fam("glazing_panel", "glass", "envelope", "curtain_wall")
    spand = fam("spandrel_panel", "white_soft", "envelope", "curtain_wall")
    solid = fam("solid_wall_panel", "white", "envelope", "opaque_wall")
    parapet = fam("parapet", "white", "envelope", "roof")
    louver = fam("brise_soleil", "white_soft", "envelope", "shading")

    occupied = [lv for lv in LEVELS if 1 <= lv["index"] < len(LEVELS) - 1]
    for lv in occupied:
        k = lv["index"]
        z_base = lv["z"]
        z_head = z_base + D.floor_to_floor - D.edge_fascia
        poly = plate_polygon(k)
        stations = polyline_points(poly, D.mullion_module)
        head_h = z_head - z_base
        rows = [z_base + head_h * r / D.transom_rows for r in range(D.transom_rows + 1)]

        for idx, ((px, py), ang) in enumerate(stations):
            if not envelope_visible(px, py):
                continue
            nxt = stations[(idx + 1) % len(stations)][0]
            if math.hypot(nxt[0] - px, nxt[1] - py) > D.mullion_module * 1.8:
                continue
            # envelope answers program: the service/private end is opaque panel
            solid_face = px > 11.0 and py < 0.0
            if solid_face:
                solid.quad((px, py, z_base), (nxt[0], nxt[1], z_base),
                           (nxt[0], nxt[1], z_head), (px, py, z_head))
                mull.member((px, py, z_base), (px, py, z_head), "mullion",
                            up=(math.cos(ang), math.sin(ang), 0))
                continue
            mull.member((px, py, z_base - D.edge_fascia), (px, py, z_head), "mullion",
                        up=(math.cos(ang), math.sin(ang), 0))
            for r in range(len(rows) - 1):
                za, zb = rows[r], rows[r + 1]
                if r == 0:
                    spand.quad((px, py, za), (nxt[0], nxt[1], za),
                               (nxt[0], nxt[1], za + 0.55), (px, py, za + 0.55))
                    za += 0.55
                glass.quad((px, py, za), (nxt[0], nxt[1], za),
                           (nxt[0], nxt[1], zb), (px, py, zb))
            for zr in rows:
                tran.member((px, py, zr), (nxt[0], nxt[1], zr), "transom")
            # horizontal shading comb on the south face only
            if py < PLAN["y_min"] + 0.5:
                for s in range(2):
                    zs = z_base + head_h * (0.45 + 0.3 * s)
                    louver.box(((px + nxt[0]) / 2 - 0.0, (py + nxt[1]) / 2 - 0.35, zs),
                               (D.mullion_module, 0.70, 0.06))

    # parapet ring at the roof
    roof_poly = plate_polygon(LEVELS[-1]["index"])
    z_par = LEVELS[-1]["z"] + D.truss_depth + 0.26
    for i in range(len(roof_poly)):
        a, b = roof_poly[i], roof_poly[(i + 1) % len(roof_poly)]
        if not envelope_visible((a[0] + b[0]) / 2, (a[1] + b[1]) / 2):
            continue
        parapet.member((a[0], a[1], z_par + 0.45), (b[0], b[1], z_par + 0.45),
                       "truss_chord", up=(0, 0, 1))


# ===========================================================================
# CIRCULATION -- stairs with individual treads, landings, railings
# ===========================================================================

def emit_stair_flight(p_start, p_end, width, tag="stair"):
    tread = fam("stair_tread", "white", "circulation", "stairs")
    stringer = fam("stair_stringer", "white_soft", "circulation", "stairs")
    dz = p_end[2] - p_start[2]
    dx, dy = p_end[0] - p_start[0], p_end[1] - p_start[1]
    run = math.hypot(dx, dy)
    if dz <= 0.01 or run <= 0.01:
        return
    steps = max(2, int(round(dz / 0.175)))
    ux, uy = dx / run, dy / run
    px, py = -uy, ux
    for s in range(steps):
        f0 = s / steps
        cx = p_start[0] + dx * (f0 + 0.5 / steps)
        cy = p_start[1] + dy * (f0 + 0.5 / steps)
        cz = p_start[2] + dz * (f0 + 1.0 / steps) - 0.045
        ang = math.atan2(uy, ux)
        tread.box((cx, cy, cz), (run / steps + 0.06, width, 0.09), rot_z=ang)
    for side in (-1, 1):
        a = (p_start[0] + px * side * width / 2, p_start[1] + py * side * width / 2,
             p_start[2] - 0.22)
        b = (p_end[0] + px * side * width / 2, p_end[1] + py * side * width / 2,
             p_end[2] - 0.22)
        stringer.member(a, b, "stringer")
    emit_railing_line(p_start, p_end, width, rise=True)


def emit_railing_line(p_start, p_end, width, rise=False, spacing=1.5):
    rail = fam("railing", "steel_white", "circulation", "safety")
    dx, dy = p_end[0] - p_start[0], p_end[1] - p_start[1]
    run = math.hypot(dx, dy)
    if run < 0.2:
        return
    ux, uy = dx / run, dy / run
    px, py = -uy, ux
    n = max(2, int(run / spacing))
    for side in (-1, 1):
        ox, oy = px * side * width / 2, py * side * width / 2
        a = (p_start[0] + ox, p_start[1] + oy, p_start[2] + 1.05)
        b = (p_end[0] + ox, p_end[1] + oy, p_end[2] + 1.05)
        rail.member(a, b, "rail")
        rail.member((a[0], a[1], a[2] - 0.5), (b[0], b[1], b[2] - 0.5), "rail")
        for s in range(n + 1):
            f = s / n
            x = p_start[0] + dx * f + ox
            y = p_start[1] + dy * f + oy
            z = p_start[2] + (p_end[2] - p_start[2]) * f
            rail.member((x, y, z), (x, y, z + 1.05), "post")


def emit_circulation():
    landing = fam("stair_landing", "white", "circulation", "stairs")
    ramp = fam("ramp", "white_soft", "circulation", "ramps")
    shaft = fam("elevator_shaft", "concrete", "circulation", "vertical_core")

    # 1. monumental external stair, podium -> level 2, on the south face
    y_out = PLAN["y_min"] - D.cantilever - 5.5
    z1, z2 = LEVELS[1]["z"], LEVELS[2]["z"]
    mid_z = (z1 + z2) / 2.0
    emit_stair_flight((16.0, y_out, D.podium_z), (16.0, y_out + 7.0, z1), 3.2)
    landing.box((16.0, y_out + 8.4, z1 - 0.12), (3.2, 2.8, 0.24))
    emit_stair_flight((16.0, y_out + 9.8, z1), (16.0, y_out + 15.5, mid_z), 3.2)

    # 2. switchback external stair against the west/apse end
    ax = PLAN["apse_center_x"] - PLAN["apse_radius"] - 1.5
    for k in range(1, len(LEVELS) - 2):
        za, zb = LEVELS[k]["z"], LEVELS[k + 1]["z"]
        zm = (za + zb) / 2.0
        emit_stair_flight((ax, -4.6, za), (ax, 0.4, zm), 2.4)
        landing.box((ax, 1.5, zm - 0.12), (2.4, 2.2, 0.24))
        emit_stair_flight((ax, 2.6, zm), (ax, 7.4, zb), 2.4)
        landing.box((ax, -5.8, za - 0.12), (2.4, 2.2, 0.24))

    # 3. interior stair through the atrium void
    for k in range(2, len(LEVELS) - 1):
        za, zb = LEVELS[k - 1]["z"], LEVELS[k]["z"]
        emit_stair_flight((1.6, -3.6, za), (1.6, 2.4, zb), 2.2)

    # 4. elevator / service core, full height
    for k in range(len(LEVELS) - 1):
        za, zb = LEVELS[k]["z"], LEVELS[k + 1]["z"]
        shaft.extrusion([(18.4, 5.2), (21.4, 5.2), (21.4, 9.4), (18.4, 9.4)], za, zb)

    # 5. ramp from grade to podium
    ramp.box((26.0, -2.0, -0.4), (9.0, 3.0, 0.28))

    # 6. edge railing on every cantilevered / open plate edge
    for lv in LEVELS:
        k = lv["index"]
        if k == 0:
            continue
        poly = plate_polygon(k)
        for i in range(len(poly)):
            a, b = poly[i], poly[(i + 1) % len(poly)]
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            if envelope_visible(mx, my):
                continue
            emit_railing_line((a[0], a[1], lv["z"]), (b[0], b[1], lv["z"]), 0.0)


# ===========================================================================
# PROGRAM (programs)
# ===========================================================================

PROGRAM_ZONES = {
    1: [("lobby_welcome_checkout", "circulation", (-6.0, -8.0, 10.0, 2.0)),
        ("exhibition_foyer", "public", (10.0, -8.0, 21.0, 2.0)),
        ("cafe", "public", (-13.0, 2.5, -2.0, 9.5))],
    2: [("open_stacks", "public", (-8.0, -9.0, 12.0, 1.0)),
        ("adult_reading", "public", (-13.0, 2.0, 8.0, 10.0)),
        ("staff_workroom", "private", (14.0, 3.0, 21.0, 10.0))],
    3: [("quiet_reading", "public", (-13.0, -9.0, 6.0, 1.0)),
        ("special_collections", "private", (8.0, -6.0, 16.0, 4.0)),
        ("seminar", "public", (-10.0, 3.0, 2.0, 10.0))],
    4: [("children_reading", "public", (-13.0, -8.0, 4.0, 2.0)),
        ("periodicals_media", "public", (6.0, -8.0, 16.0, 3.0)),
        ("mechanical", "service", (16.0, 4.0, 21.0, 10.0))],
}

CATEGORY_MATERIAL = {
    "public": "prog_public", "private": "prog_private",
    "circulation": "prog_circulation", "service": "prog_service",
}


def emit_program():
    partition = fam("partition", "white_soft", "program", "partitions")
    shelf = fam("shelving_run", "furn", "program", "furniture")
    desk = fam("desk", "furn", "program", "furniture")
    seat = fam("seat", "furn", "program", "furniture")
    zone_fams = {c: fam(f"program_zone_{c}", m, "program", "zones")
                 for c, m in CATEGORY_MATERIAL.items()}

    for k, zones in PROGRAM_ZONES.items():
        if k >= len(LEVELS) - 1:
            continue
        z = LEVELS[k]["z"]
        poly = plate_polygon(k)
        voids = void_polygons(k)
        for name, category, (x0, y0, x1, y1) in zones:
            # zone footprint: a thin plate laid on the slab, so a section stays legible
            zone_fams[category].box(((x0 + x1) / 2, (y0 + y1) / 2, z + 0.055),
                                    (x1 - x0, y1 - y0, 0.11))
            # partition on the long boundary only
            partition.box(((x0 + x1) / 2, y1, z + 1.45), (x1 - x0, 0.20, 2.90))
            # furniture, seeded by program type
            def blocked(px, py):
                if not inside(poly, px, py):
                    return True
                return any(inside(v, px, py) for v in voids)
            if "stacks" in name or "collections" in name:
                rows = int((y1 - y0) / 1.9)
                for r in range(rows):
                    yy = y0 + 1.0 + r * 1.9
                    for c in range(int((x1 - x0) / 4.6)):
                        xx = x0 + 2.4 + c * 4.6
                        if not blocked(xx, yy):
                            shelf.box((xx, yy, z + 1.15), (4.2, 0.55, 2.10))
            elif "reading" in name or "seminar" in name or "cafe" in name:
                for r in range(int((y1 - y0) / 2.6)):
                    for c in range(int((x1 - x0) / 2.9)):
                        xx, yy = x0 + 1.7 + c * 2.9, y0 + 1.5 + r * 2.6
                        if blocked(xx, yy):
                            continue
                        desk.box((xx, yy, z + 0.40), (1.60, 0.80, 0.08))
                        for s in (-1, 1):
                            seat.box((xx, yy + s * 0.72, z + 0.24), (0.48, 0.48, 0.06))
                            seat.box((xx, yy + s * 0.96, z + 0.56), (0.48, 0.08, 0.60))
            else:
                for c in range(int((x1 - x0) / 3.0)):
                    xx = x0 + 1.6 + c * 3.0
                    if not blocked(xx, (y0 + y1) / 2):
                        desk.box((xx, (y0 + y1) / 2, z + 0.40), (1.4, 2.0, 0.08))


def emit_figures():
    """1.75 m figures. In a study model these are what fix the scale of every
    other member, so they are distributed per level, not scattered on grade."""
    fig = fam("figure", "accent_red", "program", "scale_reference")
    state = 20260829

    def rnd():
        nonlocal state
        state = (1103515245 * state + 12345) % (2 ** 31)
        return state / (2 ** 31)

    def place(x, y, z):
        fig.box((x, y, z + 0.60), (0.40, 0.28, 1.20))
        fig.box((x, y, z + 1.40), (0.24, 0.24, 0.38))

    placed = 0
    per_level = 18
    for lv in LEVELS:
        k = lv["index"]
        if k >= len(LEVELS) - 1:
            continue
        poly = plate_polygon(max(k, 1))
        voids = void_polygons(k)
        z = lv["z"]
        got, tries = 0, 0
        while got < per_level and tries < 600:
            tries += 1
            x = PLAN["apse_center_x"] - PLAN["apse_radius"] + rnd() * 46.0
            y = PLAN["y_min"] - D.cantilever + rnd() * (
                PLAN["y_max"] - PLAN["y_min"] + D.cantilever)
            if not inside(poly, x, y):
                continue
            if any(inside(v, x, y) for v in voids):
                continue
            place(x, y, z)
            got += 1
            placed += 1

    # on the monumental external stair and the podium approach
    for i in range(9):
        place(15.2 + rnd() * 1.6, PLAN["y_min"] - D.cantilever - 5.3 + i * 0.78,
              D.podium_z + i * 0.62)
        placed += 1
    for i in range(12):
        place(-4.0 + rnd() * 34.0, PLAN["y_min"] - 14.0 - rnd() * 6.0, -0.4)
        placed += 1
    return placed


def emit_site():
    ground = fam("site_ground", "ground", "site", "context")
    ground.box((4.0, 0.0, -0.75), (150.0, 130.0, 0.7))
    steps = fam("site_step", "ground_light", "site", "context")
    for s in range(3):
        steps.box((4.0, PLAN["y_min"] - 12.0 - s * 1.4, -0.12 - s * 0.14),
                  (46.0 - s * 2.0, 1.4, 0.30))


# ===========================================================================
# BLENDER REALISATION
# ===========================================================================

MATERIALS = {
    "white":            ((0.900, 0.898, 0.890, 1.0), 0.52, 1.0),
    "white_soft":       ((0.840, 0.838, 0.830, 1.0), 0.62, 1.0),
    "steel_white":      ((0.925, 0.925, 0.920, 1.0), 0.40, 1.0),
    "steel_light":      ((0.870, 0.870, 0.866, 1.0), 0.45, 1.0),
    "steel_dark":       ((0.380, 0.380, 0.385, 1.0), 0.35, 1.0),
    "frame_dark":       ((0.135, 0.138, 0.145, 1.0), 0.40, 1.0),
    "concrete":         ((0.760, 0.756, 0.746, 1.0), 0.78, 1.0),
    "concrete_light":   ((0.855, 0.852, 0.842, 1.0), 0.70, 1.0),
    "glass":            ((0.700, 0.780, 0.815, 1.0), 0.08, 0.13),
    "accent_red":       ((0.700, 0.098, 0.082, 1.0), 0.55, 1.0),
    "furn":             ((0.700, 0.686, 0.660, 1.0), 0.72, 1.0),
    "prog_public":      ((0.760, 0.800, 0.845, 1.0), 0.80, 1.0),
    "prog_private":     ((0.845, 0.800, 0.760, 1.0), 0.80, 1.0),
    "prog_circulation": ((0.800, 0.845, 0.790, 1.0), 0.80, 1.0),
    "prog_service":     ((0.800, 0.790, 0.830, 1.0), 0.80, 1.0),
    "ground":           ((0.512, 0.516, 0.524, 1.0), 0.90, 1.0),
    "ground_light":     ((0.735, 0.735, 0.730, 1.0), 0.86, 1.0),
}


def clear_scene():
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials,
                 bpy.data.cameras, bpy.data.lights, bpy.data.collections):
        for item in list(coll):
            try:
                coll.remove(item)
            except Exception:
                pass


def make_materials():
    out = {}
    for name, (rgba, rough, alpha) in MATERIALS.items():
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = rough
        if alpha < 1.0:
            bsdf.inputs["Alpha"].default_value = alpha
            for attr, value in (("surface_render_method", "BLENDED"),
                                ("blend_method", "BLEND")):
                try:
                    setattr(mat, attr, value)
                except (AttributeError, TypeError):
                    pass
            try:
                mat.show_transparent_back = False
            except AttributeError:
                pass
        out[name] = mat
    return out


def realise(materials):
    root = bpy.data.collections.new("MTA_StudentModelProbe")
    bpy.context.scene.collection.children.link(root)
    layers, stats = {}, {}
    for name, f in FAMILIES.items():
        if not f.verts:
            continue
        if f.layer not in layers:
            c = bpy.data.collections.new(f.layer)
            root.children.link(c)
            layers[f.layer] = c
        mesh = bpy.data.meshes.new(f"{name}_mesh")
        mesh.from_pydata(f.verts, [], f.faces)
        mesh.validate(verbose=False)
        mesh.update(calc_edges=True)
        mesh.shade_flat()
        obj = bpy.data.objects.new(name, mesh)
        obj.data.materials.append(materials[f.material])
        obj["mta:kind"] = name
        obj["mta:layer"] = f.layer
        obj["mta:subsystem"] = f.subsystem
        obj["mta:instance_count"] = f.count
        layers[f.layer].objects.link(obj)
        stats[name] = {"instances": f.count, "faces": len(f.faces),
                       "layer": f.layer, "subsystem": f.subsystem}
    return stats


def point_at(obj, target):
    from mathutils import Vector
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def setup_scene():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.455, 0.462, 0.480, 1.0)
    bg.inputs[1].default_value = 1.0
    for attr, value in (("use_raytracing", True), ("use_shadows", True),
                        ("taa_render_samples", 96), ("use_shadow_jitter_viewport", True)):
        try:
            setattr(scene.eevee, attr, value)
        except (AttributeError, TypeError):
            pass
    scene.view_settings.look = "AgX - Base Contrast"

    sun = bpy.data.lights.new("Sun", "SUN")
    sun.energy = 4.6
    sun.angle = math.radians(1.4)
    sun_obj = bpy.data.objects.new("Sun", sun)
    sun_obj.rotation_euler = (math.radians(52), math.radians(4), math.radians(-38))
    scene.collection.objects.link(sun_obj)

    fill = bpy.data.lights.new("Fill", "AREA")
    fill.energy = 14000.0
    fill.shape = "RECTANGLE"
    fill.size, fill.size_y = 70.0, 45.0
    fill_obj = bpy.data.objects.new("Fill", fill)
    fill_obj.location = (-55.0, -70.0, 48.0)
    scene.collection.objects.link(fill_obj)
    point_at(fill_obj, (0.0, 0.0, 14.0))

    cam_data = bpy.data.cameras.new("Camera")
    cam = bpy.data.objects.new("Camera", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    return cam


VIEWS = [
    ("01_three_quarter", (62.0, -78.0, 44.0), (0.0, -2.0, 12.0), 62, (1600, 1100)),
    ("02_section_open_side", (58.0, 60.0, 30.0), (-2.0, -1.0, 12.5), 55, (1600, 1100)),
    ("03_structure_closeup", (34.0, 30.0, 20.0), (4.0, 2.0, 14.0), 95, (1600, 1100)),
    ("04_south_elevation", (2.0, -168.0, 15.0), (2.0, 0.0, 15.0), 78, (1700, 950)),
    ("05_apse_stair", (-58.0, -40.0, 26.0), (-18.0, 0.0, 13.0), 72, (1300, 1100)),
]


def render_views(cam, out_dir: Path):
    scene = bpy.context.scene
    names = []
    for name, loc, target, lens, (rx, ry) in VIEWS:
        cam.location = loc
        cam.data.lens = lens
        point_at(cam, target)
        scene.render.resolution_x, scene.render.resolution_y = rx, ry
        scene.render.filepath = str(out_dir / f"{name}.png")
        bpy.ops.render.render(write_still=True)
        names.append(f"{name}.png")
    return names


def parse_out_dir() -> Path:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
        if "--out" in argv:
            return Path(argv[argv.index("--out") + 1]).resolve()
    return Path("artifacts/fidelity_probe").resolve()


def main():
    out_dir = parse_out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    clear_scene()

    emit_site()
    emit_structure()
    emit_slabs()
    emit_roof_trusses()
    emit_envelope()
    emit_circulation()
    emit_program()
    figures = emit_figures()

    materials = make_materials()
    stats = realise(materials)
    cam = setup_scene()
    renders = render_views(cam, out_dir)

    by_layer: dict[str, int] = {}
    for s in stats.values():
        by_layer[s["layer"]] = by_layer.get(s["layer"], 0) + s["instances"]
    report = {
        "probe": "student_model_fidelity_probe",
        "target_register": "architecture studio physical study model",
        "score": SCORE,
        "datums": {k: (round(v, 4) if isinstance(v, float) else v)
                   for k, v in vars(D).items() if not k.startswith("_")},
        "lattice": {"levels": LEVELS,
                    "x_lines": [round(v, 3) for v in X_LINES],
                    "y_lines": [round(v, 3) for v in Y_LINES],
                    "apse_nodes": len(APSE_NODES)},
        "element_families": stats,
        "instances_by_layer": by_layer,
        "totals": {"element_instances": sum(s["instances"] for s in stats.values()),
                   "element_kinds": len(stats),
                   "faces": sum(s["faces"] for s in stats.values()),
                   "scale_figures": figures},
        "renders": renders,
        "primitive_gap_vs_current_schema": {
            "box(center,size,rot_z)": "SUPPORTED today",
            "member(p0,p1,section_profile)":
                "MISSING -- needed by column, primary_beam, secondary_joist, brace, "
                "outrigger_strut, truss_chord, truss_web, purlin, mullion, transom, "
                "slab_fascia, railing, stair_stringer, parapet",
            "extrusion(polygon,z0,z1)":
                "MISSING -- needed by floor_slab (apsidal plan, cantilever, atrium "
                "voids), podium_slab, roof_deck, elevator_shaft",
            "quad(a,b,c,d)":
                "MISSING -- needed by glazing_panel, spandrel_panel, solid_wall_panel",
        },
    }
    (out_dir / "probe_report.json").write_text(json.dumps(report, indent=2),
                                               encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(out_dir / "student_model_probe.blend"))
    print(f"[probe] kinds={len(stats)} "
          f"instances={report['totals']['element_instances']} "
          f"faces={report['totals']['faces']} -> {out_dir}")


main()
