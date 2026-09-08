"""The program massing as the contract everything downstream builds from.

Decision 0022. A building here is a function of its volumes: the plates level by
level, the structural grid, the vertical cores, and the datums that size what stands
in them. On a music run those volumes are chosen from the score; in practice they
are just as often handed over -- a massing drawn in Rhino, a plate a client fixed, a
core position a stair consultant set. Either way the volumes are the input and no
downstream emitter invents its own: the slab is cut where the massing put the core,
the frame is planned around it, the stair is built inside it.

Two entry points:

- `compile_from_massing(massing)` builds the full model from a `ProgramMassing`
  alone. No audio, no score: a neutral score stands in so the datum table and the
  selection screens run, and the massing's own datum values override it.
- `program_massing_of(model)` writes the massing a compiled model was built on, so a
  music run's volumes can be saved, edited by hand, and fed back through the first
  entry point to the same building.

Nothing about the model differs between the two paths after the lattice exists;
`compiler_v3._compile_from_lattice` is the shared tail.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, get_args

from pydantic import BaseModel, Field, model_validator
from shapely.geometry import Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from .datums import (
    CoreDatum, Datum, DatumSet, Lattice, LevelDatum, PlanBounds, compile_datum_set,
)
from .geometry import v2
from .massing import MassingFamily
from .project_brief import ProjectBrief
from .program_volume_contracts import ProgramCirculationIntent, ProgramVolumeRegion
from .roof import RoofControl, assert_roof_control_matches_level
from .world_xy_grid import GridBounds, WorldXYGrid

if TYPE_CHECKING:  # annotations only; keep analysis_bundle imports acyclic
    from .models import ArchitecturalScore
    from .program import ProgramAllocation
    from .archetypes import Carve, CarveRefusal

Point = tuple[float, float]


class MassingLevel(BaseModel):
    """One storey's plate. Given from the ground up.

    With `kind` left empty on every level, the levels are storeys: the ground storey
    becomes the podium level the entry stands on, the rest are occupied, and a roof
    plate is added over the top one. Give `kind` on every level to describe the stack
    exactly, podium first and roof last.
    """

    id: str | None = None
    kind: Literal['podium', 'occupied', 'roof'] | None = None
    z: float | None = None
    plate: list[Point] = Field(min_length=3)
    voids: list[list[Point]] = Field(default_factory=list)
    is_terrace: bool = False


class MassingGrid(BaseModel):
    x_lines: list[float] = Field(min_length=2)
    y_lines: list[float] = Field(min_length=2)
    # The module rows the rooms lay out on. The structural y-lines carry the core
    # faces (decision 0022); rooms banded on those would lose every strip between
    # a face and a module line. Empty means the y-lines are the rows.
    band_lines: list[float] = Field(default_factory=list)
    apse_nodes: list[Point] = Field(default_factory=list)


class MassingCore(BaseModel):
    """A vertical core the massing places. Stairs in order: primary, its egress
    partner, then the extras. `serves` lists level ids from the ground up; empty
    means every level whose plate holds it."""

    id: str
    kind: Literal['stair', 'lift']
    x: float
    y: float
    serves: list[str] = Field(default_factory=list)
    run_axis: Literal['x', 'y'] = Field(default='y', exclude_if=lambda value: value == 'y')
    access_face: Literal['south', 'north', 'east', 'west'] | None = Field(
        default=None, exclude_if=lambda value: value is None)

    @model_validator(mode='after')
    def _access_face_only_for_lift(self):
        if self.kind == 'stair' and self.access_face is not None:
            raise ValueError('access_face is only valid for lift cores')
        return self


class MassingZone(BaseModel):
    """Floor the massing assigns to named spaces of the brief (decision 0023).

    Coarse on purpose: `space_ids` are the rooms that share this part of this floor
    -- a back of house, a reading floor, a staff wing -- and the allocator lays them
    out inside `rect`, in the brief's own order, and reports by name what did not
    fit. `space_id` is the single-room shorthand. Whoever writes a zone, a designer
    or a model reading the brief and the plates, does no arithmetic: the compile
    returns each zone's usable, asked and delivered areas.
    """

    space_id: str = ''
    space_ids: list[str] = Field(default_factory=list)
    label: str = ''
    level_id: str
    rect: tuple[float, float, float, float]
    note: str = ''

    def ids(self) -> list[str]:
        return list(self.space_ids) or ([self.space_id] if self.space_id else [])


class ProgramMassing(BaseModel):
    schema_version: Literal['mta.program_massing/1.0'] = 'mta.program_massing/1.0'
    massing_id: str = 'MAS-GIVEN'
    label: str = 'Given massing'
    typology: str = 'library'
    project_brief: ProjectBrief | None = Field(
        default=None, exclude_if=lambda value: value is None)
    levels: list[MassingLevel] = Field(min_length=2)
    grid: MassingGrid | None = None
    world_xy_grid: WorldXYGrid | None = Field(
        default=None, exclude_if=lambda value: value is None)
    cores: list[MassingCore] = Field(default_factory=list)
    zones: list[MassingZone] = Field(default_factory=list)
    # Datum overrides by datum id (`flight_width_m`, `bay_x_m`, `floor_to_floor_m`,
    # ...). Anything not named here takes the neutral score's midpoint.
    datums: dict[str, float] = Field(default_factory=dict)
    structural_system_id: str | None = None
    grammar_id: str | None = None
    # Optional provenance for the upstream form-making protocol.  Older given
    # massings omit both fields and remain valid schema-1.0 inputs.
    program_volume_grammar_id: str | None = None
    program_volume_source_digest: str | None = None
    # Optional semantic handoff from Program Volumes. Legacy/given massings omit
    # both; score-authored massings carry them unchanged into the lattice.
    program_volume_regions: list[ProgramVolumeRegion] = Field(default_factory=list)
    circulation_intent: ProgramCirculationIntent | None = None
    # Optional three-dimensional roof authority. Legacy massings omit it and keep
    # the historical roof emitter behaviour.
    roof_control: RoofControl | None = None
    cutaway: bool = False
    note: str = ''

    @model_validator(mode='after')
    def _circulation_references_regions(self):
        if self.project_brief is not None and self.typology != self.project_brief.typology:
            raise ValueError('massing typology must match the project brief')
        if self.circulation_intent is None:
            return self
        region_ids = {region.id for region in self.program_volume_regions}
        if not region_ids:
            raise ValueError(
                'a Program Volume circulation intent requires Program Volume regions')
        intent = self.circulation_intent
        referenced = (set(intent.carrier_volume_ids)
                      | set(intent.connector_volume_ids)
                      | {intent.entry_station.source_volume_id})
        unknown = sorted(referenced - region_ids)
        if unknown:
            raise ValueError(
                f'circulation intent references unknown Program Volume regions {unknown}')
        return self

    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode('utf-8')).hexdigest()[:12]


def load_program_massing(path: Path) -> ProgramMassing:
    return ProgramMassing.model_validate(
        json.loads(Path(path).read_text(encoding='utf-8-sig')))


# ---------------------------------------------------------------------------
# Massing -> the inputs the compiler tail needs
# ---------------------------------------------------------------------------

def neutral_score(massing: ProgramMassing) -> ArchitecturalScore:
    """A score that decides nothing: every dimension at its midpoint, fully known.

    The datum table and the selection screens are written against a score; on a
    massing run there is no recording, so this one stands in and the massing's own
    datum values override whatever it implies. Its id carries the massing's digest,
    so the model identity follows the volumes it was built from.
    """
    from .models import ArchitecturalScore, ScoreDimension, SharedScoreDimensionId

    dimensions = [
        ScoreDimension(
            id=dimension, value=0.5, source_feature='program_massing',
            extraction_method='manual', confidence=1.0,
            architectural_proposal='Neutral. The massing, not a recording, decides '
                                   'this building; the datum sits at its midpoint '
                                   'unless the massing names a value.')
        for dimension in get_args(SharedScoreDimensionId)]
    return ArchitecturalScore(score_id=f'massing-{massing.digest()}',
                              source_audio_sha256='0' * 64,
                              dimensions=dimensions, mapping_rules=[])


def datums_for(massing: ProgramMassing, score: ArchitecturalScore) -> DatumSet:
    base = compile_datum_set(score)
    known = {datum.id for datum in base.datums}
    unknown = sorted(set(massing.datums) - known)
    if unknown:
        raise ValueError(f'unknown datums in the massing: {unknown}; known ids are '
                         f'{sorted(known)}')
    datums: list[Datum] = []
    for datum in base.datums:
        if datum.id in massing.datums:
            datums.append(datum.model_copy(update={
                'value': float(massing.datums[datum.id]),
                'provenance': 'design_fixture',
                'reason': f'{datum.reason} Given by the program massing.'}))
        else:
            datums.append(datum)
    if massing.world_xy_grid is not None:
        pitches = {'bay_x_m': massing.world_xy_grid.spacing_x,
                   'bay_y_m': massing.world_xy_grid.spacing_y}
        for index, datum in enumerate(datums):
            if datum.id in pitches and abs(datum.value - pitches[datum.id]) > 1e-8:
                datums[index] = datum.model_copy(update={
                    'value': pitches[datum.id], 'provenance': 'design_fixture',
                    'reason': 'Explicit World XY pitch overrides the proposed bay datum.'})
    control = massing.roof_control
    if control is not None and control.span_proportion is not None:
        from .roof import ROOF_SPAN_RULE, TRUSS_DEPTH_TO_SPAN_RANGE
        # A score reading is still the same reading after geometry supplies its
        # scale. Keep confidence/provenance; do not relabel it as a manual override.
        for index, datum in enumerate(datums):
            if datum.id != 'truss_depth_m':
                continue
            depth = control.profile.truss_depth_m
            if datum.id in massing.datums and abs(datum.value-depth) > 1e-6:
                raise ValueError('Explicit truss depth conflicts with Program Volume roof proportion')
            position = datum.applied_position if datum.applied_position is not None else 0.5
            if abs(position-control.span_proportion.hierarchy_position) > 1e-6:
                raise ValueError('Roof proportion belongs to a different hierarchy reading')
            datums[index] = datum.model_copy(update={
                'value': depth,
                'output_range': tuple(control.span_proportion.span_m*r
                                      for r in TRUSS_DEPTH_TO_SPAN_RANGE),
                'rule_id': ROOF_SPAN_RULE,
                'reason': control.span_proportion.basis,
            })
    return DatumSet(score_id=score.score_id, datums=datums)


def _ring(points: list[Point]) -> list:
    """A counter-clockwise ring without a repeated closing vertex."""
    if len(points) > 3 and points[0] == points[-1]:
        points = points[:-1]
    polygon = orient(Polygon(points), sign=1.0)
    return [v2(float(x), float(y)) for x, y in list(polygon.exterior.coords)[:-1]]


def lattice_for(massing: ProgramMassing, datums: DatumSet) -> Lattice:
    """The lattice the compiler reads, built from the massing's own numbers.

    Levels are stacked from the datums where the massing gives no elevation: the
    ground storey rises `ground_open_height_m`, every storey above it
    `floor_to_floor_m`. The grid is the massing's, or bays of the massing's datums
    laid over the ground plate. The plan bounds are the union of every plate.
    """
    given = list(massing.levels)
    if all(level.kind is None for level in given):
        kinds = ['podium'] + ['occupied'] * (len(given) - 1) + ['roof']
        top = given[-1]
        given = given + [MassingLevel(plate=list(top.plate), voids=[list(v) for v in top.voids])]
    else:
        kinds = [level.kind or 'occupied' for level in given]
        if kinds[0] != 'podium' or kinds[-1] != 'roof' or 'roof' in kinds[:-1] \
                or 'podium' in kinds[1:]:
            raise ValueError('levels with kinds must run podium, occupied..., roof')
    if len(given) < 3:
        raise ValueError('a massing needs a ground storey and at least one storey '
                         'above it')

    ground_open = datums.value('ground_open_height_m')
    floor_to_floor = datums.value('floor_to_floor_m')
    levels: list[LevelDatum] = []
    z = 0.0
    for index, (level, kind) in enumerate(zip(given, kinds)):
        if level.z is not None:
            z = float(level.z)
        elif index > 0:
            z = levels[-1].z + (ground_open if index == 1 else floor_to_floor)
        levels.append(LevelDatum(
            index=index, id=level.id or f'L{index:02d}', z=round(z, 4), kind=kind,
            plate=_ring(level.plate), voids=[_ring(ring) for ring in level.voids],
            is_terrace=level.is_terrace))
    for lower, upper in zip(levels, levels[1:]):
        if upper.z <= lower.z:
            raise ValueError(f'{upper.id} at z={upper.z} is not above {lower.id} at '
                             f'z={lower.z}')
    if massing.project_brief is not None:
        brief = massing.project_brief
        occupied = [level for level in levels if level.kind == 'occupied']
        if len(occupied) != brief.occupied_storeys:
            raise ValueError('occupied level count must match the project brief')
        gross = 0.0
        for level in levels:
            shape = Polygon([(p.x, p.y) for p in level.plate],
                            holes=[[(p.x, p.y) for p in ring] for ring in level.voids])
            if not shape.is_valid or not brief.massing_limit_shape.buffer(1e-7).covers(shape):
                raise ValueError(f'{level.id} plate is invalid or outside the brief site '
                                 'massing limit (setback plus facade reserve)')
            if level.kind == 'occupied':
                clearances = [box(*region.resolve_bounds(massing.grid))
                              for region in massing.program_volume_regions
                              if region.level_id == level.id and region.role == 'sectional_clearance']
                # The envelope contains tall-room airspace; the floor-area budget
                # does not. The real carve must still validate and remove it.
                gross += shape.difference(unary_union(clearances)).area
        if gross > brief.target_gross_area_m2 + 1e-6:
            raise ValueError(f'Program Volume floor area {gross:.3f} exceeds '
                             f'brief gross budget {brief.target_gross_area_m2:.3f}')
    if massing.roof_control is not None:
        assert_roof_control_matches_level(massing.roof_control, levels[-1])

    xs = [p.x for level in levels for p in level.plate]
    ys = [p.y for level in levels for p in level.plate]
    plan = PlanBounds(x_min=round(min(xs), 4), x_max=round(max(xs), 4),
                      y_min=round(min(ys), 4), y_max=round(max(ys), 4))
    if massing.grid is not None:
        source_x_lines = [round(float(x), 4) for x in sorted(massing.grid.x_lines)]
        source_y_lines = [round(float(y), 4) for y in sorted(massing.grid.y_lines)]
        if massing.program_volume_regions:
            # Program Volume grid lines are cell boundaries: putting a physical
            # column or beam section on one makes half of that structure leave the
            # authored volume.  Structure registers to the centres of those same
            # indexed cells.  The immutable boundary grid remains below for program,
            # facade, circulation and review overlays, so no authoring coordinate is
            # lost or reinterpreted.
            x_lines = [round((a + b) / 2.0, 4)
                       for a, b in zip(source_x_lines, source_x_lines[1:])]
            y_lines = [round((a + b) / 2.0, 4)
                       for a, b in zip(source_y_lines, source_y_lines[1:])]
        else:
            x_lines = source_x_lines
            y_lines = source_y_lines
        apse_nodes = [v2(float(x), float(y)) for x, y in massing.grid.apse_nodes]
    else:
        ground = levels[0].plate
        gx = [p.x for p in ground]
        gy = [p.y for p in ground]
        span_x, span_y = max(gx) - min(gx), max(gy) - min(gy)
        bays_x = max(2, round(span_x / datums.value('bay_x_m')))
        bays_y = max(2, round(span_y / datums.value('bay_y_m')))
        x_lines = [round(min(gx) + span_x * i / bays_x, 4) for i in range(bays_x + 1)]
        y_lines = [round(min(gy) + span_y * j / bays_y, 4) for j in range(bays_y + 1)]
        apse_nodes = []

    if massing.world_xy_grid is not None:
        bounds = GridBounds(plan.x_min, plan.y_min, plan.x_max, plan.y_max)
        x_lines = massing.world_xy_grid.registration_lines('x', bounds)
        y_lines = massing.world_xy_grid.registration_lines('y', bounds)
        if apse_nodes:
            raise ValueError('World XY mode does not yet support a separate radial frame')

    cores = [CoreDatum(id=core.id, kind=core.kind, x=float(core.x), y=float(core.y),
                       serves=list(core.serves), run_axis=core.run_axis,
                       access_face=core.access_face) for core in massing.cores]
    # Each given core claims its floor on the levels it serves, so the archetype
    # carvers -- which read the level, not the core list -- keep their rooms out
    # of it. The footprint is the compiler's own, not a second formula.
    if cores:
        from .compiler_v3 import CORE_CLEARANCE_M, LIFT_SHAFT_M, _core_box
        from .datums import flight_run
        width = datums.value('flight_width_m')
        run = flight_run(width)
        for core in cores:
            if core.kind == 'stair':
                footprint = _core_box(core.x, core.y, width, run,run_axis=core.run_axis)
            else:
                half = LIFT_SHAFT_M / 2.0 + CORE_CLEARANCE_M
                footprint = (core.x - half, core.y - half, core.x + half, core.y + half)
            for level in levels:
                if not core.serves or level.id in core.serves:
                    level.reserved.append(tuple(round(v, 4) for v in footprint))

    # A Program Volume role is spatial authority, not a display colour.  Carrier and
    # connector volumes remain real floor for stairs and public routes, while the
    # archetype carvers and room allocator must keep out. Resolve their indexed
    # rectangles on the immutable authoring grid before the structural grid is later
    # reframed around the chosen core.
    if massing.circulation_intent is not None:
        if massing.grid is None:
            raise ValueError(
                'Program Volume circulation intent requires its authoring grid')
        circulation_ids = (
            set(massing.circulation_intent.carrier_volume_ids)
            | set(massing.circulation_intent.connector_volume_ids))
        level_by_id = {level.id: level for level in levels}
        for region in massing.program_volume_regions:
            if region.id not in circulation_ids:
                continue
            level = level_by_id.get(region.level_id)
            if level is None:
                raise ValueError(
                    f'{region.id} reserves circulation on unknown level '
                    f'{region.level_id}')
            i0, j0, i1, j1 = region.grid_rect
            try:
                footprint = (
                    source_x_lines[i0], source_y_lines[j0],
                    source_x_lines[i1], source_y_lines[j1])
            except IndexError as exc:
                raise ValueError(
                    f'{region.id} circulation reservation lies outside its '
                    'Program Volume authoring grid') from exc
            level.reserved.append(tuple(round(v, 4) for v in footprint))

    return Lattice(
        levels=levels, x_lines=x_lines, y_lines=y_lines,
        band_lines=(list(massing.grid.band_lines)
                    if massing.grid is not None and massing.grid.band_lines
                    else list(y_lines)),
        apse_nodes=apse_nodes,
        plan_x_m=round(plan.width, 4), plan_y_m=round(plan.depth, 4), plan=plan,
        massing_id=massing.massing_id, cutaway=massing.cutaway, given_cores=cores,
        grid_given=massing.grid is not None, world_xy_grid=massing.world_xy_grid,
        site_boundary=([v2(x,y) for x,y in massing.project_brief.site.polygon[:-1]]
                       if massing.project_brief is not None else []),
        roof_control=massing.roof_control,
        program_volume_grammar_id=massing.program_volume_grammar_id,
        program_volume_source_digest=massing.program_volume_source_digest,
        program_volume_x_lines=(list(source_x_lines)
                                if massing.program_volume_regions and massing.grid
                                else []),
        program_volume_y_lines=(list(source_y_lines)
                                if massing.program_volume_regions and massing.grid
                                else []),
        program_volume_regions=list(massing.program_volume_regions),
        circulation_intent=massing.circulation_intent)


def family_for(massing: ProgramMassing, lattice: Lattice) -> MassingFamily:
    """The family record the selection and the sheets read: the given plates."""
    return MassingFamily(
        id=massing.massing_id if massing.massing_id in get_args(
            MassingFamily.model_fields['id'].annotation) else 'MAS-GIVEN',
        label=massing.label, plan_x_m=max(1.0, lattice.plan.width),
        plan_y_m=max(1.0, lattice.plan.depth), plan_tolerance=0.0,
        profile='uniform', level_factor=1.0, level_floor=1, level_ceiling=99,
        west_apse=bool(lattice.apse_nodes),
        note='Plates given by a program massing (decision 0022); the family fields '
             'describe them and choose nothing.')


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

@dataclass
class PreparedMassing:
    score: ArchitecturalScore
    datums: DatumSet
    lattice: Lattice
    family: MassingFamily
    allocation: ProgramAllocation
    carve: Carve | CarveRefusal | None


def prepare_massing(massing: ProgramMassing, *,
                    score: ArchitecturalScore | None = None) -> PreparedMassing:
    """Run the actual spatial stage without emitting detailed building members.

    Shared by diagnostics and full compilation so a fast preflight cannot invent
    its own easier allocation, core placement or carving algorithm.
    """
    from .briefs import brief_for
    from .compiler_v3 import _carve_and_allocate

    score = score or neutral_score(massing)
    datums = datums_for(massing, score)
    lattice = lattice_for(massing, datums)
    family = family_for(massing, lattice)
    typology = massing.typology
    brief = (massing.project_brief.resolved_spaces() if massing.project_brief is not None
             else brief_for(typology, storeys=len(lattice.occupied)))
    if lattice.given_cores:
        # Given cores are known before anything is carved, so the grid is drawn to
        # them first and the archetype places its rooms on that grid: a room edge
        # lands on a core face instead of a sliver away from it.
        from .compiler_v3 import core_anchors
        core_anchors(lattice, datums)
    # The archetype carves, the given cores are validated against the carve, and
    # the allocator fills the rest. No plate fit: the plate is the input.
    allocation, carve = _carve_and_allocate(lattice, datums, typology, brief,
                                            zoned=given_zones(massing, lattice))
    return PreparedMassing(score, datums, lattice, family, allocation, carve)


def compile_from_massing(massing: ProgramMassing, *, site=None,
                         score: ArchitecturalScore | None = None):
    """Build from the massing contract and its shared spatial preparation."""
    from .compiler_v3 import _compile_from_lattice
    from .site import resolve_site

    prepared = prepare_massing(massing, score=score)
    volume_source = (f'; Program Volume grammar {massing.program_volume_grammar_id} '
                     f'authored their union ({massing.program_volume_source_digest})'
                     if massing.program_volume_grammar_id else '')
    why = [f'plates, grid and cores given by program massing {massing.massing_id} '
           f'({massing.digest()}){volume_source}; downstream systems may not refit '
           'or replace that boundary'
           + (f'. {massing.note}' if massing.note else '')]
    return _compile_from_lattice(
        score=prepared.score, datums=prepared.datums, lattice=prepared.lattice,
        allocation=prepared.allocation, carve=prepared.carve,
        typology=massing.typology, massing=prepared.family, massing_why=why,
        site=site or resolve_site(), cutaway=massing.cutaway,
        pinned_massing=massing.massing_id, pinned_typology=massing.typology,
        grammar_id=massing.grammar_id, system_id=massing.structural_system_id,
        identity_token=massing.digest(), project_brief=massing.project_brief)


def brief_for_massing(massing: ProgramMassing) -> dict:
    """What a zone writer needs, computed by the kernel: the brief with its numbers
    and each storey's floor after the cores and the archetype's carve have taken
    theirs. The writer -- a designer or a model -- assigns rooms to rectangles;
    every area here is measured, none is left for the writer to work out.
    """
    from .archetypes import Carve, carve_for
    from .briefs import brief_for
    from .compiler_v3 import (_approach_keep_out, _plan_approach, core_anchors,
                              core_reservations)
    from .plan_regions import rectangular_runs, usable_region

    score = neutral_score(massing)
    datums = datums_for(massing, score)
    lattice = lattice_for(massing, datums)
    brief = (massing.project_brief.resolved_spaces() if massing.project_brief is not None
             else brief_for(massing.typology, storeys=len(lattice.occupied)))
    core_anchors(lattice, datums)
    cores = core_reservations(lattice, datums)
    carve = carve_for(massing.typology, lattice, datums, brief)
    carved: dict[int, list] = {}
    removed: dict[int, list] = {}
    settled: list[dict] = []
    if isinstance(carve, Carve):
        carved = {index: [tuple(rect) for rect in rects]
                  for index, rects in carve.reservations.items()}
        # Plates the archetype removes above its volume -- the double height over a
        # reading room -- are voids on the storey above; a zone there is refused.
        removed = {index: [tuple(rect) for rect in rects]
                   for index, rects in carve.removed.items()}
        settled = [{'space_id': zone.space_id, 'label': zone.label,
                    'level_id': zone.level_id,
                    'rect': (zone.x0, zone.y0, zone.x1, zone.y1)} for zone in carve.zones]
    # The entrance approach -- entry landing, access stair, ramp -- is decided from
    # the plate; its footprints are floor the public corridors keep, so a zone over
    # them loses that floor. Shown on the storey the entry stands on.
    approach = _plan_approach(lattice, datums)
    approach_rects = [tuple(round(v, 2) for v in rect) for rect in _approach_keep_out(approach)]
    levels = []
    for level in lattice.occupied:
        xs = [p.x for p in level.plate]
        ys = [p.y for p in level.plate]
        reservations = (tuple(cores) + tuple(carved.get(level.index, ()))
                        + tuple(removed.get(level.index, ())))
        # The rows as the allocator sees them: for each module row, the x-runs of
        # usable floor whose whole depth is inside. A zone drawn on these runs is
        # accepted; on a rotated or apsidal plate the bounding box is not.
        floor = usable_region(level, reservations)
        row_lines = lattice.band_lines or lattice.y_lines
        rows = [{'y0': y0, 'y1': y1,
                 'runs': [(x0, x1) for x0, x1 in rectangular_runs(floor, y0, y1)
                          if x1 - x0 >= 4.0]}
                for y0, y1 in zip(row_lines, row_lines[1:])]
        levels.append({
            'id': level.id, 'index': level.index, 'kind': level.kind, 'z': round(level.z, 3),
            'bbox': (round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)),
            # The ring itself: plates rotate and step, and a zone drawn to the
            # bounding box of a rotated plate stands off it at the corners.
            'plate': [(round(p.x, 2), round(p.y, 2)) for p in level.plate],
            'rows': rows,
            'plate_m2': round(usable_region(level).area, 1),
            'usable_m2': round(usable_region(level, reservations).area, 1),
            'cores': [tuple(round(v, 2) for v in rect) for rect in cores],
            'carved': [tuple(round(v, 2) for v in rect) for rect in carved.get(level.index, ())],
            'removed': [tuple(round(v, 2) for v in rect) for rect in removed.get(level.index, ())],
            'approach': approach_rects if level.id == approach.get('podium_id') else [],
            'voids': [[(round(p.x, 2), round(p.y, 2)) for p in ring] for ring in level.voids],
        })
    return {
        'typology': massing.typology,
        # Full precision: a zone edge is copied from these, and the allocator
        # compares it with the same line.
        'grid': {'x_lines': list(lattice.x_lines), 'y_lines': list(lattice.y_lines),
                 'band_lines': list(lattice.band_lines or lattice.y_lines)},
        'levels': levels,
        'brief': [{'id': space.id, 'label': space.label, 'area_m2': space.area_m2,
                   'min_dimension_m': space.min_dimension_m,
                   'level_preference': space.level_preference, 'daylight': space.daylight,
                   'category': space.category, 'adjacency': list(space.adjacency),
                   'settled_by_archetype': space.id in {z['space_id'] for z in settled}}
                  for space in brief],
        'archetype_rooms': settled,
        'zones': [zone.model_dump() for zone in massing.zones],
        'note': ('Zone rectangles are plan coordinates in metres on the level named. A '
                 'zone must lie on the usable floor: off the plate, in a void, in a '
                 'core or in carved floor it is refused by name. Rooms are laid out '
                 'inside a zone on the structural rows (band_lines) with a '
                 'circulation allowance; a room that does not fit is reported '
                 'against the zone and not placed elsewhere.'),
    }


def given_zones(massing: ProgramMassing, lattice: Lattice) -> tuple:
    """The massing's zones as the allocator reads them, levels resolved by id."""
    from .program import GivenZone

    by_id = {level.id: level for level in lattice.levels}
    out = []
    for index, zone in enumerate(massing.zones):
        label = zone.label or f'zone {index + 1}'
        if zone.level_id not in by_id:
            raise ValueError(f"zone '{label}' is on unknown level {zone.level_id}; "
                             f"levels are {', '.join(by_id)}")
        if not zone.ids():
            raise ValueError(f"zone '{label}' names no spaces")
        out.append(GivenZone(label=label, level_index=by_id[zone.level_id].index,
                             rect=tuple(zone.rect), space_ids=zone.ids()))
    return tuple(out)


def program_massing_of(model, *, with_zones: bool = False) -> ProgramMassing:
    """The massing a compiled model stands on, written out to be edited and fed back.

    With `with_zones`, every room the run placed is exported as a single-room zone,
    so a layout can be edited room by room and fed back as the contract.

    Cores are read through `core_anchors` on the model's own lattice, which carries
    the carve the run applied, so the export names the cores the run built. Every
    datum value travels with it, so the round trip reproduces the building rather
    than a neutral cousin of it.
    """
    from .compiler_v3 import core_anchors, _core_run_axis

    lattice = model.lattice
    anchors = core_anchors(lattice, model.datum_set)
    cores: list[MassingCore] = []
    if anchors['primary'] is not None:
        cores.append(MassingCore(id='CORE-A', kind='stair', x=anchors['primary'][0],
                                 y=anchors['primary'][1],
                                 run_axis=_core_run_axis(anchors,anchors['primary']),
                                 serves=[level.id for level in anchors['served']]))
    if anchors['second'] is not None:
        cores.append(MassingCore(id='CORE-B', kind='stair', x=anchors['second'][0],
                                 y=anchors['second'][1],
                                 run_axis=_core_run_axis(anchors,anchors['second']),
                                 serves=[level.id for level in anchors['second_served']]))
    for index, (point, run) in enumerate(anchors['extras']):
        cores.append(MassingCore(id=f'CORE-{chr(ord("C") + index)}', kind='stair',
                                 x=point[0], y=point[1],
                                 run_axis=_core_run_axis(anchors,point),
                                 serves=[level.id for level in run]))
    if anchors['lift'] is not None:
        cx, cy, served = anchors['lift']
        cores.append(MassingCore(id='LIFT-1', kind='lift', x=cx, y=cy,
                                 serves=[level.id for level in served]))
    levels = [MassingLevel(
        id=level.id, kind=level.kind, z=level.z,
        plate=[(p.x, p.y) for p in level.plate],
        voids=[[(p.x, p.y) for p in ring] for ring in level.voids],
        is_terrace=level.is_terrace) for level in lattice.levels]
    return ProgramMassing(
        massing_id=lattice.massing_id, label=f'Massing of {model.model_id}',
        typology=model.typology, levels=levels, project_brief=model.project_brief,
        grid=MassingGrid(
                         x_lines=list(lattice.program_volume_x_lines or lattice.x_lines),
                         y_lines=list(lattice.program_volume_y_lines or lattice.y_lines),
                         band_lines=list(lattice.band_lines or lattice.y_lines),
                         apse_nodes=[(p.x, p.y) for p in lattice.apse_nodes]),
        cores=cores, world_xy_grid=lattice.world_xy_grid,
        zones=([MassingZone(space_id=zone.space_id, label=zone.label,
                            level_id=zone.level_id,
                            rect=(zone.x0, zone.y0, zone.x1, zone.y1))
                for zone in model.program_allocation.zones] if with_zones else []),
        datums={datum.id: datum.value for datum in model.datum_set.datums},
        structural_system_id=model.structural_system_id,
        grammar_id=model.facade_grammar_id, cutaway=lattice.cutaway,
        program_volume_grammar_id=lattice.program_volume_grammar_id,
        program_volume_source_digest=lattice.program_volume_source_digest,
        program_volume_regions=list(lattice.program_volume_regions),
        circulation_intent=lattice.circulation_intent,
        roof_control=lattice.roof_control,
        note=f'Exported from {model.model_id}; the voids include the archetype carve '
             f'the run applied, which the re-import carves again from the same brief.')
