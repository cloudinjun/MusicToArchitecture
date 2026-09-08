"""Program Volume facade authority and its shared geometric validator.

The score proposes a facade stand-off, the selected tectonic scales it, and the
selected grammar may clamp it.  This module records that sequence before the envelope
emitter runs and derives every controlled ring from the Program Volume union with a
true parallel offset.  It does not edit the Program Volume artifact: its source digest
is copied into the control so the form decision and the downstream facade decision
remain independently auditable.

The control is a student coordination envelope.  It does not claim weather, thermal,
fire, structural, connection, drainage, or code compliance.
"""
from __future__ import annotations

import math
from typing import Iterable, Literal, TYPE_CHECKING

from pydantic import BaseModel, Field, model_validator
from shapely.geometry import Point as ShapelyPoint, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

if TYPE_CHECKING:  # imports only for type checking; runtime callers are duck typed
    from .grammar_specs import GrammarSpec
    from .tectonics import EnvelopeTectonic


Point = tuple[float, float]
FacadeRole = Literal[
    'weather_skin', 'recessed_infill', 'return_tie', 'outboard_screen'
]
FacadeResolutionStatus = Literal['resolved', 'provisional_unevaluated']
FacadeValidationStatus = Literal['failed', 'unevaluated']

FACADE_CONTROL_TOLERANCE_M = 1.0e-5
CANONICAL_FACADE_ROLES: tuple[FacadeRole, ...] = (
    'weather_skin', 'recessed_infill', 'return_tie', 'outboard_screen')


def _ring(points) -> list[Point]:
    return [(float(point.x), float(point.y))
            if hasattr(point, 'x') else (float(point[0]), float(point[1]))
            for point in points]


def _rings_of(polygon: Polygon) -> tuple[list[Point], list[list[Point]]]:
    polygon = orient(polygon, sign=1.0)
    outer = [(round(float(x), 6), round(float(y), 6))
             for x, y in list(polygon.exterior.coords)[:-1]]
    holes = [[(round(float(x), 6), round(float(y), 6))
              for x, y in list(ring.coords)[:-1]]
             for ring in polygon.interiors]
    return outer, holes


def _authoring_union_rings(lattice, level) -> tuple[list[Point], list[list[Point]]]:
    """Read the immutable Program Volume union for one level when it is available.

    Archetype carving may later notch or open a floor plate.  That operation controls
    internal floor, while the facade remains registered outboard of the gross Program
    Volume massing.  Falling back to the level rings keeps focused/legacy fixtures
    compatible when no Program Volume regions exist.
    """
    roof = getattr(lattice, 'roof_control', None)
    if roof is not None and level.kind == 'roof':
        return list(roof.boundary), [list(ring) for ring in roof.voids]
    regions = [region for region in getattr(lattice, 'program_volume_regions', ())
               if region.level_id == level.id]
    if not regions:
        return _ring(level.plate), [_ring(ring) for ring in level.voids]
    source = unary_union([box(*region.resolve_bounds(lattice)) for region in regions])
    if source.is_empty or source.geom_type != 'Polygon' or not source.is_valid:
        raise ValueError(
            f'{level.id} Program Volume regions do not form one valid facade union')
    return _rings_of(source)


def parallel_outboard_rings(
    boundary,
    voids: Iterable[Iterable] = (),
    distance_m: float = 0.0,
) -> tuple[list[Point], list[list[Point]]]:
    """Return a square-joined true parallel offset, including surviving voids.

    Shapely's polygon buffer operates on the exterior and every interior ring.  An
    outward facade offset therefore expands a concave exterior while contracting its
    courtyard holes by the same measured distance.  A split or erased result is
    refused because the facade emitter accepts one controlled polygon per storey.
    """

    distance = float(distance_m)
    if not math.isfinite(distance) or distance < 0.0:
        raise ValueError('facade offset distance must be finite and non-negative')
    source_boundary = _ring(boundary)
    source_voids = [_ring(ring) for ring in voids]
    source = Polygon(source_boundary, holes=source_voids)
    if source.is_empty or not source.is_valid or source.area <= 0.0:
        raise ValueError('facade source boundary/voids do not form a valid polygon')
    shifted = source if distance <= FACADE_CONTROL_TOLERANCE_M else source.buffer(
        distance, join_style=2)
    if shifted.is_empty or shifted.geom_type != 'Polygon' or not shifted.is_valid:
        raise ValueError(
            f'facade parallel offset {distance:.3f} m produced '
            f'{shifted.geom_type}; one valid polygon is required')
    return _rings_of(shifted)


class FacadeLevelControl(BaseModel):
    """Source and weather-plane rings for a storey or the registered roof band."""

    level_id: str
    z_base: float
    z_top: float
    source_boundary: list[Point] = Field(min_length=3)
    source_voids: list[list[Point]] = Field(default_factory=list)
    weather_boundary: list[Point] = Field(min_length=3)
    weather_voids: list[list[Point]] = Field(default_factory=list)

    @model_validator(mode='after')
    def _valid_rings(self):
        source = Polygon(self.source_boundary, holes=self.source_voids)
        weather = Polygon(self.weather_boundary, holes=self.weather_voids)
        if (source.is_empty or weather.is_empty or not source.is_valid
                or not weather.is_valid or source.area <= 0.0
                or weather.area <= 0.0):
            raise ValueError(f'{self.level_id} facade control contains an invalid ring')
        if self.z_top <= self.z_base:
            raise ValueError(f'{self.level_id} facade control has no positive height')
        return self


class FacadeControl(BaseModel):
    """Resolved facade collar carried beside the roof control on the lattice."""

    schema_version: Literal['mta.facade_control/1.0'] = 'mta.facade_control/1.0'
    program_volume_source_digest: str
    grammar_id: str
    tectonic_id: str
    score_offset_m: float = Field(ge=0.0)
    tectonic_multiplier: float
    multiplied_offset_m: float = Field(ge=0.0)
    grammar_depth_range_m: tuple[float, float] | None = None
    resolved_offset_m: float = Field(ge=0.0)
    resolution_status: FacadeResolutionStatus
    resolution_reason: str
    outboard_screen_allowance_m: float = Field(default=0.0, ge=0.0)
    levels: list[FacadeLevelControl] = Field(min_length=1)
    canonical_roles: tuple[FacadeRole, ...] = CANONICAL_FACADE_ROLES
    review_status: Literal['professional_review_required'] = (
        'professional_review_required')

    @model_validator(mode='after')
    def _valid_resolution(self):
        expected_multiplied = abs(self.score_offset_m * self.tectonic_multiplier)
        if not math.isclose(self.multiplied_offset_m, expected_multiplied,
                            abs_tol=FACADE_CONTROL_TOLERANCE_M):
            raise ValueError(
                'multiplied_offset_m must resolve after score_offset_m and the '
                'tectonic multiplier')
        if self.grammar_id == 'FCD-09-CRITICAL-REGIONALISM':
            if (self.grammar_depth_range_m is not None
                    or self.resolution_status != 'provisional_unevaluated'):
                raise ValueError(
                    'FCD-09 publishes no reliable universal depth range; its facade '
                    'offset must remain provisional_unevaluated')
        if self.grammar_depth_range_m is None:
            expected = self.multiplied_offset_m
            if self.resolution_status != 'provisional_unevaluated':
                raise ValueError('an absent grammar depth range must remain unevaluated')
        else:
            low, high = self.grammar_depth_range_m
            if low < 0.0 or high < low:
                raise ValueError('grammar facade depth range is invalid')
            expected = min(high, max(low, self.multiplied_offset_m))
            if self.resolution_status != 'resolved':
                raise ValueError('a published grammar depth range resolves the offset')
        if not math.isclose(self.resolved_offset_m, expected,
                            abs_tol=FACADE_CONTROL_TOLERANCE_M):
            raise ValueError(
                'resolved_offset_m must follow score offset -> tectonic multiplier '
                '-> grammar range clamp, in that order')
        if tuple(self.canonical_roles) != CANONICAL_FACADE_ROLES:
            raise ValueError('FacadeControl must publish the four canonical roles')

        for level in self.levels:
            expected_boundary, expected_voids = parallel_outboard_rings(
                level.source_boundary, level.source_voids, self.resolved_offset_m)
            expected_shape = Polygon(expected_boundary, holes=expected_voids)
            actual_shape = Polygon(level.weather_boundary, holes=level.weather_voids)
            if not actual_shape.equals_exact(
                    expected_shape, FACADE_CONTROL_TOLERANCE_M):
                symmetric = actual_shape.symmetric_difference(expected_shape).area
                if symmetric > FACADE_CONTROL_TOLERANCE_M:
                    raise ValueError(
                        f'{level.level_id} weather rings are not the exact parallel '
                        f'offset declared by FacadeControl ({symmetric:.6f} m2 differs)')
        return self

    def level(self, level_id: str) -> FacadeLevelControl | None:
        return next((level for level in self.levels if level.level_id == level_id), None)


class FacadeControlFinding(BaseModel):
    """One measured collar failure or an explicitly unevaluated control input."""

    element_id: str | None = None
    role: FacadeRole | None = None
    status: FacadeValidationStatus
    measure: float = 0.0
    unit: str = 'unmeasured'
    detail: str


def _datum_value(datums, name: str, fallback: float = 0.0) -> float:
    try:
        return float(datums.value(name))
    except (AttributeError, KeyError, TypeError, ValueError):
        return float(fallback)


def facade_band_levels(lattice):
    """Physical facade hosts; the roof band adds no occupied room or storey."""
    levels = list(getattr(lattice, 'occupied', ()))
    control = getattr(lattice, 'roof_control', None)
    if control is not None:
        from .roof import assert_roof_control_matches_level
        roof = lattice.roof
        assert_roof_control_matches_level(control, roof)
        levels.append(roof)
    return levels


def facade_control_for(lattice, datums, env: 'EnvelopeTectonic',
                       spec: 'GrammarSpec') -> FacadeControl | None:
    """Resolve a facade control without mutating its Program Volume source artifact."""

    source_digest = getattr(lattice, 'program_volume_source_digest', None)
    if not source_digest:
        return None
    score_offset = abs(_datum_value(datums, 'envelope_offset_m'))
    multiplied = abs(score_offset * float(env.setback_multiplier))

    # Critical Regionalism's guide deliberately refuses a universal depth range.
    # ``GrammarSpec.depth_range_m`` retains an old project starting interval for the
    # emitter, but it cannot be promoted to a climatic/site validation bound.
    if spec.grammar_id == 'FCD-09-CRITICAL-REGIONALISM':
        grammar_range = None
        resolved = multiplied
        status: FacadeResolutionStatus = 'provisional_unevaluated'
        reason = (
            'Score offset and tectonic multiplier are resolved, but FCD-09 requires '
            'site, latitude, orientation and material evidence before a facade depth '
            'range can be accepted; no grammar clamp is claimed.')
    else:
        grammar_range = tuple(float(value) for value in spec.depth_range_m)
        low, high = grammar_range
        resolved = min(high, max(low, multiplied))
        status = 'resolved'
        reason = (
            f'Score offset {score_offset:.3f} m x tectonic multiplier '
            f'{env.setback_multiplier:.3f} = {multiplied:.3f} m; the '
            f'{spec.grammar_id} published range {low:.3f}-{high:.3f} m resolves '
            f'the weather plane at {resolved:.3f} m.')

    # Outboard layers have a declared bounded reach beyond the weather plane.  The
    # maximum combines only dimensions already owned by the tectonic or score.
    field_depth = max((float(value) for value in env.field_depth_range_m), default=0.0)
    screen_depth = max(float(env.outboard_depth_m), field_depth)
    screen_depth = max(screen_depth, _datum_value(datums, 'shading_depth_m'))
    if _datum_value(datums, 'envelope_layer_count', 0.0) >= 2.0:
        screen_depth = max(screen_depth, resolved * 0.55)

    controls: list[FacadeLevelControl] = []
    for level in facade_band_levels(lattice):
        roof = getattr(lattice, 'roof_control', None) if level.kind == 'roof' else None
        z_top = roof.physical_top_z if roof is not None else lattice.levels[level.index + 1].z
        source_boundary, source_voids = _authoring_union_rings(lattice, level)
        weather_boundary, weather_voids = parallel_outboard_rings(
            source_boundary, source_voids, resolved)
        controls.append(FacadeLevelControl(
            level_id=level.id, z_base=float(level.z), z_top=float(z_top),
            source_boundary=source_boundary, source_voids=source_voids,
            weather_boundary=weather_boundary, weather_voids=weather_voids))

    if not controls:
        raise ValueError('Program Volume facade control requires an occupied level')
    return FacadeControl(
        program_volume_source_digest=str(source_digest),
        grammar_id=spec.grammar_id, tectonic_id=env.id,
        score_offset_m=score_offset,
        tectonic_multiplier=float(env.setback_multiplier),
        multiplied_offset_m=multiplied,
        grammar_depth_range_m=grammar_range,
        resolved_offset_m=resolved,
        resolution_status=status,
        resolution_reason=reason,
        outboard_screen_allowance_m=max(0.0, screen_depth),
        levels=controls)


def weather_plane_site_overflow(control: FacadeControl, buildable) -> dict[str, float]:
    """Measure each weather plane against the actual setback polygon.

    This is a pre-emission plane check, not proof that outboard screen bodies fit.
    """
    return {level.level_id: float(Polygon(level.weather_boundary,
            holes=level.weather_voids).difference(buildable).area)
            for level in control.levels}


_HIGH_TECH_ROLE_ADAPTER: dict[str, FacadeRole] = {
    'frame': 'outboard_screen',
    'support': 'return_tie',
    'enclosure': 'recessed_infill',
    'cassette': 'recessed_infill',
    'glazing': 'recessed_infill',
}


def canonical_role_for_fields(
    semantic_layer: str,
    subsystem: str,
    kind: str,
    part_role: str | None = None,
) -> FacadeRole | None:
    """Resolve the common role from the existing cross-grammar metadata."""

    if semantic_layer != 'envelope':
        return None
    subsystem, kind = str(subsystem), str(kind)
    if subsystem == 'roof_closure' or kind in {'roof_deck', 'parapet'}:
        return None
    # These subsystem/kind meanings are more specific than High-Tech's historical
    # ``support`` label. A screen fin and a brise-soleil are outboard layers even
    # though their connection role remains ``support`` for the High-Tech gates.
    if subsystem in {'screen', 'shading'}:
        return 'outboard_screen'
    if subsystem == 'edge_closure':
        return 'weather_skin' if kind == 'wall_panel' else 'return_tie'
    if subsystem == 'bearing_wall':
        return ('weather_skin' if kind == 'wall_panel'
                else 'recessed_infill')
    if subsystem in {'curtain_wall', 'opaque_wall', 'backing_skin'}:
        return 'weather_skin'
    if part_role in _HIGH_TECH_ROLE_ADAPTER:
        return _HIGH_TECH_ROLE_ADAPTER[part_role]
    if subsystem == 'expressed_frame':
        if kind == 'external_strut':
            return 'return_tie'
        if kind in {'spandrel_panel', 'solid_wall_panel', 'glazing_panel'}:
            return 'recessed_infill'
        return 'outboard_screen'
    if subsystem in {'lattice_screen', 'panel_field', 'applied_order'}:
        return 'outboard_screen'
    if subsystem == 'entrance':
        return ('return_tie' if kind in {'window_reveal', 'external_strut'}
                else 'recessed_infill')
    # A conceptual closure is still weather-bearing even when a new subsystem name
    # reaches the compiler before this adapter is extended.
    if kind in {'wall_panel', 'solid_wall_panel', 'glazing_panel',
                'spandrel_panel', 'backing_panel', 'facet_panel',
                'facet_glazing'}:
        return 'weather_skin'
    return None


def canonical_role_for(element) -> FacadeRole | None:
    """Adapt existing facade metadata without rewriting High-Tech ``part_role``.

    High-Tech gates continue to read ``frame/support/enclosure/cassette/glazing``.
    This adapter projects those stable roles into the four cross-grammar roles used by
    the Program Volume collar, so adding the common protocol cannot weaken its guide.
    """

    return canonical_role_for_fields(
        str(getattr(element, 'semantic_layer', '')),
        str(getattr(element, 'subsystem', '')),
        str(getattr(element, 'kind', '')),
        getattr(element, 'part_role', None))


def controlled_facade_metadata(
    control: FacadeControl,
    *,
    level_id: str,
    semantic_layer: str,
    subsystem: str,
    kind: str,
    assembly_id: str | None,
    part_role: str | None,
) -> tuple[str | None, str | None]:
    """Add stable PV facade metadata while preserving High-Tech's detailed roles."""

    canonical = canonical_role_for_fields(
        semantic_layer, subsystem, kind, part_role)
    if canonical is None:
        return assembly_id, part_role
    stable_id = f'FACADE-{control.grammar_id}-{level_id}-R00'
    return assembly_id or stable_id, part_role or canonical


def _signed_offsets(source: Polygon, footprint) -> list[float]:
    """Signed distances of the physical footprint vertices from the PV polygon."""

    polygons = ([footprint] if footprint.geom_type == 'Polygon'
                else list(getattr(footprint, 'geoms', ())))
    offsets: list[float] = []
    for polygon in polygons:
        if polygon.geom_type != 'Polygon':
            continue
        for x, y in list(polygon.exterior.coords)[:-1]:
            point = ShapelyPoint(float(x), float(y))
            offsets.append(
                -point.distance(source.boundary)
                if source.contains(point) else point.distance(source))
    return offsets


def _declared_plane_points(geometry) -> list[tuple[float, float]]:
    """Points on the semantic plane/axis, independent of physical thickness."""

    from .geometry import BoxGeometry, ExtrusionGeometry, MemberGeometry, QuadGeometry

    if isinstance(geometry, BoxGeometry):
        return [(geometry.center.x, geometry.center.y)]
    elif isinstance(geometry, MemberGeometry):
        return [(point.x, point.y) for point in geometry.path]
    elif isinstance(geometry, QuadGeometry):
        return [(point.x, point.y) for point in geometry.corners]
    elif isinstance(geometry, ExtrusionGeometry):
        representative = Polygon(
            _ring(geometry.boundary), holes=[_ring(ring) for ring in geometry.holes]
        ).representative_point()
        return [(representative.x, representative.y)]
    return []


def _normal_half_reach(element, profiles, *, radial: bool = False) -> float:
    """Conservative physical reach normal to a facade element's declared plane."""

    from .geometry import BoxGeometry, ExtrusionGeometry, MemberGeometry, QuadGeometry

    geometry = element.geometry
    if isinstance(geometry, BoxGeometry):
        # Facade boxes consistently use local X along the bay and local Y outboard.
        return float(geometry.size.y) / 2.0
    if isinstance(geometry, QuadGeometry):
        return max(0.0, float(getattr(element, 'thickness_m', 0.0) or 0.0) / 2.0)
    if isinstance(geometry, MemberGeometry):
        profile = profiles.get(geometry.profile) if profiles else None
        if profile is None:
            return 0.0
        width = float(getattr(profile, 'width_m', 0.0)
                      if hasattr(profile, 'width_m') else profile.get('width_m', 0.0))
        depth = float(getattr(profile, 'depth_m', 0.0)
                      if hasattr(profile, 'depth_m') else profile.get('depth_m', 0.0))
        return (math.hypot(width, depth) if radial else max(width, depth)) / 2.0
    if isinstance(geometry, ExtrusionGeometry):
        return 0.0
    return 0.0


def validate_facade_collar(control: FacadeControl, elements, profiles) \
        -> list[FacadeControlFinding]:
    """Measure facade elements against the same role-aware collar everywhere."""

    from .physical_geometry import physical_projection

    findings: list[FacadeControlFinding] = []
    if control.resolution_status == 'provisional_unevaluated':
        findings.append(FacadeControlFinding(
            status='unevaluated',
            detail=control.resolution_reason))

    # These polygons belong to the level contract, not to an individual panel.
    shapes = {level.level_id: (
        Polygon(level.source_boundary, holes=level.source_voids),
        Polygon(level.weather_boundary, holes=level.weather_voids))
        for level in control.levels}
    return_domains = {}

    for element in elements:
        role = canonical_role_for(element)
        if role is None:
            continue
        level = control.level(getattr(element, 'level_id', ''))
        if level is None:
            findings.append(FacadeControlFinding(
                element_id=element.id, role=role, status='unevaluated',
                detail=(f'{element.kind} has no FacadeControl level for '
                        f'{element.level_id}.')))
            continue
        try:
            footprint, _z = physical_projection(
                element.geometry, profiles,
                thickness_m=getattr(element, 'thickness_m', None))
        except ValueError as exc:
            findings.append(FacadeControlFinding(
                element_id=element.id, role=role, status='unevaluated',
                detail=f'{element.kind} physical projection is unresolved: {exc}'))
            continue
        half = _normal_half_reach(element, profiles)
        source, weather = shapes[level.level_id]

        # A return member is a relation between two controlled places, not a plane.
        # On a setback it legitimately crosses the horizontal transition between the
        # current facade and the next storey's slab. Validate its endpoints against
        # those two authorities AND its entire body against their non-convex union.
        # Endpoints alone admit a tie straight across a courtyard or an entry notch.
        from .geometry import MemberGeometry
        if role == 'return_tie' and isinstance(element.geometry, MemberGeometry):
            level_index = next(
                index for index, candidate in enumerate(control.levels)
                if candidate.level_id == level.level_id)
            adjacent = control.levels[
                max(0, level_index - 1):min(len(control.levels), level_index + 2)]
            host_shapes = [shapes[candidate.level_id][0] for candidate in adjacent]
            endpoints = [ShapelyPoint(element.geometry.path[index].x,
                                      element.geometry.path[index].y)
                         for index in (0, -1)]
            facade_zone = weather.difference(
                source.buffer(-(half + FACADE_CONTROL_TOLERANCE_M), join_style=2))
            facade_hit = any(
                facade_zone.buffer(FACADE_CONTROL_TOLERANCE_M).covers(point)
                for point in endpoints)
            host_hit = any(
                shape.buffer(half + FACADE_CONTROL_TOLERANCE_M,
                             join_style=2).covers(point)
                for shape in host_shapes for point in endpoints)
            if not facade_hit or not host_hit:
                findings.append(FacadeControlFinding(
                    element_id=element.id, role=role, status='failed',
                    measure=float((not facade_hit) + (not host_hit)), unit='endpoint',
                    detail=(f'{element.kind} return endpoints do not resolve to both '
                            'the current source-to-weather collar and a current or '
                            'adjacent Program Volume source boundary.')))
            # At a turned member the profile can rotate into any plan direction.
            # Its circumscribed radius is the half diagonal, not half the longer
            # side. This is measured section allowance; the geometric tolerance
            # and the non-convex exclusion of courtyards remain unchanged.
            radius = _normal_half_reach(element, profiles, radial=True)
            domain_key = (level.level_id, radius)
            if domain_key not in return_domains:
                return_domains[domain_key] = unary_union([weather, *host_shapes]).buffer(
                    radius + FACADE_CONTROL_TOLERANCE_M, join_style=2)
            allowed = return_domains[domain_key]
            outside = footprint.difference(allowed).area
            if outside > FACADE_CONTROL_TOLERANCE_M:
                findings.append(FacadeControlFinding(
                    element_id=element.id, role=role, status='failed',
                    measure=float(outside), unit='m2',
                    detail=(f'{element.kind} return body leaves the non-convex '
                            'union of its weather collar and adjacent Program Volumes; '
                            'valid endpoints cannot bridge an undeclared void.')))
            continue
        if role == 'outboard_screen':
            lower = control.resolved_offset_m
            upper = (control.resolved_offset_m
                     + control.outboard_screen_allowance_m)
        elif role == 'weather_skin':
            lower = upper = control.resolved_offset_m
        else:  # recessed infill and ties occupy the controlled collar
            lower, upper = 0.0, control.resolved_offset_m

        signed = _signed_offsets(source, footprint)
        if not signed:
            findings.append(FacadeControlFinding(
                element_id=element.id, role=role, status='unevaluated',
                detail=f'{element.kind} has no measurable physical plan vertices.'))
            continue
        min_offset, max_offset = min(signed), max(signed)
        declared_points = _declared_plane_points(element.geometry)
        if not declared_points:
            findings.append(FacadeControlFinding(
                element_id=element.id, role=role, status='unevaluated',
                detail=f'{element.kind} has no measurable facade plane or axis.'))
            continue
        points = [ShapelyPoint(float(x), float(y)) for x, y in declared_points]
        outer = source.buffer(upper + half + FACADE_CONTROL_TOLERANCE_M,
                              join_style=2)
        exceeds = (footprint.difference(outer).area
                   if not outer.covers(footprint) else 0.0)
        reason = ''
        if exceeds > FACADE_CONTROL_TOLERANCE_M:
            reason = 'physical body leaves the maximum outboard collar'
        elif role == 'weather_skin':
            miss = max((point.distance(weather.boundary) for point in points),
                       default=0.0)
            if miss > FACADE_CONTROL_TOLERANCE_M:
                exceeds, reason = miss, 'declared plane misses the weather ring'
        elif role == 'recessed_infill':
            miss = max((point.distance(weather) for point in points), default=0.0)
            deep = max((point.distance(source.boundary) if source.contains(point)
                        else 0.0 for point in points), default=0.0)
            if max(miss, deep) > FACADE_CONTROL_TOLERANCE_M:
                exceeds = max(miss, deep)
                reason = 'declared plane leaves the source-to-weather collar'
        elif role == 'outboard_screen':
            screen_region = source.buffer(
                upper + FACADE_CONTROL_TOLERANCE_M, join_style=2)
            miss = max((point.distance(screen_region) for point in points), default=0.0)
            deep = max((point.distance(source.boundary) if source.contains(point)
                        else 0.0 for point in points), default=0.0)
            if max(miss, deep) > FACADE_CONTROL_TOLERANCE_M:
                exceeds = max(miss, deep)
                reason = 'declared axis leaves the source-to-screen control zone'
        # A return/tie crosses the boundary to reach its internal support. Its
        # outboard extent is still checked by the physical-body test above.
        if exceeds > FACADE_CONTROL_TOLERANCE_M:
            findings.append(FacadeControlFinding(
                element_id=element.id, role=role, status='failed',
                measure=float(exceeds), unit=('m2' if 'physical body' in reason else 'm'),
                detail=(f'{element.kind} misses the {role} control: {reason} by '
                        f'{exceeds:.4f}. Allowed plane offset is '
                        f'{lower:.3f}-{upper:.3f} m; its physical footprint spans '
                        f'{min_offset:.3f}-{max_offset:.3f} m from the Program '
                        'Volume boundary.')))
    return findings


__all__ = [
    'CANONICAL_FACADE_ROLES',
    'FACADE_CONTROL_TOLERANCE_M',
    'FacadeControl',
    'FacadeControlFinding',
    'FacadeLevelControl',
    'FacadeRole',
    'canonical_role_for',
    'canonical_role_for_fields',
    'controlled_facade_metadata',
    'facade_control_for',
    'facade_band_levels',
    'parallel_outboard_rings',
    'validate_facade_collar',
]
