"""Section geometry and section properties, computed from first principles.

No catalogue values are quoted. Every property below is derived from the section's own
dimensions with standard mechanics-of-materials formulae, so any number can be checked
by hand and no proprietary table is reproduced. Mapping a chosen section back to a real
AISC / EN / APA catalogue product is a later procurement step and is deliberately not
claimed here.

Unit convention for this module and `sizing.py`:

    dimensions   mm
    area         mm^2
    second moment of area  mm^4
    section modulus        mm^3
    stress, modulus        MPa  ( = N/mm^2 )
    force                  kN
    moment                 kN*m

`loads.py` works in m, kPa, and kN/m and converts at the boundary.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field


MaterialFamily = Literal['steel', 'glulam', 'clt', 'sawn_timber', 'concrete']


class Material(BaseModel):
    """Design values. Every entry records its basis so a run can be audited."""

    id: str
    family: MaterialFamily
    basis: str
    density_kn_m3: float = Field(gt=0)
    elastic_modulus_mpa: float = Field(gt=0)
    # steel: yield strength. timber: reference bending design value Fb.
    strength_mpa: float = Field(gt=0)
    shear_strength_mpa: float = Field(gt=0)
    compression_parallel_mpa: float = Field(gt=0)
    # NDS column-stability inputs; unused for steel.
    modulus_min_mpa: float | None = None
    stability_c: float | None = None


MATERIALS: dict[str, Material] = {
    'steel_s355': Material(
        id='steel_s355', family='steel',
        basis='ASTM A992 / EN S355 nominal Fy = 345 MPa, E = 200 GPa; AISC 360 LRFD',
        density_kn_m3=78.5, elastic_modulus_mpa=200_000.0,
        strength_mpa=345.0, shear_strength_mpa=207.0, compression_parallel_mpa=345.0,
    ),
    'glulam_24f_18e': Material(
        id='glulam_24f_18e', family='glulam',
        basis='24F-1.8E softwood glulam nominal Fb = 16.5 MPa, E = 12.4 GPa; NDS ASD',
        density_kn_m3=5.5, elastic_modulus_mpa=12_400.0,
        strength_mpa=16.5, shear_strength_mpa=1.9, compression_parallel_mpa=11.0,
        modulus_min_mpa=6_400.0, stability_c=0.9,
    ),
    'clt_e1': Material(
        id='clt_e1', family='clt',
        basis='PRG 320 E1 grade major-strength direction, nominal Fb = 11.7 MPa, '
              'E = 11.7 GPa; parallel-layer effective stiffness only',
        density_kn_m3=5.0, elastic_modulus_mpa=11_700.0,
        strength_mpa=11.7, shear_strength_mpa=1.5, compression_parallel_mpa=9.0,
        modulus_min_mpa=6_000.0, stability_c=0.9,
    ),
    'sawn_spf_no2': Material(
        id='sawn_spf_no2', family='sawn_timber',
        basis='SPF No.2 nominal Fb = 8.6 MPa, E = 9.65 GPa; NDS ASD',
        density_kn_m3=5.0, elastic_modulus_mpa=9_650.0,
        strength_mpa=8.6, shear_strength_mpa=0.9, compression_parallel_mpa=8.3,
        modulus_min_mpa=3_450.0, stability_c=0.8,
    ),
    'concrete_c30': Material(
        id='concrete_c30', family='concrete',
        basis="f'c = 30 MPa normal weight; used for self weight and geometric rules only",
        density_kn_m3=24.0, elastic_modulus_mpa=25_700.0,
        strength_mpa=30.0, shear_strength_mpa=1.5, compression_parallel_mpa=30.0,
    ),
}


class SectionProperties(BaseModel):
    """Everything `sizing.py` needs, all computed."""

    id: str
    shape: Literal['i_section', 'box', 'chs', 'rectangle']
    material_id: str
    depth_mm: float
    width_mm: float
    area_mm2: float
    ix_mm4: float
    iy_mm4: float
    sx_mm3: float
    zx_mm3: float
    rx_mm: float
    ry_mm: float
    web_area_mm2: float
    self_weight_kn_m: float
    # Torsional and warping properties. Absent until now because nothing needed
    # them, and nothing needed them because the lateral-torsional buckling check
    # AISC F2.2 requires was not being run. `j_mm4` is St Venant torsion, `cw_mm6`
    # the warping constant, `rts_mm` the effective radius of gyration F2 uses.
    # Zero means the shape has none worth modelling or none was computed.
    j_mm4: float = 0.0
    cw_mm6: float = 0.0
    rts_mm: float = 0.0
    ho_mm: float = 0.0

    @property
    def depth_m(self) -> float:
        return self.depth_mm / 1000.0


def _finish(
    section_id: str, shape: str, material: Material, d: float, b: float,
    area: float, ix: float, iy: float, zx: float, web_area: float,
    j: float = 0.0, cw: float = 0.0, ho: float = 0.0,
) -> SectionProperties:
    sx = 2.0 * ix / d
    # AISC F2-7: rts^2 = sqrt(Iy * Cw) / Sx. Only meaningful where warping matters.
    rts = math.sqrt(math.sqrt(iy * cw) / sx) if cw > 0.0 and sx > 0.0 else 0.0
    return SectionProperties(
        id=section_id, shape=shape, material_id=material.id,
        depth_mm=round(d, 3), width_mm=round(b, 3),
        area_mm2=round(area, 3), ix_mm4=round(ix, 1), iy_mm4=round(iy, 1),
        sx_mm3=round(2.0 * ix / d, 2), zx_mm3=round(zx, 2),
        rx_mm=round(math.sqrt(ix / area), 3), ry_mm=round(math.sqrt(iy / area), 3),
        web_area_mm2=round(web_area, 3),
        # area mm^2 -> m^2 is 1e-6; density kN/m^3 * m^2 -> kN/m
        self_weight_kn_m=round(area * 1e-6 * material.density_kn_m3, 5),
        j_mm4=round(j, 1), cw_mm6=round(cw, 1), rts_mm=round(rts, 3),
        ho_mm=round(ho, 3),
    )


def i_section(d: float, bf: float, tw: float, tf: float, material: Material,
              section_id: str | None = None) -> SectionProperties:
    """Doubly symmetric I. All formulae are exact for the idealised shape (no fillets),
    which is conservative for area and stiffness."""
    if not (d > 2 * tf and bf > tw > 0 and tf > 0):
        raise ValueError(f'degenerate I-section d={d} bf={bf} tw={tw} tf={tf}')
    hw = d - 2.0 * tf
    area = 2.0 * bf * tf + hw * tw
    ix = (bf * d ** 3 - (bf - tw) * hw ** 3) / 12.0
    iy = (2.0 * tf * bf ** 3 + hw * tw ** 3) / 12.0
    zx = bf * tf * (d - tf) + tw * hw ** 2 / 4.0
    # St Venant torsion for an open thin-walled shape, AISC Table 1-1 basis:
    # J = sum(b*t^3)/3 over the three plates, with the web taken between flanges.
    j = (2.0 * bf * tf ** 3 + hw * tw ** 3) / 3.0
    # Warping constant of a doubly symmetric I: Cw = Iy * ho^2 / 4, ho flange centres.
    ho = d - tf
    cw = iy * ho ** 2 / 4.0
    name = section_id or f'I-{d:.0f}x{bf:.0f}x{tw:.0f}x{tf:.0f}'
    return _finish(name, 'i_section', material, d, bf, area, ix, iy, zx, d * tw,
                   j=j, cw=cw, ho=ho)


def hss_section(h: float, b: float, t: float, material: Material,
                section_id: str | None = None,
                corner_radius_factor: float = 2.0) -> SectionProperties:
    """Hollow structural section with the corner radii it is actually formed with.

    A cold-formed HSS is a rolled tube, not four welded plates: ASTM A500 puts an
    outside corner radius of about 2t on it, and the sharp-cornered idealisation
    overstates the area by two to three per cent and Ix by up to nine. That direction
    matters. For a W-shape the missing root fillets make the computed properties *low*,
    which is conservative and can be reported and left alone; for an HSS the missing
    corner radii make them *high*, so a column sized on them is weaker than the
    calculation says. An unconservative idealisation has no place in a member check.

    The corners are removed as circular segments: each one takes away (4 - pi)/4 * r^2
    of area whose centroid sits (10 - 3*pi)/(3*(4 - pi)) * r in from the corner apex.
    Checked against the published tables, this lands within half a per cent.
    """
    if not (h > 2 * t and b > 2 * t and t > 0):
        raise ValueError(f'degenerate HSS h={h} b={b} t={t}')
    r_out = corner_radius_factor * t
    r_in = max(0.0, r_out - t)

    def rounded(width: float, height: float, radius: float) -> tuple[float, float]:
        """Area and Ix of a rectangle with four rounded corners."""
        area = width * height - (4.0 - math.pi) * radius ** 2
        ix = width * height ** 3 / 12.0
        if radius > 0.0:
            cut = (4.0 - math.pi) / 4.0 * radius ** 2
            arm = height / 2.0 - radius + radius * (10.0 - 3.0 * math.pi) / (
                3.0 * (4.0 - math.pi))
            own = radius ** 4 * (1.0 / 3.0 - math.pi / 16.0
                                 - (10.0 - 3.0 * math.pi) ** 2
                                 / (36.0 * (4.0 - math.pi)))
            ix -= 4.0 * (cut * arm ** 2 + own)
        return area, ix

    outer_area, outer_ix = rounded(b, h, r_out)
    inner_area, inner_ix = rounded(b - 2.0 * t, h - 2.0 * t, r_in)
    area = outer_area - inner_area
    ix = outer_ix - inner_ix
    outer_area_y, outer_iy = rounded(h, b, r_out)
    inner_area_y, inner_iy = rounded(h - 2.0 * t, b - 2.0 * t, r_in)
    iy = outer_iy - inner_iy
    # Plastic modulus, with the corners taken off the plastic couple properly rather
    # than with an assumed lever arm. Z = 2 * S, and each corner segment removes its
    # own area times its own distance from the neutral axis; the outer corners come
    # off the section and the inner ones come back on, so the two enter with
    # opposite signs.
    def corner_couple(radius: float, height: float) -> float:
        if radius <= 0.0:
            return 0.0
        cut = (4.0 - math.pi) / 4.0 * radius ** 2
        arm = height / 2.0 - radius * (1.0 - (10.0 - 3.0 * math.pi)
                                       / (3.0 * (4.0 - math.pi)))
        return 4.0 * cut * arm

    zx = (b * h ** 2 - (b - 2.0 * t) * (h - 2.0 * t) ** 2) / 4.0
    zx -= corner_couple(r_out, h)
    zx += corner_couple(r_in, h - 2.0 * t)
    # Closed section: Bredt's formula for torsion, and warping is negligible, which
    # is why a tube does not suffer lateral-torsional buckling the way an I does.
    mid_b, mid_h = b - t, h - t
    j = 2.0 * t * (mid_b * mid_h) ** 2 / (mid_b + mid_h)
    name = section_id or f'HSS-{h:.0f}x{b:.0f}x{t:.1f}'
    return _finish(name, 'box', material, h, b, area, ix, iy, zx, 2.0 * h * t,
                   j=j, cw=0.0, ho=h - t)


def box_section(h: float, b: float, t: float, material: Material,
                section_id: str | None = None) -> SectionProperties:
    if not (h > 2 * t and b > 2 * t and t > 0):
        raise ValueError(f'degenerate box h={h} b={b} t={t}')
    hi, bi = h - 2.0 * t, b - 2.0 * t
    area = b * h - bi * hi
    ix = (b * h ** 3 - bi * hi ** 3) / 12.0
    iy = (h * b ** 3 - hi * bi ** 3) / 12.0
    zx = b * h ** 2 / 4.0 - bi * hi ** 2 / 4.0
    name = section_id or f'SHS-{h:.0f}x{b:.0f}x{t:.0f}'
    return _finish(name, 'box', material, h, b, area, ix, iy, zx, 2.0 * h * t)


def chs_section(od: float, t: float, material: Material,
                section_id: str | None = None) -> SectionProperties:
    if not (od > 2 * t and t > 0):
        raise ValueError(f'degenerate CHS od={od} t={t}')
    idm = od - 2.0 * t
    area = math.pi / 4.0 * (od ** 2 - idm ** 2)
    ix = math.pi / 64.0 * (od ** 4 - idm ** 4)
    zx = (od ** 3 - idm ** 3) / 6.0
    name = section_id or f'CHS-{od:.0f}x{t:.0f}'
    return _finish(name, 'chs', material, od, od, area, ix, ix, zx, 0.5 * area)


def rectangle_section(h: float, b: float, material: Material,
                      section_id: str | None = None) -> SectionProperties:
    if not (h > 0 and b > 0):
        raise ValueError(f'degenerate rectangle h={h} b={b}')
    area = b * h
    ix = b * h ** 3 / 12.0
    iy = h * b ** 3 / 12.0
    zx = b * h ** 2 / 4.0
    # Solid rectangle torsion constant, the standard beta*b*h^3 series truncated;
    # accurate to under one per cent for the aspect ratios this project produces.
    long_side, short_side = max(h, b), min(h, b)
    beta = 1.0 / 3.0 - 0.21 * (short_side / long_side) * (
        1.0 - (short_side / long_side) ** 4 / 12.0)
    j = beta * long_side * short_side ** 3
    name = section_id or f'RECT-{h:.0f}x{b:.0f}'
    return _finish(name, 'rectangle', material, h, b, area, ix, iy, zx, area,
                   j=j, cw=0.0, ho=h)


# ---------------------------------------------------------------------------
# Catalogues.  Generated series, not quoted tables.
# ---------------------------------------------------------------------------

def _steel_beam_series() -> list[SectionProperties]:
    """A metric I-beam series with proportions kept inside the AISC compact limits for
    Fy = 345 MPa, so `sizing.py` may use the plastic modulus without a local-buckling
    reduction. Compactness is re-verified per section in `sizing.is_compact`."""
    steel = MATERIALS['steel_s355']
    out: list[SectionProperties] = []
    for d in (200, 250, 300, 350, 400, 450, 500, 550, 600, 700, 800, 900, 1000):
        for ratio, tw_f, tf_f in ((0.50, 0.020, 0.032), (0.42, 0.024, 0.038),
                                  (0.34, 0.028, 0.045)):
            bf = round(d * ratio / 5) * 5
            tw = max(6.0, round(d * tw_f))
            tf = max(8.0, round(d * tf_f))
            if bf <= tw + 20 or d <= 2 * tf + 40:
                continue
            out.append(i_section(float(d), float(bf), float(tw), float(tf), steel))
    return sorted(out, key=lambda s: s.area_mm2)


def _steel_column_series() -> list[SectionProperties]:
    """Column-proportioned I sections (bf close to d) plus square hollow sections."""
    steel = MATERIALS['steel_s355']
    out: list[SectionProperties] = []
    for d in (150, 200, 250, 300, 350, 400, 450, 500):
        for tw_f, tf_f in ((0.030, 0.048), (0.040, 0.064), (0.052, 0.084)):
            bf = float(d)
            tw = max(6.0, round(d * tw_f))
            tf = max(8.0, round(d * tf_f))
            if d <= 2 * tf + 30:
                continue
            out.append(i_section(float(d), bf, float(tw), float(tf), steel))
    for h in (150, 200, 250, 300, 350, 400):
        for t in (8.0, 10.0, 12.5, 16.0, 20.0):
            if h > 2 * t + 40:
                out.append(box_section(float(h), float(h), t, steel))
    return sorted(out, key=lambda s: s.area_mm2)


def _glulam_series(material_id: str = 'glulam_24f_18e') -> list[SectionProperties]:
    """Glulam is made in lamination multiples, so depth steps by a lamination thickness
    and width steps by a standard billet width."""
    material = MATERIALS[material_id]
    lamination = 38.0
    out: list[SectionProperties] = []
    for width in (80.0, 130.0, 175.0, 215.0, 265.0, 315.0):
        for laminations in range(4, 33, 2):
            depth = lamination * laminations
            if depth / width > 8.0:
                continue
            out.append(rectangle_section(depth, width, material,
                                         f'GL-{depth:.0f}x{width:.0f}'))
    return sorted(out, key=lambda s: s.area_mm2)


STEEL_BEAMS: list[SectionProperties] = _steel_beam_series()
STEEL_COLUMNS: list[SectionProperties] = _steel_column_series()
GLULAM_MEMBERS: list[SectionProperties] = _glulam_series()


def _concrete_series(material_id: str = 'concrete_c30') -> list[SectionProperties]:
    """Cast rectangular sections on the increments a formwork shop actually builds.

    Fifty-millimetre steps rather than a continuous range, because a concrete section is
    made in a mould and a 437 mm beam costs what a 450 mm beam costs. The proportions
    run from square columns to beams twice as deep as wide, which is the usable band
    before a section needs compression steel or a wider web than the column below it.
    """
    material = MATERIALS[material_id]
    out: list[SectionProperties] = []
    for width in range(300, 901, 50):
        for depth in range(width, min(1601, width * 2 + 1), 50):
            out.append(rectangle_section(
                float(depth), float(width), material,
                section_id=f'RC-{depth}x{width}'))
    return sorted(out, key=lambda section: section.area_mm2)


CONCRETE_MEMBERS: list[SectionProperties] = _concrete_series()

CATALOGUES: dict[str, list[SectionProperties]] = {
    'steel_beam': STEEL_BEAMS,
    'steel_column': STEEL_COLUMNS,
    'glulam': GLULAM_MEMBERS,
}


class CltLayup(BaseModel):
    """CLT effective properties from the parallel layers only.

    This is the conservative simplification: cross layers are assumed to contribute no
    bending stiffness in the major direction. A shear-analogy or gamma-method
    calculation would give a higher stiffness, so results here are safe-sided but not
    optimal, and the run must say so rather than implying a full analysis.
    """

    id: str
    layer_thickness_mm: float = Field(gt=0)
    layer_count: int = Field(ge=3)
    material_id: str = 'clt_e1'

    @property
    def total_thickness_mm(self) -> float:
        return self.layer_thickness_mm * self.layer_count

    def effective_ix_mm4(self, width_mm: float = 1000.0) -> float:
        """Parallel layers are layers 1, 3, 5 ... counted from the outside."""
        t, n = self.layer_thickness_mm, self.layer_count
        total = t * n
        ix = 0.0
        for index in range(n):
            if index % 2 != 0:          # cross layer, ignored in the major direction
                continue
            centre = -total / 2.0 + t * (index + 0.5)
            ix += width_mm * t ** 3 / 12.0 + width_mm * t * centre ** 2
        return ix

    def effective_sx_mm3(self, width_mm: float = 1000.0) -> float:
        return 2.0 * self.effective_ix_mm4(width_mm) / self.total_thickness_mm

    def self_weight_kpa(self) -> float:
        return self.total_thickness_mm / 1000.0 * MATERIALS[self.material_id].density_kn_m3


CLT_LAYUPS: list[CltLayup] = [
    CltLayup(id='CLT-3x35', layer_thickness_mm=35.0, layer_count=3),
    CltLayup(id='CLT-5x35', layer_thickness_mm=35.0, layer_count=5),
    CltLayup(id='CLT-5x40', layer_thickness_mm=40.0, layer_count=5),
    CltLayup(id='CLT-7x35', layer_thickness_mm=35.0, layer_count=7),
    CltLayup(id='CLT-7x40', layer_thickness_mm=40.0, layer_count=7),
    CltLayup(id='CLT-9x40', layer_thickness_mm=40.0, layer_count=9),
]
