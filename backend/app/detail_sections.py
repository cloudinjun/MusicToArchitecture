"""Student-review detail sections selected and projected from the compiled model.

The detail sheet does not invent construction.  It chooses three useful cuts from the
model, calls the same geometric cutter used by the building sections, and then records
what that projection can and cannot support.  Missing membranes, insulation, flashings,
fasteners and fire-stopping stay missing and are named by the readiness report; a close
crop never upgrades them into a construction-document claim.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

from pydantic import BaseModel, Field

from .drawing_geometry import section_frame
from .drawing_standard import (
    DETAIL_10_STANDARD, DETAIL_20_STANDARD, DrawingStandard, Stroke, Tone, Weight,
)
from .drawings import Annotation, Drawing, _fit_to_annotations, compile_drawing
from .facade_control import canonical_role_for_fields
from .geometry import BoxGeometry, ExtrusionGeometry, MemberGeometry, QuadGeometry


DetailKind = Literal['roof_edge', 'facade_floor', 'entry_circulation', 'landing_access']
CheckStatus = Literal['passed', 'failed', 'unevaluated']


class DetailCheck(BaseModel):
    """One bounded statement made by a detail-readiness audit."""

    id: str
    label: str
    status: CheckStatus
    evidence: str


class DetailMaterialRole(BaseModel):
    """Visible material assignment grouped by its drawing role."""

    material_profile: str
    drawing_roles: list[str]
    element_kinds: list[str]
    element_ids: list[str]


class DetailAssemblyAudit(BaseModel):
    """One visible assembly, including its host seam or named unresolved interface."""

    assembly_id: str
    element_ids: list[str]
    part_roles: list[str]
    host_element_ids: list[str]
    unresolved_interfaces: list[str]


class DetailViewAudit(BaseModel):
    """Trace from one cropped view back to the elements that produced its marks."""

    schema_version: Literal['mta.detail_view_audit/1.0'] = 'mta.detail_view_audit/1.0'
    detail_id: str
    spec_id: str
    detail_kind: DetailKind
    scale: str
    bearing_deg: float
    target_point_m: tuple[float, float, float]
    crop_m: tuple[float, float, float, float]
    cut_bbox_m: tuple[float, float, float, float]
    cut_element_bboxes_m: dict[str, tuple[float, float, float, float]] = Field(
        default_factory=dict)
    key_dimensions_m: dict[str, float] = Field(default_factory=dict)
    target_element_ids: list[str] = Field(default_factory=list)
    target_elements_drawn: list[str] = Field(default_factory=list)
    model_element_ids: list[str] = Field(default_factory=list)
    assembly_ids: list[str] = Field(default_factory=list)
    assemblies: list[DetailAssemblyAudit] = Field(default_factory=list)
    facade_roles: list[str] = Field(default_factory=list)
    material_roles: list[DetailMaterialRole] = Field(default_factory=list)
    host_element_ids: list[str] = Field(default_factory=list)
    unresolved_interfaces: list[str] = Field(default_factory=list)
    elements_considered: int
    elements_drawn: int
    elements_cut: int
    marks: int
    source: Literal['compiled_model_projection'] = 'compiled_model_projection'
    projection_verified: bool


class DetailReadinessReport(BaseModel):
    """The review level earned by one detail, without professional status inflation."""

    schema_version: Literal['mta.detail_readiness/1.0'] = 'mta.detail_readiness/1.0'
    detail_id: str
    audience: Literal['student_design_review'] = 'student_design_review'
    status: Literal['ready_with_limitations', 'blocked']
    drawing_status: Literal['generated'] = 'generated'
    d3_status: Literal['ready_with_limitations', 'blocked']
    professional_review_required: Literal[True] = True
    construction_document_status: Literal['not_evaluated'] = 'not_evaluated'
    permit_status: Literal['not_evaluated'] = 'not_evaluated'
    checks: list[DetailCheck] = Field(default_factory=list)
    missing_layers: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class DetailCutSpec(BaseModel):
    """A selected plane and crop; all coordinates are read from model elements/datums."""

    id: str
    detail_kind: DetailKind
    title: str
    bearing_deg: float
    offset_m: float
    origin_xy: tuple[float, float]
    target_point_m: tuple[float, float, float]
    crop_width_m: float = Field(gt=0.0)
    crop_below_m: float = Field(gt=0.0)
    crop_above_m: float = Field(gt=0.0)
    scale_denominator: Literal[10, 20]
    target_element_ids: list[str]
    rationale: str
    parent_spec_id: str | None = None


@dataclass(frozen=True)
class _Element:
    group: object
    instance: object

    @property
    def id(self) -> str:
        return str(getattr(self.instance, 'id'))

    @property
    def kind(self) -> str:
        return str(getattr(self.group, 'kind'))

    @property
    def assembly_id(self) -> str | None:
        value = getattr(self.instance, 'assembly_id', None)
        return str(value) if value else None

    @property
    def part_role(self) -> str | None:
        value = getattr(self.instance, 'part_role', None)
        return str(value) if value else None

    @property
    def canonical_facade_role(self) -> str | None:
        return canonical_role_for_fields(
            str(getattr(self.group, 'semantic_layer', '')),
            str(getattr(self.group, 'subsystem', '')),
            self.kind,
            self.part_role)

    @property
    def supports(self) -> list[str]:
        return [str(value) for value in getattr(self.instance, 'supports', ())]

    @property
    def unresolved_interfaces(self) -> list[str]:
        refs = getattr(self.group, 'rule_refs', ())
        return sorted(str(ref) for ref in refs if 'UNRESOLVED' in str(ref).upper())


ROOF_KINDS = frozenset({'parapet', 'roof_deck', 'purlin', 'truss_chord', 'slab_fascia'})
FACADE_KINDS = frozenset({
    'glazing_panel', 'facet_glazing', 'mullion', 'lattice_mullion', 'screen_fin',
    'external_strut', 'frame_expression', 'spandrel_panel', 'solid_wall_panel',
    'wall_panel', 'backing_panel', 'field_panel', 'facet_panel', 'brise_soleil',
})
ENTRY_KINDS = frozenset({'entrance_door', 'entrance_head', 'entry_canopy'})
CIRCULATION_KINDS = frozenset({
    'ramp', 'ramp_landing', 'stair_landing', 'stair_half_landing', 'stair_tread',
})

_ROOF_PRIORITY = {'parapet': 0, 'roof_deck': 1, 'slab_fascia': 2, 'purlin': 3,
                  'truss_chord': 4}
_ROOF_ROLE_PRIORITY = {
    'waterproofing_membrane': 0, 'parapet_substrate': 1, 'coping': 2,
    'perimeter_closure': 3, 'structural_deck_substrate': 4,
}
_FACADE_PRIORITY_HIGH_TECH = {
    # Start on the recessed enclosure at a floor datum. The plane then runs across
    # the slab edge, carrier and exposed frame; starting on the outboard screen would
    # put the structural floor wholly behind an elevation-like cut.
    'spandrel_panel': 0, 'glazing_panel': 1, 'solid_wall_panel': 2,
    'external_strut': 3, 'frame_expression': 4, 'screen_fin': 5,
    'mullion': 6, 'backing_panel': 7,
}
_FACADE_PRIORITY = {
    'glazing_panel': 0, 'wall_panel': 1, 'solid_wall_panel': 2, 'spandrel_panel': 3,
    'mullion': 4, 'screen_fin': 5, 'external_strut': 6,
}
_ENTRY_PRIORITY = {'entrance_door': 0, 'entrance_head': 1, 'entry_canopy': 2}
_CIRCULATION_PRIORITY = {'ramp_landing': 0, 'ramp': 1, 'stair_landing': 2,
                         'stair_half_landing': 3, 'stair_tread': 4}

_MISSING_LAYERS: dict[DetailKind, list[str]] = {
    'roof_edge': [
        'continuous roofing membrane and upstand',
        'thermal insulation and vapour-control continuity',
        'tapered drainage, outlet and overflow path',
        'coping, flashing and sealed movement joint',
    ],
    'facade_floor': [
        'continuous air/water barrier at the slab edge',
        'thermal insulation and thermal-break continuity',
        'anchors, fasteners, tolerances and sealants',
        'perimeter fire-stopping and smoke seal',
    ],
    'entry_circulation': [
        'threshold waterproofing and drainage',
        'connection, fastener and support design',
        'guard/handrail termination and tactile transition',
        'movement joint and finish build-up',
    ],
    'landing_access': [
        'connection, fastener and support design',
        'guard/handrail termination and tactile transition',
        'movement joint and finish build-up',
    ],
}

# A future emitter closes a missing-layer row by emitting a physical part whose kind or
# part role says what it is. Names are deliberately broad enough to receive the roof and
# facade assembly contracts without coupling the drawing module back into either emitter.
_LAYER_EVIDENCE: dict[str, tuple[str, ...]] = {
    'continuous roofing membrane and upstand': ('membrane', 'roofing', 'weathering'),
    'thermal insulation and vapour-control continuity': ('insulation', 'vapour', 'vapor'),
    'tapered drainage, outlet and overflow path': ('drain', 'outlet', 'overflow', 'taper'),
    'coping, flashing and sealed movement joint': ('coping', 'flashing', 'movement_joint'),
    'continuous air/water barrier at the slab edge': ('air_barrier', 'water_barrier'),
    'thermal insulation and thermal-break continuity': ('insulation', 'thermal_break'),
    'anchors, fasteners, tolerances and sealants': ('anchor', 'fastener', 'sealant'),
    'perimeter fire-stopping and smoke seal': ('firestop', 'fire_stopping', 'smoke_seal'),
    'threshold waterproofing and drainage': ('threshold_membrane', 'threshold_drain', 'drain'),
    'connection, fastener and support design': ('connection', 'fastener'),
    'guard/handrail termination and tactile transition': ('guard_termination',
                                                            'handrail_termination',
                                                            'tactile_transition'),
    'movement joint and finish build-up': ('movement_joint', 'finish_build_up'),
}


def _missing_layers_for(kind: DetailKind, visible: list[_Element]) -> list[str]:
    tokens = {value.lower().replace('-', '_') for element in visible
              for value in (element.kind, element.part_role or '') if value}
    return [label for label in _MISSING_LAYERS[kind]
            if not any(any(evidence in token for token in tokens)
                       for evidence in _LAYER_EVIDENCE[label])]


def _elements(model) -> list[_Element]:
    return [_Element(group, instance) for group in model.element_groups
            for instance in group.instances]


def _centre(element: _Element) -> tuple[float, float, float]:
    geometry = element.instance.geometry
    if isinstance(geometry, BoxGeometry):
        return geometry.center.as_tuple()
    if isinstance(geometry, MemberGeometry):
        points = [point.as_tuple() for point in geometry.path]
    elif isinstance(geometry, ExtrusionGeometry):
        xy = [(point.x, point.y) for point in geometry.boundary]
        return (sum(x for x, _ in xy) / len(xy), sum(y for _, y in xy) / len(xy),
                (geometry.z_base + geometry.z_top) / 2.0)
    elif isinstance(geometry, QuadGeometry):
        points = [point.as_tuple() for point in geometry.corners]
    else:  # compatibility data is derived from the authoritative geometry
        return element.instance.position.as_tuple()
    return tuple(sum(point[i] for point in points) / len(points) for i in range(3))


def _z_span(element: _Element) -> tuple[float, float]:
    geometry = element.instance.geometry
    if isinstance(geometry, BoxGeometry):
        return (geometry.center.z - geometry.size.z / 2.0,
                geometry.center.z + geometry.size.z / 2.0)
    if isinstance(geometry, ExtrusionGeometry):
        return (geometry.z_base, geometry.z_top)
    points = (geometry.path if isinstance(geometry, MemberGeometry) else geometry.corners)
    zs = [point.z for point in points]
    return (min(zs), max(zs))


def _plan_centre(model) -> tuple[float, float]:
    points = [(point.x, point.y) for level in model.lattice.levels for point in level.plate]
    return ((min(x for x, _ in points) + max(x for x, _ in points)) / 2.0,
            (min(y for _, y in points) + max(y for _, y in points)) / 2.0)


def _bearing_from_view(dx: float, dy: float) -> float:
    if math.hypot(dx, dy) < 1.0e-8:
        return 0.0
    return round(math.degrees(math.atan2(dx, dy)) % 360.0, 6)


def _boundary_bearing(model, point: tuple[float, float, float]) -> float:
    centre = _plan_centre(model)
    # A facade detail section runs across the facade depth. `section_frame.right` is
    # the horizontal axis on paper, so align that axis with the vector into the plan;
    # the direction of view is consequently tangent to the facade.
    right = (centre[0] - point[0], centre[1] - point[1])
    if math.hypot(*right) < 1.0e-8:
        return 0.0
    return round(math.degrees(math.atan2(-right[1], right[0])) % 360.0, 6)


def _offset_for(model, origin: tuple[float, float], bearing: float) -> float:
    centre = _plan_centre(model)
    angle = math.radians(bearing)
    view = (math.sin(angle), math.cos(angle))
    return round(-((origin[0] - centre[0]) * view[0]
                   + (origin[1] - centre[1]) * view[1]), 6)


def _roof_spec(model, elements: list[_Element]) -> DetailCutSpec | None:
    candidates = [element for element in elements if element.kind in ROOF_KINDS]
    if not candidates:
        return None
    top = max(level.z for level in model.lattice.levels)
    selected = min(candidates, key=lambda element: (
        _ROOF_ROLE_PRIORITY.get(element.part_role or '', 50),
        _ROOF_PRIORITY.get(element.kind, 99), abs(_centre(element)[2] - top), element.id))
    # The roof datum is the support datum, while a warm-roof membrane can sit a full
    # truss depth above it.  Centring the crop on the lattice level consequently drew
    # the roof assembly below the crop while omitting the very membrane selected as
    # its target.  Read the elevation from that emitted solid so selection, crop and
    # projection retain one model authority.
    low, high = _z_span(selected)
    target_z = (low + high) / 2.0
    geometry = selected.instance.geometry
    if isinstance(geometry, ExtrusionGeometry):
        centre = _plan_centre(model)
        ring = [(point.x, point.y) for point in geometry.boundary]
        segments = [((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
                    for a, b in zip(ring, ring[1:] + ring[:1])]
        x, y = max(segments, key=lambda point: (
            math.dist(point, centre), point[0], point[1]))
    else:
        x, y, _ = _centre(selected)
    bearing = _boundary_bearing(model, (x, y, target_z))
    origin = (x, y)
    return DetailCutSpec(
        id='DTL-ROOF-EDGE-20', detail_kind='roof_edge', title='Roof edge detail',
        bearing_deg=bearing, offset_m=_offset_for(model, origin, bearing),
        origin_xy=origin, target_point_m=(x, y, target_z), crop_width_m=5.5,
        crop_below_m=2.6, crop_above_m=1.8, scale_denominator=20,
        target_element_ids=[selected.id],
        rationale=(f'{selected.id} is the highest-priority emitted roof-edge element; '
                   'the cut turns toward the plate centre and crosses its real solid.'))


def _facade_spec(model, elements: list[_Element]) -> DetailCutSpec | None:
    candidates = [element for element in elements if element.kind in FACADE_KINDS]
    if not candidates:
        return None
    occupied = [level for level in model.lattice.levels if level.kind != 'roof']
    high_tech = 'HIGH-TECH' in str(getattr(model, 'facade_grammar_id', '')).upper()
    priority = _FACADE_PRIORITY_HIGH_TECH if high_tech else _FACADE_PRIORITY

    choices: list[tuple[tuple[float, ...], _Element, float]] = []
    mid_z = (min(level.z for level in occupied) + max(level.z for level in occupied)) / 2.0
    for element in candidates:
        low, high = _z_span(element)
        levels = [level.z for level in occupied if low - 0.15 <= level.z <= high + 0.15]
        if not levels:
            levels = [min((level.z for level in occupied),
                          key=lambda z: abs(z - _centre(element)[2]))]
        target_z = min(levels, key=lambda z: (abs(z - mid_z), z))
        choices.append(((priority.get(element.kind, 50),
                         0 if element.assembly_id else 1,
                         abs(target_z - mid_z), element.id), element, target_z))
    _score, selected, target_z = min(choices, key=lambda choice: choice[0])
    x, y, _ = _centre(selected)
    bearing = _boundary_bearing(model, (x, y, target_z))
    origin = (x, y)
    target_ids = [selected.id]
    if selected.assembly_id:
        target_ids = sorted(element.id for element in candidates
                            if element.assembly_id == selected.assembly_id)
    identity_note = (
        'its High-tech assembly identity is retained.' if high_tech
        else 'its facade assembly identity is retained.'
    ) if selected.assembly_id else (
        'no assembly identity is present, which the audit records.'
    )
    return DetailCutSpec(
        id='DTL-FACADE-FLOOR-20', detail_kind='facade_floor',
        title=('High-tech facade–floor detail' if high_tech
               else 'Facade–floor detail'),
        bearing_deg=bearing, offset_m=_offset_for(model, origin, bearing),
        origin_xy=origin, target_point_m=(x, y, target_z), crop_width_m=5.2,
        crop_below_m=1.8, crop_above_m=2.2, scale_denominator=20,
        target_element_ids=target_ids,
        rationale=(f'{selected.id} is an emitted facade component at a real floor datum; '
                   + identity_note))


def _entry_spec(model, elements: list[_Element]) -> DetailCutSpec | None:
    entrances = [element for element in elements if element.kind in ENTRY_KINDS]
    circulation = [element for element in elements if element.kind in CIRCULATION_KINDS]
    if not entrances and not circulation:
        return None
    pair: tuple[_Element, _Element] | None = None
    if entrances and circulation:
        pair = min(((entry, route) for entry in entrances for route in circulation),
                   key=lambda item: (
                       math.dist(_centre(item[0])[:2], _centre(item[1])[:2]),
                       _ENTRY_PRIORITY.get(item[0].kind, 50),
                       _CIRCULATION_PRIORITY.get(item[1].kind, 50),
                       item[0].id, item[1].id))
        selected = [pair[0], pair[1]]
    else:
        pool = entrances or circulation
        priority = _ENTRY_PRIORITY if entrances else _CIRCULATION_PRIORITY
        selected = [min(pool, key=lambda element: (priority.get(element.kind, 50), element.id))]

    points = [_centre(element) for element in selected]
    x = sum(point[0] for point in points) / len(points)
    y = sum(point[1] for point in points) / len(points)
    levels = [level.z for level in model.lattice.levels if level.kind != 'roof']
    target_z = min(levels, key=lambda z: abs(z - min(point[2] for point in points)))
    if pair is not None:
        a, b = points
        right = (b[0] - a[0], b[1] - a[1])
        length = math.hypot(*right)
        if length > 1.0e-6:
            right = (right[0] / length, right[1] / length)
            bearing = _bearing_from_view(-right[1], right[0])
        else:
            bearing = _boundary_bearing(model, (x, y, target_z))
        crop_width = min(10.0, max(6.0, length + 3.0))
    else:
        bearing = _boundary_bearing(model, (x, y, target_z))
        crop_width = 6.0
    origin = (x, y)
    return DetailCutSpec(
        id='DTL-ENTRY-CIRCULATION-20', detail_kind='entry_circulation',
        title='Entry and circulation detail', bearing_deg=bearing,
        offset_m=_offset_for(model, origin, bearing), origin_xy=origin,
        target_point_m=(x, y, target_z), crop_width_m=crop_width,
        crop_below_m=1.0, crop_above_m=4.2, scale_denominator=20,
        target_element_ids=[element.id for element in selected],
        rationale=('The cut joins the nearest emitted entrance and circulation elements '
                   'in one vertical plane; a missing half of that pair stays visible in '
                   'the audit.'))


def _landing_spec(model, elements: list[_Element]) -> DetailCutSpec | None:
    """Select an actual floor landing and its registered doorway, including failures."""
    landings = {e.id: e for e in elements if e.part_role == 'floor_landing'}
    report = getattr(model, 'portals', None)
    portals = getattr(report, 'portals', ())
    choices = []
    for portal in portals:
        support_ids = [*portal.side_a.support_ids, *portal.side_b.support_ids]
        linked = [landings[key] for key in support_ids if key in landings]
        if linked:
            choices.append((portal, linked[0]))
    if not choices:
        return None
    levels = sorted(model.lattice.levels, key=lambda level: level.z)
    middle = (levels[0].z + levels[-1].z) / 2
    # A failed connection is the most useful review location; never filter it out.
    portal, landing = min(choices, key=lambda pair: (
        pair[0].passable, abs(pair[0].floor_z-middle), pair[0].id))
    gaps = [b.z-a.z for a,b in zip(levels,levels[1:]) if b.z>a.z]
    height = next((level.z-portal.floor_z for level in levels
                   if level.z>portal.floor_z+1e-6), min(gaps))
    x,y = portal.center
    nx,ny = portal.normal
    bearing = _bearing_from_view(-ny,nx)
    return DetailCutSpec(
        id='DTL-LANDING-ACCESS-20', detail_kind='landing_access',
        title='Stair landing and doorway', bearing_deg=bearing,
        offset_m=_offset_for(model,(x,y),bearing), origin_xy=(x,y),
        target_point_m=(x,y,portal.floor_z), crop_width_m=height*2,
        crop_below_m=height*.55, crop_above_m=height*.8, scale_denominator=20,
        target_element_ids=sorted({landing.id,*portal.door_ids}),
        rationale=(f'{portal.id} links the emitted floor landing {landing.id} to '
                   f'its doorway. Portal passable={portal.passable}; the plane follows '
                   'the portal normal, and the crop follows the storey height.'))


def select_detail_cuts(model, *, include_enlargement: bool = True) -> list[DetailCutSpec]:
    """Select the repeatable roof, facade/floor and entry/circulation detail cuts."""

    elements = _elements(model)
    selected = [spec for spec in (
        _roof_spec(model, elements), _facade_spec(model, elements),
        _entry_spec(model, elements), _landing_spec(model, elements)) if spec is not None]
    facade = next((spec for spec in selected if spec.detail_kind == 'facade_floor'), None)
    high_tech = 'HIGH-TECH' in str(getattr(model, 'facade_grammar_id', '')).upper()
    if include_enlargement and high_tech and facade is not None:
        selected.append(facade.model_copy(update={
            'id': 'DTL-FACADE-FLOOR-10',
            'title': 'High-tech facade–floor enlargement',
            'crop_width_m': 2.4,
            'crop_below_m': 1.1,
            'crop_above_m': 1.3,
            'scale_denominator': 10,
            'parent_spec_id': facade.id,
            'rationale': (facade.rationale
                          + ' The 1:10 crop enlarges the same plane and model identity.'),
        }))
    return selected


def _detail_scale_bar(drawing: Drawing) -> None:
    """A two-metre measured bar sized for a 1:20/1:10 crop."""

    u0, v0, _u1, _v1 = drawing.extents
    # The overall-width dimension occupies the first line below the crop.
    y = v0 - 1.15
    step = 0.5
    solid = Stroke(Weight.THIN, Tone.CUT)
    for index in range(4):
        x0 = u0 + step * index
        box = [(x0, y), (x0 + step, y), (x0 + step, y + 0.12), (x0, y + 0.12), (x0, y)]
        drawing.annotations.append(Annotation('line', solid, box))
        if index % 2 == 0:
            drawing.annotations.append(Annotation('fill', solid, box))
    for index in range(5):
        drawing.annotations.append(Annotation(
            'text', Stroke(Weight.FINE, Tone.CUT), text=f'{step * index:g}',
            anchor=(u0 + step * index, y - 0.16), size_mm=2.0))
    drawing.annotations.append(Annotation(
        'text', Stroke(Weight.FINE, Tone.MIDDLE),
        text=f'metres · {drawing.standard.scale.name}',
        anchor=(u0 + 2.25, y + 0.05), size_mm=2.0, align='start'))


def _detail_overall_dimensions(drawing: Drawing) -> None:
    """Dimension the actual projected crop in millimetres on two clear strings."""

    u0, v0, u1, v1 = drawing.extents
    dim = Stroke(Weight.FINE, Tone.NEAR)
    label = Stroke(Weight.FINE, Tone.CUT)
    tick = 0.12

    horizontal = v0 - 0.48
    drawing.annotations.extend([
        Annotation('line', dim, [(u0, v0), (u0, horizontal - tick)]),
        Annotation('line', dim, [(u1, v0), (u1, horizontal - tick)]),
        Annotation('line', dim, [(u0, horizontal), (u1, horizontal)]),
        Annotation('line', dim, [(u0, horizontal - tick), (u0, horizontal + tick)]),
        Annotation('line', dim, [(u1, horizontal - tick), (u1, horizontal + tick)]),
        Annotation('text', label, text=f'OVERALL {(u1 - u0) * 1000:.0f}',
                   anchor=((u0 + u1) / 2.0, horizontal + 0.14), size_mm=2.1),
    ])

    vertical = u1 + 0.48
    drawing.annotations.extend([
        Annotation('line', dim, [(u1, v0), (vertical + tick, v0)]),
        Annotation('line', dim, [(u1, v1), (vertical + tick, v1)]),
        Annotation('line', dim, [(vertical, v0), (vertical, v1)]),
        Annotation('line', dim, [(vertical - tick, v0), (vertical + tick, v0)]),
        Annotation('line', dim, [(vertical - tick, v1), (vertical + tick, v1)]),
        Annotation('text', label, text=f'OVERALL {(v1 - v0) * 1000:.0f}',
                   anchor=(vertical + 0.14, (v0 + v1) / 2.0), size_mm=2.1,
                   rotate=-90.0),
    ])


def _human_token(value: str) -> str:
    words = value.replace('-', ' ').replace('_', ' ').strip().lower()
    return words[:1].upper() + words[1:] if words else ''


def _short_note(prefix: str, values: list[str], *, limit: int = 66) -> str:
    text = prefix + ' · '.join(_human_token(value) for value in values if value)
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


def _detail_label_elements(audit, spec, index):
    """One cut representative per assembly role/material, targets first."""
    targets=set(spec.target_element_ids)
    assemblies={index[key].assembly_id for key in targets
                if key in index and index[key].assembly_id}
    selected=[]
    seen=set()
    ordered=sorted((index[key] for key in audit.cut_element_bboxes_m if key in index),
        key=lambda element:(element.id not in targets,
                            element.assembly_id not in assemblies,element.id))
    for element in ordered:
        if not (element.id in targets or element.assembly_id in assemblies
                or element.canonical_facade_role):
            continue
        role=element.part_role or element.canonical_facade_role or element.kind
        material=str(getattr(element.group,'material_profile','') or '')
        key=(role,material)
        if key in seen:
            continue
        seen.add(key)
        selected.append((element,role,material))
        if len(selected)==6:
            break
    return sorted(selected,key=lambda row:(
        -sum(audit.cut_element_bboxes_m[row[0].id][i] for i in (1,3)),row[0].id))


def _detail_evidence_notes(drawing: Drawing, spec: DetailCutSpec,
                           index: dict[str, _Element]) -> None:
    """Put the model evidence and its open seam beside the projected geometry."""

    audit: DetailViewAudit = drawing.detail_audit
    readiness: DetailReadinessReport = drawing.detail_readiness
    _u0, v0, u1, v1 = drawing.extents
    note_x = u1 + 1.05
    note_y = v1 - 0.12
    leader = Stroke(Weight.FINE, Tone.NEAR)
    ink = Stroke(Weight.FINE, Tone.CUT)
    soft = Stroke(Weight.FINE, Tone.MIDDLE)

    selected=_detail_label_elements(audit,spec,index)
    # Paper-space rows stay legible at either supported detail scale.
    spacing=drawing.standard.scale.to_metres(10.)
    label_y=note_y
    for element,role,material in selected:
        x0, y0, x1, y1 = audit.cut_element_bboxes_m[element.id]
        anchor = (x1, (y0 + y1) / 2.0)
        elbow = (u1 + 0.72, anchor[1])
        label_y=min(label_y,anchor[1])
        end = (note_x - 0.08, label_y)
        # Group thickness may describe assembly depth (or a coping width), not
        # this material layer. Only a role-specific measurement may label a size.
        material_note=_human_token(material)
        drawing.annotations.extend([
            Annotation('line', leader, [anchor, elbow, end]),
            Annotation('text', ink, text=_human_token(role), anchor=(note_x, label_y),
                       size_mm=2.5, align='start', weight=600),
            Annotation('text', soft, text=material_note,
                       anchor=(note_x,label_y-spacing*.4),size_mm=2.2,align='start'),
        ])
        label_y-=spacing

    materials = [role.material_profile for role in audit.material_roles]
    rows = [
        f'{len(audit.assemblies)} assemblies · {audit.elements_cut} cut elements',
        _short_note('Materials: ', materials[:5]),
    ]
    if audit.facade_roles:
        rows.append(_short_note('Facade roles: ', audit.facade_roles))
    if readiness.missing_layers:
        rows.append(_short_note('Open: ', readiness.missing_layers[:1]))
    rows.append('Student review · professional follow-on retained')
    for row, content in enumerate(rows):
        drawing.annotations.append(Annotation(
            'text', soft if row else ink, text=content,
            anchor=(note_x, label_y - spacing - row * spacing*.6), size_mm=2.2,
            align='start', weight=600 if row == 0 else None))


def _annotate_detail(drawing: Drawing, model, spec: DetailCutSpec,
                     index: dict[str, _Element]) -> None:
    u0, _v0, u1, v1 = drawing.extents
    target_z = spec.target_point_m[2]
    level = min(model.lattice.levels, key=lambda item: abs(item.z - target_z))
    datum = drawing.standard.stroke('grid', 'cut')
    drawing.annotations.extend([
        Annotation('line', datum, [(u0, level.z), (u1, level.z)]),
        Annotation('text', Stroke(Weight.FINE, Tone.CUT),
                   text=f'{level.id} · FFL {level.z:+.3f}',
                   anchor=(u1, level.z + 0.18), size_mm=2.2, align='end'),
        Annotation('text', Stroke(Weight.FINE, Tone.CUT),
                   text=spec.detail_kind.replace('_', ' '),
                   anchor=(u0, v1 + 0.22), size_mm=2.4, align='start', weight=600),
        Annotation('text', Stroke(Weight.FINE, Tone.MIDDLE),
                   text='PROFESSIONAL REVIEW REQUIRED',
                   anchor=(u1, v1 + 0.22), size_mm=2.1, align='end'),
    ])
    _detail_overall_dimensions(drawing)
    _detail_scale_bar(drawing)
    _detail_evidence_notes(drawing, spec, index)
    _fit_to_annotations(drawing)


def _readiness(model, spec: DetailCutSpec, drawing: Drawing,
               audit: DetailViewAudit, index: dict[str, _Element]) -> DetailReadinessReport:
    visible = [index[element_id] for element_id in audit.model_element_ids
               if element_id in index]
    assembly_ids = sorted({element.assembly_id for element in visible
                           if element.assembly_id})
    facade_roles = sorted({element.canonical_facade_role for element in visible
                           if element.canonical_facade_role})
    profiles = [getattr(element.group, 'material_profile', None) for element in visible]
    material_registry = getattr(model, 'materials', {}) or {}
    assigned = bool(profiles) and all(profile and profile in material_registry
                                      for profile in profiles)
    target_cut = sorted({mark.element_id for mark in drawing.marks
                         if mark.state == 'cut' and mark.element_id in spec.target_element_ids})
    missing = _missing_layers_for(spec.detail_kind, visible)
    dimensioned = (audit.key_dimensions_m.get('projected_width', 0.0) > 0.0
                   and audit.key_dimensions_m.get('projected_height', 0.0) > 0.0)
    host_accounted = bool(audit.assemblies) and all(
        assembly.host_element_ids or assembly.unresolved_interfaces
        for assembly in audit.assemblies)
    checks = [
        DetailCheck(
            id='D3-PROJECTION', label='Model-derived projection',
            status='passed' if audit.projection_verified else 'failed',
            evidence=(f'{len(audit.model_element_ids)} model elements produced '
                      f'{audit.marks} marks inside the crop.')),
        DetailCheck(
            id='D3-TARGET-CUT', label='Selected assembly intersects the cut',
            status='passed' if target_cut else 'failed',
            evidence=(', '.join(target_cut) if target_cut
                      else 'No selected target produced a cut mark.')),
        DetailCheck(
            id='D3-ASSEMBLY-ID', label='Assembly identity and part roles',
            status='passed' if assembly_ids else 'failed',
            evidence=(', '.join(assembly_ids) if assembly_ids
                      else 'The emitted elements carry no assembly identity for this view; '
                           'student-review detail readiness is blocked.')),
        DetailCheck(
            id='D3-KEY-DIMENSIONS', label='Cut bounds and overall dimensions',
            status='passed' if dimensioned else 'failed',
            evidence=(f'{audit.key_dimensions_m.get("projected_width", 0.0):.3f} m × '
                      f'{audit.key_dimensions_m.get("projected_height", 0.0):.3f} m '
                      'projected extent.')),
        DetailCheck(
            id='D3-MATERIAL-ASSIGNMENT', label='Material assignments resolve',
            status='passed' if assigned else 'failed',
            evidence=('Every visible element resolves into the model material registry.'
                      if assigned else
                      'One or more visible material profiles are absent or unresolved.')),
        DetailCheck(
            id='D3-HOST-INTERFACE', label='Assembly host or named unresolved interface',
            status='passed' if host_accounted else 'failed',
            evidence=(f'{len(audit.host_element_ids)} host ids and '
                      f'{len(audit.unresolved_interfaces)} named unresolved interfaces '
                      'are carried by the visible assemblies.' if host_accounted else
                      'A visible assembly has neither a resolvable host nor a named '
                      'unresolved interface.')),
        DetailCheck(
            id='D3-LAYER-BUILDUP', label='Layered construction build-up',
            status='unevaluated' if missing else 'passed',
            evidence=(('The model has no physical elements for: ' + '; '.join(missing))
                      if missing else
                      'Every declared layer family is represented by an emitted part.')),
        DetailCheck(
            id='D3-CONNECTION-DESIGN', label='Connections, tolerances and fabrication',
            status='unevaluated',
            evidence='No connection or fabrication calculation governs this detail.'),
    ]
    if audit.unresolved_interfaces:
        checks.append(DetailCheck(
            id='D3-DECLARED-INTERFACES',
            label='Declared unresolved coordination interfaces',
            status='unevaluated',
            evidence=', '.join(audit.unresolved_interfaces)
                     + ' require professional follow-on.'))
    if spec.detail_kind == 'facade_floor':
        roles = set(facade_roles)
        # FacadeControl permits two honest closure conditions. Expressed-frame
        # grammars expose recessed infill; layered screen grammars such as Critical
        # Regionalism expose a weather skin behind their outboard screen. Requiring
        # only the first mislabeled a complete screen/skin section as absent. The
        # detail still needs both a closure layer and an outboard/return relation.
        closure = {'recessed_infill', 'weather_skin'} & roles
        returns = {'return_tie', 'outboard_screen'} & roles
        role_ready = bool(closure) and bool(returns)
        checks.insert(3, DetailCheck(
            id='D3-FACADE-ROLE-COVERAGE', label='Facade control roles reach the cut',
            status='passed' if role_ready else 'failed',
            evidence=((', '.join(facade_roles) + ' are visible in the crop.')
                      if role_ready else
                      'The crop does not yet contain a weather/recessed closure plus '
                      'a return tie or outboard screen from FacadeControl.')))
    if spec.detail_kind == 'landing_access':
        portals = getattr(getattr(model, 'portals', None), 'portals', ())
        portal = next((p for p in portals if set(p.door_ids) & set(spec.target_element_ids)), None)
        checks.append(DetailCheck(
            id='D3-LANDING-ACCESS', label='Model doorway access',
            status=('unevaluated' if portal is None else
                    'passed' if portal.passable else 'failed'),
            evidence=('Portal record missing.' if portal is None else
                      f'{portal.id}: model passable={portal.passable}; not code approval.')))
    blocking_ids = {'D3-PROJECTION', 'D3-TARGET-CUT', 'D3-ASSEMBLY-ID',
                    'D3-KEY-DIMENSIONS', 'D3-MATERIAL-ASSIGNMENT',
                    'D3-HOST-INTERFACE', 'D3-FACADE-ROLE-COVERAGE', 'D3-LANDING-ACCESS'}
    blocked = any(check.status == 'failed' and check.id in blocking_ids
                  for check in checks)
    unresolved = [check.label for check in checks if check.status == 'unevaluated']
    unresolved.extend(f'interface:{identifier}' for identifier in audit.unresolved_interfaces)
    return DetailReadinessReport(
        detail_id=drawing.id,
        status='blocked' if blocked else 'ready_with_limitations',
        d3_status='blocked' if blocked else 'ready_with_limitations',
        checks=checks,
        missing_layers=missing,
        unresolved=unresolved,
        limitations=[
            'Suitable for student design review only; dimensions and interfaces require professional review.',
            'Geometry is projected from emitted model solids; no construction line is authored on the sheet.',
            'Site, code, fire, accessibility, lateral, connection, envelope and fabrication checks retain their source status.',
        ] + ([
            'Named unresolved interfaces are declared coordination seams and remain a professional follow-on.'
        ] if audit.unresolved_interfaces else []))


def _assembly_audits(visible: list[_Element]) -> list[DetailAssemblyAudit]:
    grouped: dict[str, list[_Element]] = {}
    for element in visible:
        if element.assembly_id:
            grouped.setdefault(element.assembly_id, []).append(element)
    return [DetailAssemblyAudit(
        assembly_id=assembly_id,
        element_ids=sorted(element.id for element in elements),
        part_roles=sorted({element.part_role for element in elements if element.part_role}),
        host_element_ids=sorted({host for element in elements for host in element.supports}),
        unresolved_interfaces=sorted({ref for element in elements
                                      for ref in element.unresolved_interfaces}),
    ) for assembly_id, elements in sorted(grouped.items())]


def _material_roles(drawing: Drawing, visible: list[_Element]) -> list[DetailMaterialRole]:
    grouped: dict[str, list[_Element]] = {}
    for element in visible:
        profile = str(getattr(element.group, 'material_profile', '') or '')
        if profile:
            grouped.setdefault(profile, []).append(element)
    return [DetailMaterialRole(
        material_profile=profile,
        drawing_roles=sorted({drawing.standard.role_of(element.kind) for element in elements}),
        element_kinds=sorted({element.kind for element in elements}),
        element_ids=sorted(element.id for element in elements),
    ) for profile, elements in sorted(grouped.items())]


def _cut_element_bboxes(drawing: Drawing) -> dict[str, tuple[float, float, float, float]]:
    grouped: dict[str, list[tuple[float, float]]] = {}
    for mark in drawing.marks:
        if mark.state == 'cut':
            grouped.setdefault(mark.element_id, []).extend(mark.points)
    return {element_id: (
        round(min(point[0] for point in points), 6),
        round(min(point[1] for point in points), 6),
        round(max(point[0] for point in points), 6),
        round(max(point[1] for point in points), 6),
    ) for element_id, points in sorted(grouped.items())}


def compile_detail_sections(model, *, include_enlargement: bool = True) -> list[Drawing]:
    """Project the selected cuts and bind each drawing to its audit/readiness report."""

    index = {element.id: element for element in _elements(model)}
    drawings: list[Drawing] = []
    for spec in select_detail_cuts(model, include_enlargement=include_enlargement):
        standard: DrawingStandard = (DETAIL_10_STANDARD if spec.scale_denominator == 10
                                     else DETAIL_20_STANDARD)
        plane, frame = section_frame(spec.origin_xy, spec.bearing_deg)
        target_u = frame.project(spec.target_point_m)[0]
        target_z = spec.target_point_m[2]
        crop = (target_u - spec.crop_width_m / 2.0,
                target_z - spec.crop_below_m,
                target_u + spec.crop_width_m / 2.0,
                target_z + spec.crop_above_m)
        drawing = compile_drawing(
            model, plane, frame, standard,
            drawing_id=f'DWG-{spec.id}', title=spec.title, kind='detail',
            subtitle=(f'Model-derived {standard.scale.name} section · {spec.rationale}'),
            clip_rect=crop)
        visible_ids = sorted({mark.element_id for mark in drawing.marks})
        visible = [index[element_id] for element_id in visible_ids if element_id in index]
        target_drawn = sorted(set(spec.target_element_ids) & set(visible_ids))
        assembly_ids = sorted({index[element_id].assembly_id for element_id in visible_ids
                               if element_id in index and index[element_id].assembly_id})
        facade_roles = sorted({index[element_id].canonical_facade_role
                               for element_id in visible_ids if element_id in index
                               and index[element_id].canonical_facade_role})
        assemblies = _assembly_audits(visible)
        material_roles = _material_roles(drawing, visible)
        host_ids = sorted({host for assembly in assemblies
                           for host in assembly.host_element_ids})
        unresolved = sorted({ref for assembly in assemblies
                             for ref in assembly.unresolved_interfaces})
        cut_bbox = tuple(float(value) for value in drawing.extents)
        audit = DetailViewAudit(
            detail_id=drawing.id, spec_id=spec.id, detail_kind=spec.detail_kind,
            scale=standard.scale.name, bearing_deg=spec.bearing_deg,
            target_point_m=spec.target_point_m, crop_m=crop, cut_bbox_m=cut_bbox,
            cut_element_bboxes_m=_cut_element_bboxes(drawing),
            key_dimensions_m={
                'projected_width': round(cut_bbox[2] - cut_bbox[0], 6),
                'projected_height': round(cut_bbox[3] - cut_bbox[1], 6),
                'crop_width': round(crop[2] - crop[0], 6),
                'crop_height': round(crop[3] - crop[1], 6),
                'target_elevation': round(spec.target_point_m[2], 6),
            },
            target_element_ids=spec.target_element_ids,
            target_elements_drawn=target_drawn, model_element_ids=visible_ids,
            assembly_ids=assembly_ids, assemblies=assemblies,
            facade_roles=facade_roles, material_roles=material_roles,
            host_element_ids=host_ids, unresolved_interfaces=unresolved,
            elements_considered=drawing.audit.elements_considered,
            elements_drawn=drawing.audit.elements_drawn,
            elements_cut=drawing.audit.elements_cut, marks=drawing.audit.marks,
            projection_verified=bool(visible_ids and target_drawn))
        readiness = _readiness(model, spec, drawing, audit, index)
        drawing.detail_audit = audit
        drawing.detail_readiness = readiness
        drawing.detail_cut = (spec.id, spec.bearing_deg, spec.offset_m)
        drawing.subtitle += (
            f' · student design review: {readiness.status.replace("_", " ")} · '
            'professional review required')
        _annotate_detail(drawing, model, spec, index)
        drawings.append(drawing)
    return drawings
