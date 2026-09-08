"""Program volumes are the form-making contract.

The brief supplies rooms and the score selects how those rooms are organised.  Each
room becomes a full-storey volume registered by bay indices.  The union of the
volumes on a storey is then written as that storey's plate; downstream structure,
circulation and envelope all read the same boundary through ``ProgramMassing``.

This module is deliberately upstream of ``program.py``'s detailed allocator.  The
volumes reserve gross program capacity and make the form.  The allocator then measures
whether the actual rooms, cores and public routes fit inside that form.  A failed fit
is reported; it never silently expands the plate or shrinks a room.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, model_validator
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from .briefs import brief_for
from .approach import APRON_DEPTH_M, ENTRANCE_MIN_WIDTH_M, plan_boundary_switchback
from .datums import DatumSet, compile_datum_set
from .program import ProgramCategory, SpaceRequirement
from .project_brief import ProjectBrief
from .program_massing import (
    MassingCore, MassingGrid, MassingLevel, MassingZone, ProgramMassing,
)
from .program_volume_contracts import (
    GridBoundaryStation, ProgramCirculationIntent, ProgramVolumeRegion,
    _validate_shared_route_claim,
)
from .roof import RoofControl, score_roof_control
from .world_xy_grid import WorldXYGrid

if TYPE_CHECKING:  # score annotations stay lazy and avoid the analysis bundle cycle
    from .models import ArchitecturalScore

Point = tuple[float, float]
GridRect = tuple[int, int, int, int]
ProgramVolumeGrammarId = Literal[
    'PVG-STACKED-BANDS',
    'PVG-TERRACED-WEAVE',
    'PVG-SPLIT-BRIDGE',
    'PVG-LEGACY-ELLIPSE',
]
VolumeRole = Literal[
    'program', 'archetype', 'circulation_spine', 'connector',
    'sectional_clearance',
]

# Cell counts, not model coordinates.  The remote carrier is large enough to host a
# complete protected stair core, and its one-cell link remains visibly subordinate to
# the program volumes it connects.
COMMON_SPINE_CELLS = 2
REMOTE_SPINE_CELLS = 2
REMOTE_SPINE_GAP_CELLS = 1
REMOTE_CONNECTOR_CELLS = 1
STACKED_PHASE_GATE = 0.5
STACKED_PHASE_CELLS = 1

CIRCULATION_FAMILIES = {
    'PVG-STACKED-BANDS': ('broad_straight', 'edge_parallel'),
    'PVG-TERRACED-WEAVE': ('terraced_cascade', 'terrace_return'),
    'PVG-SPLIT-BRIDGE': ('bridge_split', 'notch_switchback'),
    'PVG-LEGACY-ELLIPSE': ('terraced_cascade', 'terrace_return'),
}

ARCHETYPE_SPACE_IDS = {
    'museum': {'SP-GALLERY-A', 'SP-GALLERY-B'},
    'theater': {'SP-AUDITORIUM', 'SP-STAGE'},
    'library': {'SP-ADULT'},
    'pavilion': {'SP-HALL'},
}

# Authored plan relationships.  The first pair is also the theatre's sectional
# owner; the second remains a same-level museum pair with independent depths.
SHELF_PAIRS: tuple[tuple[str, str], ...] = (
    ('SP-AUDITORIUM', 'SP-STAGE'),
    ('SP-GALLERY-A', 'SP-GALLERY-B'),
)


class ProgramVolumeLevel(BaseModel):
    """One occupied storey in the volume stack."""

    index: int = Field(ge=1)
    id: str
    z_base: float
    z_top: float


class ProgramVolume(BaseModel):
    """A full-storey box located only by indices into the registration grid."""

    id: str
    level_index: int = Field(ge=1)
    level_id: str
    category: ProgramCategory
    role: VolumeRole = 'program'
    space_ids: list[str] = Field(default_factory=list)
    shared_route_volume_ids: list[str] = Field(
        default_factory=list, exclude_if=lambda value: not value)
    grid_rect: GridRect
    target_area_m2: float = Field(default=0.0, ge=0.0)
    gross_area_m2: float = Field(gt=0.0)
    reason: str

    @model_validator(mode='after')
    def _valid_rect(self):
        i0, j0, i1, j1 = self.grid_rect
        if i1 <= i0 or j1 <= j0:
            raise ValueError(f'{self.id} has an empty grid rectangle')
        if self.role in ('program', 'archetype') and not self.space_ids:
            raise ValueError(f'{self.id} is a program volume with no brief space')
        if self.role == 'sectional_clearance' and self.space_ids:
            raise ValueError(
                f'{self.id} is sectional clearance and cannot claim a brief space')
        _validate_shared_route_claim(
            volume_id=self.id,
            role=self.role,
            category=self.category,
            space_ids=self.space_ids,
            target_ids=self.shared_route_volume_ids,
        )
        return self


class ProgramVolumeCoreIntent(BaseModel):
    """A core whose plan position is owned by one circulation spine volume."""

    id: str
    kind: Literal['stair', 'lift']
    source_volume_id: str
    run_axis: Literal['x', 'y'] = Field(default='y', exclude_if=lambda value: value == 'y')
    access_face: Literal['south', 'north', 'east', 'west'] | None = Field(
        default=None, exclude_if=lambda value: value is None)

    @model_validator(mode='after')
    def _access_face_only_for_lift(self):
        if self.kind == 'stair' and self.access_face is not None:
            raise ValueError('access_face is only valid for lift cores')
        return self


class ProgramVolumeUnion(BaseModel):
    """The exact plan union downstream systems use for one occupied storey."""

    level_index: int = Field(ge=1)
    level_id: str
    boundary: list[Point] = Field(min_length=3)
    voids: list[list[Point]] = Field(default_factory=list)
    gross_area_m2: float = Field(gt=0.0)
    source_volume_ids: list[str]


class ProgramVolumeModel(BaseModel):
    """Serializable form decision between the score/brief and building compiler."""

    schema_version: Literal['mta.program_volumes/1.0'] = 'mta.program_volumes/1.0'
    score_id: str
    typology: str
    project_brief: ProjectBrief | None = Field(
        default=None, exclude_if=lambda value: value is None)
    grammar_id: ProgramVolumeGrammarId
    grammar_reason: list[str]
    levels: list[ProgramVolumeLevel] = Field(min_length=1)
    grid: MassingGrid
    world_xy_grid: WorldXYGrid | None = Field(
        default=None, exclude_if=lambda value: value is None)
    volumes: list[ProgramVolume] = Field(min_length=1)
    level_unions: list[ProgramVolumeUnion] = Field(min_length=1)
    topology_signature: str
    design_datums: dict[str, float] = Field(default_factory=dict,
                                          exclude_if=lambda value: not value)
    # These compact semantic records are repeated deliberately. ``volumes`` remain
    # the authoring artifact; regions and the circulation intent are the stable
    # compiler-boundary contract read by facade and circulation emitters.
    program_volume_regions: list[ProgramVolumeRegion] = Field(default_factory=list)
    circulation_intent: ProgramCirculationIntent | None = None
    # Optional on the schema for compatibility with hand-authored/legacy volume
    # payloads. The score-authored path always fills it from the highest union.
    roof_control: RoofControl | None = None
    # A core intent carries no coordinates.  Its centre is resolved from the
    # referenced circulation volume on ``grid`` when the massing is adapted.
    authored_cores: list[ProgramVolumeCoreIntent] = Field(
        default_factory=list, exclude_if=lambda value: not value)
    note: str = (
        'Gross program volumes make the form. Their union is the plate authority; '
        'detailed allocation, structure and circulation are measured inside it, and '
        'the facade is generated from its outboard boundary.')

    @model_validator(mode='after')
    def _semantic_references_exist(self):
        if self.project_brief is not None:
            if self.typology != self.project_brief.typology:
                raise ValueError('Program Volume typology must match the project brief')
            if len(self.levels) != self.project_brief.occupied_storeys:
                raise ValueError('Program Volume level count must match the project brief')
        volume_ids = {volume.id for volume in self.volumes}
        if self.program_volume_regions:
            region_ids = [region.id for region in self.program_volume_regions]
            if len(region_ids) != len(set(region_ids)):
                raise ValueError('Program Volume region ids must be unique')
            if set(region_ids) != volume_ids:
                missing = sorted(volume_ids - set(region_ids))
                unknown = sorted(set(region_ids) - volume_ids)
                raise ValueError(
                    'Program Volume regions must describe every authored volume; '
                    f'missing={missing}, unknown={unknown}')
        if self.circulation_intent is not None:
            intent = self.circulation_intent
            referenced = (set(intent.carrier_volume_ids)
                          | set(intent.connector_volume_ids)
                          | {intent.entry_station.source_volume_id})
            unknown = sorted(referenced - volume_ids)
            if unknown:
                raise ValueError(
                    f'circulation intent references unknown Program Volumes {unknown}')
        core_ids = [core.id for core in self.authored_cores]
        if len(core_ids) != len(set(core_ids)):
            raise ValueError('authored core ids must be unique')
        source_ids = [core.source_volume_id for core in self.authored_cores]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError('authored cores cannot share a source Program Volume')
        volumes_by_id = {volume.id: volume for volume in self.volumes}
        for core in self.authored_cores:
            source = volumes_by_id.get(core.source_volume_id)
            if source is None:
                raise ValueError(
                    f'authored core {core.id} references unknown Program Volume '
                    f'{core.source_volume_id}')
            if source.role != 'circulation_spine':
                raise ValueError(
                    f'authored core {core.id} source {core.source_volume_id} must '
                    'be a circulation_spine volume')
        core_source_ids = {core.source_volume_id for core in self.authored_cores}
        core_sources = [volumes_by_id[source_id] for source_id in core_source_ids]
        for owner in self.volumes:
            if not owner.shared_route_volume_ids:
                continue
            owner_shape = box(*self.rect_of(owner))
            for core_source in core_sources:
                if owner_shape.intersection(box(*self.rect_of(core_source))).area > 1.0e-7:
                    raise ValueError(
                        f'shared route owner {owner.id} overlaps authored core source '
                        f'{core_source.id}')
            for target_id in owner.shared_route_volume_ids:
                target = volumes_by_id.get(target_id)
                if target is None:
                    raise ValueError(
                        f'{owner.id} shared route target {target_id} is unknown')
                if target.level_id != owner.level_id:
                    raise ValueError(
                        f'{owner.id} shared route target {target_id} must be on '
                        'the same level')
                if target.role not in ('circulation_spine', 'connector'):
                    raise ValueError(
                        f'{owner.id} shared route target {target_id} must be a '
                        'circulation_spine or connector')
                if target.id in core_source_ids:
                    raise ValueError(
                        f'{owner.id} shared route target {target_id} cannot be an '
                        'authored core source')
                if owner_shape.intersection(box(*self.rect_of(target))).area <= 1.0e-7:
                    raise ValueError(
                        f'{owner.id} shared route target {target_id} must physically '
                        'overlap the owner')
        return self

    def rect_of(self, volume: ProgramVolume) -> tuple[float, float, float, float]:
        i0, j0, i1, j1 = volume.grid_rect
        return (self.grid.x_lines[i0], self.grid.y_lines[j0],
                self.grid.x_lines[i1], self.grid.y_lines[j1])

    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode('utf-8')).hexdigest()[:12]

    def to_program_massing(self, *, include_zones: bool = False,
                           facade_grammar_id: str | None = None,
                           structural_system_id: str | None = None,
                           cutaway: bool = False) -> ProgramMassing:
        """Adapt the volume union to the existing common compiler tail.

        ``include_zones`` is intentionally opt-in.  The volumes describe gross form;
        a detailed room zone cannot claim floor later occupied by a core or public
        route.  The normal protocol therefore lets the kernel allocate and measure
        the brief inside the union.  A reviewed author may opt into fixed zones.
        """
        unions = {union.level_id: union for union in self.level_unions}
        first = unions[self.levels[0].id]
        last = unions[self.levels[-1].id]
        levels = [MassingLevel(
            id='L00', kind='podium', z=0.0,
            plate=list(first.boundary), voids=[list(v) for v in first.voids])]
        levels.extend(MassingLevel(
            id=level.id, kind='occupied', z=level.z_base,
            plate=list(unions[level.id].boundary),
            voids=[list(v) for v in unions[level.id].voids],
            # A shifted or stepped Program Volume floor is still enclosed occupied
            # program. ``is_terrace`` means the score deliberately strips the whole
            # storey's envelope; using it as a silhouette-change flag would leave
            # every varied upper mass open to weather.
            is_terrace=False)
                      for level in self.levels)
        levels.append(MassingLevel(
            id=f'L{len(self.levels) + 1:02d}', kind='roof', z=self.levels[-1].z_top,
            plate=list(last.boundary), voids=[list(v) for v in last.voids]))

        zones = []
        if include_zones:
            zones = [MassingZone(
                label=volume.id, level_id=volume.level_id,
                rect=self.rect_of(volume), space_ids=list(volume.space_ids),
                note='Fixed from a reviewed ProgramVolume; the kernel still measures it.')
                     for volume in self.volumes
                     if volume.role == 'program' and volume.space_ids]

        # The core intent stays coordinate-free across the contract boundary.  An
        # empty ``serves`` list is the existing MassingCore convention for every
        # level from grade; the compiler validates the complete footprint on each
        # such level and refuses the massing when the centre cannot fit.
        authored_cores = []
        for intent in self.authored_cores:
            source = next(volume for volume in self.volumes
                          if volume.id == intent.source_volume_id)
            x0, y0, x1, y1 = self.rect_of(source)
            authored_cores.append(MassingCore(
                id=intent.id, kind=intent.kind,
                x=(x0 + x1) / 2.0, y=(y0 + y1) / 2.0,
                serves=[], run_axis=intent.run_axis,
                access_face=intent.access_face))

        regions = (list(self.program_volume_regions)
                   or _program_volume_regions(self.volumes, self.levels))
        circulation_intent = self.circulation_intent or _circulation_intent_for(
            grammar=self.grammar_id,
            topology_signature=self.topology_signature,
            volumes=self.volumes,
            levels=self.levels,
            unions=self.level_unions,
            grid=self.grid)

        return ProgramMassing(
            massing_id='MAS-PROGRAM-VOLUME',
            label=f'{self.grammar_id} program-volume massing',
            typology=self.typology,
            project_brief=self.project_brief,
            levels=levels,
            grid=self.grid,
            world_xy_grid=self.world_xy_grid,
            cores=authored_cores,
            zones=zones,
            # The grid and elevations above are explicit geometry. Repeating their
            # score-derived dimensions as datum overrides would relabel musical
            # evidence as a design fixture and corrupt translation coverage.
            datums=dict(self.design_datums),
            structural_system_id=structural_system_id,
            grammar_id=facade_grammar_id,
            cutaway=cutaway,
            program_volume_grammar_id=self.grammar_id,
            program_volume_source_digest=self.digest(),
            program_volume_regions=regions,
            circulation_intent=circulation_intent,
            roof_control=self.roof_control,
            note=(f'{self.note} Topology {self.topology_signature}; '
                  f'{len(self.volumes)} full-height volumes on {len(self.levels)} '
                  'occupied storeys.'))


@dataclass(frozen=True)
class _Placed:
    level: int
    category: ProgramCategory
    space_ids: tuple[str, ...]
    role: VolumeRole
    rect: GridRect
    target_area: float
    reason: str


@dataclass(frozen=True)
class _EntryCandidate:
    source: ProgramVolume
    grid_edge: tuple[int, int, int, int]
    length_m: float
    midpoint: Point


def _program_volume_regions(
    volumes: list[ProgramVolume],
    levels: list[ProgramVolumeLevel],
) -> list[ProgramVolumeRegion]:
    """Reduce every authored box to the immutable facts downstream systems need."""
    by_level = {level.id: level for level in levels}
    regions = []
    for volume in volumes:
        level = by_level.get(volume.level_id)
        if level is None:
            raise ValueError(
                f'{volume.id} references unknown Program Volume level {volume.level_id}')
        regions.append(ProgramVolumeRegion(
            id=volume.id,
            level_id=volume.level_id,
            category=volume.category,
            role=volume.role,
            space_ids=list(volume.space_ids),
            shared_route_volume_ids=list(volume.shared_route_volume_ids),
            grid_rect=volume.grid_rect,
            z_base=level.z_base,
            z_top=level.z_top))
    return regions


def _grid_index(lines: list[float], value: float) -> int:
    tolerance = max(1.0, max((abs(line) for line in lines), default=1.0)) * 1.0e-7
    matches = [index for index, line in enumerate(lines)
               if abs(float(line) - float(value)) <= tolerance]
    if not matches:
        raise ValueError(f'Program Volume boundary coordinate {value} is off its grid')
    return matches[0]


def _volume_edge_candidate(
    volume: ProgramVolume,
    start: Point,
    end: Point,
    grid: MassingGrid,
) -> _EntryCandidate | None:
    """Intersect one CCW union edge with one volume face, preserving its direction."""
    i0, j0, i1, j1 = volume.grid_rect
    x0, x1 = grid.x_lines[i0], grid.x_lines[i1]
    y0, y1 = grid.y_lines[j0], grid.y_lines[j1]
    ax, ay = start
    bx, by = end
    scale = max(abs(x1 - x0), abs(y1 - y0), 1.0)
    tolerance = scale * 1.0e-7

    if abs(ay - by) <= tolerance:
        if min(abs(ay - y0), abs(ay - y1)) > tolerance:
            return None
        low = max(min(ax, bx), x0)
        high = min(max(ax, bx), x1)
        if high - low <= tolerance:
            return None
        if bx > ax:
            edge_start, edge_end = (low, ay), (high, ay)
        else:
            edge_start, edge_end = (high, ay), (low, ay)
    elif abs(ax - bx) <= tolerance:
        if min(abs(ax - x0), abs(ax - x1)) > tolerance:
            return None
        low = max(min(ay, by), y0)
        high = min(max(ay, by), y1)
        if high - low <= tolerance:
            return None
        if by > ay:
            edge_start, edge_end = (ax, low), (ax, high)
        else:
            edge_start, edge_end = (ax, high), (ax, low)
    else:
        raise ValueError('a Program Volume union edge must be axis-aligned to its grid')

    grid_edge = (
        _grid_index(grid.x_lines, edge_start[0]),
        _grid_index(grid.y_lines, edge_start[1]),
        _grid_index(grid.x_lines, edge_end[0]),
        _grid_index(grid.y_lines, edge_end[1]),
    )
    return _EntryCandidate(
        source=volume,
        grid_edge=grid_edge,
        length_m=math.hypot(edge_end[0] - edge_start[0],
                            edge_end[1] - edge_start[1]),
        midpoint=((edge_start[0] + edge_end[0]) / 2.0,
                  (edge_start[1] + edge_end[1]) / 2.0))


def _entry_candidates(
    sources: list[ProgramVolume],
    union: ProgramVolumeUnion,
    grid: MassingGrid,
) -> list[_EntryCandidate]:
    candidates = []
    ring = list(union.boundary)
    for start, end in zip(ring, ring[1:] + ring[:1]):
        for volume in sources:
            candidate = _volume_edge_candidate(volume, start, end, grid)
            if candidate is not None and candidate.length_m >= ENTRANCE_MIN_WIDTH_M:
                candidates.append(candidate)
    return candidates


def _rect_distance(a: ProgramVolume, b: ProgramVolume,
                   grid: MassingGrid) -> float:
    def shape(volume: ProgramVolume):
        i0, j0, i1, j1 = volume.grid_rect
        return box(grid.x_lines[i0], grid.y_lines[j0],
                   grid.x_lines[i1], grid.y_lines[j1])
    return float(shape(a).distance(shape(b)))


def _validate_entry_station(
    station: GridBoundaryStation,
    union: ProgramVolumeUnion,
    grid: MassingGrid,
) -> None:
    """Prove the stored edge is CCW: inside left, exterior right."""
    shape = Polygon(union.boundary, holes=union.voids)
    point, _tangent, outward = station.resolve(grid)
    gaps = [abs(b - a) for lines in (grid.x_lines, grid.y_lines)
            for a, b in zip(lines, lines[1:]) if abs(b - a) > 1.0e-9]
    if not gaps:
        raise ValueError('Program Volume entry station has no non-empty grid bay')
    epsilon = min(gaps) * 1.0e-6
    station_point = ShapelyPoint(*point)
    if shape.boundary.distance(station_point) > epsilon:
        raise ValueError(
            f'{station.source_volume_id} entry station is not on the first union boundary')
    outside = ShapelyPoint(point[0] + outward[0] * epsilon,
                           point[1] + outward[1] * epsilon)
    inside = ShapelyPoint(point[0] - outward[0] * epsilon,
                          point[1] - outward[1] * epsilon)
    if shape.covers(outside) or not shape.covers(inside):
        raise ValueError(
            f'{station.source_volume_id} entry edge violates the CCW interior-left '
            'boundary protocol')


def _circulation_intent_for(
    *,
    grammar: ProgramVolumeGrammarId,
    topology_signature: str,
    volumes: list[ProgramVolume],
    levels: list[ProgramVolumeLevel],
    unions: list[ProgramVolumeUnion],
    grid: MassingGrid,
    flight_width_m: float | None = None,
    entry_carrier_id: str | None = None,
) -> ProgramCirculationIntent:
    """Resolve one executable, grid-indexed entry from authored volume geometry."""
    if not levels or not unions:
        raise ValueError('a circulation intent needs an occupied Program Volume union')
    first_level = levels[0]
    first_union = next((union for union in unions
                        if union.level_id == first_level.id), None)
    if first_union is None:
        raise ValueError(f'no Program Volume union exists for {first_level.id}')
    first_volumes = [volume for volume in volumes
                     if volume.level_id == first_level.id]
    carriers = sorted(
        (volume for volume in volumes if volume.role == 'circulation_spine'),
        key=lambda volume: (volume.level_index, volume.id))
    connectors = sorted(
        (volume for volume in volumes if volume.role == 'connector'),
        key=lambda volume: (volume.level_index, volume.id))
    if not carriers:
        raise ValueError(
            f'{grammar} made no circulation_spine Program Volume to carry its route')

    first_carriers = [volume for volume in first_volumes
                      if volume.role == 'circulation_spine']
    if entry_carrier_id is not None:
        entry_carrier = next((volume for volume in first_carriers
                              if volume.id == entry_carrier_id), None)
        if entry_carrier is None:
            raise ValueError(
                f'entry_carrier_id {entry_carrier_id} must name a first-level '
                'circulation_spine Program Volume')
        candidates = _entry_candidates([entry_carrier], first_union, grid)
        if not candidates:
            raise ValueError(
                f'{grammar} authored entry carrier {entry_carrier_id} has no '
                f'exterior face on the {first_level.id} union')
        source_reason = (
            f'authored first-level circulation_spine {entry_carrier_id} supplies '
            'the entry face')
    else:
        # The west/common datum remains the arrival carrier.  A second carrier is an
        # exit and travel-distance authority at the remote end; letting its shorter
        # exterior face enter the grammar-specific entry ranking would move the public
        # entrance as an accidental consequence of adding egress capacity.
        entry_carrier = min(
            first_carriers,
            key=lambda volume: (
                volume.grid_rect[0],
                -(volume.grid_rect[2] - volume.grid_rect[0])
                * (volume.grid_rect[3] - volume.grid_rect[1]),
                volume.id))
        boundary_sources = [entry_carrier]
        candidates = _entry_candidates(boundary_sources, first_union, grid)
        source_reason = 'the first-level circulation_spine reaches the exterior union'
    if not candidates:
        eligible = [volume for volume in first_volumes
                    if volume.category in ('public', 'circulation')]
        candidates = _entry_candidates(eligible, first_union, grid)
        if not candidates:
            raise ValueError(
                f'{grammar} has no public or circulation Program Volume face on the '
                f'{first_level.id} exterior union; an entry point cannot be guessed')
        first_carriers = [volume for volume in first_volumes
                          if volume.role == 'circulation_spine']
        targets = first_carriers + [volume for volume in connectors
                                    if volume.level_id == first_level.id]
        if targets:
            candidates.sort(key=lambda candidate: (
                min(_rect_distance(candidate.source, target, grid)
                    for target in targets),
                candidate.source.id, candidate.grid_edge))
            nearest = candidates[0].source
            candidates = [candidate for candidate in candidates
                          if candidate.source.id == nearest.id]
        source_reason = (
            'the circulation_spine does not reach the exterior; the nearest connected '
            'first-level public/circulation volume supplies the entry face')

    connector_centres = []
    for connector in connectors:
        if connector.level_id != first_level.id:
            continue
        i0, j0, i1, j1 = connector.grid_rect
        connector_centres.append((
            (grid.x_lines[i0] + grid.x_lines[i1]) / 2.0,
            (grid.y_lines[j0] + grid.y_lines[j1]) / 2.0))

    stair_family, ramp_preference = CIRCULATION_FAMILIES[grammar]

    def source_depth(candidate):
        i0, j0, i1, j1 = candidate.source.grid_rect
        if candidate.grid_edge[1] == candidate.grid_edge[3]:
            return abs(grid.y_lines[j1] - grid.y_lines[j0])
        return abs(grid.x_lines[i1] - grid.x_lines[i0])

    if flight_width_m is not None:
        feasible = [candidate for candidate in candidates
                    if plan_boundary_switchback(
                        edge_length_m=candidate.length_m, fraction=0.5,
                        flight_width_m=flight_width_m, rise_m=first_level.z_base,
                        approach_depth_m=source_depth(candidate),
                        preference=ramp_preference).ramp is not None]
        if feasible:
            candidates = feasible
            source_reason += '; feasible ramp faces take precedence within that carrier'
        else:
            source_reason += '; no compliant ramp fits its available exterior faces'

    if grammar == 'PVG-STACKED-BANDS':
        chosen = min(candidates, key=lambda candidate: (
            -candidate.length_m, candidate.source.id, candidate.grid_edge))
    elif grammar == 'PVG-TERRACED-WEAVE':
        chosen = min(candidates, key=lambda candidate: (
            candidate.length_m, candidate.source.id, candidate.grid_edge))
    else:
        chosen = min(candidates, key=lambda candidate: (
            min((math.hypot(candidate.midpoint[0] - cx,
                            candidate.midpoint[1] - cy)
                 for cx, cy in connector_centres), default=0.0),
            candidate.source.id, candidate.grid_edge))

    station = GridBoundaryStation(
        level_id=first_level.id,
        source_volume_id=chosen.source.id,
        grid_edge=chosen.grid_edge,
        fraction=0.5)
    _validate_entry_station(station, first_union, grid)

    return ProgramCirculationIntent(
        source_volume_digest=topology_signature,
        carrier_volume_ids=[volume.id for volume in carriers],
        connector_volume_ids=[volume.id for volume in connectors],
        entry_station=station,
        public_stair_family=stair_family,
        ramp_preference=ramp_preference,
        entry_floor_elevation_m=first_level.z_base,
        approach_depth_m=source_depth(chosen),
        approach_depth_provenance=(
            f'normal grid span of entry source {chosen.source.id}'),
        reason=(
            f'{grammar} assigns {stair_family} public circulation and '
            f'{ramp_preference} accessible approach; {source_reason}.'))


def _score_value(score: ArchitecturalScore, dimension: str,
                 default: float = 0.5) -> float:
    return next((item.value for item in score.dimensions if item.id == dimension), default)


def _stacked_band_phase(score: ArchitecturalScore, level: int) -> int:
    """Ask whether repeated bands align or alternate on the lattice.

    The midpoint is a semantic question on the full normalized axis, not a corpus-fit
    threshold: a repeated score keeps every band registered; a less repeated score
    gives zero-based odd storeys one whole-cell AB phase.
    """
    repetition = _score_value(score, 'repetition')
    if repetition >= STACKED_PHASE_GATE or level % 2 == 0:
        return 0
    return STACKED_PHASE_CELLS


def choose_program_volume_grammar(
    score: ArchitecturalScore,
) -> tuple[ProgramVolumeGrammarId, list[str]]:
    """Choose one organisation with short, independently reachable questions."""
    interruption = _score_value(score, 'interruption')
    hierarchy = _score_value(score, 'hierarchy')
    variation = _score_value(score, 'variation')
    if interruption >= 0.58:
        return 'PVG-SPLIT-BRIDGE', [
            f'interruption {interruption:.2f} crosses 0.58: program separates into '
            'two occupied bodies and circulation becomes the bridge between them']
    if hierarchy >= 0.58 or variation >= 0.62:
        decisive = max((hierarchy, 'hierarchy'), (variation, 'variation'))
        return 'PVG-TERRACED-WEAVE', [
            f'{decisive[1]} {decisive[0]:.2f} is decisive: a stable vertical '
            'circulation datum holds shifted program floors together']
    return 'PVG-STACKED-BANDS', [
        f'interruption {interruption:.2f}, hierarchy {hierarchy:.2f} and variation '
        f'{variation:.2f} stay below their departure gates: rooms form compact, '
        'registered bands around one shared vertical spine']


def _storey_count(typology: str, datums: DatumSet) -> int:
    requested = datums.integer('level_count')
    lower, upper = {
        'pavilion': (1, 2),
        'theater': (2, 4),
        'museum': (3, 6),
        'library': (3, 6),
    }.get(typology, (2, 6))
    return max(lower, min(upper, requested))


def _allowed_storeys(space: SpaceRequirement, count: int) -> list[int]:
    if space.level_preference == 'ground':
        return [0]
    middle = max(1, math.ceil(count / 2))
    if space.level_preference == 'low':
        return list(range(middle))
    if space.level_preference == 'high':
        return list(range(count - 1, max(-1, count - middle - 1), -1))
    return list(range(count))


def _assign_storeys(spaces: tuple[SpaceRequirement, ...], count: int,
                     allowance: float, typology: str) -> list[list[SpaceRequirement]]:
    """Balance gross area while respecting each briefed level preference."""
    groups: list[list[SpaceRequirement]] = [[] for _ in range(count)]
    loads = [0.0] * count
    by_id = {space.id: space for space in spaces}
    # Spatial archetypes own these relationships. Seed them on the storey their
    # carver expects before balancing the remainder, so the Program Volume grammar
    # gives the archetype a viable host instead of asking it to repair the form.
    pinned = {
        'museum': ((count - 1, ('SP-GALLERY-A', 'SP-GALLERY-B')),),
        'theater': ((0, ('SP-AUDITORIUM', 'SP-STAGE')),),
        'library': ((max(0, count - 2), ('SP-ADULT',)),),
        'pavilion': ((0, ('SP-HALL',)),),
    }.get(typology, ())
    seeded = set()
    for level, ids in pinned:
        for space_id in ids:
            space = by_id.get(space_id)
            if space is None:
                continue
            groups[level].append(space)
            loads[level] += space.area_m2 / max(0.55, 1.0 - allowance)
            seeded.add(space_id)
    preference_order = {'ground': 0, 'high': 1, 'low': 2, 'any': 3}
    ordered = sorted((space for space in spaces if space.id not in seeded),
                     key=lambda s: (preference_order[s.level_preference],
                                    -s.area_m2, s.id))
    for space in ordered:
        allowed = _allowed_storeys(space, count)
        level = min(allowed, key=lambda i: (loads[i], i))
        groups[level].append(space)
        loads[level] += space.area_m2 / max(0.55, 1.0 - allowance)

    # A stack with no program on a storey is the defect this protocol exists to stop.
    # Collapse empty bins and preserve the vertical order of every assigned room.
    return [group for group in groups if group]


def _block_dimensions(space: SpaceRequirement, bay_x: float, bay_y: float,
                      allowance: float, elongation: float) -> tuple[int, int, float]:
    gross = space.area_m2 / max(0.55, 1.0 - allowance)
    cells = max(1, math.ceil(gross / (bay_x * bay_y)))
    min_i = max(1, math.ceil(space.min_dimension_m / bay_x))
    min_j = max(1, math.ceil(space.min_dimension_m / bay_y))
    candidates = []
    for j in range(min_j, max(min_j + 1, cells + 1)):
        i = max(min_i, math.ceil(cells / j))
        ratio = i / max(1, j)
        # A zero-waste 2 x 7 room is still a corridor. Shape carries more weight
        # than a few spare bay cells; the brief's minimum dimension remains hard.
        shape_cost = abs(math.log(max(0.05, ratio) / max(0.05, elongation)))
        candidates.append(((i * j - cells) * 0.18 + shape_cost * 2.0, i, j))
    _cost, i, j = min(candidates)
    return i, j, gross


def _shelf(spaces: list[SpaceRequirement], *, bay_x: float, bay_y: float,
           allowance: float, elongation: float, reverse: bool = False) -> list[_Placed]:
    blocks = [(space, *_block_dimensions(
        space, bay_x, bay_y, allowance, elongation)) for space in spaces]
    category_order = {'public': 0, 'circulation': 1, 'private': 2, 'service': 3}
    blocks.sort(key=lambda item: (category_order[item[0].category], -item[1] * item[2],
                                  item[0].id), reverse=reverse)

    # These are authored spatial relationships, not a by-product of category sort.
    # Keep the pair at the west/east seam even when a reverse shelf order or a room
    # from another category would otherwise split it across rows.  The theatre pair
    # shares its complete sectional band; the museum galleries retain their own
    # depths so their independent gross areas remain legible.
    by_id = {item[0].id: item for item in blocks}
    pair = next((pair for pair in SHELF_PAIRS if set(pair) <= set(by_id)), None)
    pair_ids: set[str] = set()
    if pair is not None:
        pair_ids = set(pair)
        paired = [by_id[space_id] for space_id in pair]
        if pair == SHELF_PAIRS[0]:
            pair_depth = max(item[2] for item in paired)
            paired = [(
                space, width, pair_depth, gross)
                for space, width, _depth, gross in paired]
        blocks = paired + [item for item in blocks if item[0].id not in pair_ids]

    cells = sum(i * j for _space, i, j, _gross in blocks)
    target_width = max(max((i for _s, i, _j, _g in blocks), default=1),
                       math.ceil(math.sqrt(cells * max(0.7, elongation))))
    if pair is not None:
        widths = {space.id: width for space, width, _depth, _gross in blocks}
        target_width = max(target_width, sum(widths[space_id] for space_id in pair))
    x = y = row_height = 0
    placed = []
    for space, width, depth, gross in blocks:
        if x and x + width > target_width:
            y += row_height
            x = row_height = 0
        placed.append(_Placed(
            level=0, category=space.category, space_ids=(space.id,), role='program',
            rect=(x, y, x + width, y + depth), target_area=space.area_m2,
            reason=(f'{space.label}: {space.area_m2:.0f} m2 brief plus circulation '
                    'allowance, registered as whole structural bays.'
                    + (' Authored as the west/east sectional pair with '
                       'SP-AUDITORIUM.' if space.id == 'SP-STAGE' and
                       'SP-AUDITORIUM' in pair_ids else '')
                    + (' Authored as the west/east sectional pair with '
                       'SP-STAGE.' if space.id == 'SP-AUDITORIUM' and
                       'SP-STAGE' in pair_ids else ''))))
        x += width
        row_height = max(row_height, depth)
    return placed


def _linear_wing(spaces: list[SpaceRequirement], *, bay_x: float, bay_y: float,
                 allowance: float, elongation: float) -> list[_Placed]:
    """Stack a split-massing wing along y, widest room first at the bridge."""
    blocks = [(space, *_block_dimensions(
        space, bay_x, bay_y, allowance, elongation)) for space in spaces]
    blocks.sort(key=lambda item: (-item[1], -item[2], item[0].id))
    y = 0
    placed = []
    for space, width, depth, _gross in blocks:
        placed.append(_Placed(
            level=0, category=space.category, space_ids=(space.id,), role='program',
            rect=(0, y, width, y + depth), target_area=space.area_m2,
            reason=(f'{space.label}: {space.area_m2:.0f} m2 brief plus circulation '
                    'allowance, registered in one side of the split mass.')))
        y += depth
    return placed


def _translate(items: list[_Placed], dx: int, dy: int, level: int,
               *, reason_suffix: str = '') -> list[_Placed]:
    return [_Placed(
        level=level, category=item.category, space_ids=item.space_ids, role=item.role,
        rect=(item.rect[0] + dx, item.rect[1] + dy,
              item.rect[2] + dx, item.rect[3] + dy),
        target_area=item.target_area, reason=item.reason + reason_suffix)
            for item in items]


def _layout_level(spaces: list[SpaceRequirement], grammar: ProgramVolumeGrammarId,
                  level: int, bay_x: float, bay_y: float, allowance: float,
                  score: ArchitecturalScore) -> list[_Placed]:
    hierarchy = _score_value(score, 'hierarchy')
    elongation = 0.85 + hierarchy * 0.9
    if grammar != 'PVG-SPLIT-BRIDGE':
        room_blocks = _shelf(
            spaces, bay_x=bay_x, bay_y=bay_y, allowance=allowance,
            elongation=elongation, reverse=(grammar == 'PVG-TERRACED-WEAVE'
                                            and level % 2 == 1))
        shift = 0
        reason_suffix = ''
        if grammar == 'PVG-TERRACED-WEAVE':
            shift = level * max(1, round(1 + _score_value(score, 'variation') * 2))
        elif grammar == 'PVG-STACKED-BANDS':
            shift = _stacked_band_phase(score, level)
            if shift:
                repetition = _score_value(score, 'repetition')
                reason_suffix = (
                    f' Repetition {repetition:.2f} stays below '
                    f'{STACKED_PHASE_GATE:.2f}: this alternating storey shifts '
                    f'{STACKED_PHASE_CELLS} whole lattice cell east.')
        return _translate(
            room_blocks, COMMON_SPINE_CELLS + shift, 0, level,
            reason_suffix=reason_suffix)

    # Split-bridge keeps its two wings, while the theatre's house/stage pair still
    # owns one continuous west/east sectional band.  Pull that pair out of the
    # category wings before laying out the remaining rooms; otherwise the private
    # stage is sorted into the opposite wing and the archetype has no shared seam.
    pair_ids = set(SHELF_PAIRS[0])
    pair_spaces = [space for space in spaces if space.id in pair_ids]
    pair_blocks = _shelf(
        pair_spaces, bay_x=bay_x, bay_y=bay_y, allowance=allowance,
        elongation=elongation) if len(pair_spaces) == len(pair_ids) else []
    public = [space for space in spaces
              if space.category in ('public', 'circulation')
              and space.id not in pair_ids]
    controlled = [space for space in spaces
                  if space.category in ('private', 'service')
                  and space.id not in pair_ids]
    left = _linear_wing(public, bay_x=bay_x, bay_y=bay_y, allowance=allowance,
                        elongation=elongation) if public else []
    right = _linear_wing(controlled, bay_x=bay_x, bay_y=bay_y, allowance=allowance,
                         elongation=elongation) if controlled else []
    pair_width = max((item.rect[2] for item in pair_blocks), default=0)
    pair_depth = max((item.rect[3] for item in pair_blocks), default=0)
    left_width = max(
        pair_width, max((item.rect[2] for item in left), default=COMMON_SPINE_CELLS))
    gap = max(1, round(1 + _score_value(score, 'interruption') * 2))
    out = _translate(pair_blocks, COMMON_SPINE_CELLS, 0, level)
    out.extend(_translate(left, COMMON_SPINE_CELLS, pair_depth, level))
    out.extend(_translate(
        right, COMMON_SPINE_CELLS + left_width + gap, 0, level))
    bridge_y = 0
    out.append(_Placed(
        level=level, category='circulation', space_ids=(), role='connector',
        rect=(COMMON_SPINE_CELLS + left_width, bridge_y,
              COMMON_SPINE_CELLS + left_width + gap, bridge_y + 1),
        target_area=0.0,
        reason='The occupied wings remain distinct; this full-height bridge is their '
               'shared public route and the geometric connection in the union.'))
    return out


def _coordinate_sectional_archetype(
    layouts: list[list[_Placed]], typology: str, *, datums: DatumSet,
) -> list[list[_Placed]]:
    """Reserve every storey the derived sectional room actually passes through."""
    if typology != 'theater':
        return _coordinate_one_section(layouts, typology)
    from .archetypes import derive_bowl, theatre_clearance_height
    owners = {space_id: item for item in layouts[0] for space_id in item.space_ids
              if space_id in SHELF_PAIRS[0]}
    if len(owners) != 2:
        return layouts
    brief = {space.id: space for space in brief_for(typology, storeys=len(layouts))}
    house, stage = (owners[space_id] for space_id in SHELF_PAIRS[0])
    bay_x, bay_y = datums.value('bay_x_m'), datums.value('bay_y_m')
    depth_cells = min(house.rect[3], stage.rect[3]) - max(house.rect[1], stage.rect[1])
    minimum = max(brief[space_id].min_dimension_m for space_id in owners)
    widths = None
    for cells in range(depth_cells, 0, -1):
        depth = cells * bay_y
        if not minimum <= depth <= 33.0:
            continue
        trial = {space_id: max(item.target_area / depth, brief[space_id].min_dimension_m)
                 for space_id, item in owners.items()}
        if all(trial[space_id] <= (item.rect[2] - item.rect[0]) * bay_x
               for space_id, item in owners.items()):
            widths = trial
            break
    if widths is None:
        return layouts  # The owner-aware carver records the unsatisfied room geometry.
    rows = derive_bowl(widths['SP-AUDITORIUM'])
    if not rows:
        return layouts
    # The paired theatre section has one gross upper enclosure and transfer zone.
    # Keeping the two owner prisms through that common height also connects a taller
    # stage enclosure back to the circulation carrier through its adjacent house.
    clear = theatre_clearance_height(widths['SP-AUDITORIUM'])
    coordinated = layouts
    for upper_index in range(1, len(layouts)):
        if upper_index * datums.value('floor_to_floor_m') < clear:
            coordinated = _coordinate_one_section(
                coordinated, typology, upper_index=upper_index)
    return coordinated


def _coordinate_one_section(
    layouts: list[list[_Placed]], typology: str, *,
    upper_index: int = 1, owner_space_ids: tuple[str, ...] = SHELF_PAIRS[0],
) -> list[list[_Placed]]:
    """Make a sectional archetype's overhead claim visible before plate union.

    The theatre house/stage pair is the ground-level sectional owner.  Its two
    upper clearances are kept as gross volumes so the envelope remains continuous
    until the theatre archetype applies its own measured floor carve.  The museum
    galleries remain a plan pair only; they do not receive a fabricated clearance.

    The library adult-reading room is double height.  Its earlier one-storey gross
    box let the next floor assign rooms across the slab the carver would later remove,
    creating a capacity deficit only after the form was supposedly settled.  Move
    those intersecting upper blocks together, preserving their relative layout, and
    author the vacated prism as explicit sectional clearance.  The clearance keeps
    the facade/roof envelope over the tall room while the carver removes its floor.
    """
    coordinated = [list(level) for level in layouts]
    if len(coordinated) < 2:
        return coordinated

    def overlaps(a: GridRect, b: GridRect) -> bool:
        return min(a[2], b[2]) > max(a[0], b[0]) \
            and min(a[3], b[3]) > max(a[1], b[1])

    if typology == 'theater':
        owners = [item for item in coordinated[0]
                  if set(item.space_ids) & set(SHELF_PAIRS[0])]
        by_space = {space_id: next((item for item in owners
                                    if space_id in item.space_ids), None)
                    for space_id in SHELF_PAIRS[0]}
        if any(owner is None for owner in by_space.values()):
            return coordinated
        owner_items = [by_space[space_id] for space_id in owner_space_ids]
        owner_rects = [item.rect for item in owner_items]
        upper = list(coordinated[upper_index])
        residual = unary_union([box(*item.rect) for item in upper]).difference(
            unary_union([box(*rect) for rect in owner_rects]))
        common = min((item for item in upper if item.role == 'circulation_spine'),
                     key=lambda item: (item.rect[0], item.rect))
        common_point = box(*common.rect).representative_point()
        residual_parts = list(residual.geoms) if residual.geom_type == 'MultiPolygon' else [residual]
        reachable = next(part for part in residual_parts
                         if part.buffer(1e-9).covers(common_point))
        # Removing a room prism can strand its neighbour without overlapping that
        # neighbour. Move both the intersected and stranded program together so the
        # remaining floor can still reach the common carrier after the actual cut.
        intersecting = [item for item in upper
                        if item.role in ('program', 'archetype')
                        and (any(overlaps(item.rect, rect) for rect in owner_rects)
                             or not reachable.buffer(1e-9).covers(box(*item.rect)))]

        if intersecting:
            # Search whole-grid translations for the intersecting group. The carve
            # will remove the two clearance rectangles, so the winning position must
            # already form one connected residual floor without borrowing either
            # prism as a bridge. This closes the earlier east-shift case where a
            # mechanical owner survived in area yet became an island after carving.
            retained = [
                item for item in upper
                if item not in intersecting
                and not (item.role == 'connector'
                         and any(overlaps(item.rect, rect)
                                 for rect in owner_rects))
            ]
            blockers = [item for item in retained
                        if item.role != 'connector']
            retained_union = unary_union([box(*item.rect) for item in retained])
            common = min(
                (item for item in retained if item.role == 'circulation_spine'),
                key=lambda item: (item.rect[0], item.rect))
            components = (list(retained_union.geoms)
                          if retained_union.geom_type == 'MultiPolygon'
                          else [retained_union])
            common_point = box(*common.rect).representative_point()
            common_component = next(
                component for component in components
                if component.buffer(1e-9).covers(common_point))
            extent = max(
                8,
                max(rect[2] for rect in owner_rects)
                - min(rect[0] for rect in owner_rects)
                + max(item.rect[2] - item.rect[0] for item in intersecting),
                max(rect[3] for rect in owner_rects)
                - min(rect[1] for rect in owner_rects)
                + max(item.rect[3] - item.rect[1] for item in intersecting),
            )
            translations = sorted(
                ((dx, dy)
                 for dx in range(-extent, extent + 1)
                 for dy in range(-extent, extent + 1)
                 if dx or dy),
                key=lambda shift: (
                    abs(shift[0]) + abs(shift[1]),
                    0 if shift[1] > 0 else 1,
                    0 if shift[0] > 0 else 1,
                    abs(shift[1]), abs(shift[0]), shift),
            )
            selected_shift = None
            for dx, dy in translations:
                moved_rects = [(
                    item.rect[0] + dx, item.rect[1] + dy,
                    item.rect[2] + dx, item.rect[3] + dy)
                    for item in intersecting]
                if any(overlaps(rect, owner_rect)
                       for rect in moved_rects for owner_rect in owner_rects):
                    continue
                if any(overlaps(rect, fixed.rect)
                       for rect in moved_rects for fixed in blockers):
                    continue
                connected_to_common = unary_union(
                    [common_component] + [box(*rect) for rect in moved_rects])
                if (not connected_to_common.is_empty
                        and connected_to_common.is_valid
                        and connected_to_common.geom_type == 'Polygon'):
                    selected_shift = (dx, dy)
                    break
            if selected_shift is None:
                raise ValueError(
                    'the theatre upper owners cannot move clear of their authored '
                    'section while preserving one connected residual floor')

            dx, dy = selected_shift
            moved_by_id = {
                id(item): (item.rect[0] + dx, item.rect[1] + dy,
                           item.rect[2] + dx, item.rect[3] + dy)
                for item in intersecting}
            rewritten = []
            for item in retained:
                rewritten.append(item)
            for item in intersecting:
                rewritten.append(_Placed(
                    level=item.level, category=item.category,
                    space_ids=item.space_ids, role=item.role,
                    rect=moved_by_id[id(item)], target_area=item.target_area,
                    reason=(item.reason + ' Shifted as one registered upper-floor '
                            'group clear of the theatre section and connected after '
                            'its authored floor carve.')))
            upper = rewritten

        # One clearance per authored owner keeps the relation auditable and leaves
        # both rooms as independent volumes for the archetype and facade readers.
        for owner in owner_items:
            space_id = owner.space_ids[0]
            upper.append(_Placed(
                level=upper_index, category=owner.category, space_ids=(),
                role='sectional_clearance', rect=owner.rect, target_area=0.0,
                reason=(f'Gross sectional clearance above {space_id}; it keeps the '
                        'theatre envelope continuous while the archetype removes '
                        'the upper floor.')))
        coordinated[upper_index] = upper
        return coordinated

    if typology != 'library':
        return coordinated
    host_index = len(coordinated) - 2
    upper_index = host_index + 1
    owner = next((item for item in coordinated[host_index]
                  if 'SP-ADULT' in item.space_ids), None)
    if owner is None:
        return coordinated

    intersecting = [item for item in coordinated[upper_index]
                    if item.role in ('program', 'archetype')
                    and overlaps(item.rect, owner.rect)]
    if intersecting:
        dx = owner.rect[2] - min(item.rect[0] for item in intersecting)
        moved = []
        for item in coordinated[upper_index]:
            if item in intersecting:
                i0, j0, i1, j1 = item.rect
                item = _Placed(
                    level=item.level, category=item.category,
                    space_ids=item.space_ids, role=item.role,
                    rect=(i0 + dx, j0, i1 + dx, j1),
                    target_area=item.target_area,
                    reason=(item.reason + ' Shifted as one registered upper-floor '
                            'group clear of the library double-height volume.'))
            moved.append(item)
        coordinated[upper_index] = moved

    coordinated[upper_index].append(_Placed(
        level=upper_index, category='public', space_ids=(),
        role='sectional_clearance', rect=owner.rect, target_area=0.0,
        reason=('Gross sectional clearance above SP-ADULT; it keeps the weather '
                'envelope continuous while the archetype removes the upper floor.')))
    return coordinated


def _add_common_spine(
    layouts: list[list[_Placed]], typology: str, *,
    datums: DatumSet, grammar: ProgramVolumeGrammarId,
) -> list[_Placed]:
    """Align storeys, add their common datum, then coordinate sectional airspace.

    Sectional clearance is authored after this alignment.  Adding it before the
    per-storey north alignment let the clearance itself change the upper storey's
    local depth, shifting it one grid row away from the room whose void it governs.
    """
    depth = max(4, max((item.rect[3] for level in layouts for item in level), default=4))
    bay_x, bay_y = datums.value('bay_x_m'), datums.value('bay_y_m')
    # Reserve the common carrier before it becomes the plate authority. Its west
    # face is continuous on every floor and leads into public circulation. Grow only
    # by whole cells, within the declared approach-depth planning budget. A larger
    # site/brief decision is left visible as unresolved if this finite search fails.
    spine_cells = COMMON_SPINE_CELLS
    feasible = False
    for cells in range(COMMON_SPINE_CELLS,
                       max(COMMON_SPINE_CELLS, math.ceil(APRON_DEPTH_M / bay_x)) + 1):
        feasible = plan_boundary_switchback(
            edge_length_m=depth * bay_y, fraction=0.5,
            flight_width_m=datums.value('flight_width_m'),
            rise_m=datums.value('ground_open_height_m'),
            approach_depth_m=cells * bay_x,
            preference=CIRCULATION_FAMILIES[grammar][1]).ramp is not None
        if feasible:
            spine_cells = cells
            break
    reservation_reason = (
        f' {spine_cells} whole grid cells reserve the smallest tested carrier width '
        'with a compliant boundary-ramp plan.' if feasible else
        ' No boundary ramp fits within the declared approach budget; the minimum '
        'carrier is retained and accessibility remains unresolved.')
    aligned_layouts: list[list[_Placed]] = []
    for level, layout in enumerate(layouts):
        local_depth = max((item.rect[3] for item in layout), default=1)
        # Align occupied blocks to the north end of the shared spine. Museum
        # galleries then truly sit on the top-lit perimeter the archetype measures,
        # while smaller floors leave a terrace at the opposite end.
        dy = depth - local_depth
        aligned = _translate(layout, spine_cells - COMMON_SPINE_CELLS, dy, level)
        nearest = min(
            (item.rect[0] for item in aligned), default=spine_cells)
        aligned.append(_Placed(
            level=level, category='circulation', space_ids=(),
            role='circulation_spine',
            rect=(0, 0, spine_cells, depth), target_area=0.0,
            reason='Common vertical program datum reserved on every occupied storey; '
                   'the core and public route are checked inside this shared volume.'
                   + reservation_reason))
        if nearest > spine_cells:
            aligned.append(_Placed(
                level=level, category='circulation', space_ids=(), role='connector',
                rect=(spine_cells, dy, nearest, dy + 1), target_area=0.0,
                reason='Registered connector from the common spine to this shifted floor.'))
        aligned_layouts.append(aligned)
    coordinated = _coordinate_sectional_archetype(aligned_layouts, typology, datums=datums)
    coordinated = _add_theatre_edge_gallery(coordinated, typology)
    coordinated = _add_remote_spine(coordinated, typology)
    return [item for layout in coordinated for item in layout]


def _add_theatre_edge_gallery(
    layouts: list[list[_Placed]], typology: str,
) -> list[list[_Placed]]:
    """Reserve an occupied perimeter bay where the hall reaches the plan edge.

    The structural grid occupies cell centres, so an edge-flush auditorium has no
    outside-the-room / inside-the-building pier station. A one-cell circulation
    gallery supplies that band before the massing is fixed. It keeps room areas and
    the paired seam unchanged, and remains real floor through the transfer storeys.
    Member capacity and actual section containment still require downstream checks.
    """
    if typology != 'theater':
        return layouts
    owners = [item for item in layouts[0]
              if set(item.space_ids) & set(SHELF_PAIRS[0])]
    if len(owners) != 2:
        return layouts
    low, high = min(item.rect[1] for item in owners), max(item.rect[3] for item in owners)
    rows = (low - 1, high)
    common = min((item for item in layouts[0] if item.role == 'circulation_spine'),
                 key=lambda item: item.rect[0])
    left, right = common.rect[0], max(item.rect[2] for item in owners)
    augmented = []
    for level, layout in enumerate(layouts):
        additions = []
        for south in rows:
            start = None
            # Existing room or circulation cells already provide gross support.
            # Add only consecutive absent cells, never overwrite their ownership.
            for i in range(left, right + 1):
                missing = i < right and not any(
                    item.rect[0] <= i < item.rect[2]
                    and item.rect[1] <= south < item.rect[3] for item in layout)
                if missing and start is None:
                    start = i
                elif not missing and start is not None:
                    additions.append(_Placed(
                        level=level, category='circulation', space_ids=(), role='connector',
                        rect=(start, south, i, south + 1), target_area=0.0,
                        reason='Registered perimeter gallery connects the common carrier '
                               'to the theatre edge and reserves inboard transfer-pier stations. '
                               'Existing room ownership is preserved; structural capacity is unverified.'))
                    start = None
        augmented.append([*layout, *additions])
    return augmented


def _add_remote_spine(
    layouts: list[list[_Placed]], typology: str,
) -> list[list[_Placed]]:
    """Add one aligned far-side carrier and one narrow link on every storey.

    The existing common spine establishes the near/west datum.  The opposite plan
    bound is read after storey alignment and sectional coordination, so stepped,
    split and shifted grammars all receive the same remote grid rectangle.  A one-cell
    empty bay separates it from the former global bound.  The connector occupies the
    first free row beyond the old north bound and joins the complete top edge of both
    carriers.  It therefore forms a walkable bypass between the carriers without
    consuming any program/archetype owner rectangle.
    """
    if not layouts or not any(layout for layout in layouts):
        return layouts

    existing = [item for layout in layouts for item in layout]
    global_i1 = max(item.rect[2] for item in existing)
    global_j0 = min(item.rect[1] for item in existing)
    global_j1 = max(item.rect[3] for item in existing)
    if global_j1 - global_j0 < REMOTE_SPINE_CELLS:
        raise ValueError(
            'Program Volume plan has fewer than two grid rows for a remote stair carrier')

    spine_i0 = global_i1 + REMOTE_SPINE_GAP_CELLS
    spine_i1 = spine_i0 + REMOTE_SPINE_CELLS
    spine_j1 = global_j1
    spine_j0 = spine_j1 - REMOTE_SPINE_CELLS
    connector_j0 = global_j1
    connector_j1 = connector_j0 + REMOTE_CONNECTOR_CELLS

    brief_spaces = brief_for(typology, storeys=len(layouts))
    brief_by_id = {space.id: space for space in brief_spaces}
    remote_owner_priority = {
        space.id: (
            0 if space.category == 'public' and space.daylight == 'required'
            else 1 if space.category != 'service'
            else 2,
            -space.area_m2,
            space.id,
        )
        for space in brief_spaces
        if (space.level_preference == 'high'
            and ((space.category == 'public' and space.daylight == 'required')
                 or space.space_type == 'special_collections'))
    }

    def overlaps(a: GridRect, b: GridRect) -> bool:
        return (min(a[2], b[2]) > max(a[0], b[0])
                and min(a[3], b[3]) > max(a[1], b[1]))

    augmented: list[list[_Placed]] = []
    for level, layout in enumerate(layouts):
        # A high-level occupied room benefits from a short route to the second stair,
        # so give one eligible owner the bay face immediately inside the remote
        # carrier when that move is collision-free. Daylit public rooms take first
        # priority, followed by other occupied rooms, then service rooms. This keeps
        # the quiet reading room on its second perimeter and prevents a controlled
        # collection at the far end of a long top floor from inheriting the entire
        # north bypass as its only route. Its size is unchanged; only its lattice
        # address moves, and the bypass keeps both clusters in one storey union.
        eligible = [item for item in layout
                    if item.role == 'program'
                    and remote_owner_priority.keys() & set(item.space_ids)]
        if eligible:
            chosen = min(
                eligible,
                key=lambda item: (
                    min(remote_owner_priority[space_id]
                        for space_id in item.space_ids
                        if space_id in remote_owner_priority),
                    item.rect,
                ),
            )
            width = chosen.rect[2] - chosen.rect[0]
            depth = chosen.rect[3] - chosen.rect[1]
            remote_rect = (
                spine_i0 - width, spine_j1 - depth, spine_i0, spine_j1)
            if not any(overlaps(remote_rect, item.rect)
                       for item in layout if item is not chosen):
                moved = _Placed(
                    level=chosen.level, category=chosen.category,
                    space_ids=chosen.space_ids, role=chosen.role,
                    rect=remote_rect, target_area=chosen.target_area,
                    reason=(chosen.reason + ' Relocated by whole lattice cells to '
                            'share the remote circulation carrier'
                            + (' and its second daylit perimeter.'
                               if any(remote_owner_priority[space_id][0] == 0
                                      for space_id in chosen.space_ids
                                      if space_id in remote_owner_priority)
                               else ' and shorten the measured route to a stair.')))
                layout = [moved if item is chosen else item for item in layout]

                # A library's double-height adult room pushes the upper collection
                # rooms to the far side of its void.  Special collections now meets
                # the remote carrier on its west; wrap the periodicals room around
                # the carrier's south edge as the second part of that collection
                # cluster. Both rooms retain their authored bay count and area, while
                # each receives a direct boundary to the same circulation datum.
                if any(brief_by_id[space_id].space_type == 'special_collections'
                       for space_id in chosen.space_ids
                       if space_id in brief_by_id):
                    companions = [
                        item for item in layout
                        if item.role == 'program'
                        and any(brief_by_id[space_id].space_type == 'periodicals_media'
                                for space_id in item.space_ids
                                if space_id in brief_by_id)
                    ]
                    if companions:
                        companion = min(companions, key=lambda item: (
                            item.space_ids, item.rect))
                        companion_width = companion.rect[2] - companion.rect[0]
                        companion_depth = companion.rect[3] - companion.rect[1]
                        companion_rect = (
                            spine_i1 - companion_width,
                            spine_j0 - companion_depth,
                            spine_i1,
                            spine_j0,
                        )
                        if not any(overlaps(companion_rect, item.rect)
                                   for item in layout if item is not companion):
                            companion_moved = _Placed(
                                level=companion.level,
                                category=companion.category,
                                space_ids=companion.space_ids,
                                role=companion.role,
                                rect=companion_rect,
                                target_area=companion.target_area,
                                reason=(companion.reason + ' Wrapped by whole lattice '
                                        'cells around the remote circulation carrier '
                                        'with the high-level special-collections '
                                        'volume, shortening both measured stair routes.'))
                            layout = [companion_moved if item is companion else item
                                      for item in layout]

        near_carriers = [item for item in layout
                         if item.role == 'circulation_spine']
        if not near_carriers:
            raise ValueError(
                f'Program Volume level {level + 1} has no common circulation carrier')
        near = min(near_carriers, key=lambda item: (item.rect[0], item.rect))
        connector_i0 = near.rect[0]

        additions = []
        if near.rect[3] < connector_j0:
            additions.append(_Placed(
                level=level, category='circulation', space_ids=(),
                role='circulation_spine',
                rect=(near.rect[0], near.rect[3], near.rect[2], connector_j0),
                target_area=0.0,
                reason=('Registered extension of the common circulation carrier to '
                        'the shared north bypass datum.')))
        additions.extend([
            _Placed(
                level=level, category='circulation', space_ids=(), role='connector',
                rect=(connector_i0, connector_j0, spine_i1, connector_j1),
                target_area=0.0,
                reason=('One-cell registered north bypass connecting the common and '
                        'remote circulation carriers without crossing an owner volume.')),
            _Placed(
                level=level, category='circulation', space_ids=(),
                role='circulation_spine',
                rect=(spine_i0, spine_j0, spine_i1, spine_j1),
                target_area=0.0,
                reason=('Second cross-storey circulation carrier at the far global '
                        'plan bound; two-by-two grid cells protect a complete remote '
                        'stair core and exit separation.')),
        ])
        augmented.append([*layout, *additions])
    return augmented


def _normalise_grid(placed: list[_Placed], bay_x: float, bay_y: float
                    ) -> tuple[list[_Placed], MassingGrid]:
    min_i = min(item.rect[0] for item in placed)
    min_j = min(item.rect[1] for item in placed)
    shifted = _translate(placed, -min_i, -min_j, 0)
    # _translate assigns one level to all items; restore their original level.
    shifted = [item.__class__(
        level=source.level, category=item.category, space_ids=item.space_ids,
        role=item.role, rect=item.rect, target_area=item.target_area,
        reason=item.reason) for source, item in zip(placed, shifted)]
    max_i = max(item.rect[2] for item in shifted)
    max_j = max(item.rect[3] for item in shifted)
    x_centre = max_i / 2.0
    y_centre = max_j / 2.0
    grid = MassingGrid(
        x_lines=[round((i - x_centre) * bay_x, 4) for i in range(max_i + 1)],
        y_lines=[round((j - y_centre) * bay_y, 4) for j in range(max_j + 1)],
        band_lines=[round((j - y_centre) * bay_y, 4) for j in range(max_j + 1)])
    return shifted, grid


def _polygon_rings(geometry) -> tuple[list[Point], list[list[Point]]]:
    if geometry.geom_type != 'Polygon':
        raise ValueError(
            'a Program Volume storey must be one connected union; add a circulation '
            'connector before it becomes a massing contract')
    polygon = orient(geometry, sign=1.0)
    boundary = [(round(x, 4), round(y, 4))
                for x, y in list(polygon.exterior.coords)[:-1]]
    # Lattice plan rings are normalised counter-clockwise, including holes.  Emit
    # the Program Volume control in that same canonical orientation so an introduced
    # courtyard survives the exact roof-control identity check byte for byte.
    voids = [[(round(x, 4), round(y, 4))
              for x, y in list(orient(Polygon(ring), sign=1.0)
                               .exterior.coords)[:-1]]
             for ring in polygon.interiors]
    return boundary, voids


def organize_program_volumes(
    score: ArchitecturalScore,
    typology: str,
    *,
    grammar_id: ProgramVolumeGrammarId | None = None,
    datums: DatumSet | None = None,
    project_brief: ProjectBrief | None = None,
    legacy_controls=None,
) -> ProgramVolumeModel:
    """Turn a brief into full-height volumes, then make their unions authoritative."""
    datums = datums or compile_datum_set(score)
    if project_brief is not None:
        if typology != project_brief.typology:
            raise ValueError('volume typology must match project brief')
        if grammar_id not in (None, 'PVG-LEGACY-ELLIPSE'):
            raise ValueError('a bounded project brief currently uses PVG-LEGACY-ELLIPSE')
        from .legacy_program_layout import organize_legacy_volumes
        return organize_legacy_volumes(score, project_brief, datums, controls=legacy_controls)
    if grammar_id == 'PVG-LEGACY-ELLIPSE':
        raise ValueError('PVG-LEGACY-ELLIPSE requires a bounded project brief')
    chosen, reasons = choose_program_volume_grammar(score)
    if grammar_id is not None:
        chosen = grammar_id
        reasons = [f'Program Volume grammar pinned to {grammar_id} for comparison.']
    if chosen == 'PVG-STACKED-BANDS':
        repetition = _score_value(score, 'repetition')
        if repetition >= STACKED_PHASE_GATE:
            reasons.append(
                f'repetition {repetition:.2f} reaches {STACKED_PHASE_GATE:.2f}: '
                'stacked bands keep the same lattice phase on every storey')
        else:
            reasons.append(
                f'repetition {repetition:.2f} stays below {STACKED_PHASE_GATE:.2f}: '
                f'zero-based odd storeys shift {STACKED_PHASE_CELLS} lattice cell '
                'to form an alternating AB phase')

    storeys = _storey_count(typology, datums)
    allowance = datums.value('circulation_allowance')
    spaces = brief_for(typology, storeys=storeys)
    assigned = _assign_storeys(spaces, storeys, allowance, typology)
    bay_x = datums.value('bay_x_m')
    bay_y = datums.value('bay_y_m')
    layouts = [_layout_level(group, chosen, level, bay_x, bay_y, allowance, score)
               for level, group in enumerate(assigned)]
    placed, grid = _normalise_grid(
        _add_common_spine(layouts, typology, datums=datums, grammar=chosen), bay_x, bay_y)

    ground_open = datums.value('ground_open_height_m')
    floor_to_floor = datums.value('floor_to_floor_m')
    levels = [ProgramVolumeLevel(
        index=index + 1, id=f'L{index + 1:02d}',
        z_base=round(ground_open + index * floor_to_floor, 4),
        z_top=round(ground_open + (index + 1) * floor_to_floor, 4))
              for index in range(len(assigned))]

    volumes = []
    serials: defaultdict[tuple[int, str], int] = defaultdict(int)
    for item in placed:
        level = levels[item.level]
        key = (item.level, item.role)
        serials[key] += 1
        i0, j0, i1, j1 = item.rect
        gross = (grid.x_lines[i1] - grid.x_lines[i0]) * (
            grid.y_lines[j1] - grid.y_lines[j0])
        token = item.space_ids[0] if item.space_ids else item.role.upper()
        role = item.role
        if (item.space_ids and item.space_ids[0] in
                ARCHETYPE_SPACE_IDS.get(typology, set())):
            role = 'archetype'
        volumes.append(ProgramVolume(
            id=f'PV-{level.id}-{token}-{serials[key]:02d}',
            level_index=level.index, level_id=level.id,
            category=item.category, role=role,
            space_ids=list(item.space_ids), grid_rect=item.rect,
            target_area_m2=round(item.target_area, 2), gross_area_m2=round(gross, 2),
            reason=item.reason))

    unions = []
    for level in levels:
        sources = [volume for volume in volumes if volume.level_id == level.id]
        geometry = unary_union([box(*(
            grid.x_lines[volume.grid_rect[0]], grid.y_lines[volume.grid_rect[1]],
            grid.x_lines[volume.grid_rect[2]], grid.y_lines[volume.grid_rect[3]]))
                                for volume in sources])
        boundary, voids = _polygon_rings(geometry)
        unions.append(ProgramVolumeUnion(
            level_index=level.index, level_id=level.id,
            boundary=boundary, voids=voids,
            gross_area_m2=round(geometry.area, 2),
            source_volume_ids=[volume.id for volume in sources]))

    signature_payload = [
        chosen,
        [(volume.level_id, volume.category, volume.role, volume.space_ids,
          volume.grid_rect) for volume in volumes],
        [(union.level_id, union.boundary, union.voids) for union in unions],
    ]
    signature = hashlib.sha256(
        json.dumps(signature_payload, sort_keys=True).encode('utf-8')).hexdigest()[:12]
    highest = levels[-1]
    highest_union = unions[-1]
    roof_control = score_roof_control(
        highest_union.boundary, highest_union.voids,
        datum_z=highest.z_top,
        hierarchy_datum=datums.by_id('truss_depth_m'))
    regions = _program_volume_regions(volumes, levels)
    circulation_intent = _circulation_intent_for(
        grammar=chosen,
        topology_signature=signature,
        volumes=volumes,
        levels=levels,
        unions=unions,
        grid=grid, flight_width_m=datums.value('flight_width_m'))
    return ProgramVolumeModel(
        score_id=score.score_id, typology=typology, grammar_id=chosen,
        grammar_reason=reasons, levels=levels, grid=grid, volumes=volumes,
        level_unions=unions, topology_signature=signature,
        program_volume_regions=regions,
        circulation_intent=circulation_intent,
        roof_control=roof_control)


def compile_program_volume_candidate(
    score: ArchitecturalScore,
    *,
    typology: str | None = None,
    volume_grammar_id: ProgramVolumeGrammarId | None = None,
    facade_grammar_id: str | None = None,
    structural_system_id: str | None = None,
    site=None,
    cutaway: bool = False,
    project_brief: ProjectBrief | None = None,
    legacy_controls=None,
):
    """Run the shared building compiler from a score-authored volume contract.

    Returns ``(building, program_volumes)`` so the review model remains a first-class
    artifact beside the accepted candidate geometry.
    """
    from .program_massing import compile_from_massing
    from .selection import select_massing

    datums = compile_datum_set(score)
    if project_brief is not None:
        if typology is not None and typology != project_brief.typology:
            raise ValueError('candidate typology must match project brief')
        typology = project_brief.typology
    if typology is None:
        _legacy_family, typology, _why = select_massing(score)
    volumes = organize_program_volumes(
        score, typology, grammar_id=volume_grammar_id, datums=datums,
        project_brief=project_brief, legacy_controls=legacy_controls)
    massing = volumes.to_program_massing(
        facade_grammar_id=facade_grammar_id,
        structural_system_id=structural_system_id,
        cutaway=cutaway)
    building = compile_from_massing(massing, site=site, score=score).model_copy(
        update={'program_volume_model': volumes})
    # The shared compiler tail runs the legacy spatial checks before this first-class
    # authoring contract is attached. Re-run the same report once the exact unions are
    # present so the Program Volume solid-containment and facade-collar gates inspect
    # the completed emitted model rather than an incomplete handoff.
    from .spatial_rules import check_spatial_rules
    building.spatial = check_spatial_rules(building)
    return building, volumes


__all__ = [
    'ProgramVolume', 'ProgramVolumeCoreIntent', 'ProgramVolumeGrammarId',
    'ProgramVolumeLevel',
    'ProgramVolumeModel', 'ProgramVolumeUnion', 'choose_program_volume_grammar',
    'compile_program_volume_candidate', 'organize_program_volumes',
]
