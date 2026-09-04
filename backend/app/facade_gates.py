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

from pydantic import BaseModel

from .geometry import BoxGeometry, QuadGeometry
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

    @property
    def passed(self) -> bool:
        return not any(g.verdict == 'failed' for g in self.gates)

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
_NOT_THE_WALL = {'canopy', 'roof', 'parapet', 'applied_order'}


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
    low, high = spec.material_families
    count = len(materials)
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
            verdict='unevaluated', required=f'>= {spec.minimum_fragment_m} m',
            detail='No panel-like element to measure.')
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
# Entry
# ---------------------------------------------------------------------------

def evaluate(model) -> FacadeGateReport:
    """Run every gate this grammar's guide declares."""
    spec = GRAMMAR_SPECS[model.facade_grammar_id]
    gates = [
        _gate_opening_ratio(model, spec),
        _gate_material_families(model, spec),
        _gate_minimum_fragment(model, spec),
        _gate_score_authority(model, spec),
    ]
    if spec.requires_orientation_response:
        gates.append(_gate_orientation_response(model, spec))
    if spec.neighbour_jump_max is not None:
        gates.append(_gate_neighbour_jump(model, spec))
    if spec.unique_panel_ratio_max is not None:
        gates.append(_gate_unique_panels(model, spec))
    if spec.requires_recoverable_baseline:
        gates.append(_gate_recoverable_baseline(model, spec))
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
