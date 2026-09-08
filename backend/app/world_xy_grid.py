"""World-XY column candidates against actual Program Volume polygons.

This planning layer preserves failed fits and transfer conditions; it does not size
members or claim structural feasibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
import re
from typing import Iterable, Sequence

from shapely.geometry import (GeometryCollection, LineString, MultiLineString,
                              MultiPoint, MultiPolygon, Point, Polygon, box)
from shapely.geometry.base import BaseGeometry

Point2 = tuple[float, float]
PolygonInput = BaseGeometry | Sequence[Point2]
DEFAULT_SNAP_TOLERANCE_M = 1.0e-7  # float identity, not a structural allowance


@dataclass(frozen=True)
class GridBounds:
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def __post_init__(self) -> None:
        values = (self.x_min, self.y_min, self.x_max, self.y_max)
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("World XY grid bounds must be finite")
        if self.x_max <= self.x_min or self.y_max <= self.y_min:
            raise ValueError("World XY grid bounds must have positive extents")


@dataclass(frozen=True)
class WorldXYGrid:
    origin: Point2 = (0.0, 0.0)
    spacing_x: float = 6.0
    spacing_y: float = 6.0

    def __post_init__(self) -> None:
        if (len(self.origin) != 2
                or not all(math.isfinite(float(value)) for value in self.origin)):
            raise ValueError("World XY grid origin must be finite")
        if (not math.isfinite(float(self.spacing_x))
                or not math.isfinite(float(self.spacing_y))
                or self.spacing_x <= 0.0 or self.spacing_y <= 0.0):
            raise ValueError("World XY grid spacing must be finite and positive")

    def coordinate(self, axis: str, index: int) -> float:
        if axis == "x":
            return float(self.origin[0] + index * self.spacing_x)
        if axis == "y":
            return float(self.origin[1] + index * self.spacing_y)
        raise ValueError(f"Unknown World XY grid axis {axis!r}")

    def index_range(self, axis: str, bounds: GridBounds) -> range:
        if axis == "x":
            origin, spacing, low, high = self.origin[0], self.spacing_x, bounds.x_min, bounds.x_max
        elif axis == "y":
            origin, spacing, low, high = self.origin[1], self.spacing_y, bounds.y_min, bounds.y_max
        else:
            raise ValueError(f"Unknown World XY grid axis {axis!r}")
        epsilon = 1.0e-10
        start = math.ceil((low - origin) / spacing - epsilon)
        stop = math.floor((high - origin) / spacing + epsilon)
        return range(start, stop + 1)

    def node_id(self, i: int, j: int) -> str:
        return f"WXG-N-{i}-{j}"

    def registration_lines(self, axis: str, bounds: GridBounds) -> list[float]:
        """Whole world bays bracketing the plan, without fitting their pitch to it.

        Outside lines are registration only. Member emission still has to fit the
        actual floor and openings; these lines never enlarge a Program Volume.
        """
        if axis == 'x':
            low, high, origin, spacing = bounds.x_min, bounds.x_max, self.origin[0], self.spacing_x
        elif axis == 'y':
            low, high, origin, spacing = bounds.y_min, bounds.y_max, self.origin[1], self.spacing_y
        else:
            raise ValueError(f"Unknown World XY grid axis {axis!r}")
        start = math.floor((low - origin) / spacing)
        stop = math.ceil((high - origin) / spacing)
        return [self.coordinate(axis, i) for i in range(start, stop + 1)]


@dataclass(frozen=True)
class ProgramVolumeLevelFootprint:
    floor_id: str
    polygon: PolygonInput
    level_index: int | None = None


@dataclass(frozen=True)
class ColumnFootprint:
    width_m: float = 0.4
    depth_m: float = 0.4

    def __post_init__(self) -> None:
        if (not math.isfinite(float(self.width_m))
                or not math.isfinite(float(self.depth_m))
                or self.width_m <= 0.0 or self.depth_m <= 0.0):
            raise ValueError("Column footprint dimensions must be finite and positive")

    @property
    def half_width_m(self) -> float:
        return float(self.width_m) / 2.0

    @property
    def half_depth_m(self) -> float:
        return float(self.depth_m) / 2.0

    @property
    def inset_radius_m(self) -> float:
        return math.hypot(self.half_width_m, self.half_depth_m)

    def geometry_at(self, point: Point2) -> Polygon:
        x, y = point
        return box(x - self.half_width_m, y - self.half_depth_m,
                   x + self.half_width_m, y + self.half_depth_m)


@dataclass(frozen=True)
class ColumnCandidate:
    id: str
    floor_id: str
    point_xy: Point2
    grid_source: str
    grid_node_id: str | None
    grid_line_axis: str | None
    grid_line_index: int | None
    raw_boundary_anchor: Point2 | None
    boundary_provenance: str | None
    inset_distance_m: float
    fits_whole_footprint: bool
    fits_status: str
    support_status: str
    supporting_floor_ids: tuple[str, ...] = field(default_factory=tuple)
    reason: str = ""


@dataclass(frozen=True)
class WorldXYColumnPlan:
    grid: WorldXYGrid
    bounds: GridBounds
    footprint: ColumnFootprint
    candidates: tuple[ColumnCandidate, ...]
    inset_policy: str

    @property
    def fitted_candidates(self) -> tuple[ColumnCandidate, ...]:
        return tuple(item for item in self.candidates if item.fits_whole_footprint)


def _as_shape(value: PolygonInput) -> Polygon | MultiPolygon:
    if isinstance(value, (Polygon, MultiPolygon)):
        shape = value
    elif isinstance(value, BaseGeometry):
        raise ValueError("Program Volume level geometry must be Polygon or MultiPolygon")
    else:
        try:
            shape = Polygon([(float(x), float(y)) for x, y in value])
        except (TypeError, ValueError) as exc:
            raise ValueError("Program Volume level polygon must contain (x, y) points") from exc
    if shape.is_empty or not shape.is_valid or shape.area <= 0.0:
        raise ValueError("Program Volume level polygon must be valid and have positive area")
    return shape


def _geometry_points(geometry: BaseGeometry) -> Iterable[Point]:
    if geometry.is_empty:
        return
    if isinstance(geometry, Point):
        yield geometry
    elif isinstance(geometry, LineString):
        coords = list(geometry.coords)
        if coords:
            yield Point(coords[0])
            if len(coords) > 1:
                yield Point(coords[-1])
    elif isinstance(geometry, (MultiPoint, MultiLineString, GeometryCollection)):
        for item in geometry.geoms:
            yield from _geometry_points(item)


def _line(axis: str, coordinate: float, bounds: GridBounds) -> LineString:
    if axis == "x":
        points = [(coordinate, bounds.y_min), (coordinate, bounds.y_max)]
    elif axis == "y":
        points = [(bounds.x_min, coordinate), (bounds.x_max, coordinate)]
    else:
        raise ValueError(f"Unknown World XY grid axis {axis!r}")
    return LineString(points)


def _line_parameter(axis: str, point: Point2) -> float:
    return point[1] if axis == "x" else point[0]


def _inset_point(
    shape: Polygon | MultiPolygon,
    safe_shape: BaseGeometry,
    axis: str,
    line_coordinate: float,
    bounds: GridBounds,
    raw: Point2,
    tolerance: float,
) -> tuple[Point2 | None, float]:
    """Nearest safe point reachable along the original grid line."""
    raw_parameter = _line_parameter(axis, raw)
    points = _geometry_points(safe_shape.intersection(_line(axis, line_coordinate, bounds)))
    reachable: list[tuple[float, Point2]] = []
    for item in points:
        point = (float(item.x), float(item.y))
        if math.dist(point, raw) <= tolerance:
            continue
        if not shape.covers(LineString([raw, point])):
            continue
        distance = abs(_line_parameter(axis, point) - raw_parameter)
        reachable.append((distance, point))
    if reachable:
        reachable.sort(key=lambda item: (item[0], item[1][0], item[1][1]))
        point = reachable[0][1]
        return point, math.dist(point, raw)
    return None, 0.0


def _fits(shape: Polygon | MultiPolygon, footprint: ColumnFootprint, point: Point2) -> bool:
    return bool(shape.covers(footprint.geometry_at(point)))


def _point_key(point: Point2, tolerance: float) -> tuple[int, int]:
    return round(point[0] / tolerance), round(point[1] / tolerance)


def _safe_id_part(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("_")
    return result or "level"


def _add_candidate(
    table: dict[tuple[int, int], ColumnCandidate],
    candidate: ColumnCandidate,
    tolerance: float,
) -> None:
    """Deduplicate coincident edge discoveries while preserving provenance."""
    key = _point_key(candidate.point_xy, tolerance)
    prior = table.get(key)
    if prior is None:
        table[key] = candidate
        return
    anchors = [point for point in (prior.raw_boundary_anchor,
                                   candidate.raw_boundary_anchor) if point is not None]
    line_index = (prior.grid_line_index if prior.grid_line_index is not None
                  else candidate.grid_line_index)
    table[key] = replace(prior, id=min(prior.id, candidate.id),
        grid_source="+".join(sorted({prior.grid_source, candidate.grid_source})),
        grid_node_id=prior.grid_node_id or candidate.grid_node_id,
        grid_line_axis=prior.grid_line_axis or candidate.grid_line_axis,
        grid_line_index=line_index, raw_boundary_anchor=min(anchors) if anchors else None,
        boundary_provenance=prior.boundary_provenance or candidate.boundary_provenance,
        inset_distance_m=min(prior.inset_distance_m, candidate.inset_distance_m))


def _sort_key(item: ColumnCandidate) -> tuple:
    source_order = {"grid_node": 0, "grid_line_x": 1, "grid_line_y": 2}
    return (item.floor_id, source_order.get(item.grid_source, 9),
            item.grid_line_index if item.grid_line_index is not None else 0,
            item.point_xy[0], item.point_xy[1], item.id)


def plan_world_xy_columns(
    grid: WorldXYGrid,
    levels: Sequence[ProgramVolumeLevelFootprint],
    bounds: GridBounds,
    *,
    footprint: ColumnFootprint | None = None,
    column_width_m: float | None = None,
    column_depth_m: float | None = None,
    snap_tolerance_m: float = DEFAULT_SNAP_TOLERANCE_M,
) -> WorldXYColumnPlan:
    """Plan fixed-grid nodes and boundary intersections for actual level polygons.

    Bounds are caller-owned.  Boundary points move only along their source grid line
    to a conservative inset; every final axis-aligned footprint is checked directly.
    """
    if not levels:
        raise ValueError("At least one Program Volume level is required")
    if not math.isfinite(float(snap_tolerance_m)) or snap_tolerance_m <= 0.0:
        raise ValueError("snap_tolerance_m must be finite and positive")
    if footprint is not None and (column_width_m is not None or column_depth_m is not None):
        raise ValueError("Pass footprint or column_width_m/column_depth_m, not both")
    footprint = footprint or ColumnFootprint(
        width_m=0.4 if column_width_m is None else column_width_m,
        depth_m=0.4 if column_depth_m is None else column_depth_m)

    prepared = []
    for sequence_index, level in enumerate(levels):
        if not level.floor_id:
            raise ValueError("Every Program Volume level needs a non-empty floor_id")
        shape = _as_shape(level.polygon)
        order = sequence_index if level.level_index is None else int(level.level_index)
        prepared.append((order, sequence_index, level.floor_id, shape))
    prepared.sort(key=lambda row: (row[0], row[1], row[2]))
    if len({row[2] for row in prepared}) != len(prepared):
        raise ValueError("Program Volume floor_id values must be unique")
    floor_order = {row[2]: index for index, row in enumerate(prepared)}
    shapes = {row[2]: row[3] for row in prepared}
    inset_policy = (
        "negative polygon buffer by half the footprint diagonal, followed by a direct "
        "whole-footprint check against the unbuffered Program Volume")
    all_candidates: list[ColumnCandidate] = []

    for _, _, floor_id, shape in prepared:
        safe_shape = shape.buffer(-footprint.inset_radius_m, join_style=2)
        table: dict[tuple[int, int], ColumnCandidate] = {}

        for i in grid.index_range("x", bounds):
            for j in grid.index_range("y", bounds):
                point = (grid.coordinate("x", i), grid.coordinate("y", j))
                if not shape.contains(Point(point)):
                    continue
                fits = _fits(shape, footprint, point)
                _add_candidate(table, ColumnCandidate(
                    id=f"{_safe_id_part(floor_id)}-{grid.node_id(i, j)}",
                    floor_id=floor_id, point_xy=point, grid_source="grid_node",
                    grid_node_id=grid.node_id(i, j), grid_line_axis=None,
                    grid_line_index=None, raw_boundary_anchor=None,
                    boundary_provenance=None, inset_distance_m=0.0,
                    fits_whole_footprint=fits,
                    fits_status="fits" if fits else "footprint_outside_program_volume",
                    support_status="pending",
                    reason="Interior World XY node; footprint checked against actual polygon"),
                    snap_tolerance_m)

        for axis in ("x", "y"):
            for line_index in grid.index_range(axis, bounds):
                coordinate = grid.coordinate(axis, line_index)
                raw_points = sorted({
                    (float(point.x), float(point.y))
                    for point in _geometry_points(shape.boundary.intersection(
                        _line(axis, coordinate, bounds)))
                })
                for raw in raw_points:
                    resolved, inset_distance = _inset_point(
                        shape, safe_shape, axis, coordinate, bounds, raw,
                        snap_tolerance_m)
                    actual = resolved or raw
                    fits = _fits(shape, footprint, actual)
                    status = "fits" if fits else (
                        "no_inset_intersection_for_full_column_footprint"
                        if resolved is None else "footprint_outside_program_volume")
                    suffix = (f"{line_index}_{round(raw[0] / snap_tolerance_m)}_"
                              f"{round(raw[1] / snap_tolerance_m)}")
                    _add_candidate(table, ColumnCandidate(
                        id=f"{_safe_id_part(floor_id)}-B-{axis}-{suffix}",
                        floor_id=floor_id, point_xy=actual,
                        grid_source=f"grid_line_{axis}", grid_node_id=None,
                        grid_line_axis=axis, grid_line_index=line_index,
                        raw_boundary_anchor=raw,
                        boundary_provenance="program_volume_boundary",
                        inset_distance_m=inset_distance,
                        fits_whole_footprint=fits, fits_status=status,
                        support_status="pending",
                        reason="Boundary anchor followed along its World XY line to inset"),
                        snap_tolerance_m)

        lower_ids = [row[2] for row in prepared
                     if floor_order[row[2]] < floor_order[floor_id]]
        for key, candidate in list(table.items()):
            if not candidate.fits_whole_footprint:
                status, supporting = "not_fittable", ()
                reason = candidate.reason + "; failed footprint retained"
            elif not lower_ids:
                status, supporting = "grounded", ()
                reason = candidate.reason + "; no lower plate supplied"
            else:
                supporting = tuple(lower_id for lower_id in lower_ids
                                   if _fits(shapes[lower_id], footprint, candidate.point_xy))
                status = ("supported" if len(supporting) == len(lower_ids)
                          else "transfer_required")
                reason = candidate.reason + ("; full footprint supported by every lower plate"
                                             if status == "supported"
                                             else "; lower-plate miss retained as transfer_required")
            table[key] = replace(candidate, support_status=status,
                                  supporting_floor_ids=supporting, reason=reason)
        all_candidates.extend(table.values())

    return WorldXYColumnPlan(
        grid=grid, bounds=bounds, footprint=footprint,
        candidates=tuple(sorted(all_candidates, key=_sort_key)),
        inset_policy=inset_policy)


__all__ = ["ColumnCandidate", "ColumnFootprint", "GridBounds",
           "ProgramVolumeLevelFootprint", "WorldXYColumnPlan", "WorldXYGrid",
           "plan_world_xy_columns"]
