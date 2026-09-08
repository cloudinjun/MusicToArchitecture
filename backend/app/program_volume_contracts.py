"""Small contracts that let Program Volume meaning survive the compiler boundary.

The Program Volume geometry lives in :mod:`program_volumes`, while the common compiler
tail reads :class:`ProgramMassing` and :class:`Lattice`.  Importing the full authoring
model into those low-level modules would close several model/schema cycles.  These
records carry only the immutable facts downstream systems need: registered regions and
one circulation intent whose coordinates are still indices into the shared grid.
"""
from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .ada import RampPlan
from .approach import ArrivalAssembly

Point = tuple[float, float]
GridRect = tuple[int, int, int, int]
GridEdge = tuple[int, int, int, int]
ProgramCategory = Literal['public', 'private', 'circulation', 'service']
VolumeRole = Literal[
    'program', 'archetype', 'circulation_spine', 'connector',
    'sectional_clearance',
]

# Authored polygon rings and their boundary registration are serialized at 0.1 mm.
# This admits only arithmetic quantization, never a design-area relaxation.
PROGRAM_COORDINATE_PRECISION_M = 1e-4
# Existing core-placement arithmetic identity tolerance (0.1 micrometre), much
# smaller than serialized PV precision. It is not additional usable floor.
PLAN_IDENTITY_TOLERANCE_M = 1e-7


def covers_registered_footprint(region, footprint):
    """Compare reconstructed bounds using the same rule before and after emission."""
    return region.buffer(PLAN_IDENTITY_TOLERANCE_M).covers(footprint)


def is_exact_registered_room(rect, area_m2: float, minimum_m: float) -> bool:
    x0, y0, x1, y1 = rect
    width, depth = x1-x0, y1-y0
    error = PROGRAM_COORDINATE_PRECISION_M * (width+depth) + PROGRAM_COORDINATE_PRECISION_M**2
    return (min(width, depth) >= minimum_m-PROGRAM_COORDINATE_PRECISION_M
            and abs(width*depth-area_m2) <= error)


class ProgramVolumeRegion(BaseModel):
    """One authored volume reduced to the facts a downstream adapter may read."""

    id: str
    level_id: str
    category: ProgramCategory
    role: VolumeRole
    space_ids: list[str] = Field(default_factory=list)
    shared_route_volume_ids: list[str] = Field(
        default_factory=list, exclude_if=lambda value: not value)
    grid_rect: GridRect
    z_base: float
    z_top: float

    @model_validator(mode='after')
    def _nonempty(self):
        i0, j0, i1, j1 = self.grid_rect
        if i1 <= i0 or j1 <= j0 or self.z_top <= self.z_base:
            raise ValueError(f'{self.id} has an empty Program Volume region')
        _validate_shared_route_claim(
            volume_id=self.id,
            role=self.role,
            category=self.category,
            space_ids=self.space_ids,
            target_ids=self.shared_route_volume_ids,
        )
        return self

    def resolve_bounds(self, lattice) -> tuple[float, float, float, float]:
        """Resolve this region on the immutable Program Volume authoring grid.

        The structural grid is deliberately reframed to stair/core faces during
        compilation.  Reading ``grid_rect`` from those mutable lines would move the
        authored volume after it had already made the building.
        """
        x_lines = (getattr(lattice, 'program_volume_x_lines', None)
                   or getattr(lattice, 'x_lines', None))
        y_lines = (getattr(lattice, 'program_volume_y_lines', None)
                   or getattr(lattice, 'y_lines', None))
        if not x_lines or not y_lines:
            raise ValueError(f'{self.id} cannot resolve without a registration grid')
        i0, j0, i1, j1 = self.grid_rect
        try:
            return (float(x_lines[i0]), float(y_lines[j0]),
                    float(x_lines[i1]), float(y_lines[j1]))
        except (IndexError, TypeError) as exc:
            raise ValueError(
                f'{self.id} grid_rect {self.grid_rect} is outside the Program Volume '
                'authoring grid') from exc


def _validate_shared_route_claim(*, volume_id: str, role: VolumeRole,
                                 category: ProgramCategory,
                                 space_ids: list[str],
                                 target_ids: list[str]) -> None:
    """Validate the local shape of an opt-in shared public-floor claim.

    A region still owns one ordinary program space.  The named targets identify
    already-authored circulation geometry that may be shared by that owner; the
    model-level validator checks their identity and physical relationship.
    """
    if not target_ids:
        return
    if len(target_ids) != len(set(target_ids)):
        raise ValueError(f'{volume_id} shared route volume ids must be unique')
    if role != 'program' or category != 'circulation' or len(space_ids) != 1:
        raise ValueError(
            f'{volume_id} shared route claims require a circulation program volume '
            'with exactly one owner space')


class GridBoundaryStation(BaseModel):
    """A point on an oriented grid edge; interior is on the edge's left side."""

    level_id: str
    source_volume_id: str
    grid_edge: GridEdge
    fraction: float = Field(default=0.5, ge=0.0, le=1.0)

    @model_validator(mode='after')
    def _axis_aligned(self):
        i0, j0, i1, j1 = self.grid_edge
        if (i0 == i1) == (j0 == j1):
            raise ValueError('a boundary station needs one non-empty axis-aligned edge')
        return self

    def resolve(self, grid) -> tuple[Point, Point, Point]:
        """Return world point, unit tangent and unit outward normal from a grid."""
        i0, j0, i1, j1 = self.grid_edge
        x_lines = (getattr(grid, 'program_volume_x_lines', None)
                   or getattr(grid, 'x_lines', None))
        y_lines = (getattr(grid, 'program_volume_y_lines', None)
                   or getattr(grid, 'y_lines', None))
        try:
            a = (float(x_lines[i0]), float(y_lines[j0]))
            c = (float(x_lines[i1]), float(y_lines[j1]))
        except (IndexError, TypeError) as exc:
            raise ValueError(
                f'{self.source_volume_id} entry edge {self.grid_edge} is outside the '
                'registration grid') from exc
        dx, dy = c[0] - a[0], c[1] - a[1]
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            raise ValueError(f'{self.source_volume_id} entry edge resolves to zero length')
        tangent = (dx / length, dy / length)
        # The edge is stored in counter-clockwise order, so the building is to its
        # left and the exterior is to its right.
        outward = (tangent[1], -tangent[0])
        point = (a[0] + dx * self.fraction, a[1] + dy * self.fraction)
        return point, tangent, outward


class ProgramCirculationIntent(BaseModel):
    """The spatial decision; code dimensions remain owned by the route planners."""

    source_volume_digest: str
    carrier_volume_ids: list[str] = Field(min_length=1)
    connector_volume_ids: list[str] = Field(default_factory=list)
    entry_station: GridBoundaryStation
    public_stair_family: Literal[
        'broad_straight', 'terraced_cascade', 'bridge_split',
    ]
    ramp_preference: Literal[
        'edge_parallel', 'terrace_return', 'notch_switchback',
    ]
    entry_floor_elevation_m: float = Field(ge=0.0)
    approach_depth_m: float = Field(gt=0.0)
    approach_depth_provenance: str
    reason: str
    arrival_assembly: ArrivalAssembly | None = Field(default=None,
        exclude_if=lambda value: value is None)


class CirculationFinding(BaseModel):
    id: str
    status: Literal['passed', 'failed', 'unevaluated']
    subject: str
    detail: str


class ResolvedCirculationPlan(BaseModel):
    """What was actually emitted and checked from one circulation intent."""

    intent: ProgramCirculationIntent
    primary_core_ids: list[str] = Field(default_factory=list)
    public_stair_ids: list[str] = Field(default_factory=list)
    ramp_plan: RampPlan | None = None
    attachment_portal_id: str | None = None
    exterior_exception_ids: list[str] = Field(default_factory=list)
    findings: list[CirculationFinding] = Field(default_factory=list)

    @property
    def status(self) -> Literal['passed', 'failed', 'unevaluated']:
        if any(item.status == 'failed' for item in self.findings):
            return 'failed'
        if (not self.findings
                or any(item.status == 'unevaluated' for item in self.findings)):
            return 'unevaluated'
        return 'passed'


__all__ = [
    'CirculationFinding', 'GridBoundaryStation', 'ProgramCirculationIntent',
    'ProgramVolumeRegion', 'ResolvedCirculationPlan',
]
