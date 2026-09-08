"""The facade quality gate: check an emitted model against its grammar's own guide.

Each of the ten style guides ends with a *Validation* section, and most of what those
sections ask for is checkable on the geometry rather than by eye: family counts stay
within declared limits, no unreasoned sliver panels, opening ratios inside the published
band, neighbour parameter jumps under 20 %, unique panel ratio reported honestly. Until
now those sections were prose beside a compiler that never read them.

This module runs them. Three things about how it behaves are deliberate.

**A gate reports; it does not silently repair.** `evaluate` returns a verdict per gate
with the measured number beside the required one. Where a failure has a single obvious
deterministic fix -- an opening ratio a few points outside its band, which is a scalar
the emitter already accepts -- `correction_for` proposes it and the compiler re-emits
once, recording that it did. Anything else fails loudly, because a repair that guesses
at intent is worse than a stated failure.

**A gate the pipeline cannot evaluate says so.** Critical Regionalism requires responses
that differ by orientation and forbids a silent default -- "removing context causes a
validation stop, not a silent default" (CR-INV-04, CR-INV-06). There is no solar or rain
data in this project, so that gate returns `unevaluated`, never `passed`. The distinction
between "checked and fine" and "could not check" is the whole reason the verdict has
three states instead of two.

**Passing is not approval.** These gates check that a model is consistent with the
grammar it claims. They say nothing about whether the building is any good, and every
element remains `professional_review_required` regardless.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, computed_field
from shapely.affinity import rotate as rotate_shape
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import nearest_points, unary_union

from .geometry import BoxGeometry, ExtrusionGeometry, MemberGeometry, QuadGeometry
from .grammar_specs import GRAMMAR_SPECS, GrammarSpec

Verdict = Literal['passed', 'failed', 'unevaluated']


class GateResult(BaseModel):
    """One validation criterion, its source in the guide, and what was measured."""

    id: str
    invariant_ref: str
    verdict: Verdict
    measured: float | None = None
    required: str
    detail: str


class FacadeGateReport(BaseModel):
    grammar_id: str
    grammar_label: str
    guide_ref: str
    gates: list[GateResult]
    corrected: str | None = None

    @computed_field
    @property
    def status(self) -> Verdict:
        if any(gate.verdict == 'failed' for gate in self.gates):
            return 'failed'
        if not self.gates or any(gate.verdict == 'unevaluated' for gate in self.gates):
            return 'unevaluated'
        return 'passed'

    @property
    def passed(self) -> bool:
        return self.status == 'passed'

    @property
    def failures(self) -> list[GateResult]:
        return [g for g in self.gates if g.verdict == 'failed']

    @property
    def unevaluated(self) -> list[GateResult]:
        return [g for g in self.gates if g.verdict == 'unevaluated']

    def summary(self) -> str:
        ok = sum(1 for g in self.gates if g.verdict == 'passed')
        return (f'{self.grammar_label}: {ok}/{len(self.gates)} gates passed, '
                f'{len(self.failures)} failed, {len(self.unevaluated)} not evaluable')


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

# Kinds that are the opening rather than the wall. A glazing panel in a punched wall is
# the hole; a wall panel beside it is the mass.
_OPENING_KINDS = {'glazing_panel', 'facet_glazing', 'slot_opening'}
_WALL_KINDS = {'wall_panel', 'solid_wall_panel', 'spandrel_panel', 'backing_panel',
               'facet_panel', 'rainscreen_panel'}


def _area(geometry) -> float:
    """Elevation area of one element, near enough for a ratio."""
    if isinstance(geometry, QuadGeometry):
        a, b, c, _ = geometry.corners
        width = math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))
        height = math.dist((b.x, b.y, b.z), (c.x, c.y, c.z))
        return width * height
    if isinstance(geometry, BoxGeometry):
        # the two largest dimensions, since a panel's thickness is not its face
        dims = sorted((geometry.size.x, geometry.size.y, geometry.size.z))
        return dims[1] * dims[2]
    return 0.0


def _smallest_face_dimension(geometry) -> float | None:
    """The shorter side of a panel's face, which is what 'sliver' means."""
    if isinstance(geometry, QuadGeometry):
        a, b, c, _ = geometry.corners
        return min(math.dist((a.x, a.y, a.z), (b.x, b.y, b.z)),
                   math.dist((b.x, b.y, b.z), (c.x, c.y, c.z)))
    if isinstance(geometry, BoxGeometry):
        return sorted((geometry.size.x, geometry.size.y, geometry.size.z))[1]
    return None


# Subsystems in the envelope layer that are not the wall. A parapet caps the roof and
# a canopy shelters the door; counting their materials against a guide's facade palette
# is measuring the wrong assembly, and it was reporting four materials on an elevation
# that draws two.
_NOT_THE_WALL = {'canopy', 'roof', 'parapet', 'applied_order', 'roof_closure'}


def _envelope_elements(model, *, wall_only: bool = False):
    out = [e for e in model.elements
           if e.semantic_layer == 'envelope' and e.subsystem not in _NOT_THE_WALL]
    if wall_only:
        out = [e for e in out if e.kind not in ('parapet', 'roof_deck')]
    return out


# ---------------------------------------------------------------------------
# The gates
# ---------------------------------------------------------------------------

def _gate_opening_ratio(model, spec: GrammarSpec) -> GateResult:
    opening = wall = 0.0
    for element in _envelope_elements(model):
        area = _area(element.geometry)
        if element.kind in _OPENING_KINDS:
            opening += area
        elif element.kind in _WALL_KINDS:
            wall += area
    total = opening + wall
    if spec.opening_ratio_range is None:
        ratio = opening / total if total > 0.0 else None
        return GateResult(
            id='opening_ratio', invariant_ref=spec.invariants[0],
            verdict='unevaluated', measured=(round(ratio, 4)
                                              if ratio is not None else None),
            required='no universal ratio published',
            detail='The guide governs opening choice through programme and assembly '
                   'logic and publishes no numeric opening band. The emitted ratio is '
                   'reported for comparison only and cannot receive a pass verdict.')
    low, high = spec.opening_ratio_range
    if total <= 0.0:
        return GateResult(
            id='opening_ratio', invariant_ref=spec.invariants[0],
            verdict='unevaluated', required=f'{low:.2f}-{high:.2f}',
            detail='No panelised wall or opening area was emitted, so the ratio has no '
                   'denominator. A grammar built entirely from members rather than '
                   'panels cannot be checked this way.')
    ratio = opening / total
    inside = low <= ratio <= high
    return GateResult(
        id='opening_ratio', invariant_ref=spec.invariants[0],
        verdict='passed' if inside else 'failed', measured=round(ratio, 4),
        required=f'{low:.2f}-{high:.2f}',
        detail=('Opening area over opening-plus-wall area, from the emitted panels. '
                + ('Inside the band the guide publishes.' if inside else
                   'Outside the published band: at this ratio the elevation stops '
                   'reading as the grammar it claims.')))


def _gate_material_families(model, spec: GrammarSpec) -> GateResult:
    materials = {e.material_profile
                 for e in _envelope_elements(model, wall_only=True)}
    count = len(materials)
    if spec.material_families is None:
        return GateResult(
            id='material_families', invariant_ref=spec.invariants[0],
            verdict='unevaluated', measured=float(count),
            required='no visible-material count published',
            detail=f'Distinct envelope materials: {", ".join(sorted(materials))}. '
                   'The guide bounds function-colour families, which this material '
                   'count cannot verify, so it is reported without a pass verdict.')
    low, high = spec.material_families
    inside = low <= count <= high
    return GateResult(
        id='material_families', invariant_ref=spec.invariants[0],
        verdict='passed' if inside else 'failed', measured=float(count),
        required=f'{low}-{high}',
        detail=f'Distinct envelope materials: {", ".join(sorted(materials))}. '
               + ('Within the declared limit.' if inside else
                  'Outside it; the guide caps the visible material family count.'))


# A sliver is a *panel* too small to fabricate or justify. A head, a sill, a mullion
# and a transom are linear trim, and a 160 mm lintel is not an offcut -- measuring them
# against a 300 mm panel limit failed the gate on four Brutalist models whose panels
# were all well over it.
_LINEAR_TRIM = {'mullion', 'transom', 'window_head', 'sill', 'window_reveal',
                'seam_edge', 'screen_fin', 'external_strut', 'frame_expression',
                'lattice_mullion', 'lattice_transom', 'order_jamb', 'order_lintel'}


def _gate_minimum_fragment(model, spec: GrammarSpec) -> GateResult:
    smallest = None
    offender = ''
    for element in _envelope_elements(model):
        if element.kind in _LINEAR_TRIM:
            continue
        value = _smallest_face_dimension(element.geometry)
        if value is None:
            continue
        if smallest is None or value < smallest:
            smallest, offender = value, element.id
    if smallest is None:
        return GateResult(
            id='minimum_fragment', invariant_ref=spec.invariants[0],
            verdict='unevaluated',
            required=(f'>= {spec.minimum_fragment_m} m'
                      if spec.minimum_fragment_m is not None
                      else 'no grammar minimum published'),
            detail='No panel-like element to measure.')
    if spec.minimum_fragment_m is None:
        return GateResult(
            id='minimum_fragment', invariant_ref=spec.invariants[0],
            verdict='unevaluated', measured=round(smallest, 4),
            required='no grammar minimum published',
            detail='The smallest panel is reported, but the guide publishes no numeric '
                   'fragment limit; the compiler used its project-level closure guard.')
    # A millimetre of tolerance. The emitter clamps slot widths to exactly this
    # limit, and floating point puts the result a fraction under it; failing a panel
    # for being 0.2999 m wide would be the gate reporting arithmetic rather than
    # geometry.
    ok = smallest >= spec.minimum_fragment_m - 0.001
    return GateResult(
        id='minimum_fragment', invariant_ref=spec.invariants[0],
        verdict='passed' if ok else 'failed', measured=round(smallest, 4),
        required=f'>= {spec.minimum_fragment_m} m',
        detail=('Smallest emitted panel face. No unreasoned slivers.' if ok else
                f'{offender} is below the material limit and would be an offcut '
                f'nobody could fabricate or justify.'))


def _gate_score_authority(model, spec: GrammarSpec) -> GateResult:
    """How far the score moved the *elevation*, against the guide's published cap.

    The first version of this gate measured how far the envelope datums travelled from
    the midpoint of their declared ranges. That was the wrong quantity, and the mistake
    is worth recording: the datum layer is shared by every grammar and its travel is set
    by the confidence clamp, so a Minimalist model was being failed for a number its
    emitter never touched. What `score_authority` actually governs is how much of the
    range between a tectonic's own base opacity and a solid wall the score is allowed to
    use, so that is what is measured -- the opaque share that was drawn, against the
    share the tectonic would have drawn with no music at all.
    """
    wall = opening = 0.0
    for element in _envelope_elements(model, wall_only=True):
        area = _area(element.geometry)
        if element.kind in _OPENING_KINDS:
            opening += area
        elif element.kind in _WALL_KINDS:
            wall += area
    total = wall + opening
    if total <= 0.0:
        return GateResult(
            id='score_authority', invariant_ref=spec.invariants[0],
            verdict='unevaluated', required=f'<= {spec.score_authority:.2f}',
            detail='No panelised elevation to measure the opaque share on.')

    from .tectonics import ENVELOPE_TECTONICS
    base = ENVELOPE_TECTONICS[model.envelope_tectonic_id].base_opacity
    drawn = wall / total
    # An absolute share of the elevation, not a share of the remaining headroom.
    # Dividing by headroom was the second wrong quantity this gate measured: Minimalism
    # sits at 92 % base opacity, so its headroom is 0.08 and one bay's worth of
    # difference reported as 109 % authority used. What the guide caps is the *variation
    # in the elevation* -- "+/-0-12%" -- which is a percentage of the wall, not of what
    # was left over.
    used = abs(drawn - base)
    # A tolerance, because the emitted share is quantised by whole bays: on a nine-bay
    # elevation the opaque run can only land on ninths.
    ok = used <= min(1.0, spec.score_authority + 0.14)
    return GateResult(
        id='score_authority', invariant_ref=spec.invariants[0],
        verdict='passed' if ok else 'failed', measured=round(used, 4),
        required=f'<= {spec.score_authority:.2f} (+0.14 for bay quantisation)',
        detail=f'The tectonic alone would draw {base:.0%} opaque; this elevation drew '
               f'{drawn:.0%}, a shift of {used:.0%} of the elevation. '
               f'Guide basis: {spec.score_authority_source}.')


def _gate_orientation_response(model, spec: GrammarSpec) -> GateResult:
    """CR-INV-02 and CR-INV-06, which this pipeline cannot honestly satisfy."""
    return GateResult(
        id='orientation_response', invariant_ref='CR-INV-02',
        verdict='unevaluated', required='responses differ by orientation',
        detail='This project holds no solar, rain or privacy data for a site, so an '
               'orientation-varying response would be a decoration wearing an '
               'environmental justification. The guide is explicit that removing '
               'context must cause a validation stop rather than a silent default, so '
               'this gate never returns passed until a site exists.')


def _gate_neighbour_jump(model, spec: GrammarSpec) -> GateResult:
    """Parametricism caps how far two adjacent panels may differ."""
    panels = [e for e in model.elements if e.kind == 'field_panel']
    if len(panels) < 4:
        return GateResult(
            id='neighbour_jump', invariant_ref='PA-INV-01', verdict='unevaluated',
            required=f'<= {spec.neighbour_jump_max:.0%}',
            detail='Fewer than four field panels; nothing to compare.')
    by_cell: dict[tuple, float] = {}
    for panel in panels:
        index = panel.lattice_index
        key = (index.get('level'), index.get('station'), index.get('row'),
               index.get('col'))
        by_cell[key] = max(panel.dimensions.x, panel.dimensions.y, panel.dimensions.z)
    worst = 0.0
    for (level, station, row, col), depth in by_cell.items():
        for neighbour in ((level, station, row, (col or 0) + 1),
                          (level, station, (row or 0) + 1, col)):
            other = by_cell.get(neighbour)
            if other is None or max(depth, other) <= 0:
                continue
            worst = max(worst, abs(depth - other) / max(depth, other))
    ok = worst <= spec.neighbour_jump_max
    return GateResult(
        id='neighbour_jump', invariant_ref='PA-INV-01',
        verdict='passed' if ok else 'failed', measured=round(worst, 4),
        required=f'<= {spec.neighbour_jump_max:.0%}',
        detail='Largest depth step between two adjacent field panels. A gradient that '
               'jumps is a pattern with a mistake in it, not a field.')


def _gate_unique_panels(model, spec: GrammarSpec) -> GateResult:
    panels = [e for e in model.elements if e.kind == 'field_panel']
    if not panels:
        return GateResult(
            id='unique_panel_ratio', invariant_ref='PA-INV-01', verdict='unevaluated',
            required=f'<= {spec.unique_panel_ratio_max:.2f}',
            detail='No field panels emitted.')
    shapes = {(round(p.dimensions.x, 2), round(p.dimensions.y, 2),
               round(p.dimensions.z, 2)) for p in panels}
    ratio = len(shapes) / len(panels)
    ok = ratio <= spec.unique_panel_ratio_max
    return GateResult(
        id='unique_panel_ratio', invariant_ref='PA-INV-01',
        verdict='passed' if ok else 'failed', measured=round(ratio, 4),
        required=f'<= {spec.unique_panel_ratio_max:.2f}',
        detail=f'{len(shapes)} distinct panel geometries across {len(panels)} panels. '
               'The guide treats this as a fabrication cost proxy.')


def _gate_recoverable_baseline(model, spec: GrammarSpec) -> GateResult:
    """The transformed facade must resolve back to a source that still exists."""
    transformed = [e for e in model.elements
                   if e.kind in ('seam_edge', 'facet_panel', 'field_panel')]
    if not transformed:
        return GateResult(
            id='recoverable_baseline', invariant_ref=spec.invariants[0],
            verdict='unevaluated', required='every transformed element names a source',
            detail='No transformed elements in this model.')
    unsourced = [e.id for e in transformed if not e.lattice_index]
    ok = not unsourced
    return GateResult(
        id='recoverable_baseline', invariant_ref=spec.invariants[0],
        verdict='passed' if ok else 'failed', measured=float(len(unsourced)),
        required='0 elements without a lattice index',
        detail=('Every transformed element still indexes into the lattice it came '
                'from, so turning the transformation off returns a valid baseline.'
                if ok else
                f'{len(unsourced)} transformed elements carry no lattice index and '
                'cannot be traced back to a source.'))


# ---------------------------------------------------------------------------
# High-Tech: a legible kit of parts, not a glass ratio
# ---------------------------------------------------------------------------

_HT_ALLOWED_ROLES = {'frame', 'support', 'enclosure', 'cassette', 'glazing'}
_HT_ASSEMBLY_ROLES = {'frame', 'support', 'enclosure'}
_HT_INFILL_ROLES = {'cassette', 'glazing'}
_HT_STRUCTURAL_HOST_KINDS = {
    'floor_slab', 'slab_fascia', 'column', 'piloti_column', 'primary_beam',
    'podium_slab', 'roof_deck',
}


def _high_tech_elements(model):
    return _envelope_elements(model)


def _gate_high_tech_assembly_metadata(model) -> GateResult:
    elements = _high_tech_elements(model)
    if not elements:
        return GateResult(
            id='high_tech_assembly_metadata', invariant_ref='HT-INV-01/HT-INV-03',
            verdict='unevaluated', required='100% carry assembly_id and part_role',
            detail='No visible facade components were emitted.')
    missing = [element.id for element in elements
               if not element.assembly_id or not element.part_role]
    complete = (len(elements) - len(missing)) / len(elements)
    return GateResult(
        id='high_tech_assembly_metadata', invariant_ref='HT-INV-01/HT-INV-03',
        verdict='passed' if not missing else 'failed', measured=round(complete, 4),
        required='1.00',
        detail=('Every visible facade component has a stable assembly and functional '
                'part role.' if not missing else
                f'{len(missing)} components lack assembly_id or part_role; first: '
                f'{", ".join(missing[:5])}.'))


def _gate_high_tech_system_roles(model) -> GateResult:
    elements = _high_tech_elements(model)
    roles = {element.part_role for element in elements if element.part_role}
    if not elements or not roles:
        return GateResult(
            id='high_tech_system_roles', invariant_ref='HT-INV-01/HT-INV-03',
            verdict='unevaluated', required=', '.join(sorted(_HT_ALLOWED_ROLES)),
            detail='No classified facade system roles are available to inspect.')
    illegal = sorted(role for role in roles if role not in _HT_ALLOWED_ROLES)
    primary_ids = {
        element.assembly_id for element in elements
        if element.assembly_id and element.part_role == 'frame'
        and isinstance(element.geometry, MemberGeometry)
        and 'primary_span' in element.lattice_index}
    primary = {}
    for element in elements:
        if element.assembly_id in primary_ids:
            primary.setdefault(element.assembly_id, set()).add(element.part_role)
    incomplete = [ident for ident, assembly_roles in primary.items()
                  if not _HT_ASSEMBLY_ROLES <= assembly_roles
                  or not (_HT_INFILL_ROLES & assembly_roles)]
    if not primary:
        return GateResult(
            id='high_tech_system_roles', invariant_ref='HT-INV-01/HT-INV-03',
            verdict='unevaluated', measured=float(len(roles)),
            required='frame + support + enclosure + one programme-selected infill',
            detail='No primary facade assembly is available to inspect.')
    ok = not illegal and not incomplete
    return GateResult(
        id='high_tech_system_roles', invariant_ref='HT-INV-01/HT-INV-03',
        verdict='passed' if ok else 'failed', measured=float(len(roles)),
        required='frame + support + enclosure + cassette or glazing per repeated bay',
        detail=(f'Roles present: {", ".join(sorted(roles))}. '
                + ('Every primary bay resolves as an inspectable assembly.' if ok else
                   f'Illegal roles: {illegal}; incomplete repeated assemblies: '
                   f'{incomplete[:5]}.')))


def _quad_width(element) -> float | None:
    geometry = element.geometry
    if not isinstance(geometry, QuadGeometry):
        return None
    a, b = geometry.corners[:2]
    return math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))


def _gate_high_tech_primary_bays(model, spec: GrammarSpec) -> GateResult:
    interval = spec.primary_assembly_bay_range_m
    if interval is None:
        return GateResult(
            id='high_tech_primary_bay', invariant_ref='HT-INV-02',
            verdict='unevaluated', required='guide primary-bay interval unavailable',
            detail='The grammar spec carries no primary assembly bay interval.')
    unresolved = [element.id for element in _high_tech_elements(model)
                  if 'HT-PRIMARY-BAY-UNRESOLVED' in element.rule_refs]
    by_assembly: dict[str, list[float]] = {}
    for element in _high_tech_elements(model):
        if (element.assembly_id and element.part_role == 'frame'
                and isinstance(element.geometry, MemberGeometry)
                and 'primary_span' in element.lattice_index
                and 'HT-PRIMARY-BAY-UNRESOLVED' not in element.rule_refs):
            path = element.geometry.path
            by_assembly.setdefault(element.assembly_id, []).append(math.dist(
                (path[0].x, path[0].y, path[0].z),
                (path[-1].x, path[-1].y, path[-1].z)))
    if not by_assembly:
        return GateResult(
            id='high_tech_primary_bay', invariant_ref='HT-INV-02',
            verdict='unevaluated', required=f'{interval[0]:.2f}-{interval[1]:.2f} m',
            detail='No repeated primary assembly infill is available to measure.')
    widths = {ident: max(spans) for ident, spans in by_assembly.items()}
    outside = {ident: width for ident, width in widths.items()
               if not interval[0] - 1.0e-3 <= width <= interval[1] + 1.0e-3}
    low_measured, high_measured = min(widths.values()), max(widths.values())
    verdict: Verdict = ('failed' if outside else
                        'unevaluated' if unresolved else 'passed')
    unresolved_note = (f' {len(unresolved)} components also belong to a special '
                       f'assembly on an edge too short to evaluate; first: '
                       f'{", ".join(unresolved[:5])}.' if unresolved else '')
    return GateResult(
        id='high_tech_primary_bay', invariant_ref='HT-INV-02',
        verdict=verdict,
        measured=round(high_measured, 4),
        required=f'{interval[0]:.2f}-{interval[1]:.2f} m measured primary bay',
        detail=((f'{len(widths)} primary assemblies measure '
                 f'{low_measured:.3f}-{high_measured:.3f} m across the emitted infill.'
                 + unresolved_note) if not outside else
                f'Primary assemblies outside the guide interval: '
                f'{[(key, round(value, 3)) for key, value in list(outside.items())[:5]]}.'
                + unresolved_note))


def _gate_high_tech_submodules(model, spec: GrammarSpec) -> GateResult:
    interval = spec.enclosure_submodule_range_m
    unresolved = [element.id for element in _high_tech_elements(model)
                  if ({'HT-SUBMODULE-PROGRAM-BOUNDARY-UNRESOLVED',
                       'HT-SUBMODULE-UNRESOLVED'} & set(element.rule_refs))]
    panels = [element for element in _high_tech_elements(model)
              if element.assembly_id and element.part_role in _HT_INFILL_ROLES
              and 'submodule' in element.lattice_index
              and not ({'HT-SUBMODULE-PROGRAM-BOUNDARY-UNRESOLVED',
                        'HT-SUBMODULE-UNRESOLVED'} & set(element.rule_refs))]
    if interval is None or not panels:
        return GateResult(
            id='high_tech_enclosure_submodule', invariant_ref='HT-INV-02/HT-INV-03',
            verdict='unevaluated',
            required=('guide submodule interval unavailable' if interval is None
                      else 'emitted repeated submodules'),
            detail='No repeated enclosure submodule is available to measure.')
    widths = {element.id: _quad_width(element) for element in panels}
    unmeasurable = [ident for ident, width in widths.items() if width is None]
    outside = {ident: width for ident, width in widths.items()
               if width is not None
               and not interval[0] - 1.0e-3 <= width <= interval[1] + 1.0e-3}
    measured = [float(width) for width in widths.values() if width is not None]
    if not measured:
        return GateResult(
            id='high_tech_enclosure_submodule', invariant_ref='HT-INV-02/HT-INV-03',
            verdict='unevaluated', required=f'{interval[0]:.2f}-{interval[1]:.2f} m',
            detail='No enclosure submodule has measurable quad geometry.')
    verdict: Verdict = ('failed' if outside else 'unevaluated'
                        if unresolved or unmeasurable else 'passed')
    unresolved_notes = []
    if unresolved:
        unresolved_notes.append(
            f'{len(unresolved)} components have an unresolved sub-minimum fragment; '
            f'first: {", ".join(unresolved[:5])}')
    if unmeasurable:
        unresolved_notes.append(
            f'{len(unmeasurable)} enclosure components are not measurable quads')
    unresolved_note = (' Unresolved: ' + '; '.join(unresolved_notes) + '.'
                       if unresolved_notes else '')
    return GateResult(
        id='high_tech_enclosure_submodule', invariant_ref='HT-INV-02/HT-INV-03',
        verdict=verdict, measured=round(max(measured), 4),
        required=f'{interval[0]:.2f}-{interval[1]:.2f} m per enclosure submodule',
        detail=((f'{len(measured)} emitted submodules measure '
                 f'{min(measured):.3f}-{max(measured):.3f} m.' + unresolved_note)
                if not outside else
                f'Submodules outside the guide interval: '
                f'{[(key, round(value, 3)) for key, value in list(outside.items())[:5]]}.'
                + unresolved_note))


def _gate_high_tech_system_depth(model, spec: GrammarSpec) -> GateResult:
    low, high = spec.depth_range_m
    elements = _high_tech_elements(model)
    assemblies = sorted({element.assembly_id for element in elements
                         if element.assembly_id
                         and element.part_role == 'frame'
                         and isinstance(element.geometry, MemberGeometry)})
    if not assemblies:
        return GateResult(
            id='high_tech_system_depth', invariant_ref='HT-INV-03/HT-INV-04',
            verdict='unevaluated', required=f'{low:.2f}-{high:.2f} m',
            detail='No repeated primary assembly is available to measure.')
    depths: dict[str, float] = {}
    incomplete = []
    for assembly_id in assemblies:
        frames = [element for element in elements
                  if element.assembly_id == assembly_id and element.part_role == 'frame'
                  and isinstance(element.geometry, MemberGeometry)
                  and 'primary_span' not in element.lattice_index]
        infill = [element for element in elements
                  if element.assembly_id == assembly_id
                  and element.part_role in _HT_INFILL_ROLES
                  and isinstance(element.geometry, QuadGeometry)
                  and 'submodule' in element.lattice_index]
        if not frames or not infill:
            incomplete.append(assembly_id)
            continue
        def normal_distance(point, line):
            (x, y), ((x0, y0), (x1, y1)) = point, line
            length = math.hypot(x1 - x0, y1 - y0)
            if length <= 1.0e-9:
                return math.inf
            return abs((x1 - x0) * (y0 - y) - (x0 - x) * (y1 - y0)) / length

        for panel in infill:
            station = panel.lattice_index.get('station')
            local_frames = [item for item in frames
                            if item.lattice_index.get('station') == station]
            if not local_frames:
                incomplete.append(f'{assembly_id}:{panel.id}')
                continue
            line = ((panel.geometry.corners[0].x, panel.geometry.corners[0].y),
                    (panel.geometry.corners[1].x, panel.geometry.corners[1].y))
            # Measure every authoritative vertical primary axis.  Horizontal TOP
            # members share its station, but their old endpoint must not mask a moved
            # or malformed primary frame through a convenient minimum distance.
            for frame in local_frames:
                frame_points = [(point.x, point.y) for point in frame.geometry.path]
                depths[f'{panel.id}->{frame.id}'] = max(
                    normal_distance(point, line) for point in frame_points)
    if incomplete or not depths:
        return GateResult(
            id='high_tech_system_depth', invariant_ref='HT-INV-03/HT-INV-04',
            verdict='unevaluated', required=f'{low:.2f}-{high:.2f} m',
            detail=f'Cannot pair frame and enclosure geometry for {incomplete[:5]}.')
    outside = {ident: depth for ident, depth in depths.items()
               if not low - 1.0e-3 <= depth <= high + 1.0e-3}
    return GateResult(
        id='high_tech_system_depth', invariant_ref='HT-INV-03/HT-INV-04',
        verdict='passed' if not outside else 'failed',
        measured=round(max(depths.values()), 4), required=f'{low:.2f}-{high:.2f} m',
        detail=(f'Exposed-frame axes to recessed enclosure faces measure '
                f'{min(depths.values()):.3f}-{max(depths.values()):.3f} m.'
                if not outside else
                f'Assembly depths outside the guide interval: '
                f'{[(key, round(value, 3)) for key, value in list(outside.items())[:5]]}.'))


def _profile_mapping(model) -> dict:
    profiles = getattr(model, 'profiles', None) or {}
    return {key: (value.model_dump() if hasattr(value, 'model_dump') else value)
            for key, value in profiles.items()}


def _physical_body(element, profiles: dict):
    """Return (plan body, z-low, z-high) from emitted solid/member geometry."""
    geometry = element.geometry
    if isinstance(geometry, ExtrusionGeometry):
        shape = Polygon([(point.x, point.y) for point in geometry.boundary],
                        [[(point.x, point.y) for point in hole]
                         for hole in geometry.holes])
        return shape, geometry.z_base, geometry.z_top
    if isinstance(geometry, BoxGeometry):
        hx, hy = geometry.size.x / 2.0, geometry.size.y / 2.0
        shape = Polygon(((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)))
        shape = rotate_shape(shape, geometry.rotation_z, origin=(0, 0),
                             use_radians=True)
        shape = type(shape)([(x + geometry.center.x, y + geometry.center.y)
                             for x, y in shape.exterior.coords])
        return (shape, geometry.center.z - geometry.size.z / 2.0,
                geometry.center.z + geometry.size.z / 2.0)
    if isinstance(geometry, MemberGeometry):
        profile = profiles.get(geometry.profile)
        if profile is None:
            return None
        radius = max(float(profile['depth_m']), float(profile['width_m'])) / 2.0
        points = [(point.x, point.y) for point in geometry.path]
        shape = (Point(points[0]).buffer(radius)
                 if len(set(points)) == 1 else
                 LineString(points).buffer(radius, cap_style=2, join_style=2))
        zs = [point.z for point in geometry.path]
        return shape, min(zs) - radius, max(zs) + radius
    if isinstance(geometry, QuadGeometry):
        thickness = element.thickness_m
        if thickness is None or thickness <= 0.0:
            return None
        points = [(point.x, point.y) for point in geometry.corners]
        unique = list(dict.fromkeys(points))
        shape = (Point(unique[0]).buffer(thickness / 2.0)
                 if len(unique) == 1 else
                 LineString(unique).buffer(thickness / 2.0,
                                           cap_style=2, join_style=2))
        zs = [point.z for point in geometry.corners]
        return shape, min(zs), max(zs)
    return None


def _bodies_touch(a, b, profiles: dict) -> bool | None:
    first, second = _physical_body(a, profiles), _physical_body(b, profiles)
    if first is None or second is None:
        return None
    a_shape, a_low, a_high = first
    b_shape, b_low, b_high = second
    vertical_gap = max(0.0, a_low - b_high, b_low - a_high)
    return vertical_gap <= 1.0e-3 and a_shape.distance(b_shape) <= 1.0e-3


def _gate_high_tech_interfaces(model) -> GateResult:
    elements = _high_tech_elements(model)
    by_id = {element.id: element for element in model.elements}
    profiles = _profile_mapping(model)
    if not elements:
        return GateResult(
            id='high_tech_interfaces', invariant_ref='HT-INV-04',
            verdict='unevaluated', required='real contacts and a carrier path to structure',
            detail='No High-Tech facade components are available to inspect.')

    invalid: list[str] = []
    unmeasurable: list[str] = []
    allowed_hosts = {
        'frame': {'frame', 'support'},
        'support': {'frame', 'support'},
        'enclosure': {'frame', 'support', 'enclosure'},
        'cassette': {'frame', 'support', 'enclosure'},
        'glazing': {'frame', 'support', 'enclosure'},
    }

    def reaches_structure(element, seen: set[str]) -> bool:
        if element.id in seen:
            return False
        seen = {*seen, element.id}
        for host_id in element.supports:
            host = by_id.get(host_id)
            if host is None:
                continue
            if (host.semantic_layer == 'structure'
                    and host.kind in _HT_STRUCTURAL_HOST_KINDS):
                return True
            if (host.semantic_layer == 'envelope'
                    and host.assembly_id == element.assembly_id
                    and reaches_structure(host, seen)):
                return True
        return False

    for element in elements:
        role = element.part_role
        if role not in _HT_ALLOWED_ROLES or not element.assembly_id:
            invalid.append(f'{element.id}:classification')
            continue
        if not element.supports:
            invalid.append(f'{element.id}:no_host')
            continue
        for host_id in element.supports:
            host = by_id.get(host_id)
            if host is None:
                invalid.append(f'{element.id}:missing:{host_id}')
                continue
            structural_host = (host.semantic_layer == 'structure'
                               and host.kind in _HT_STRUCTURAL_HOST_KINDS)
            facade_host = host.semantic_layer == 'envelope'
            if not structural_host:
                if (not facade_host or host.assembly_id != element.assembly_id
                        or host.part_role not in allowed_hosts[role]):
                    invalid.append(f'{element.id}:illegal_host:{host_id}')
                    continue
            contact = _bodies_touch(element, host, profiles)
            if contact is None:
                unmeasurable.append(f'{element.id}->{host_id}')
            elif not contact:
                invalid.append(f'{element.id}:no_contact:{host_id}')
        if not reaches_structure(element, set()):
            invalid.append(f'{element.id}:no_structure_path')

    checked = len(elements) - len({entry.split(':', 1)[0] for entry in invalid})
    if invalid:
        return GateResult(
            id='high_tech_interfaces', invariant_ref='HT-INV-04',
            verdict='failed', measured=round(checked / len(elements), 4),
            required='all roles, hosts, contacts and carrier paths resolve',
            detail=f'{len(invalid)} interface defects; first: {", ".join(invalid[:6])}.')
    if unmeasurable:
        return GateResult(
            id='high_tech_interfaces', invariant_ref='HT-INV-04',
            verdict='unevaluated', measured=round(checked / len(elements), 4),
            required='all declared contacts geometrically measurable',
            detail=f'{len(unmeasurable)} contacts lack a section/thickness needed for '
                   f'measurement; first: {", ".join(unmeasurable[:5])}.')
    return GateResult(
        id='high_tech_interfaces', invariant_ref='HT-INV-04', verdict='passed',
        measured=1.0, required='all roles, hosts, contacts and carrier paths resolve',
        detail=f'All {len(elements)} visible components have legal same-assembly '
               'interfaces, measured contact, and a carrier path to structure.')


def _gate_high_tech_program_control(model) -> GateResult:
    high_tech = _high_tech_elements(model)
    exempt = [element for element in high_tech
              if element.part_role in _HT_INFILL_ROLES
              and 'HT-PROGRAM-HUMAN-EXEMPT' in element.rule_refs]
    exemption_note = (f' {len(exempt)} entrance infill components carry the explicit '
                      'human/program exemption.' if exempt else '')
    unresolved_breaks = [element.id for element in high_tech
                         if 'HT-SUBMODULE-PROGRAM-BOUNDARY-UNRESOLVED'
                         in element.rule_refs]
    infill = [element for element in high_tech
              if element.assembly_id and element.part_role in _HT_INFILL_ROLES
              and 'HT-PROGRAM-HUMAN-EXEMPT' not in element.rule_refs]
    if not infill:
        return GateResult(
            id='high_tech_program_control', invariant_ref='HT-INV-01',
            verdict='unevaluated', required='Program Volume category selects infill',
            detail='No non-exempt enclosure infill is available to inspect.'
                   + exemption_note)
    lattice = getattr(model, 'lattice', None)
    regions = list(getattr(lattice, 'program_volume_regions', ()) or ())
    x_lines = list(getattr(lattice, 'program_volume_x_lines', ()) or ())
    y_lines = list(getattr(lattice, 'program_volume_y_lines', ()) or ())
    if lattice is None or not regions or not x_lines or not y_lines:
        return GateResult(
            id='high_tech_program_control', invariant_ref='HT-INV-01',
            verdict='unevaluated', measured=0.0,
            required='authored Program Volume regions on their immutable grid',
            detail=('No complete Program Volume region/grid evidence is carried by the model.'
                    + exemption_note))

    def field(record, name, default=None):
        return record.get(name, default) if isinstance(record, dict) else getattr(
            record, name, default)

    shapes = []
    for region in regions:
        i0, j0, i1, j1 = map(int, field(region, 'grid_rect'))
        try:
            shape = Polygon(((x_lines[i0], y_lines[j0]),
                             (x_lines[i1], y_lines[j0]),
                             (x_lines[i1], y_lines[j1]),
                             (x_lines[i0], y_lines[j1])))
        except IndexError:
            return GateResult(
                id='high_tech_program_control', invariant_ref='HT-INV-01',
                verdict='failed', required='valid immutable Program Volume grid indices',
                detail=f'{field(region, "id", "unknown")} indexes outside the authored grid.')
        shapes.append((region, shape))

    levels = {level.id: Polygon([(point.x, point.y) for point in level.plate])
              for level in lattice.levels}
    mismatched: list[str] = []
    unresolved: list[str] = []
    sourced = 0
    for element in infill:
        if 'HT-SUBMODULE-PROGRAM-BOUNDARY-UNRESOLVED' in element.rule_refs:
            unresolved.append(f'{element.id}:subminimum_program_boundary_fragment')
            continue
        geometry = element.geometry
        a, b = geometry.corners[:2]
        plate = levels.get(element.level_id)
        if plate is None:
            unresolved.append(f'{element.id}:missing_level')
            continue
        inner = plate.buffer(-0.05, join_style=2)
        if inner.is_empty:
            unresolved.append(f'{element.id}:no_interior_probe')
            continue
        inward_a = nearest_points(inner, Point(a.x, a.y))[0]
        inward_b = nearest_points(inner, Point(b.x, b.y))[0]
        probe = LineString([(inward_a.x, inward_a.y), (inward_b.x, inward_b.y)])
        if probe.length <= 1.0e-5:
            unresolved.append(f'{element.id}:degenerate_probe')
            continue
        plan_covering = [(region, shape) for region, shape in shapes
                         if field(region, 'level_id') == element.level_id
                         and shape.intersection(probe).length > 1.0e-5]
        plan_parts = [shape.intersection(probe)
                      for _region, shape in plan_covering]
        plan_length = unary_union(plan_parts).length if plan_parts else 0.0
        if plan_length < probe.length - 1.0e-4:
            unresolved.append(f'{element.id}:partly_outside_program_volume_plan')
            continue
        if any(field(region, 'z_base') is None or field(region, 'z_top') is None
               for region, _shape in plan_covering):
            unresolved.append(f'{element.id}:missing_program_volume_z_extent')
            continue
        z_values = [point.z for point in geometry.corners]
        panel_low, panel_high = min(z_values), max(z_values)
        covering = [(region, shape) for region, shape in plan_covering
                    if float(field(region, 'z_base')) <= panel_low + 1.0e-5
                    and float(field(region, 'z_top')) >= panel_high - 1.0e-5]
        covered_parts = [shape.intersection(probe) for _region, shape in covering]
        covered_length = unary_union(covered_parts).length if covered_parts else 0.0
        if covered_length < probe.length - 1.0e-4:
            mismatched.append(
                f'{element.id}:outside_program_volume_z_{panel_low:.3f}-{panel_high:.3f}')
            continue
        matching = [(region, shape) for region, shape in covering
                    if (element.program in (field(region, 'space_ids', ()) or ())
                        or element.program == field(region, 'id'))]
        if not covering:
            unresolved.append(f'{element.id}:no_covering_volume')
            continue
        if not matching:
            mismatched.append(f'{element.id}:program_not_in_covering_volume')
            continue
        # The declared program may match one end while the physical panel crosses a
        # second category. Category authority therefore comes from every region the
        # complete inward panel line occupies, not only the region named in metadata.
        expected_categories = {field(region, 'category') for region, _ in covering}
        expected_role = ('cassette' if expected_categories <= {'service', 'private'}
                         else 'glazing' if expected_categories <= {'public', 'circulation'}
                         else None)
        if (expected_role is None or element.category not in expected_categories
                or element.part_role != expected_role):
            mismatched.append(f'{element.id}:declared_{element.category}/{element.part_role}'
                              f'_vs_{sorted(expected_categories)}')
            continue
        if 'PROGRAM_VOLUME_TO_FACADE' not in element.rule_refs:
            unresolved.append(f'{element.id}:missing_provenance_ref')
            continue
        sourced += 1
    if mismatched:
        unresolved_note = (f' {len(unresolved_breaks)} components also carry an '
                           'unresolved sub-minimum programme-boundary fragment.'
                           if unresolved_breaks else '')
        return GateResult(
            id='high_tech_program_control', invariant_ref='HT-INV-01',
            verdict='failed', measured=round(sourced / len(infill), 4),
            required='service/private=cassette; public/circulation=glazing',
            detail=f'{len(mismatched)} submodules contradict their programme category; '
                   f'first: {", ".join(mismatched[:5])}.'
                   + unresolved_note + exemption_note)
    if unresolved_breaks or unresolved or sourced != len(infill):
        break_note = (f' {len(unresolved_breaks)} components belong to a primary bay '
                      'whose programme boundary leaves a sub-0.75 m fragment; first: '
                      f'{", ".join(unresolved_breaks[:5])}.'
                      if unresolved_breaks else '')
        return GateResult(
            id='high_tech_program_control', invariant_ref='HT-INV-01',
            verdict='unevaluated', measured=round(sourced / len(infill), 4),
            required='100% sourced from authored Program Volume regions',
            detail=(f'{sourced}/{len(infill)} submodules carry Program Volume '
                    'evidence independently matched to their geometric region. '
                    f'Unresolved: {", ".join(unresolved[:5])}.'
                    + break_note + exemption_note))
    return GateResult(
        id='high_tech_program_control', invariant_ref='HT-INV-01',
        verdict='passed', measured=1.0,
        required='service/private=cassette; public/circulation=glazing',
        detail=(f'All {len(infill)} non-exempt infill components follow authored '
                'Program Volume categories.' + exemption_note))


def _secondary_expected(model, low: int, high: int) -> int | None:
    datums = getattr(model, 'datum_set', None)
    if datums is None:
        return None
    position = None
    try:
        datum = datums.by_id('transom_rows')
        position = datum.applied_position
        if position is None:
            position = datum.dimension_value
    except (AttributeError, KeyError):
        pass
    if position is None:
        try:
            rows = max(2, min(4, datums.integer('transom_rows')))
            position = (rows - 2) / 2.0
        except (AttributeError, KeyError):
            return None
    position = min(1.0, max(0.0, float(position)))
    return max(low, min(high, int(round(low + (high - low) * position))))


def _gate_high_tech_secondary_density(model, spec: GrammarSpec) -> GateResult:
    density_range = spec.visible_secondary_members_per_bay
    if density_range is None:
        return GateResult(
            id='high_tech_secondary_density', invariant_ref='HT-INV-02',
            verdict='unevaluated', required='guide density range unavailable',
            detail='The grammar spec carries no secondary-member interval.')
    low, high = density_range
    counts = {}
    for element in _high_tech_elements(model):
        if (element.subsystem == 'expressed_frame'
                and element.kind == 'external_strut'
                and element.assembly_id
                and 'secondary' in element.lattice_index
                and 'DENSITY_TO_FACADE' in element.rule_refs):
            counts[element.assembly_id] = counts.get(element.assembly_id, 0) + 1
    if not counts:
        return GateResult(
            id='high_tech_secondary_density', invariant_ref='HT-INV-02',
            verdict='unevaluated', required=f'{low}-{high} per bay, score-derived',
            detail='No repeated secondary members were emitted.')
    expected = _secondary_expected(model, low, high)
    worst = max(counts.values())
    outside = {ident: count for ident, count in counts.items()
               if not low <= count <= high}
    if expected is None:
        return GateResult(
            id='high_tech_secondary_density', invariant_ref='HT-INV-02',
            verdict='unevaluated', measured=float(worst),
            required=f'{low}-{high} per bay, score-derived',
            detail=('Member counts are inside the guide interval, but the source '
                    'density datum is absent so score control cannot be verified.'
                    if not outside else
                    f'Counts outside the guide interval: {outside}.'))
    mismatched = {ident: count for ident, count in counts.items()
                  if count != expected}
    ok = not outside and not mismatched
    return GateResult(
        id='high_tech_secondary_density', invariant_ref='HT-INV-02',
        verdict='passed' if ok else 'failed', measured=float(worst),
        required=f'{expected} per bay from score density; legal interval {low}-{high}',
        detail=(f'All {len(counts)} repeated bays carry {expected} visible secondary '
                'members.' if ok else
                f'Bays not matching the score-derived count: '
                f'{list(mismatched.items())[:5]}; outside interval: '
                f'{list(outside.items())[:5]}.'))


def _gate_high_tech_standard_share(model, spec: GrammarSpec) -> GateResult:
    minimum = spec.standard_component_share_min
    elements = _high_tech_elements(model)
    if minimum is None or not elements:
        return GateResult(
            id='high_tech_standard_component_share', invariant_ref='HT-INV-05',
            verdict='unevaluated',
            required=('guide target unavailable' if minimum is None
                      else f'>= {minimum:.0%}'),
            detail=('No classifiable facade components were emitted.' if not elements
                    else 'The grammar spec carries no standard-component target.'))
    classifiable = [element for element in elements if element.assembly_id]
    if len(classifiable) != len(elements):
        return GateResult(
            id='high_tech_standard_component_share', invariant_ref='HT-INV-05',
            verdict='unevaluated', measured=None, required=f'>= {minimum:.0%}',
            detail='At least one component lacks an assembly class, so standard versus '
                   'special counts cannot be reported honestly.')
    assembly_refs: dict[str, set[str]] = {}
    for element in classifiable:
        assembly_refs.setdefault(element.assembly_id, set()).update(element.rule_refs)
    assembly_ids = set(assembly_refs)
    contradictory = sorted(
        ident for ident, refs in assembly_refs.items()
        if {'HT-STANDARD-COMPONENT', 'HT-SPECIAL-COMPONENT'} <= refs)
    unknown = sorted(
        ident for ident, refs in assembly_refs.items()
        if (not ident.startswith(('HTA-', 'HTS-'))
            or (ident.startswith('HTS-')
                and not ({'HT-STANDARD-COMPONENT', 'HT-SPECIAL-COMPONENT'} & refs))))
    if unknown or contradictory:
        return GateResult(
            id='high_tech_standard_component_share', invariant_ref='HT-INV-05',
            verdict='unevaluated', measured=None, required=f'>= {minimum:.0%}',
            detail=('Every non-repeated HTS assembly needs one explicit standard/special '
                    'component classification. '
                    f'Unknown: {unknown[:5]}; contradictory: {contradictory[:5]}.'))
    # One assembly enters exactly one side of the denominator. Explicit special
    # metadata overrides the HTA repeated-family default; explicit standard metadata
    # is what lets a continuous HTS edge-return kit declare that it is repeatable.
    special = {ident for ident, refs in assembly_refs.items()
               if 'HT-SPECIAL-COMPONENT' in refs}
    standard = {
        ident for ident, refs in assembly_refs.items()
        if ident not in special
        and (ident.startswith('HTA-') or 'HT-STANDARD-COMPONENT' in refs)}
    share = len(standard) / len(assembly_ids)
    ok = share >= minimum
    return GateResult(
        id='high_tech_standard_component_share', invariant_ref='HT-INV-05',
        verdict='passed' if ok else 'failed', measured=round(share, 4),
        required=f'>= {minimum:.0%}',
        detail=f'{len(standard)} standard assembly/component IDs and {len(special)} named '
               f'special IDs in a {len(assembly_ids)}-ID denominator '
               f'({share:.1%} standard); instance density does not enter this count.')


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def evaluate(model) -> FacadeGateReport:
    """Run every gate this grammar's guide declares."""
    spec = GRAMMAR_SPECS[model.facade_grammar_id]
    gates = [
        _gate_opening_ratio(model, spec),
        _gate_material_families(model, spec),
        _gate_minimum_fragment(model, spec),
    ]
    if spec.score_control == 'opaque_share':
        gates.append(_gate_score_authority(model, spec))
    if spec.grammar_id == 'FCD-05-HIGH-TECH':
        gates.extend([
            _gate_high_tech_assembly_metadata(model),
            _gate_high_tech_system_roles(model),
            _gate_high_tech_primary_bays(model, spec),
            _gate_high_tech_submodules(model, spec),
            _gate_high_tech_system_depth(model, spec),
            _gate_high_tech_interfaces(model),
            _gate_high_tech_program_control(model),
            _gate_high_tech_secondary_density(model, spec),
            _gate_high_tech_standard_share(model, spec),
        ])
    if spec.requires_orientation_response:
        gates.append(_gate_orientation_response(model, spec))
    if spec.neighbour_jump_max is not None:
        gates.append(_gate_neighbour_jump(model, spec))
    if spec.unique_panel_ratio_max is not None:
        gates.append(_gate_unique_panels(model, spec))
    if spec.requires_recoverable_baseline:
        gates.append(_gate_recoverable_baseline(model, spec))
    closures = [group for group in model.element_groups
                if 'ENVELOPE-CLOSURE-UNRESOLVED-GRAMMAR' in group.rule_refs]
    if closures:
        gates.append(GateResult(id='closure_grammar', invariant_ref='GEOMETRIC-CLOSURE',
            verdict='unevaluated', measured=float(sum(len(group.instances) for group in closures)),
            required='Closed boundary with guide-compatible opening modules',
            detail='Solid closure pieces close short boundary fragments; their local grammar '
                   'fit remains unresolved even if the overall opening ratio is inside its band.'))
    return FacadeGateReport(
        grammar_id=spec.grammar_id, grammar_label=spec.label,
        guide_ref=spec.guide_ref, gates=gates)


def correction_for(report: FacadeGateReport) -> tuple[float, str] | None:
    """A deterministic repair for the one failure that has one, or nothing.

    Only the opening ratio qualifies. It is a scalar the emitter already accepts, the
    direction of the fix is unambiguous, and the target is published in the guide. Every
    other failure -- a sliver panel, too many materials, a neighbour jump -- would need
    a judgement about what the designer meant, and a compiler that guesses at that is
    more dangerous than one that reports the failure and stops.
    """
    for gate in report.failures:
        if gate.id != 'opening_ratio' or gate.measured is None:
            continue
        low, _, high = gate.required.partition('-')
        low, high = float(low), float(high)
        target = min(high, max(low, gate.measured))
        target = high - 0.04 if gate.measured > high else low + 0.04
        return target, (
            f'Opening ratio came out at {gate.measured:.2f} against a published band of '
            f'{low:.2f}-{high:.2f}; re-emitted with the opaque share adjusted to land '
            f'near {target:.2f}.')
    return None
