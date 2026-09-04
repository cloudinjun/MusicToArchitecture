"""Load model: assembly dead loads, occupancy live loads, reduction, and combinations.

Working units in this module are m, kPa, kN/m, kN. Section capacities live in
`sections.py` / `sizing.py` and use mm, MPa, kN.

Basis and its limits, stated once so no downstream report has to hedge:

- Live loads are the ASCE/SEI 7 minimum uniformly distributed occupancy values, given
  here in kPa. The adopted jurisdiction profile decides the applicable edition and any
  local amendment; until `structural_code_profile.status` is `resolved`, every result
  produced from these values is `code_inputs_incomplete`.
- Dead loads are built up from the modelled assembly, not assumed as a lump sum, so a
  change in deck, topping, or finish propagates.
- Only gravity is implemented. Wind, seismic, snow drift, rain ponding, and notional
  lateral loads are out of scope and are reported as unresolved rather than as zero.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .sections import MATERIALS


PSF_TO_KPA = 0.047880258


# ---------------------------------------------------------------------------
# Occupancy live loads (ASCE/SEI 7 minimum uniform values)
# ---------------------------------------------------------------------------

class OccupancyLive(BaseModel):
    id: str
    label: str
    live_kpa: float = Field(gt=0)
    source_psf: float
    reducible: bool


OCCUPANCY_LIVE: dict[str, OccupancyLive] = {
    'library_reading': OccupancyLive(
        id='library_reading', label='Library reading rooms',
        live_kpa=round(60 * PSF_TO_KPA, 3), source_psf=60, reducible=True),
    'library_stacks': OccupancyLive(
        id='library_stacks', label='Library stack rooms',
        live_kpa=round(150 * PSF_TO_KPA, 3), source_psf=150, reducible=False),
    'corridor_above_first': OccupancyLive(
        id='corridor_above_first', label='Corridors above the first floor',
        live_kpa=round(80 * PSF_TO_KPA, 3), source_psf=80, reducible=True),
    'lobby_first_corridor': OccupancyLive(
        id='lobby_first_corridor', label='Lobbies and first-floor corridors',
        live_kpa=round(100 * PSF_TO_KPA, 3), source_psf=100, reducible=False),
    'office': OccupancyLive(
        id='office', label='Offices',
        live_kpa=round(50 * PSF_TO_KPA, 3), source_psf=50, reducible=True),
    'assembly_fixed_seats': OccupancyLive(
        id='assembly_fixed_seats', label='Assembly areas, fixed seats',
        live_kpa=round(60 * PSF_TO_KPA, 3), source_psf=60, reducible=False),
    'assembly_movable_seats': OccupancyLive(
        id='assembly_movable_seats', label='Assembly areas, movable seats',
        live_kpa=round(100 * PSF_TO_KPA, 3), source_psf=100, reducible=False),
    'stage': OccupancyLive(
        id='stage', label='Stages',
        live_kpa=round(150 * PSF_TO_KPA, 3), source_psf=150, reducible=False),
    'stairs_exit': OccupancyLive(
        id='stairs_exit', label='Stairs and exitways',
        live_kpa=round(100 * PSF_TO_KPA, 3), source_psf=100, reducible=False),
    'roof_ordinary': OccupancyLive(
        id='roof_ordinary', label='Ordinary flat roof',
        live_kpa=round(20 * PSF_TO_KPA, 3), source_psf=20, reducible=True),
}


# ---------------------------------------------------------------------------
# Assemblies: dead load built up from the modelled layers
# ---------------------------------------------------------------------------

class AssemblyLayer(BaseModel):
    label: str
    thickness_m: float | None = None
    material_id: str | None = None
    fixed_kpa: float | None = None

    def load_kpa(self) -> float:
        if self.fixed_kpa is not None:
            return self.fixed_kpa
        if self.thickness_m is None or self.material_id is None:
            raise ValueError(f'layer {self.label} has neither thickness nor a fixed load')
        return self.thickness_m * MATERIALS[self.material_id].density_kn_m3


class FloorAssembly(BaseModel):
    """A named build-up. `superimposed_dead_kpa` is everything above and below the
    structural deck; the structural member's own weight is added separately by
    `sizing.py` so it stays visible in the load path."""

    id: str
    label: str
    layers: list[AssemblyLayer]

    def superimposed_dead_kpa(self) -> float:
        return round(sum(layer.load_kpa() for layer in self.layers), 4)


def composite_steel_deck(topping_m: float = 0.075) -> FloorAssembly:
    return FloorAssembly(
        id='composite_steel_deck', label='Composite metal deck with concrete topping',
        layers=[
            AssemblyLayer(label='concrete over deck (average)',
                          thickness_m=topping_m + 0.025, material_id='concrete_c30'),
            AssemblyLayer(label='steel deck profile', fixed_kpa=0.15),
            AssemblyLayer(label='floor finish', fixed_kpa=0.30),
            AssemblyLayer(label='ceiling, lighting, and services', fixed_kpa=0.35),
            AssemblyLayer(label='movable partition allowance', fixed_kpa=0.72),
        ])


def clt_floor(panel_thickness_m: float, topping_m: float = 0.06) -> FloorAssembly:
    return FloorAssembly(
        id='clt_floor', label='CLT panel with acoustic topping',
        layers=[
            AssemblyLayer(label='CLT panel', thickness_m=panel_thickness_m,
                          material_id='clt_e1'),
            AssemblyLayer(label='concrete acoustic topping', thickness_m=topping_m,
                          material_id='concrete_c30'),
            AssemblyLayer(label='resilient layer and finish', fixed_kpa=0.25),
            AssemblyLayer(label='ceiling and services', fixed_kpa=0.30),
            AssemblyLayer(label='movable partition allowance', fixed_kpa=0.72),
        ])


def timber_joist_floor(deck_m: float = 0.045) -> FloorAssembly:
    return FloorAssembly(
        id='timber_joist_floor', label='Timber deck on joists',
        layers=[
            AssemblyLayer(label='structural timber deck', thickness_m=deck_m,
                          material_id='sawn_spf_no2'),
            AssemblyLayer(label='floor finish and levelling', fixed_kpa=0.35),
            AssemblyLayer(label='ceiling and services', fixed_kpa=0.25),
            AssemblyLayer(label='movable partition allowance', fixed_kpa=0.72),
        ])


def flat_roof_assembly() -> FloorAssembly:
    return FloorAssembly(
        id='flat_roof', label='Insulated single-ply flat roof',
        layers=[
            AssemblyLayer(label='membrane and protection', fixed_kpa=0.10),
            AssemblyLayer(label='insulation and fall build-up', fixed_kpa=0.25),
            AssemblyLayer(label='steel deck profile', fixed_kpa=0.15),
            AssemblyLayer(label='ceiling and services', fixed_kpa=0.25),
            AssemblyLayer(label='rooftop plant allowance', fixed_kpa=0.50),
        ])


# ---------------------------------------------------------------------------
# Live load reduction (ASCE/SEI 7 basic reduction)
# ---------------------------------------------------------------------------

MemberRole = Literal['beam', 'girder', 'column', 'slab']

# K_LL, the live load element factor.
K_LL: dict[MemberRole, float] = {
    'beam': 2.0, 'girder': 2.0, 'column': 4.0, 'slab': 1.0,
}


class LiveReduction(BaseModel):
    reduced_kpa: float
    factor: float
    influence_area_m2: float
    permitted: bool
    reason: str


def reduce_live_load(
    occupancy: OccupancyLive, tributary_area_m2: float, role: MemberRole,
    floors_supported: int = 1,
) -> LiveReduction:
    """ASCE/SEI 7 basic reduction, SI form:

        L = Lo * (0.25 + 4.57 / sqrt(K_LL * A_T))

    floored at 0.50*Lo for members supporting one floor and 0.40*Lo for two or more.
    No reduction is taken below an influence area of 37.2 m^2, nor for non-reducible
    occupancies, except that a member supporting two or more floors carrying a live load
    above 4.79 kPa may take a 20 % reduction.
    """
    k = K_LL[role]
    influence = k * tributary_area_m2
    floor_limit = 0.40 if floors_supported >= 2 else 0.50

    if not occupancy.reducible:
        if floors_supported >= 2 and occupancy.live_kpa > 4.79:
            return LiveReduction(
                reduced_kpa=round(occupancy.live_kpa * 0.80, 4), factor=0.80,
                influence_area_m2=round(influence, 2), permitted=True,
                reason='non-reducible occupancy above 4.79 kPa supporting two or more '
                       'floors: 20 % reduction permitted')
        return LiveReduction(
            reduced_kpa=occupancy.live_kpa, factor=1.0,
            influence_area_m2=round(influence, 2), permitted=False,
            reason=f'{occupancy.label} is a non-reducible occupancy')

    if influence < 37.2:
        return LiveReduction(
            reduced_kpa=occupancy.live_kpa, factor=1.0,
            influence_area_m2=round(influence, 2), permitted=False,
            reason='influence area below 37.2 m^2; no reduction permitted')

    factor = max(floor_limit, min(1.0, 0.25 + 4.57 / influence ** 0.5))
    return LiveReduction(
        reduced_kpa=round(occupancy.live_kpa * factor, 4), factor=round(factor, 4),
        influence_area_m2=round(influence, 2), permitted=True,
        reason=f'basic reduction with K_LL={k:g}, floor limit {floor_limit:.2f}')


# ---------------------------------------------------------------------------
# Combinations
# ---------------------------------------------------------------------------

class LoadCase(BaseModel):
    dead_kpa: float
    live_kpa: float
    roof_live_kpa: float = 0.0

    def lrfd(self) -> tuple[float, str]:
        """Governing gravity strength combination (ASCE/SEI 7 2.3.1, cases 1 and 2)."""
        c1 = 1.4 * self.dead_kpa
        c2 = 1.2 * self.dead_kpa + 1.6 * self.live_kpa + 0.5 * self.roof_live_kpa
        return ((c1, '1.4D') if c1 >= c2
                else (c2, '1.2D + 1.6L + 0.5Lr'))

    def service_total(self) -> float:
        return self.dead_kpa + self.live_kpa + self.roof_live_kpa

    def service_live(self) -> float:
        return self.live_kpa + self.roof_live_kpa


class LinearLoad(BaseModel):
    """A uniform area load resolved onto one spanning member, in kN/m."""

    factored_kn_m: float
    service_total_kn_m: float
    service_live_kn_m: float
    combination: str
    tributary_width_m: float


def line_load_from_area(
    case: LoadCase, tributary_width_m: float, member_self_weight_kn_m: float = 0.0,
) -> LinearLoad:
    factored_area, combination = case.lrfd()
    return LinearLoad(
        factored_kn_m=round(factored_area * tributary_width_m
                            + 1.2 * member_self_weight_kn_m, 5),
        service_total_kn_m=round(case.service_total() * tributary_width_m
                                 + member_self_weight_kn_m, 5),
        service_live_kn_m=round(case.service_live() * tributary_width_m, 5),
        combination=combination, tributary_width_m=round(tributary_width_m, 4),
    )
