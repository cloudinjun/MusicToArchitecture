"""Standard component registry: parts a fabricator can actually order.

`sections.py` generated its steel from proportions -- `I-450x225x9x14` at ratios chosen
to stay inside the compact limits. Every property was computed correctly and no
fabricator has ever rolled one. A model whose members cannot be ordered is a schematic
model however good its arithmetic, and the difference between that and a permit set is
exactly this: a designation, a producing standard, and a supplier who recognises it.

So the registry lists real products. Each entry carries:

- the **designation** a drawing would call out (`W18X50`, `HSS10X10X1/2`, `GL28h
  215x608`, `CLT-5s-175`),
- the **producing standard** it is made to (ASTM A992, ASTM A500 Gr. C, EN 14080,
  ANSI/APA PRG 320),
- the **published dimensions**, which are the authoritative geometry, and
- a **catalogue cross-check** on the published section properties.

Properties are computed from the dimensions rather than transcribed, which is the rule
this project already holds elsewhere: a number nobody can recompute is a number nobody
can audit. The published values travel alongside as `catalogue_ix_mm4` and
`catalogue_zx_mm3` and are used for one purpose only -- `verify_against_catalogue()`
reports the deviation, so a transcription error announces itself instead of quietly
sizing a beam.

**A rolled shape's computed Ix runs a few per cent below the published value** because
the idealised geometry has no root fillets. That direction is conservative for strength
and for stiffness, and the deviation is reported rather than corrected: adding a fudge
factor to match a catalogue would be the opposite of an auditable number.

**What this registry does not make true.** Listing `W18X50` means the member can be
ordered. It does not mean the run that selected it checked everything a permit needs:
see `validators.py` for which clauses are evaluated and which are still absent.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .geometry import ProfileSpec
from .sections import (
    MATERIALS, SectionProperties, hss_section, i_section, rectangle_section,
)

ProductFamily = Literal[
    'steel_w_shape', 'steel_hss_square', 'glulam', 'clt', 'concrete_cast',
]


class ProductSpec(BaseModel):
    """One orderable product, with the standard it is made to."""

    designation: str
    family: ProductFamily
    producing_standard: str
    material_id: str
    # Published dimensions in millimetres. These are the authoritative geometry.
    depth_mm: float = Field(gt=0)
    width_mm: float = Field(gt=0)
    web_mm: float = Field(default=0.0, ge=0.0)
    flange_mm: float = Field(default=0.0, ge=0.0)
    # Published section properties, for transcription cross-check only.
    catalogue_area_mm2: float | None = None
    catalogue_ix_mm4: float | None = None
    catalogue_zx_mm3: float | None = None
    note: str = ''

    def to_section(self) -> SectionProperties:
        material = MATERIALS[self.material_id]
        if self.family == 'steel_w_shape':
            return i_section(self.depth_mm, self.width_mm, self.web_mm,
                             self.flange_mm, material, section_id=self.designation)
        if self.family == 'steel_hss_square':
            return hss_section(self.depth_mm, self.width_mm, self.web_mm,
                               material, section_id=self.designation)
        return rectangle_section(self.depth_mm, self.width_mm, material,
                                 section_id=self.designation)


class CatalogueDeviation(BaseModel):
    """How far a computed property sits from the published one, and why."""

    designation: str
    property_name: str
    computed: float
    published: float
    deviation: float

    @property
    def within_expected(self) -> bool:
        """A rolled shape's fillets add material the idealised geometry has none of.

        Six per cent low on Ix is the top of the ordinary band for a W-shape; beyond
        that the entry is more likely mistyped than idealised, which is the whole point
        of keeping the published number beside the computed one.
        """
        return -0.06 <= self.deviation <= 0.005


# ---------------------------------------------------------------------------
# Steel: AISC 15th edition shapes, ASTM A992 (W) and A500 Grade C (HSS)
# ---------------------------------------------------------------------------
#
# Dimensions are the published ones converted to millimetres. Designations are the ones
# a drawing calls out and a mill rolls.

_W_SHAPES: tuple[tuple[str, float, float, float, float, float, float, float], ...] = (
    # designation,      d,     bf,    tw,    tf,   A mm2,  Ix mm4,   Zx mm3
    ('W12X19',       308.9, 101.7,  5.97,  8.89,   3594,  54.1e6,  404.7e3),
    ('W10X22',       258.3, 146.1,  6.10,  9.14,   4187,  49.1e6,  426.0e3),
    ('W12X26',       310.4, 164.8,  5.84,  9.65,   4935,  84.9e6,  609.6e3),
    ('W14X26',       353.3, 127.6,  6.48, 10.67,   4961, 102.0e6,  658.7e3),
    ('W16X26',       398.5, 139.7,  6.35,  8.76,   4955, 125.3e6,  724.3e3),
    ('W16X31',       403.4, 140.3,  6.99, 11.18,   5890, 156.1e6,  884.9e3),
    ('W18X40',       454.7, 152.8,  8.00, 13.34,   7613, 254.7e6, 1284.7e3),
    ('W18X50',       456.9, 190.4,  9.02, 14.48,   9484, 333.0e6, 1655.0e3),
    ('W21X50',       529.1, 165.9,  9.65, 13.59,   9484, 409.6e6, 1802.0e3),
    ('W21X62',       533.1, 209.3, 10.16, 15.62,  11806, 553.6e6, 2360.0e3),
    ('W24X55',       598.7, 177.9, 10.03, 12.83,  10452, 561.9e6, 2196.0e3),
    ('W24X68',       602.7, 227.7, 10.54, 14.86,  12968, 761.7e6, 2900.0e3),
    ('W24X76',       607.6, 228.3, 11.18, 17.27,  14452, 874.1e6, 3277.0e3),
    ('W27X84',       678.4, 253.0, 11.68, 16.26,  16000,1186.0e6, 3999.0e3),
    ('W30X90',       750.1, 264.2, 11.94, 15.49,  17032,1503.0e6, 4637.0e3),
    ('W30X108',      757.7, 266.2, 13.84, 19.30,  20452,1861.0e6, 5670.0e3),
    ('W33X118',      834.6, 291.6, 13.97, 18.80,  22387,2456.0e6, 6801.0e3),
    ('W36X135',      903.0, 303.5, 15.24, 20.07,  25613,3247.0e6, 8341.0e3),
)

# Column-proportioned W shapes: bf close to d, so the weak axis is not the whole story.
_W_COLUMNS: tuple[tuple[str, float, float, float, float, float, float, float], ...] = (
    ('W10X49',       253.5, 254.0,  8.64, 14.22,   9290, 113.2e6,  989.8e3),
    ('W12X65',       307.8, 304.8,  9.91, 15.37,  12323, 221.9e6, 1586.3e3),
    ('W12X87',       318.3, 308.1, 13.08, 20.57,  16516, 308.0e6, 2163.1e3),
    ('W14X90',       356.1, 368.8, 11.18, 18.03,  17097, 415.8e6, 2573.0e3),
    ('W14X120',      367.8, 372.6, 14.99, 23.88,  22774, 574.4e6, 3474.0e3),
    ('W14X159',      380.5, 395.5, 18.92, 30.23,  30129, 790.8e6, 4703.0e3),
    ('W14X211',      399.3, 401.3, 24.89, 39.62,  40000,1107.0e6, 6391.0e3),
)

# ASTM A500 Grade C square HSS. `t` is the design wall thickness (0.93 x nominal),
# which is what AISC requires for strength calculations.
#
# Only the area is carried for cross-check. The computed area lands within 0.9 % of
# the published value across the whole range once the corner radii are modelled,
# which is strong evidence the dimensions and the geometry are both right -- area is
# far more sensitive to a wrong dimension than to anything else. The published Ix and
# Zx are deliberately absent: the values available to this project could not be
# vouched for against the printed table, and a cross-check against a number nobody
# can stand behind either passes spuriously or fails spuriously. Both are computed
# from the dimensions with the corner radii included; see `sections.hss_section`.
_HSS_SQUARE: tuple[tuple[str, float, float, float], ...] = (
    # designation,        b,      t,   A mm2
    ('HSS6X6X1/4',    152.4,   5.92,   3381),
    ('HSS8X8X1/4',    203.2,   5.92,   4581),
    ('HSS8X8X3/8',    203.2,   8.86,   6710),
    ('HSS10X10X3/8',  254.0,   8.86,   8516),
    ('HSS10X10X1/2',  254.0,  11.81,  11097),
    ('HSS12X12X3/8',  304.8,   8.86,  10387),
    ('HSS12X12X1/2',  304.8,  11.81,  13548),
    ('HSS14X14X1/2',  355.6,  11.81,  16000),
    ('HSS16X16X1/2',  406.4,  11.81,  18516),
    ('HSS16X16X5/8',  406.4,  14.76,  22774),
)


def _steel_products() -> list[ProductSpec]:
    out: list[ProductSpec] = []
    for group, note in ((_W_SHAPES, 'Beam-proportioned rolled shape.'),
                        (_W_COLUMNS, 'Column-proportioned rolled shape, bf near d.')):
        for name, d, bf, tw, tf, area, ix, zx in group:
            out.append(ProductSpec(
                designation=name, family='steel_w_shape',
                producing_standard='ASTM A992 / AISC 15th ed. shape tables',
                material_id='steel_s355', depth_mm=d, width_mm=bf, web_mm=tw,
                flange_mm=tf, catalogue_area_mm2=area, catalogue_ix_mm4=ix,
                catalogue_zx_mm3=zx, note=note))
    for name, b, t, area in _HSS_SQUARE:
        out.append(ProductSpec(
            designation=name, family='steel_hss_square',
            producing_standard='ASTM A500 Grade C; design wall 0.93 x nominal',
            material_id='steel_s355', depth_mm=b, width_mm=b, web_mm=t,
            catalogue_area_mm2=area,
            note='Square hollow section, equal about both axes. Corner radii are '
                 'modelled; see sections.hss_section.'))
    return out


# ---------------------------------------------------------------------------
# Glulam: EN 14080 billet widths, laminations in 40 mm
# ---------------------------------------------------------------------------
#
# Unlike the steel, this was already close to real: EN 14080 finishes billets at
# 90/115/140/165/190/215/240 mm and builds depth in whole laminations. What it lacked
# was the designation a supplier quotes and the strength class the design values belong
# to, so a reader could not tell GL24h from GL28h in a model that used one of them.

_GLULAM_WIDTHS_MM = (90.0, 115.0, 140.0, 165.0, 190.0, 215.0, 240.0)
_GLULAM_LAMINATION_MM = 40.0


def _glulam_products(strength_class: str = 'GL28h') -> list[ProductSpec]:
    out: list[ProductSpec] = []
    for width in _GLULAM_WIDTHS_MM:
        for laminations in range(4, 31):
            depth = _GLULAM_LAMINATION_MM * laminations
            # EN 14080 limits the depth-to-width ratio a billet is produced at, and a
            # deeper one needs lateral restraint the model does not describe.
            if depth / width > 8.0 or depth > 1400.0:
                continue
            out.append(ProductSpec(
                designation=f'{strength_class} {width:.0f}x{depth:.0f}',
                family='glulam',
                producing_standard='EN 14080:2013 homogeneous glulam',
                material_id='glulam_24f_18e', depth_mm=depth, width_mm=width,
                note=f'{laminations} laminations at {_GLULAM_LAMINATION_MM:.0f} mm.'))
    return out


# ---------------------------------------------------------------------------
# CLT: ANSI/APA PRG 320 published layups
# ---------------------------------------------------------------------------

_CLT_LAYUPS: tuple[tuple[str, int, float], ...] = (
    ('CLT-3s-105', 3, 105.0),
    ('CLT-3s-105E', 3, 105.0),
    ('CLT-5s-175', 5, 175.0),
    ('CLT-5s-210', 5, 210.0),
    ('CLT-7s-245', 7, 245.0),
    ('CLT-7s-280', 7, 280.0),
)


def _clt_products() -> list[ProductSpec]:
    return [
        ProductSpec(
            designation=name, family='clt',
            producing_standard='ANSI/APA PRG 320 performance-rated cross-laminated timber',
            material_id='clt_e1', depth_mm=thickness, width_mm=1000.0,
            note=f'{plies}-ply panel, properties per metre of width.')
        for name, plies, thickness in _CLT_LAYUPS
    ]


# ---------------------------------------------------------------------------
# Concrete: cast sections on formwork increments, with reinforcement to ASTM A615
# ---------------------------------------------------------------------------

REBAR_A615: dict[str, float] = {
    # designation: nominal diameter in millimetres
    '#4': 12.7, '#5': 15.9, '#6': 19.1, '#7': 22.2, '#8': 25.4,
    '#9': 28.7, '#10': 32.3, '#11': 35.8,
}
REBAR_AREA_MM2: dict[str, float] = {
    '#4': 129.0, '#5': 199.0, '#6': 284.0, '#7': 387.0, '#8': 510.0,
    '#9': 645.0, '#10': 819.0, '#11': 1006.0,
}


def _concrete_products() -> list[ProductSpec]:
    out: list[ProductSpec] = []
    for width in range(300, 901, 50):
        for depth in range(width, min(1601, width * 2 + 1), 50):
            out.append(ProductSpec(
                designation=f'RC-{depth}x{width}',
                family='concrete_cast',
                producing_standard='ACI 318-19 cast-in-place; ASTM A615 Grade 420 bar',
                material_id='concrete_c30', depth_mm=float(depth),
                width_mm=float(width),
                note='Cast section on a 50 mm formwork increment.'))
    return out


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

REGISTRY: list[ProductSpec] = (
    _steel_products() + _glulam_products() + _clt_products() + _concrete_products()
)

BY_DESIGNATION: dict[str, ProductSpec] = {p.designation: p for p in REGISTRY}


def products(family: ProductFamily) -> list[ProductSpec]:
    return [p for p in REGISTRY if p.family == family]


def catalogue(family: ProductFamily) -> list[SectionProperties]:
    """Section properties for one family, smallest first."""
    return sorted((p.to_section() for p in products(family)),
                  key=lambda section: section.area_mm2)


def spec_for(designation: str) -> ProductSpec | None:
    return BY_DESIGNATION.get(designation)


def profile_for(designation: str) -> ProfileSpec | None:
    """A drawable profile for a registered product, or nothing if it is not one.

    The compiler asks the registry before it asks the id parser, because a real
    designation carries no dimensions in its name: `W18X50` says which shape to order
    and nothing about how deep it is, where `I-450x225x9x14` said everything and named
    a shape nobody rolls. That trade is the whole point of the registry, and this
    function is where the drawing gets its geometry back.
    """
    spec = BY_DESIGNATION.get(designation)
    if spec is None:
        return None
    if spec.family == 'steel_w_shape':
        return ProfileSpec(
            id=spec.designation, shape='i_section', depth_m=spec.depth_mm / 1000.0,
            width_m=spec.width_mm / 1000.0, web_m=spec.web_mm / 1000.0,
            flange_m=spec.flange_mm / 1000.0, source='sized')
    if spec.family == 'steel_hss_square':
        return ProfileSpec(
            id=spec.designation, shape='box', depth_m=spec.depth_mm / 1000.0,
            width_m=spec.width_mm / 1000.0, web_m=spec.web_mm / 1000.0,
            source='sized')
    return ProfileSpec(
        id=spec.designation, shape='rectangle', depth_m=spec.depth_mm / 1000.0,
        width_m=spec.width_mm / 1000.0, source='sized')


def verify_against_catalogue() -> list[CatalogueDeviation]:
    """Compare every computed property with the published one.

    This is the transcription check, and it is the reason the published numbers are in
    the table at all. A computed Ix a few per cent under the published value is the
    fillets; one that is out by twenty is a typo, and a typo in a section table sizes a
    beam wrong in a way no downstream check can catch.
    """
    out: list[CatalogueDeviation] = []
    for spec in REGISTRY:
        section = spec.to_section()
        for name, computed, published in (
            ('area_mm2', section.area_mm2, spec.catalogue_area_mm2),
            ('ix_mm4', section.ix_mm4, spec.catalogue_ix_mm4),
            ('zx_mm3', section.zx_mm3, spec.catalogue_zx_mm3),
        ):
            if published is None or published <= 0:
                continue
            out.append(CatalogueDeviation(
                designation=spec.designation, property_name=name,
                computed=round(computed, 1), published=published,
                deviation=round((computed - published) / published, 5)))
    return out
