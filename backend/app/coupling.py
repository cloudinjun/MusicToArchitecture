"""Program -> structure -> facade compatibility chain.

One connected screen, run before anything is selected and again as a compile-time gate:

    typology constitution + brief
          |  area, storey count, clear span, load class, occupancy
          v
    ProgramDemand  --- gate 1 --->  StructuralSupply  --- gate 2 --->  FacadeDemand
                                          |
                                          v
                            surviving (system, grammar) options,
                            each with a weight and named mitigations
                                          |
                                          v
                      the architectural score modulates only what survived

Every verdict is **computed from declared physical quantities**, never from a
hand-authored opinion matrix, so any result can be explained by naming the axis that
failed and the number that failed it.

Two worked examples, the ones this module exists for:

1. *A six-storey library cannot be a tensile membrane.* The decisive reason is not
   height. It is that a membrane does not provide occupied floor plates at all -- it is
   a covering system. Timber then fails on a second, softer axis: light frame tops out
   around five storeys and 2.5 kPa, while library stack rooms need 7.2 kPa (ASCE 7).
   Mass timber survives on height but needs a named answer for the stack load.

2. *A heavy panel facade cannot sit on a tensile membrane.* Not only because of mass
   (500 kg/m2 against 5) but because of stiffness: a precast panel needs a backup that
   moves less than L/480, and a membrane delivers L/50. Strength is not stiffness, and
   that is the axis designers miss.

Registry provenance: every number is traceable to the "Legal variables and starting
ranges" table of the named guide, or to ASCE 7 occupancy live loads. The guides are the
source; this module is their machine projection and must be updated when they change.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field

from .codes import (
    UNRESOLVED_JURISDICTION, CodeScreen, JurisdictionProfile,
    OCCUPANCY_GROUP_BY_TYPOLOGY, OccupancyGroup,
    gate_combustible_cladding, gate_construction_type, gate_exterior_opening_area,
    gate_frame_fire_rating, gate_seismic_system,
)


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

BackupType = Literal[
    'continuous_line',   # an uninterrupted slab edge or spandrel beam to fix to
    'point_grid',        # discrete nodes or brackets at a regular module
    'bearing_wall',      # the structure itself is the wall plane
    'flexible_edge',     # a cable or membrane boundary that moves under load
    'self_supporting',   # the envelope spans on its own between rare supports
]

SurfaceClass = Literal['planar', 'single_curved', 'double_curved']

PanelGeometry = Literal[
    'planar_required',    # flat glass, stone, precast
    'single_curved_ok',   # rollable metal, cold-formed sheet
    'double_curved_ok',   # ETFE cushion, fabric, GFRC, cast panels
    'not_applicable',
]

Continuity = Literal['full', 'partial', 'none']

ConstructionClass = Literal['combustible', 'heavy_timber', 'noncombustible']

# Two different kinds of statement, deliberately not on one scale.
#
# `feasibility` is the only thing that eliminates. It is binary and comes from hard
# gates alone.
#
# `InterfaceBurden` describes what a feasible pair would cost to detail. It is a
# **description, not a ranking**: it says how many interfaces are left to resolve, never
# which building is better. Choosing among feasible options is a separate set of
# criteria the project has not defined yet, and nothing in this module may pre-empt it.
Feasibility = Literal['feasible', 'infeasible']

InterfaceBurden = Literal[
    'clean',                  # every axis comfortable
    'minor_interfaces',       # one or two details to design
    'significant_interfaces', # a secondary system or a re-detailing exercise
    'many_interfaces',        # feasible, but most axes need work
    'not_applicable',         # infeasible; burden is undefined
]

# Retained for the shortlist prose in decision 0002; never used to filter.
Verdict = Literal[
    'native', 'conditional', 'requires_secondary_system', 'poor', 'incompatible',
]

_CONSTRUCTION_RANK: dict[ConstructionClass, int] = {
    'combustible': 0, 'heavy_timber': 1, 'noncombustible': 2,
}
_CONTINUITY_RANK: dict[Continuity, int] = {'none': 0, 'partial': 1, 'full': 2}
_SCORE_FLOOR = 0.05


# ---------------------------------------------------------------------------
# The three participants
# ---------------------------------------------------------------------------

class ProgramDemand(BaseModel):
    """What the typology constitution and the brief ask of a structural system."""

    program_id: str
    typology: Literal['library', 'theater', 'museum']
    source_ref: str
    storey_count: int = Field(ge=1)
    building_height_m: float = Field(gt=0)
    requires_occupied_floor_plates: bool = True
    max_clear_span_m: float = Field(gt=0)
    governing_span_space: str
    peak_floor_live_load_kpa: float = Field(gt=0)
    governing_load_space: str
    acoustic_separation_required: Continuity
    humidity_control_required: Continuity
    min_construction_class: ConstructionClass
    exposed_structure_intended: bool = True

    @property
    def occupancy_group(self) -> OccupancyGroup:
        return OCCUPANCY_GROUP_BY_TYPOLOGY[self.typology]


class StructuralSupply(BaseModel):
    """What one structural system can actually offer program and envelope."""

    system_id: str
    qualified_name: str
    tectonic_family: Literal['frame', 'tensile', 'shell']
    source_ref: str

    # --- offered to program ---
    provides_occupied_floor_plates: bool
    max_storeys: int = Field(ge=1)
    max_height_m: float = Field(gt=0)
    clear_span_ordinary_m: float = Field(gt=0)
    clear_span_longspan_subtype_m: float = Field(gt=0)
    floor_load_capacity_kpa: float = Field(ge=0)
    acoustic_separation_support: Continuity
    humidity_tolerance: Continuity
    construction_class: ConstructionClass

    # --- offered to envelope ---
    envelope_mass_capacity_kg_m2: float = Field(gt=0)
    offered_backup_types: list[BackupType]
    hardpoint_spacing_m: tuple[float, float]
    deflection_at_envelope_ratio: int = Field(gt=0, description='L/n actually delivered')
    host_surface: SurfaceClass
    envelope_depth_available_m: tuple[float, float]
    barrier_continuity_support: Continuity


class FacadeDemand(BaseModel):
    """What one facade grammar asks of whatever stands behind it."""

    grammar_id: str
    qualified_name: str
    source_ref: str
    areal_mass_kg_m2: tuple[float, float]
    accepted_backup_types: list[BackupType]
    support_spacing_max_m: float = Field(gt=0)
    deflection_limit_ratio: int = Field(gt=0, description='L/n; larger is stricter')
    panel_geometry: PanelGeometry
    depth_zone_m: tuple[float, float]
    barrier_continuity_required: Continuity
    opening_ratio: tuple[float, float]
    combustible_cladding: bool


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

class AxisResult(BaseModel):
    axis: str
    score: float = Field(ge=0.0, le=1.0)
    weight: float
    hard_gate: bool
    passed_gate: bool
    detail: str
    mitigation: str | None = None


class CouplingResult(BaseModel):
    """Two independent outputs.

    `feasibility` and `failed_gates` come from the hard gates and are the **only** thing
    allowed to eliminate an option.

    `resolution_burden` and `burden` describe what a feasible pair would cost to detail.
    They are a description, not a ranking, and no caller may filter on them.
    """

    stage: Literal['program_structure', 'structure_facade']
    left_id: str
    right_id: str
    feasibility: Feasibility
    failed_gates: list[str]
    resolution_burden: float = Field(ge=0.0, le=1.0)
    burden: InterfaceBurden
    axes: list[AxisResult]
    mitigations: list[str]


Admissibility = Literal[
    'admissible',                      # no blocking rule, jurisdiction resolved
    'admissible_pending_code_inputs',  # no blocking rule, but rules could not be evaluated
    'provisionally_excluded',          # blocked, but only by a placeholder table
    'excluded',                        # blocked by a resolved jurisdiction rule
]


class ProjectOption(BaseModel):
    """One (system, grammar) pair for a given program.

    Three independent statements, deliberately never merged into one number:

    - `admissibility` -- the building-code layer. A screen, not a score. It decides
      whether the option may lawfully exist and contributes nothing to any number.
    - `feasibility` -- the physical hard gates. Binary. Together with `admissibility`
      this is the **only** thing that eliminates an option.
    - `resolution_burden` / `burden` -- a description of how much detailing a feasible
      option would need. It ranks nothing. Selecting among feasible options is a
      separate set of criteria the project has not defined yet.
    """

    program_id: str
    system_id: str
    grammar_id: str
    feasibility: Feasibility
    failed_gates: list[str]
    resolution_burden: float = Field(ge=0.0, le=1.0)
    burden: InterfaceBurden
    admissibility: Admissibility
    program_structure: CouplingResult
    structure_facade: CouplingResult
    code_screen: CodeScreen
    blocking_rules: list[str]
    unevaluated_rules: list[str]
    mitigations: list[str]

    @property
    def admissible(self) -> bool:
        return self.admissibility.startswith('admissible')

    @property
    def survives(self) -> bool:
        return self.admissible and self.feasibility == 'feasible'


class FeasibleDomain(BaseModel):
    """The output of the whole chain: a domain, not a shortlist and not a ranking.

    `feasible` is every option that no hard standard rules out. It is returned in a
    stable identifier order, **not** sorted by burden, so that nothing about the
    presentation suggests a preference. Choosing inside this set is a later stage with
    its own criteria; this module deliberately provides none of them.

    `burden_profile` counts how the feasible set distributes across the descriptive
    burden bands. It is context for the designer, not a score to maximise.
    """

    program_id: str
    jurisdiction_id: str
    jurisdiction_resolved: bool
    feasible: list[ProjectOption]
    physically_infeasible: list[ProjectOption]
    provisionally_excluded: list[ProjectOption]
    excluded: list[ProjectOption]
    unevaluated_rules: list[str]

    @property
    def burden_profile(self) -> dict[str, int]:
        profile: dict[str, int] = {}
        for option in self.feasible:
            profile[option.burden] = profile.get(option.burden, 0) + 1
        return profile

    @property
    def feasible_systems(self) -> list[str]:
        seen: list[str] = []
        for option in self.feasible:
            if option.system_id not in seen:
                seen.append(option.system_id)
        return seen

    @property
    def feasible_grammars(self) -> list[str]:
        seen: list[str] = []
        for option in self.feasible:
            if option.grammar_id not in seen:
                seen.append(option.grammar_id)
        return seen

    def eliminated_because(self) -> dict[str, list[str]]:
        """Every removed option with the standard that removed it. The elimination log
        is the deliverable at this stage, not the surviving list."""
        out: dict[str, list[str]] = {}
        for option in (self.physically_infeasible + self.provisionally_excluded
                       + self.excluded):
            key = f'{option.system_id} x {option.grammar_id}'
            out[key] = sorted(set(option.failed_gates) | set(option.blocking_rules))
        return out


# Axis weights.
#
# Program -> structure: floor plates, storeys, and span carry the most, because those
# three are what make a system categorically right or wrong for a building type. Load is
# next because it is usually solvable by zoning rather than by changing system.
PROGRAM_AXIS_WEIGHTS: dict[str, float] = {
    'floor_plates': 0.22,
    'storey_count': 0.20,
    'clear_span': 0.20,
    'floor_load': 0.15,
    'acoustic_separation': 0.10,
    'construction_class': 0.08,
    'humidity_control': 0.05,
}

# Structure -> facade: deflection carries the largest share because stiffness mismatch is
# the most common and least intuitive failure. A designer checks weight and forgets that
# a structure strong enough to hold the panel can still move too much for its joints.
FACADE_AXIS_WEIGHTS: dict[str, float] = {
    'areal_mass': 0.20,
    'deflection': 0.25,
    'backup_type': 0.15,
    'panel_geometry': 0.15,
    'support_spacing': 0.10,
    'barrier_continuity': 0.10,
    'envelope_depth': 0.05,
}

# Descriptive bands for the burden, ascending. These name how much detailing work a
# feasible pair implies. They are NOT quality tiers and must never be used to filter.
BURDEN_BANDS: tuple[tuple[float, InterfaceBurden], ...] = (
    (0.20, 'clean'),
    (0.40, 'minor_interfaces'),
    (0.60, 'significant_interfaces'),
    (1.01, 'many_interfaces'),
)


def _score(
    axes: list[AxisResult], weights: dict[str, float],
) -> tuple[Feasibility, float, InterfaceBurden]:
    """Hard gates decide feasibility. The soft axes only describe the residue.

    The soft aggregate is a weighted **geometric** mean, not arithmetic, so one very bad
    axis is visible rather than averaged away by six comfortable ones. It is reported as
    a burden (0 = nothing left to resolve) precisely so it does not read as a score.
    """
    if any(a.hard_gate and not a.passed_gate for a in axes):
        return 'infeasible', 1.0, 'not_applicable'
    log_sum = sum(a.weight * math.log(max(a.score, _SCORE_FLOOR)) for a in axes)
    burden = round(1.0 - math.exp(log_sum / sum(weights.values())), 4)
    return 'feasible', burden, next(b for t, b in BURDEN_BANDS if burden < t)


# ---------------------------------------------------------------------------
# Gate 1 axes: program -> structure
# ---------------------------------------------------------------------------

def _p_floor_plates(p: ProgramDemand, s: StructuralSupply) -> AxisResult:
    """Hard gate, and the sharpest rule in the chain.

    Tensile and shell systems do not make occupied floors. They cover a volume. A
    multi-storey building on one of them is really two systems, and saying so is the
    honest answer rather than pretending the roof is the building."""
    ok = s.provides_occupied_floor_plates or not p.requires_occupied_floor_plates
    return AxisResult(
        axis='floor_plates', score=1.0 if ok else 0.0,
        weight=PROGRAM_AXIS_WEIGHTS['floor_plates'], hard_gate=True, passed_gate=ok,
        detail=(f'program needs occupied floor plates: {p.requires_occupied_floor_plates}; '
                f'system provides them: {s.provides_occupied_floor_plates}'),
        mitigation=None if ok else (
            f'{s.qualified_name} is a covering system, not a floor system. Pair it with a '
            f'frame system that carries the floors and declare the hybrid explicitly, or '
            f'reduce the program to a single covered volume.'),
    )


def _p_storey_count(p: ProgramDemand, s: StructuralSupply) -> AxisResult:
    """Hard gate. Height limits are material and code facts, not preferences."""
    ratio = p.storey_count / s.max_storeys
    if ratio <= 0.60:
        score = 1.0
    elif ratio <= 0.85:
        score = 0.80
    elif ratio <= 1.00:
        score = 0.60
    else:
        score = 0.0
    passed = ratio <= 1.0 and p.building_height_m <= s.max_height_m
    mitigation = None
    if not passed:
        mitigation = (
            f'{s.qualified_name} is credible to about {s.max_storeys} storeys / '
            f'{s.max_height_m:.0f} m; this program is {p.storey_count} storeys / '
            f'{p.building_height_m:.0f} m. Reduce storeys, or declare a hybrid with a '
            f'taller-capable system carrying the upper levels.')
    elif score < 1.0:
        mitigation = ('near the practical height limit for this material; expect the '
                      'lateral system and fire strategy to govern the design')
    return AxisResult(
        axis='storey_count', score=score, weight=PROGRAM_AXIS_WEIGHTS['storey_count'],
        hard_gate=True, passed_gate=passed,
        detail=(f'{p.storey_count} storeys / {p.building_height_m:.0f} m against a limit '
                f'of {s.max_storeys} storeys / {s.max_height_m:.0f} m'),
        mitigation=mitigation,
    )


def _p_clear_span(p: ProgramDemand, s: StructuralSupply) -> AxisResult:
    """Hard gate, with the long-span subtype route the guides already require."""
    need = p.max_clear_span_m
    if need <= s.clear_span_ordinary_m:
        score, mitigation = 1.0, None
    elif need <= s.clear_span_longspan_subtype_m:
        score = 0.70
        mitigation = (f'{p.governing_span_space} at {need:.0f} m exceeds the ordinary '
                      f'{s.clear_span_ordinary_m:.0f} m; declare a long-span subtype '
                      f'(truss, girder, transfer) rather than deepening a normal member')
    else:
        score = 0.0
        mitigation = (f'{p.governing_span_space} needs {need:.0f} m; this system reaches '
                      f'{s.clear_span_longspan_subtype_m:.0f} m even with a long-span '
                      f'subtype. Change system for that volume or change the program.')
    return AxisResult(
        axis='clear_span', score=score, weight=PROGRAM_AXIS_WEIGHTS['clear_span'],
        hard_gate=True, passed_gate=score > 0.0,
        detail=(f'{p.governing_span_space} needs {need:.0f} m; ordinary '
                f'{s.clear_span_ordinary_m:.0f} m, long-span '
                f'{s.clear_span_longspan_subtype_m:.0f} m'),
        mitigation=mitigation,
    )


def _p_floor_load(p: ProgramDemand, s: StructuralSupply) -> AxisResult:
    """Hard gate. Usually solvable by zoning the heavy program rather than by changing
    system, so the mitigation says that explicitly."""
    if s.floor_load_capacity_kpa <= 0.0:
        return AxisResult(
            axis='floor_load', score=0.0, weight=PROGRAM_AXIS_WEIGHTS['floor_load'],
            hard_gate=True, passed_gate=False,
            detail='the system carries no floor live load (covering system)',
            mitigation='floors must come from a paired frame system',
        )
    ratio = p.peak_floor_live_load_kpa / s.floor_load_capacity_kpa
    if ratio <= 0.70:
        score, mitigation = 1.0, None
    elif ratio <= 1.00:
        score = 0.65
        mitigation = (f'{p.governing_load_space} at {p.peak_floor_live_load_kpa:.1f} kPa '
                      f'uses most of the capacity; zone it onto a strengthened bay')
    elif ratio <= 1.60:
        score = 0.30
        mitigation = (f'{p.governing_load_space} at {p.peak_floor_live_load_kpa:.1f} kPa '
                      f'exceeds {s.floor_load_capacity_kpa:.1f} kPa; relocate it to grade, '
                      f'or declare a local hybrid (steel or concrete) for that zone')
    else:
        score = 0.0
        mitigation = (f'{p.governing_load_space} at {p.peak_floor_live_load_kpa:.1f} kPa '
                      f'is far beyond {s.floor_load_capacity_kpa:.1f} kPa; this system '
                      f'cannot carry the governing program')
    return AxisResult(
        axis='floor_load', score=score, weight=PROGRAM_AXIS_WEIGHTS['floor_load'],
        hard_gate=True, passed_gate=score > 0.0,
        detail=(f'{p.governing_load_space} needs {p.peak_floor_live_load_kpa:.1f} kPa; '
                f'system carries {s.floor_load_capacity_kpa:.1f} kPa (ratio {ratio:.2f})'),
        mitigation=mitigation,
    )


def _p_acoustic(p: ProgramDemand, s: StructuralSupply) -> AxisResult:
    gap = _CONTINUITY_RANK[p.acoustic_separation_required] - \
        _CONTINUITY_RANK[s.acoustic_separation_support]
    if gap <= 0:
        score, mitigation = 1.0, None
    elif gap == 1:
        score, mitigation = 0.55, ('add mass: concrete topping, a floating floor, or a '
                                   'separate isolated inner box for the critical volume')
    else:
        score, mitigation = 0.20, ('a fully isolated box-in-box is required; the '
                                   'structural system contributes no separation')
    return AxisResult(
        axis='acoustic_separation', score=score,
        weight=PROGRAM_AXIS_WEIGHTS['acoustic_separation'], hard_gate=False,
        passed_gate=True,
        detail=(f'program needs {p.acoustic_separation_required} separation, system '
                f'provides {s.acoustic_separation_support}'),
        mitigation=mitigation,
    )


def _p_construction_class(p: ProgramDemand, s: StructuralSupply) -> AxisResult:
    gap = _CONSTRUCTION_RANK[p.min_construction_class] - \
        _CONSTRUCTION_RANK[s.construction_class]
    if gap <= 0:
        score, mitigation = 1.0, None
    elif gap == 1:
        score, mitigation = 0.50, ('encapsulation or a sprinklered alternative path must '
                                   'be declared; it usually forbids exposing the material')
    else:
        score, mitigation = 0.15, ('the occupancy and height demand a construction class '
                                   'this material cannot reach')
    return AxisResult(
        axis='construction_class', score=score,
        weight=PROGRAM_AXIS_WEIGHTS['construction_class'], hard_gate=False,
        passed_gate=True,
        detail=(f'program needs at least {p.min_construction_class}, system is '
                f'{s.construction_class}'),
        mitigation=mitigation,
    )


def _p_humidity(p: ProgramDemand, s: StructuralSupply) -> AxisResult:
    gap = _CONTINUITY_RANK[p.humidity_control_required] - \
        _CONTINUITY_RANK[s.humidity_tolerance]
    if gap <= 0:
        score, mitigation = 1.0, None
    elif gap == 1:
        score, mitigation = 0.55, ('the collection zone needs a separated, vapour-'
                                   'controlled enclosure inside the structure')
    else:
        score, mitigation = 0.25, ('the material cannot sit inside the required humidity '
                                   'regime; separate it from the collection entirely')
    return AxisResult(
        axis='humidity_control', score=score,
        weight=PROGRAM_AXIS_WEIGHTS['humidity_control'], hard_gate=False,
        passed_gate=True,
        detail=(f'program needs {p.humidity_control_required} humidity control, system '
                f'tolerates {s.humidity_tolerance}'),
        mitigation=mitigation,
    )


_PROGRAM_AXES = (
    _p_floor_plates, _p_storey_count, _p_clear_span, _p_floor_load,
    _p_acoustic, _p_construction_class, _p_humidity,
)


# ---------------------------------------------------------------------------
# Gate 2 axes: structure -> facade
# ---------------------------------------------------------------------------

def _f_areal_mass(d: FacadeDemand, s: StructuralSupply) -> AxisResult:
    """Two-tier, like the code opening-area rule.

    The **hard gate** is the grammar's lightest legal palette: if even that cannot be
    carried, the pair is impossible. The **score** is driven by the heaviest palette,
    because a grammar restricted to the light end of its own material range has given
    something up, and the report should say so rather than pass silently.
    """
    low, high = d.areal_mass_kg_m2
    capacity = s.envelope_mass_capacity_kg_m2
    if low > capacity * 1.30:
        return AxisResult(
            axis='areal_mass', score=0.0, weight=FACADE_AXIS_WEIGHTS['areal_mass'],
            hard_gate=True, passed_gate=False,
            detail=(f'even the lightest palette in this grammar is {low:.0f} kg/m2 '
                    f'against a capacity of {capacity:.0f} kg/m2 '
                    f'(ratio {low / capacity:.2f})'),
            mitigation=('no material in this grammar can be carried; add a secondary '
                        'load-bearing backup wall that the grammar must then express, '
                        'or change grammar'))

    ratio = high / capacity
    if ratio <= 0.60:
        score, mitigation = 1.0, None
    elif ratio <= 0.85:
        score, mitigation = 0.75, 'stay in the lower half of the grammar palette'
    elif ratio <= 1.00:
        score, mitigation = 0.50, 'the heavy end of the palette sits at the capacity limit'
    elif ratio <= 1.60:
        score = 0.30
        mitigation = (f'only the light end of the palette is available: cap the cladding '
                      f'near {capacity:.0f} kg/m2 rather than the grammar maximum of '
                      f'{high:.0f} kg/m2')
    else:
        score = 0.15
        mitigation = (f'the grammar is restricted to its lightest materials '
                      f'(<= {capacity:.0f} kg/m2 against a range top of {high:.0f}); '
                      f'confirm the grammar still reads at that weight')
    return AxisResult(
        axis='areal_mass', score=score, weight=FACADE_AXIS_WEIGHTS['areal_mass'],
        hard_gate=True, passed_gate=True,
        detail=(f'grammar palette {low:.0f}-{high:.0f} kg/m2 against a capacity of '
                f'{capacity:.0f} kg/m2'),
        mitigation=mitigation,
    )


def _f_deflection(d: FacadeDemand, s: StructuralSupply) -> AxisResult:
    """Hard gate. The axis most often missed: strength is not stiffness."""
    ratio = s.deflection_at_envelope_ratio / d.deflection_limit_ratio
    if ratio >= 1.0:
        score = 1.0
    elif ratio >= 0.75:
        score = 0.70
    elif ratio >= 0.55:
        score = 0.40
    elif ratio >= 0.35:
        score = 0.15
    else:
        score = 0.0
    # A backup that moves nearly three times more than the envelope tolerates cannot be
    # detailed out; below this ratio the pair is not buildable, not merely awkward.
    passed = ratio >= 0.35
    mitigation = None
    if not passed:
        mitigation = (f'the structure moves at L/{s.deflection_at_envelope_ratio} but the '
                      f'envelope needs L/{d.deflection_limit_ratio}; re-detail for '
                      f'movement (open joints, gasketed laps, articulated brackets, '
                      f'sliding heads) or select a stiffer structural system')
    elif score < 1.0:
        mitigation = ('movement joints and bracket articulation must be designed '
                      'explicitly at every support')
    return AxisResult(
        axis='deflection', score=score, weight=FACADE_AXIS_WEIGHTS['deflection'],
        hard_gate=True, passed_gate=passed,
        detail=(f'structure delivers L/{s.deflection_at_envelope_ratio}, envelope requires '
                f'L/{d.deflection_limit_ratio} (ratio {ratio:.2f})'),
        mitigation=mitigation,
    )


def _f_backup_type(d: FacadeDemand, s: StructuralSupply) -> AxisResult:
    """Hard gate only when the structure offers nothing but a moving edge."""
    shared = sorted(set(d.accepted_backup_types) & set(s.offered_backup_types))
    if shared:
        return AxisResult(
            axis='backup_type', score=1.0, weight=FACADE_AXIS_WEIGHTS['backup_type'],
            hard_gate=True, passed_gate=True,
            detail=f'shared backup type: {", ".join(shared)}')
    rigid_offer = [t for t in s.offered_backup_types if t != 'flexible_edge']
    if not rigid_offer:
        return AxisResult(
            axis='backup_type', score=0.0, weight=FACADE_AXIS_WEIGHTS['backup_type'],
            hard_gate=True, passed_gate=False,
            detail=('the structure offers only a flexible edge; this grammar accepts '
                    f'{", ".join(d.accepted_backup_types)}'),
            mitigation=('the envelope must become the structure (a form-found surface) or '
                        'a separate rigid backup system must be declared'))
    return AxisResult(
        axis='backup_type', score=0.40, weight=FACADE_AXIS_WEIGHTS['backup_type'],
        hard_gate=True, passed_gate=True,
        detail=(f'no shared backup type; structure offers {", ".join(rigid_offer)}, '
                f'grammar accepts {", ".join(d.accepted_backup_types)}'),
        mitigation='insert a secondary subframe; the grammar must own its expression')


def _f_panel_geometry(d: FacadeDemand, s: StructuralSupply) -> AxisResult:
    table: dict[tuple[PanelGeometry, SurfaceClass], tuple[float, str | None]] = {
        ('planar_required', 'planar'): (1.0, None),
        ('planar_required', 'single_curved'): (0.70, 'facet the host along one direction'),
        ('planar_required', 'double_curved'): (
            0.35, 'planarise the host mesh, or adopt cold-bent or cushion cladding'),
        ('single_curved_ok', 'planar'): (1.0, None),
        ('single_curved_ok', 'single_curved'): (1.0, None),
        ('single_curved_ok', 'double_curved'): (
            0.60, 'segment the host into single-curvature strips'),
        ('double_curved_ok', 'planar'): (0.85, 'the grammar loses its native geometry'),
        ('double_curved_ok', 'single_curved'): (1.0, None),
        ('double_curved_ok', 'double_curved'): (1.0, None),
    }
    if d.panel_geometry == 'not_applicable':
        score, mitigation = 1.0, None
    else:
        score, mitigation = table[(d.panel_geometry, s.host_surface)]
    return AxisResult(
        axis='panel_geometry', score=score, weight=FACADE_AXIS_WEIGHTS['panel_geometry'],
        hard_gate=False, passed_gate=True,
        detail=f'{d.panel_geometry} panels on a {s.host_surface} host surface',
        mitigation=mitigation)


def _f_support_spacing(d: FacadeDemand, s: StructuralSupply) -> AxisResult:
    tightest = s.hardpoint_spacing_m[0]
    if tightest <= d.support_spacing_max_m:
        score, mitigation = 1.0, None
    elif tightest <= d.support_spacing_max_m * 1.5:
        score, mitigation = 0.60, 'a secondary subframe spans between structural hardpoints'
    elif tightest <= d.support_spacing_max_m * 2.5:
        score, mitigation = 0.35, 'a full secondary structure carries the envelope module'
    else:
        score, mitigation = 0.15, 'the envelope must span as a self-supporting system'
    return AxisResult(
        axis='support_spacing', score=score, weight=FACADE_AXIS_WEIGHTS['support_spacing'],
        hard_gate=False, passed_gate=True,
        detail=(f'closest structural hardpoint spacing {tightest:.2f} m against an envelope '
                f'maximum of {d.support_spacing_max_m:.2f} m'),
        mitigation=mitigation)


def _f_barrier_continuity(d: FacadeDemand, s: StructuralSupply) -> AxisResult:
    gap = _CONTINUITY_RANK[d.barrier_continuity_required] - \
        _CONTINUITY_RANK[s.barrier_continuity_support]
    if gap <= 0:
        score, mitigation = 1.0, None
    elif gap == 1:
        score, mitigation = 0.50, ('a separate liner carries the air, water, and thermal '
                                   'barrier behind the expressed envelope')
    else:
        score, mitigation = 0.20, ('a complete second envelope is required; the expressed '
                                   'layer becomes a rainscreen or a canopy only')
    return AxisResult(
        axis='barrier_continuity', score=score,
        weight=FACADE_AXIS_WEIGHTS['barrier_continuity'], hard_gate=False, passed_gate=True,
        detail=(f'envelope needs {d.barrier_continuity_required} barrier continuity, '
                f'structure supports {s.barrier_continuity_support}'),
        mitigation=mitigation)


def _f_envelope_depth(d: FacadeDemand, s: StructuralSupply) -> AxisResult:
    need_lo, need_hi = d.depth_zone_m
    have_lo, have_hi = s.envelope_depth_available_m
    overlap = min(need_hi, have_hi) - max(need_lo, have_lo)
    if overlap >= 0:
        span = max(need_hi - need_lo, 1e-6)
        score = min(1.0, 0.6 + 0.4 * (overlap / span))
        mitigation = None if score >= 0.95 else 'the grammar works at the shallow end only'
    else:
        score = 0.30
        mitigation = (f'the grammar wants {need_lo:.2f}-{need_hi:.2f} m of facade zone but '
                      f'the structure offers {have_lo:.2f}-{have_hi:.2f} m; cantilever a '
                      f'support zone or reduce the expressed depth')
    return AxisResult(
        axis='envelope_depth', score=score, weight=FACADE_AXIS_WEIGHTS['envelope_depth'],
        hard_gate=False, passed_gate=True,
        detail=(f'envelope zone {need_lo:.2f}-{need_hi:.2f} m against available '
                f'{have_lo:.2f}-{have_hi:.2f} m'),
        mitigation=mitigation)


_FACADE_AXES = (
    _f_areal_mass, _f_deflection, _f_backup_type, _f_panel_geometry,
    _f_support_spacing, _f_barrier_continuity, _f_envelope_depth,
)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_program_structure(p: ProgramDemand, s: StructuralSupply) -> CouplingResult:
    axes = [rule(p, s) for rule in _PROGRAM_AXES]
    feasibility, burden_value, burden = _score(axes, PROGRAM_AXIS_WEIGHTS)
    return CouplingResult(
        stage='program_structure', left_id=p.program_id, right_id=s.system_id,
        feasibility=feasibility, resolution_burden=burden_value, burden=burden,
        failed_gates=[a.axis for a in axes if a.hard_gate and not a.passed_gate],
        axes=axes, mitigations=[a.mitigation for a in axes if a.mitigation])


def evaluate_structure_facade(d: FacadeDemand, s: StructuralSupply) -> CouplingResult:
    axes = [rule(d, s) for rule in _FACADE_AXES]
    feasibility, burden_value, burden = _score(axes, FACADE_AXIS_WEIGHTS)
    return CouplingResult(
        stage='structure_facade', left_id=s.system_id, right_id=d.grammar_id,
        feasibility=feasibility, resolution_burden=burden_value, burden=burden,
        failed_gates=[a.axis for a in axes if a.hard_gate and not a.passed_gate],
        axes=axes, mitigations=[a.mitigation for a in axes if a.mitigation])


def run_code_screen(
    program: ProgramDemand, supply: StructuralSupply,
    demand: FacadeDemand | None = None,
    jurisdiction: JurisdictionProfile = UNRESOLVED_JURISDICTION,
) -> CodeScreen:
    """Building-code gates. Separate from the physical axes on purpose.

    A physical axis says "this is hard to build". A code gate says "this may not be
    built". Averaging the two into one number would let a comfortable physical score
    hide an unlawful design, so a code failure is absolute and is never weighted.
    """
    results = [
        gate_construction_type(
            program.occupancy_group, program.storey_count, program.building_height_m,
            supply.system_id, jurisdiction),
        gate_frame_fire_rating(
            supply.system_id, program.exposed_structure_intended, jurisdiction),
        gate_seismic_system(supply.system_id, program.building_height_m, jurisdiction),
    ]
    if demand is not None:
        for orientation in ('north', 'south', 'east', 'west'):
            results.append(gate_exterior_opening_area(
                demand.opening_ratio, orientation, jurisdiction))
        results.append(gate_combustible_cladding(
            supply.system_id, program.building_height_m, demand.combustible_cladding,
            jurisdiction))
    return CodeScreen(
        program_id=program.program_id, system_id=supply.system_id,
        grammar_id=demand.grammar_id if demand else None,
        jurisdiction_id=jurisdiction.id, results=results)


def _classify(codes: CodeScreen, jurisdiction: JurisdictionProfile) -> Admissibility:
    """The code layer screens; it does not score and it does not choose.

    A blocking rule evaluated against a placeholder table produces
    `provisionally_excluded`, never `excluded`. Removing a design option on unverified
    code data would be a real architectural decision taken on data the project has not
    yet sourced, so the state is kept separate and stays visible in every report until a
    resolved jurisdiction confirms or clears it.
    """
    blocking = [r for r in codes.results if r.blocking]
    if blocking:
        provisional = any(r.provenance == 'placeholder' for r in blocking)
        return 'provisionally_excluded' if provisional else 'excluded'
    return 'admissible' if jurisdiction.resolved else 'admissible_pending_code_inputs'


def screen_project(
    program: ProgramDemand, *,
    jurisdiction: JurisdictionProfile = UNRESOLVED_JURISDICTION,
) -> FeasibleDomain:
    """Eliminate on hard standards only. Return the domain, ranked by nothing.

    Two independent screens run on every (system, grammar) pair, and **only these two**
    may remove an option:

        1. physical hard gates   floor plates, storeys, span, floor load,
                                 areal mass, deflection, backup type
        2. building-code gates   construction type, frame rating, opening area,
                                 combustible cladding, seismic system

    The soft axes are computed but have **no elimination power**. A pile of small
    penalties can never remove a physically possible and lawful option; it can only
    describe how much detailing that option would need. That distinction is the whole
    point of this stage: the job here is to rule out what is absolutely impossible, and
    choosing among what remains is a later question with its own criteria.

    The returned lists are in stable identifier order rather than sorted by burden, so
    that the presentation itself carries no preference.
    """
    buckets: dict[str, list[ProjectOption]] = {
        'feasible': [], 'physically_infeasible': [],
        'provisionally_excluded': [], 'excluded': []}
    unevaluated: set[str] = set()

    for supply in STRUCTURAL_SUPPLIES:
        gate1 = evaluate_program_structure(program, supply)
        for demand in FACADE_DEMANDS:
            gate2 = evaluate_structure_facade(demand, supply)
            codes = run_code_screen(program, supply, demand, jurisdiction)
            admissibility = _classify(codes, jurisdiction)
            unevaluated.update(codes.incomplete)

            failed = gate1.failed_gates + gate2.failed_gates
            feasibility: Feasibility = 'infeasible' if failed else 'feasible'
            burden_value = round(
                1.0 - (1.0 - gate1.resolution_burden) * (1.0 - gate2.resolution_burden), 4
            ) if feasibility == 'feasible' else 1.0
            burden = (next(b for t, b in BURDEN_BANDS if burden_value < t)
                      if feasibility == 'feasible' else 'not_applicable')

            option = ProjectOption(
                program_id=program.program_id, system_id=supply.system_id,
                grammar_id=demand.grammar_id, feasibility=feasibility,
                failed_gates=failed, resolution_burden=burden_value, burden=burden,
                admissibility=admissibility, program_structure=gate1,
                structure_facade=gate2, code_screen=codes,
                blocking_rules=[r.rule_id for r in codes.results if r.blocking],
                unevaluated_rules=codes.incomplete,
                mitigations=sorted(
                    set(gate1.mitigations) | set(gate2.mitigations)
                    | {r.mitigation for r in codes.results if r.mitigation}))

            if not option.admissible:
                buckets[admissibility].append(option)
            elif feasibility == 'infeasible':
                buckets['physically_infeasible'].append(option)
            else:
                buckets['feasible'].append(option)

    key = lambda o: (o.system_id, o.grammar_id)
    return FeasibleDomain(
        program_id=program.program_id, jurisdiction_id=jurisdiction.id,
        jurisdiction_resolved=jurisdiction.resolved,
        feasible=sorted(buckets['feasible'], key=key),
        physically_infeasible=sorted(buckets['physically_infeasible'], key=key),
        provisionally_excluded=sorted(buckets['provisionally_excluded'], key=key),
        excluded=sorted(buckets['excluded'], key=key),
        unevaluated_rules=sorted(unevaluated))


def program_by_id(program_id: str) -> ProgramDemand:
    for program in PROGRAM_DEMANDS:
        if program.program_id == program_id:
            return program
    raise KeyError(f'unknown program: {program_id}')


def supply_by_id(system_id: str) -> StructuralSupply:
    for supply in STRUCTURAL_SUPPLIES:
        if supply.system_id == system_id:
            return supply
    raise KeyError(f'unknown structural system: {system_id}')


def demand_by_id(grammar_id: str) -> FacadeDemand:
    for demand in FACADE_DEMANDS:
        if demand.grammar_id == grammar_id:
            return demand
    raise KeyError(f'unknown facade grammar: {grammar_id}')


# ---------------------------------------------------------------------------
# Registry: program demands (docs/decisions/0001, program constitution guideline)
# Live loads are ASCE/SEI 7 occupancy values, converted to kPa.
# ---------------------------------------------------------------------------

PROGRAM_DEMANDS: list[ProgramDemand] = [
    ProgramDemand(
        program_id='PRG-LIBRARY-MID-RISE',
        typology='library',
        source_ref='docs/decisions/0001-primary-typology-shortlist.md',
        storey_count=6,
        building_height_m=26.0,
        max_clear_span_m=18.0,
        governing_span_space='main reading room',
        peak_floor_live_load_kpa=7.2,          # ASCE 7 library stack rooms, 150 psf
        governing_load_space='open stacks',
        acoustic_separation_required='partial',
        humidity_control_required='partial',
        min_construction_class='heavy_timber',
    ),
    ProgramDemand(
        program_id='PRG-THEATER-MID-RISE',
        typology='theater',
        source_ref='docs/decisions/0001-primary-typology-shortlist.md',
        storey_count=4,
        building_height_m=28.0,
        max_clear_span_m=30.0,
        governing_span_space='auditorium',
        peak_floor_live_load_kpa=7.2,          # ASCE 7 stages, 150 psf
        governing_load_space='stage',
        acoustic_separation_required='full',
        humidity_control_required='none',
        min_construction_class='noncombustible',
    ),
    ProgramDemand(
        program_id='PRG-MUSEUM-MID-RISE',
        typology='museum',
        source_ref='docs/decisions/0001-primary-typology-shortlist.md',
        storey_count=4,
        building_height_m=22.0,
        max_clear_span_m=20.0,
        governing_span_space='principal gallery',
        peak_floor_live_load_kpa=4.8,          # ASCE 7 assembly, movable seats, 100 psf
        governing_load_space='gallery and art handling',
        acoustic_separation_required='partial',
        humidity_control_required='full',
        min_construction_class='noncombustible',
    ),
    ProgramDemand(
        program_id='PRG-PAVILION-SINGLE-VOLUME',
        typology='museum',
        source_ref='docs/guidelines/program_constitution_guideline.md',
        storey_count=1,
        building_height_m=12.0,
        requires_occupied_floor_plates=False,
        max_clear_span_m=40.0,
        governing_span_space='covered single volume',
        peak_floor_live_load_kpa=4.8,
        governing_load_space='public floor at grade',
        acoustic_separation_required='none',
        humidity_control_required='none',
        min_construction_class='combustible',
    ),
]


# ---------------------------------------------------------------------------
# Registry: structural systems (docs/guidelines/structural_systems/)
# ---------------------------------------------------------------------------

_S = 'docs/guidelines/structural_systems'

STRUCTURAL_SUPPLIES: list[StructuralSupply] = [
    StructuralSupply(
        system_id='STR-SYS-STEEL-FRAME',
        qualified_name='Structural steel frame',
        tectonic_family='frame',
        source_ref=f'{_S}/01_steel_frame.md',
        provides_occupied_floor_plates=True,
        max_storeys=60, max_height_m=250.0,
        clear_span_ordinary_m=12.0, clear_span_longspan_subtype_m=60.0,
        floor_load_capacity_kpa=12.0,
        acoustic_separation_support='partial',
        humidity_tolerance='full',
        construction_class='noncombustible',
        envelope_mass_capacity_kg_m2=600.0,
        offered_backup_types=['continuous_line', 'point_grid'],
        hardpoint_spacing_m=(1.5, 3.0),
        deflection_at_envelope_ratio=360,
        host_surface='planar',
        envelope_depth_available_m=(0.20, 2.40),
        barrier_continuity_support='full',
    ),
    StructuralSupply(
        system_id='STR-SYS-RC-FRAME-WALL',
        qualified_name='Reinforced concrete frame and wall',
        tectonic_family='frame',
        source_ref=f'{_S}/02_reinforced_concrete_frame_wall.md',
        provides_occupied_floor_plates=True,
        max_storeys=60, max_height_m=250.0,
        clear_span_ordinary_m=9.0, clear_span_longspan_subtype_m=20.0,
        floor_load_capacity_kpa=15.0,
        acoustic_separation_support='full',
        humidity_tolerance='full',
        construction_class='noncombustible',
        envelope_mass_capacity_kg_m2=900.0,
        offered_backup_types=['continuous_line', 'bearing_wall', 'point_grid'],
        hardpoint_spacing_m=(0.3, 1.0),
        deflection_at_envelope_ratio=480,
        host_surface='planar',
        envelope_depth_available_m=(0.10, 1.00),
        barrier_continuity_support='full',
    ),
    StructuralSupply(
        system_id='STR-SYS-MASS-TIMBER-CLT-GLULAM',
        qualified_name='Mass timber: CLT on glulam',
        tectonic_family='frame',
        source_ref=f'{_S}/03_mass_timber_clt_glulam.md',
        provides_occupied_floor_plates=True,
        max_storeys=18, max_height_m=85.0,     # Brock Commons / Mjostarnet order
        clear_span_ordinary_m=8.0, clear_span_longspan_subtype_m=25.0,
        floor_load_capacity_kpa=5.0,
        acoustic_separation_support='partial',
        humidity_tolerance='partial',
        construction_class='heavy_timber',
        envelope_mass_capacity_kg_m2=320.0,
        offered_backup_types=['continuous_line', 'bearing_wall'],
        hardpoint_spacing_m=(2.4, 3.0),
        deflection_at_envelope_ratio=300,
        host_surface='planar',
        envelope_depth_available_m=(0.15, 0.80),
        barrier_continuity_support='full',
    ),
    StructuralSupply(
        system_id='STR-SYS-GLULAM-POST-BEAM',
        qualified_name='Glulam post-and-beam',
        tectonic_family='frame',
        source_ref=f'{_S}/04_glulam_post_and_beam.md',
        provides_occupied_floor_plates=True,
        max_storeys=6, max_height_m=24.0,
        clear_span_ordinary_m=7.2, clear_span_longspan_subtype_m=25.0,
        floor_load_capacity_kpa=5.0,
        acoustic_separation_support='none',
        humidity_tolerance='partial',
        construction_class='heavy_timber',
        envelope_mass_capacity_kg_m2=260.0,
        offered_backup_types=['point_grid', 'continuous_line'],
        hardpoint_spacing_m=(3.6, 7.2),
        deflection_at_envelope_ratio=300,
        host_surface='planar',
        envelope_depth_available_m=(0.15, 0.60),
        barrier_continuity_support='full',
    ),
    StructuralSupply(
        system_id='STR-SYS-LIGHT-WOOD-FRAME',
        qualified_name='Light wood frame',
        tectonic_family='frame',
        source_ref=f'{_S}/05_light_wood_frame.md',
        provides_occupied_floor_plates=True,
        max_storeys=5, max_height_m=18.0,
        clear_span_ordinary_m=6.0, clear_span_longspan_subtype_m=9.0,
        floor_load_capacity_kpa=2.9,
        acoustic_separation_support='none',
        humidity_tolerance='partial',
        construction_class='combustible',
        envelope_mass_capacity_kg_m2=240.0,
        offered_backup_types=['bearing_wall', 'continuous_line'],
        hardpoint_spacing_m=(0.4, 0.6),
        deflection_at_envelope_ratio=360,
        host_surface='planar',
        envelope_depth_available_m=(0.05, 0.35),
        barrier_continuity_support='full',
    ),
    StructuralSupply(
        system_id='STR-SYS-TENSILE-MEMBRANE',
        qualified_name='Tensile membrane',
        tectonic_family='tensile',
        source_ref=f'{_S}/06_tensile_membrane.md',
        provides_occupied_floor_plates=False,
        max_storeys=1, max_height_m=40.0,
        clear_span_ordinary_m=45.0, clear_span_longspan_subtype_m=120.0,
        floor_load_capacity_kpa=0.0,
        acoustic_separation_support='none',
        humidity_tolerance='full',
        construction_class='combustible',
        envelope_mass_capacity_kg_m2=5.0,
        offered_backup_types=['flexible_edge'],
        hardpoint_spacing_m=(6.0, 20.0),
        deflection_at_envelope_ratio=50,
        host_surface='double_curved',
        envelope_depth_available_m=(0.00, 0.15),
        barrier_continuity_support='none',
    ),
    StructuralSupply(
        system_id='STR-SYS-CABLE-NET-HYBRID',
        qualified_name='Cable net and cable-supported hybrid',
        tectonic_family='tensile',
        source_ref=f'{_S}/07_cable_net_hybrid.md',
        provides_occupied_floor_plates=False,
        max_storeys=1, max_height_m=60.0,
        clear_span_ordinary_m=60.0, clear_span_longspan_subtype_m=150.0,
        floor_load_capacity_kpa=0.0,
        acoustic_separation_support='none',
        humidity_tolerance='full',
        construction_class='noncombustible',
        envelope_mass_capacity_kg_m2=60.0,
        offered_backup_types=['point_grid', 'flexible_edge'],
        hardpoint_spacing_m=(0.75, 3.0),
        deflection_at_envelope_ratio=150,
        host_surface='double_curved',
        envelope_depth_available_m=(0.05, 0.50),
        barrier_continuity_support='partial',
    ),
    StructuralSupply(
        system_id='STR-SYS-RC-SHELL',
        qualified_name='Reinforced concrete shell',
        tectonic_family='shell',
        source_ref=f'{_S}/08_reinforced_concrete_shell.md',
        provides_occupied_floor_plates=False,
        max_storeys=1, max_height_m=35.0,
        clear_span_ordinary_m=30.0, clear_span_longspan_subtype_m=45.0,
        floor_load_capacity_kpa=0.0,
        acoustic_separation_support='full',
        humidity_tolerance='full',
        construction_class='noncombustible',
        envelope_mass_capacity_kg_m2=400.0,
        offered_backup_types=['bearing_wall', 'continuous_line'],
        hardpoint_spacing_m=(0.3, 1.5),
        deflection_at_envelope_ratio=500,
        host_surface='double_curved',
        envelope_depth_available_m=(0.05, 0.35),
        barrier_continuity_support='full',
    ),
    StructuralSupply(
        system_id='STR-SYS-TIMBER-GRIDSHELL',
        qualified_name='Timber gridshell',
        tectonic_family='shell',
        source_ref=f'{_S}/09_timber_gridshell.md',
        provides_occupied_floor_plates=False,
        max_storeys=1, max_height_m=25.0,
        clear_span_ordinary_m=30.0, clear_span_longspan_subtype_m=60.0,
        floor_load_capacity_kpa=0.0,
        acoustic_separation_support='none',
        humidity_tolerance='partial',
        construction_class='heavy_timber',
        envelope_mass_capacity_kg_m2=80.0,
        offered_backup_types=['point_grid'],
        hardpoint_spacing_m=(0.5, 1.5),
        deflection_at_envelope_ratio=200,
        host_surface='double_curved',
        envelope_depth_available_m=(0.10, 0.40),
        barrier_continuity_support='partial',
    ),
    StructuralSupply(
        system_id='STR-SYS-STEEL-SPACE-FRAME-SHELL',
        qualified_name='Steel space frame and gridshell',
        tectonic_family='shell',
        source_ref=f'{_S}/10_steel_space_frame_shell.md',
        provides_occupied_floor_plates=False,
        max_storeys=1, max_height_m=50.0,
        clear_span_ordinary_m=45.0, clear_span_longspan_subtype_m=120.0,
        floor_load_capacity_kpa=0.0,
        acoustic_separation_support='none',
        humidity_tolerance='full',
        construction_class='noncombustible',
        envelope_mass_capacity_kg_m2=220.0,
        offered_backup_types=['point_grid', 'continuous_line'],
        hardpoint_spacing_m=(1.2, 4.0),
        deflection_at_envelope_ratio=250,
        host_surface='double_curved',
        envelope_depth_available_m=(0.20, 2.50),
        barrier_continuity_support='partial',
    ),
]


# ---------------------------------------------------------------------------
# Registry: facade grammars (docs/style_guides/facade/)
# ---------------------------------------------------------------------------

_G = 'docs/style_guides/facade'

FACADE_DEMANDS: list[FacadeDemand] = [
    FacadeDemand(
        grammar_id='FCD-01-INTERNATIONAL-STYLE',
        qualified_name='International Style-informed abstract facade grammar',
        source_ref=f'{_G}/01_international_style.md',
        areal_mass_kg_m2=(50.0, 90.0),
        accepted_backup_types=['continuous_line', 'point_grid'],
        support_spacing_max_m=1.8,
        deflection_limit_ratio=175,
        panel_geometry='planar_required',
        depth_zone_m=(0.15, 0.45),
        barrier_continuity_required='full',
        opening_ratio=(0.55, 0.9),
        combustible_cladding=False,
    ),
    FacadeDemand(
        grammar_id='FCD-02-BAUHAUS',
        qualified_name='Bauhaus-informed functional modular grammar',
        source_ref=f'{_G}/02_bauhaus.md',
        areal_mass_kg_m2=(60.0, 200.0),
        accepted_backup_types=['continuous_line', 'bearing_wall', 'point_grid'],
        support_spacing_max_m=2.4,
        deflection_limit_ratio=240,
        panel_geometry='planar_required',
        depth_zone_m=(0.15, 0.60),
        barrier_continuity_required='full',
        opening_ratio=(0.35, 0.65),
        combustible_cladding=False,
    ),
    FacadeDemand(
        grammar_id='FCD-03-BRUTALISM',
        qualified_name='Brutalism-informed mass-and-assembly grammar',
        source_ref=f'{_G}/03_brutalism.md',
        areal_mass_kg_m2=(280.0, 500.0),
        accepted_backup_types=['bearing_wall', 'continuous_line'],
        support_spacing_max_m=3.0,
        deflection_limit_ratio=480,
        panel_geometry='planar_required',
        depth_zone_m=(0.35, 1.80),
        barrier_continuity_required='full',
        opening_ratio=(0.1, 0.45),
        combustible_cladding=False,
    ),
    FacadeDemand(
        grammar_id='FCD-04-ORGANIC',
        qualified_name='Organic Architecture-informed site-and-growth grammar',
        source_ref=f'{_G}/04_organic_architecture.md',
        areal_mass_kg_m2=(100.0, 350.0),
        accepted_backup_types=['bearing_wall', 'continuous_line', 'point_grid'],
        support_spacing_max_m=2.4,
        deflection_limit_ratio=360,
        panel_geometry='single_curved_ok',
        depth_zone_m=(0.20, 0.90),
        barrier_continuity_required='full',
        opening_ratio=(0.25, 0.55),
        combustible_cladding=True,
    ),
    FacadeDemand(
        grammar_id='FCD-05-HIGH-TECH',
        qualified_name='High-tech-informed legible assembly grammar',
        source_ref=f'{_G}/05_high_tech.md',
        areal_mass_kg_m2=(30.0, 90.0),
        accepted_backup_types=['point_grid', 'continuous_line', 'self_supporting'],
        support_spacing_max_m=4.0,
        deflection_limit_ratio=240,
        panel_geometry='planar_required',
        depth_zone_m=(0.60, 2.40),
        barrier_continuity_required='partial',
        opening_ratio=(0.45, 0.8),
        combustible_cladding=False,
    ),
    FacadeDemand(
        grammar_id='FCD-06-POSTMODERNISM',
        qualified_name='Postmodernism-informed communicative facade grammar',
        source_ref=f'{_G}/06_postmodernism.md',
        areal_mass_kg_m2=(150.0, 400.0),
        accepted_backup_types=['bearing_wall', 'continuous_line'],
        support_spacing_max_m=2.4,
        deflection_limit_ratio=480,
        panel_geometry='planar_required',
        depth_zone_m=(0.20, 0.90),
        barrier_continuity_required='full',
        opening_ratio=(0.25, 0.55),
        combustible_cladding=False,
    ),
    FacadeDemand(
        grammar_id='FCD-07-DECONSTRUCTIVISM',
        qualified_name='Deconstructivism-informed controlled-fragmentation grammar',
        source_ref=f'{_G}/07_deconstructivism.md',
        areal_mass_kg_m2=(40.0, 130.0),
        accepted_backup_types=['point_grid', 'continuous_line'],
        support_spacing_max_m=3.0,
        deflection_limit_ratio=240,
        panel_geometry='single_curved_ok',
        depth_zone_m=(0.40, 1.60),
        barrier_continuity_required='full',
        opening_ratio=(0.3, 0.65),
        combustible_cladding=True,
    ),
    FacadeDemand(
        grammar_id='FCD-08-MINIMALISM',
        qualified_name='Minimalism-informed reductive facade grammar',
        source_ref=f'{_G}/08_minimalism.md',
        areal_mass_kg_m2=(60.0, 260.0),
        accepted_backup_types=['continuous_line', 'bearing_wall'],
        support_spacing_max_m=1.8,
        deflection_limit_ratio=500,
        panel_geometry='planar_required',
        depth_zone_m=(0.10, 0.35),
        barrier_continuity_required='full',
        opening_ratio=(0.3, 0.7),
        combustible_cladding=False,
    ),
    FacadeDemand(
        grammar_id='FCD-09-CRITICAL-REGIONALISM',
        qualified_name='Critical Regionalism-informed place-responsive grammar',
        source_ref=f'{_G}/09_critical_regionalism.md',
        areal_mass_kg_m2=(150.0, 450.0),
        accepted_backup_types=['bearing_wall', 'continuous_line'],
        support_spacing_max_m=2.4,
        deflection_limit_ratio=480,
        panel_geometry='planar_required',
        depth_zone_m=(0.30, 1.00),
        barrier_continuity_required='full',
        opening_ratio=(0.2, 0.5),
        combustible_cladding=True,
    ),
    FacadeDemand(
        grammar_id='FCD-10-PARAMETRICISM',
        qualified_name='Parametricism-informed relational facade grammar',
        source_ref=f'{_G}/10_parametricism.md',
        areal_mass_kg_m2=(20.0, 150.0),
        accepted_backup_types=['point_grid', 'continuous_line', 'flexible_edge'],
        support_spacing_max_m=3.0,
        deflection_limit_ratio=240,
        panel_geometry='double_curved_ok',
        depth_zone_m=(0.20, 1.00),
        barrier_continuity_required='partial',
        opening_ratio=(0.35, 0.75),
        combustible_cladding=True,
    ),
]
