"""Shared roof-section rules and the Program Volume roof control contract.

The roof is a real part of the Program Volume contract, not a viewport overlay.  A
volume-authored candidate carries the highest union as the roof plan and carries a
three-dimensional cap derived from the same section recipe the emitter uses.  The
recipe is intentionally architectural/conventional: it gives the student model a
coherent section envelope while leaving member capacity, connections, drainage,
waterproofing and code review open.
"""
from __future__ import annotations

import math
from typing import Literal, Mapping

from pydantic import BaseModel, Field, model_validator
from shapely.geometry import LineString, Point as ShapelyPoint, Polygon, box

from .geometry import (
    BoxGeometry,
    CONVENTION_PROFILES,
    ExtrusionGeometry,
    Geometry,
    MemberGeometry,
    QuadGeometry,
    Vector2,
    profile_from_section_id,
)

Point = tuple[float, float]

# These dimensions are architectural conventions, not a construction or code claim.
# Keeping them here makes the control volume and the roof emitter use one rule.
# Existing structural roof substrate depth.  The legacy path continues to emit this
# one layer only; a Program Volume RoofControl adds the warm-roof build-up below.
ROOF_DECK_THICKNESS_M = 0.18
# Student-detail architectural conventions.  These are visible geometry and shared
# control dimensions, not a product specification or an envelope-performance claim.
ROOF_VAPOUR_CONTROL_THICKNESS_M = 0.003
ROOF_INSULATION_FALL_THICKNESS_M = 0.180
ROOF_COVER_BOARD_THICKNESS_M = 0.015
ROOF_WATERPROOFING_THICKNESS_M = 0.005
ROOF_COPING_THICKNESS_M = 0.040
ROOF_PARAPET_WIDTH_M = 0.200
ROOF_COPING_WIDTH_M = 0.260
ROOF_PARAPET_INSULATION_UPSTAND_THICKNESS_M = 0.080
# Visible lining convention for student models; product/fixing design stays open.
ROOF_PARAPET_FINISH_THICKNESS_M = 0.020
PARAPET_UPSTAND_M = 0.58
ROOF_CONTROL_TOLERANCE_M = 1.0e-6
# Project-authored study proportions: 01_steel_frame.md, Legal variables.
# These do not size members or verify support/connection capacity.
TRUSS_DEPTH_TO_SPAN_RANGE = (1.0 / 12.0, 1.0 / 8.0)
ROOF_SPAN_RULE = 'PV-ROOF-SPAN-PROPORTION'

ROOF_ASSEMBLY_RULE = 'ROOF-WARM-ASSEMBLY-CONVENTION'
ROOF_CONTROL_RULE = 'PV-ROOF-CONTROL'
ROOF_PROFESSIONAL_REVIEW_RULE = 'PROFESSIONAL-REVIEW-REQUIRED'
ROOF_PROFESSIONAL_REVIEW_ITEMS = (
    'drainage falls, outlets and overflows',
    'membrane laps, upstands and penetrations',
    'thermal, condensation, fire and code performance',
    'product selection, tolerances, fixings and connection capacity',
)


def supported_purlin_stations(region, x0: float, x1: float, y0: float, y1: float,
                              *, width_m: float, max_spacing_m: float) -> list[float]:
    """Stations where a complete member can join both existing truss supports.

    Project the missing floor inside this bay onto Y. Each projected interval is
    forbidden to a spanning purlin, including concavities and holes between two
    individually valid supports. Subdivide only the remaining bands. No shortened
    member with an unsupported cut end is manufactured, and the roof stays intact.
    """
    if width_m <= 0 or max_spacing_m <= 0:
        raise ValueError('Purlin width and spacing must be positive')
    if x1 <= x0 or y1 <= y0:
        return []
    safe = region.buffer(-width_m / 2.0, join_style=2)
    missing = box(x0, y0, x1, y1).difference(safe)
    parts = [missing] if missing.geom_type == 'Polygon' else list(getattr(missing, 'geoms', ()))
    forbidden = sorted((part.bounds[1], part.bounds[3]) for part in parts
                       if part.geom_type == 'Polygon' and not part.is_empty and part.area > 1e-10)
    bands, cursor = [], y0
    for low, high in forbidden:
        if low > cursor:
            bands.append((cursor, low))
        cursor = max(cursor, high)
    if cursor < y1:
        bands.append((cursor, y1))
    stations = set()
    allowed = region.buffer(ROOF_CONTROL_TOLERANCE_M)
    for low, high in bands:
        count = max(1, math.ceil((high-low) / max_spacing_m))
        for index in range(count + 1):
            y = low + (high-low) * index / count
            footprint = LineString([(x0, y), (x1, y)]).buffer(
                width_m / 2.0, cap_style=2, join_style=2)
            if allowed.covers(footprint):
                stations.add(y)
    return sorted(stations)


class RoofSectionProfile(BaseModel):
    """Vertical recipe measured upward from the Program Volume roof datum."""

    truss_depth_m: float = Field(gt=0.0)
    chord_depth_m: float = Field(gt=0.0)
    purlin_depth_m: float = Field(gt=0.0)
    deck_thickness_m: float = Field(gt=0.0)
    vapour_control_thickness_m: float = Field(default=0.0, ge=0.0)
    insulation_fall_thickness_m: float = Field(default=0.0, ge=0.0)
    cover_board_thickness_m: float = Field(default=0.0, ge=0.0)
    waterproofing_thickness_m: float = Field(default=0.0, ge=0.0)
    coping_thickness_m: float = Field(default=0.0, ge=0.0)
    parapet_upstand_m: float = Field(gt=0.0)

    @property
    def truss_top_offset_m(self) -> float:
        return self.truss_depth_m

    @property
    def deck_base_offset_m(self) -> float:
        # Bottom chord -> top chord -> purlin top face.
        return self.truss_depth_m + self.chord_depth_m / 2.0 + self.purlin_depth_m

    @property
    def deck_top_offset_m(self) -> float:
        return self.deck_base_offset_m + self.deck_thickness_m

    @property
    def warm_roof_top_offset_m(self) -> float:
        return self.deck_top_offset_m + sum((
            self.vapour_control_thickness_m,
            self.insulation_fall_thickness_m,
            self.cover_board_thickness_m,
            self.waterproofing_thickness_m,
        ))

    @property
    def parapet_body_top_offset_m(self) -> float:
        return (self.warm_roof_top_offset_m + self.parapet_upstand_m
                - self.coping_thickness_m)

    @property
    def physical_top_offset_m(self) -> float:
        # The cap encloses the complete warm-roof build-up and the coping.  Coping is
        # the last ``coping_thickness_m`` of the declared parapet upstand, so it is not
        # counted twice here.
        return self.warm_roof_top_offset_m + self.parapet_upstand_m

    @property
    def has_warm_roof_layers(self) -> bool:
        return all(value > 0.0 for value in (
            self.vapour_control_thickness_m,
            self.insulation_fall_thickness_m,
            self.cover_board_thickness_m,
            self.waterproofing_thickness_m,
            self.coping_thickness_m,
        ))


class RoofAssemblyLayer(BaseModel):
    """One emitted horizontal layer measured from the roof-control datum."""

    id: str
    part_role: str
    material_profile: str
    base_offset_m: float = Field(ge=0.0)
    thickness_m: float = Field(gt=0.0)

    @property
    def top_offset_m(self) -> float:
        return self.base_offset_m + self.thickness_m


def roof_section_profile(
    truss_depth_m: float,
    *,
    chord_depth_m: float | None = None,
    purlin_depth_m: float | None = None,
    deck_thickness_m: float = ROOF_DECK_THICKNESS_M,
    parapet_upstand_m: float = PARAPET_UPSTAND_M,
    include_warm_roof_layers: bool = True,
) -> RoofSectionProfile:
    """Return the one roof section profile shared by control and emission.

    ``None`` for the section depths reads the registered convention profiles.  The
    emitter passes its active profile dimensions explicitly, so a future profile
    change cannot leave the Program Volume cap one section behind.
    """

    if chord_depth_m is None:
        chord_depth_m = CONVENTION_PROFILES['TRUSSCHORD-200x260'].depth_m
    if purlin_depth_m is None:
        purlin_depth_m = CONVENTION_PROFILES['PURLIN-120x200'].depth_m
    return RoofSectionProfile(
        truss_depth_m=truss_depth_m,
        chord_depth_m=chord_depth_m,
        purlin_depth_m=purlin_depth_m,
        deck_thickness_m=deck_thickness_m,
        vapour_control_thickness_m=(ROOF_VAPOUR_CONTROL_THICKNESS_M
                                    if include_warm_roof_layers else 0.0),
        insulation_fall_thickness_m=(ROOF_INSULATION_FALL_THICKNESS_M
                                     if include_warm_roof_layers else 0.0),
        cover_board_thickness_m=(ROOF_COVER_BOARD_THICKNESS_M
                                 if include_warm_roof_layers else 0.0),
        waterproofing_thickness_m=(ROOF_WATERPROOFING_THICKNESS_M
                                   if include_warm_roof_layers else 0.0),
        coping_thickness_m=(ROOF_COPING_THICKNESS_M
                            if include_warm_roof_layers else 0.0),
        parapet_upstand_m=parapet_upstand_m,
    )


def roof_assembly_layers(profile: RoofSectionProfile) -> list[RoofAssemblyLayer]:
    """Derive the cuttable horizontal build-up from the serialized section profile."""

    layers = [RoofAssemblyLayer(
        id='ENV-DECK-ROOF', part_role='structural_deck_substrate',
        material_profile='roof_deck_substrate',
        base_offset_m=profile.deck_base_offset_m,
        thickness_m=profile.deck_thickness_m,
    )]
    if not profile.has_warm_roof_layers:
        return layers
    cursor = profile.deck_top_offset_m
    for element_id, part_role, material_profile, thickness in (
        ('ENV-ROOF-VCL', 'vapour_control_layer', 'roof_vapour_control',
         profile.vapour_control_thickness_m),
        ('ENV-ROOF-INS', 'insulation_fall_build_up', 'roof_insulation',
         profile.insulation_fall_thickness_m),
        ('ENV-ROOF-COVER', 'cover_board', 'roof_cover_board',
         profile.cover_board_thickness_m),
        ('ENV-ROOF-MEMBRANE', 'waterproofing_membrane', 'roof_waterproofing',
         profile.waterproofing_thickness_m),
    ):
        layers.append(RoofAssemblyLayer(
            id=element_id, part_role=part_role, material_profile=material_profile,
            base_offset_m=cursor, thickness_m=thickness))
        cursor += thickness
    if not math.isclose(cursor, profile.warm_roof_top_offset_m,
                        abs_tol=ROOF_CONTROL_TOLERANCE_M):
        raise ValueError('roof assembly layers do not sum to RoofSectionProfile')
    return layers


def roof_perimeter_geometries(
    control: 'RoofControl',
    *,
    width_m: float,
    z_base: float,
    z_top: float,
    inset_m: float = 0.0,
) -> list[ExtrusionGeometry]:
    """Return exact inboard perimeter bands around the outer ring and every void.

    The band is ``plan - inset(plan)``.  This keeps every solid inside the highest
    Program Volume union while producing real upstands at roof openings.  A narrow or
    split remainder is kept as multiple stable pieces instead of being filled by a
    convex hull.
    """

    if width_m <= 0.0 or inset_m < 0.0 or z_top <= z_base:
        raise ValueError('roof perimeter band requires positive width and height')
    plan = Polygon(control.boundary, holes=control.voids)
    outer = plan if inset_m <= ROOF_CONTROL_TOLERANCE_M else plan.buffer(
        -inset_m, join_style=2)
    inner = plan.buffer(-(inset_m + width_m), join_style=2)
    if outer.is_empty:
        raise ValueError(
            f'roof perimeter inset {inset_m:.3f} m consumes the controlled plan')
    if inner.is_empty:
        raise ValueError(
            f'roof perimeter width {inset_m + width_m:.3f} m consumes the controlled plan')
    region = outer.difference(inner)
    parts = ([region] if region.geom_type == 'Polygon'
             else sorted(region.geoms, key=lambda item: item.bounds))

    def ring(coordinates) -> list[Vector2]:
        return [Vector2(x=round(float(x), 6), y=round(float(y), 6))
                for x, y in list(coordinates)[:-1]]

    return [ExtrusionGeometry(
        boundary=ring(part.exterior.coords),
        holes=[ring(interior.coords) for interior in part.interiors],
        z_base=z_base,
        z_top=z_top,
    ) for part in parts if not part.is_empty and part.area > ROOF_CONTROL_TOLERANCE_M]


class RoofSpanProportion(BaseModel):
    """Conservative plan span budget; never a measured structural support span."""

    span_m: float = Field(gt=0.0)
    depth_to_span: float = Field(ge=TRUSS_DEPTH_TO_SPAN_RANGE[0],
                                 le=TRUSS_DEPTH_TO_SPAN_RANGE[1])
    hierarchy_position: float = Field(ge=0.0, le=1.0)
    method: Literal['longest_interior_world_y_chord'] = 'longest_interior_world_y_chord'
    basis: str = ('01_steel_frame.md: project-authored span/12 to span/8 study band. '
                  'Roof plan chord before core trimming is a conservative span budget, '
                  'not verified support spacing or structural sizing.')


def roof_plan_span(boundary: list[Point], voids: list[list[Point]]) -> float:
    """Exact longest interior Y chord of a rectilinear PV union, excluding holes.

    Between consecutive vertex X stations, every Y interval is constant. Sampling
    those open bands avoids counting a boundary line along a notch as an interior
    bridge. No bounding rectangle fills a concavity or joins disconnected segments.
    """
    plan = Polygon(boundary, holes=voids)
    if not plan.is_valid or plan.is_empty:
        raise ValueError('Roof span requires a valid Program Volume plan')
    rings = [list(plan.exterior.coords), *[list(r.coords) for r in plan.interiors]]
    for ring in rings:
        if any(abs(a[0]-b[0]) > ROOF_CONTROL_TOLERANCE_M and
               abs(a[1]-b[1]) > ROOF_CONTROL_TOLERANCE_M for a, b in zip(ring, ring[1:])):
            raise ValueError('Roof span proportioning requires a rectilinear Program Volume plan')
    stations = sorted({point[0] for ring in rings for point in ring})
    _, y0, _, y1 = plan.bounds
    spans = []
    for a, b in zip(stations, stations[1:]):
        x = (a+b)/2.0
        cut = plan.intersection(LineString([(x, y0), (x, y1)]))
        parts = [cut] if cut.geom_type == 'LineString' else list(getattr(cut, 'geoms', ()))
        spans.extend(part.length for part in parts if part.geom_type == 'LineString')
    return max(spans)


class RoofControl(BaseModel):
    """The optional three-dimensional roof boundary for a Program Volume massing."""

    schema_version: Literal['mta.roof_control/1.0'] = 'mta.roof_control/1.0'
    # Kept as rings rather than a repaired Shapely polygon: the source union remains
    # inspectable and byte-for-byte comparable with the highest Program Volume union.
    boundary: list[Point] = Field(min_length=3)
    voids: list[list[Point]] = Field(default_factory=list)
    datum_z: float
    physical_top_z: float
    profile: RoofSectionProfile
    span_proportion: RoofSpanProportion | None = None
    # This is a coordination envelope for a student candidate, not a professional
    # approval.  Keep the seam explicit in serialized evidence.
    review_status: Literal['professional_review_required'] = 'professional_review_required'

    @model_validator(mode='after')
    def _valid_control(self):
        outer = Polygon(self.boundary, holes=self.voids)
        if outer.is_empty or not outer.is_valid or outer.area <= 0.0:
            raise ValueError('roof_control boundary/voids do not form a valid plan')
        if self.span_proportion is not None:
            proportion = self.span_proportion
            span = roof_plan_span(self.boundary, self.voids)
            low, high = TRUSS_DEPTH_TO_SPAN_RANGE
            ratio = low + (high-low)*proportion.hierarchy_position
            if (not math.isclose(proportion.span_m, span, abs_tol=ROOF_CONTROL_TOLERANCE_M)
                    or not math.isclose(proportion.depth_to_span, ratio, abs_tol=1e-9)
                    or not math.isclose(self.profile.truss_depth_m, span*ratio,
                                        abs_tol=ROOF_CONTROL_TOLERANCE_M)):
                raise ValueError('Roof depth must follow its measured plan span and hierarchy ratio')
            if self.profile.truss_depth_m <= self.profile.chord_depth_m:
                raise ValueError('Roof span is too short for the declared two-chord truss recipe')
        expected = self.datum_z + self.profile.physical_top_offset_m
        if not math.isclose(self.physical_top_z, expected,
                            abs_tol=ROOF_CONTROL_TOLERANCE_M):
            raise ValueError(
                'roof_control physical_top_z must equal datum_z plus the shared '
                f'roof profile offset ({expected:.5f} m)')
        return self


def roof_control_for(
    boundary: list[Point],
    voids: list[list[Point]],
    *,
    datum_z: float,
    truss_depth_m: float,
) -> RoofControl:
    """Create a control whose plan rings are copied exactly from the highest union."""

    profile = roof_section_profile(truss_depth_m)
    return RoofControl(
        boundary=[(float(x), float(y)) for x, y in boundary],
        voids=[[(float(x), float(y)) for x, y in ring] for ring in voids],
        datum_z=float(datum_z),
        physical_top_z=float(datum_z + profile.physical_top_offset_m),
        profile=profile,
    )


def score_roof_control(boundary: list[Point], voids: list[list[Point]], *,
                       datum_z: float, hierarchy_datum) -> RoofControl:
    """Let PV geometry set scale and the confidence-clamped score set proportion."""
    position = hierarchy_datum.applied_position
    if position is None:
        position = 0.5  # Unobserved hierarchy: neutral study proportion, not coverage.
    low, high = TRUSS_DEPTH_TO_SPAN_RANGE
    ratio = low + (high-low)*position
    span = roof_plan_span(boundary, voids)
    control = roof_control_for(boundary, voids, datum_z=datum_z,
                               truss_depth_m=span*ratio)
    return RoofControl.model_validate({**control.model_dump(), 'span_proportion':
        RoofSpanProportion(span_m=span, depth_to_span=ratio, hierarchy_position=position)})


def _ring_points(points) -> list[tuple[float, float]]:
    return [(float(point.x), float(point.y)) for point in points]


def assert_roof_control_matches_level(control: RoofControl, level) -> None:
    """Refuse a propagated control whose plan or datum no longer matches the roof."""

    boundary = _ring_points(level.plate)
    voids = [_ring_points(ring) for ring in level.voids]
    if control.boundary != boundary or control.voids != voids:
        raise ValueError(
            'Program Volume roof_control plan must exactly copy the highest union; '
            'downstream roof geometry cannot substitute another plate')
    if not math.isclose(control.datum_z, level.z, abs_tol=ROOF_CONTROL_TOLERANCE_M):
        raise ValueError(
            f'Program Volume roof_control datum_z={control.datum_z:.5f} does not '
            f'match roof level {level.id} z={level.z:.5f}')


def _member_profile(geometry: MemberGeometry, profiles: Mapping[str, object] | None):
    if profiles and geometry.profile in profiles:
        return profiles[geometry.profile]
    profile = CONVENTION_PROFILES.get(geometry.profile)
    if profile is not None:
        return profile
    try:
        return profile_from_section_id(geometry.profile)
    except ValueError as exc:
        raise ValueError(
            f'roof plan containment cannot measure unknown member profile '
            f'{geometry.profile}') from exc


def _plan_footprint(
    geometry: Geometry,
    *,
    profiles: Mapping[str, object] | None = None,
    thickness_m: float | None = None,
):
    """Project one emitted roof primitive to its conservative physical footprint.

    Centre-lines are buffered by the largest horizontal section dimension. This is
    deliberately conservative: a profile crossing the Program Volume edge or a void
    is rejected even when its centre-line still looks safely inside in plan.
    """

    if isinstance(geometry, ExtrusionGeometry):
        return Polygon(_ring_points(geometry.boundary),
                       holes=[_ring_points(ring) for ring in geometry.holes])
    if isinstance(geometry, MemberGeometry):
        profile = _member_profile(geometry, profiles)
        plan_span = max(
            math.hypot(b.x - a.x, b.y - a.y)
            for a, b in zip(geometry.path, geometry.path[1:]))
        vertical_span = max(
            abs(b.z - a.z) for a, b in zip(geometry.path, geometry.path[1:]))
        # Roof chords, purlins and parapets run horizontally, so the profile width
        # is the plan breadth and the section depth is vertical. A steep/diagonal
        # member gets the larger conservative radius because its local section can
        # project in both plan directions.
        radius = (profile.width_m / 2.0 if plan_span >= vertical_span
                  else max(profile.width_m, profile.depth_m) / 2.0)
        line = LineString([(point.x, point.y) for point in geometry.path])
        if line.length <= ROOF_CONTROL_TOLERANCE_M:
            return ShapelyPoint(geometry.path[0].x, geometry.path[0].y).buffer(radius)
        return line.buffer(radius, cap_style=2, join_style=2)
    if isinstance(geometry, BoxGeometry):
        angle = geometry.rotation_z
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        half_x, half_y = geometry.size.x / 2.0, geometry.size.y / 2.0
        corners = []
        for sx, sy in ((-half_x, -half_y), (half_x, -half_y),
                       (half_x, half_y), (-half_x, half_y)):
            corners.append((geometry.center.x + sx * cos_a - sy * sin_a,
                            geometry.center.y + sx * sin_a + sy * cos_a))
        return Polygon(corners)
    if isinstance(geometry, QuadGeometry):
        points = [(point.x, point.y) for point in geometry.corners]
        # Vertical panels project to a line; horizontal panels project to a polygon.
        unique = list(dict.fromkeys(points))
        if len(unique) < 3 or Polygon(unique).area <= ROOF_CONTROL_TOLERANCE_M:
            footprint = LineString(unique[:2]) if len(unique) >= 2 else LineString()
        else:
            footprint = Polygon(unique)
        return (footprint.buffer(thickness_m / 2.0, join_style=2)
                if thickness_m and thickness_m > 0.0 else footprint)
    raise TypeError(f'unsupported roof geometry {type(geometry)!r}')


def roof_geometry_max_z(
    geometry: Geometry,
    *,
    profiles: Mapping[str, object] | None = None,
    thickness_m: float | None = None,
) -> float:
    """Return the conservative top of an emitted primitive, including its profile."""

    if isinstance(geometry, MemberGeometry):
        profile = _member_profile(geometry, profiles)
        top = max(point.z for point in geometry.path) + max(
            profile.width_m, profile.depth_m) / 2.0
    elif isinstance(geometry, ExtrusionGeometry):
        top = geometry.z_top
    elif isinstance(geometry, QuadGeometry):
        top = max(point.z for point in geometry.corners)
    else:
        top = geometry.center.z + geometry.size.z / 2.0
    # Read primitive coordinates, not viewport compatibility bounds: those round
    # centre/size and pad thin bodies, so they cannot establish a physical cap.
    # A Quad is a zero-thickness carrier and needs its declared construction depth.
    # Boxes and extrusions already carry the complete physical body; adding their
    # metadata thickness again would enlarge them twice during control validation.
    if (isinstance(geometry, QuadGeometry)
            and thickness_m is not None and thickness_m > 0.0):
        top += thickness_m / 2.0
    return top


def validate_roof_emission(
    control: RoofControl,
    emitted: list[tuple[str, Geometry] | tuple[str, Geometry, float | None]],
    *,
    profiles: Mapping[str, object] | None = None,
    tolerance: float = ROOF_CONTROL_TOLERANCE_M,
) -> None:
    """Validate roof primitives against the declared 3D cap and plan region."""

    plan = Polygon(control.boundary, holes=control.voids)
    if not plan.is_valid or plan.is_empty:
        raise ValueError('Program Volume roof_control plan is invalid')
    allowed = plan.buffer(tolerance)
    for item in emitted:
        element_id, geometry = item[0], item[1]
        thickness_m = item[2] if len(item) > 2 else None
        top = roof_geometry_max_z(geometry, profiles=profiles,
                                  thickness_m=thickness_m)
        if top > control.physical_top_z + tolerance:
            raise ValueError(
                f'Program Volume roof cap exceeded by {element_id}: '
                f'{top:.9f} m > physical_top_z {control.physical_top_z:.9f} m '
                f'(excess {top-control.physical_top_z:.9g} m; tolerance {tolerance:g} m)')
        footprint = _plan_footprint(geometry, profiles=profiles,
                                    thickness_m=thickness_m)
        if not allowed.covers(footprint):
            raise ValueError(
                f'Program Volume roof plan exceeded by {element_id}: emitted '
                'roof geometry lies outside the highest-union boundary or voids')


__all__ = [
    'PARAPET_UPSTAND_M',
    'ROOF_ASSEMBLY_RULE',
    'ROOF_CONTROL_RULE',
    'ROOF_COPING_THICKNESS_M',
    'ROOF_COPING_WIDTH_M',
    'ROOF_CONTROL_TOLERANCE_M',
    'ROOF_COVER_BOARD_THICKNESS_M',
    'ROOF_DECK_THICKNESS_M',
    'ROOF_INSULATION_FALL_THICKNESS_M',
    'ROOF_PARAPET_INSULATION_UPSTAND_THICKNESS_M',
    'ROOF_PARAPET_WIDTH_M',
    'ROOF_PROFESSIONAL_REVIEW_ITEMS',
    'ROOF_PROFESSIONAL_REVIEW_RULE',
    'ROOF_VAPOUR_CONTROL_THICKNESS_M',
    'ROOF_WATERPROOFING_THICKNESS_M',
    'RoofAssemblyLayer',
    'RoofControl',
    'RoofSectionProfile',
    'RoofSpanProportion',
    'assert_roof_control_matches_level',
    'roof_assembly_layers',
    'roof_control_for',
    'roof_plan_span',
    'score_roof_control',
    'roof_geometry_max_z',
    'roof_perimeter_geometries',
    'roof_section_profile',
    'validate_roof_emission',
]
