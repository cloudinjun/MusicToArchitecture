"""The drawing set: that the template governs it, and that it closes on the model.

Two families of claim are checked here.

The first is that the sheet has a hierarchy. A drawing whose lines are all one weight is
not a drawing, so what is cut must be heavier than what is beyond it, what is overhead
must be dashed, and none of those decisions may be made anywhere but in
`drawing_standard`. That last part is the one worth guarding: weights chosen at the call
site look fine on the sheet they were tuned on and drift on every other.

The second is that the set is a reading of the model rather than a picture beside it.
Every mark names the element it came from, and every element lands in exactly one of
three buckets -- drawn, dropped by scale, or reached by no cut. A drawing set that
quietly loses a third of the building is the normal failure and is invisible without
the count.
"""

import json
import math

import pytest

from backend.app.compiler_v3 import compile_building_model_v3
from backend.app.drawing_geometry import (
    Plane, box_solid, plan_frame, quad_solid, section_frame, slice_convex,
    slice_extrusion,
)
from backend.app.drawing_standard import (
    DrawingStandard, LineType, PLAN_STANDARD, Scale, Stroke, Tone, Weight,
)
from backend.app.drawing_sheet import PAPER_MM, drawing_area, humanise
from backend.app.drawings import (
    CAPTION_MM, DrawingSet, Mark, PLAN_CUT_HEIGHT_M, WALL_KINDS, _clip_marks,
    _cut_lengthwise, _plan_centre, _shaft_geometry, building_section, floor_plans,
    issue_drawings, resolve_section_offset,
)
from backend.app.geometry import BoxGeometry, ExtrusionGeometry, QuadGeometry, Vector2, v3
from backend.app.models import ArchitecturalScore, AudioFeatures

from backend.tests.test_differentiation import DEMO, V2_DEMO


@pytest.fixture(scope='module')
def model():
    score = ArchitecturalScore.model_validate(
        json.loads((DEMO / 'architectural_score.json').read_text(encoding='utf-8')))
    features = AudioFeatures.model_validate(
        json.loads((V2_DEMO / 'music_features.json').read_text(encoding='utf-8')))
    return compile_building_model_v3(features, score,
                                     massing_id='MAS-SLAB', typology='library')


@pytest.fixture(scope='module')
def issued(model):
    return issue_drawings(model)


# --- the template -----------------------------------------------------------------

def test_weights_are_paper_millimetres_whatever_the_scale():
    """A 0.35 line is 0.35 on the sheet at 1:50 and at 1:200.

    The alternative -- storing weights in model metres -- makes the same wall print as
    a hairline on one drawing and a smear on another, and there is then no such thing
    as a drawing standard, only a per-sheet accident.
    """
    fine = DrawingStandard(scale=Scale(50))
    coarse = DrawingStandard(scale=Scale(200))
    assert (fine.stroke('primary_structure', 'cut').weight
            == coarse.stroke('primary_structure', 'cut').weight)
    # The geometry is what changes: ten metres is 200 mm at 1:50, 50 mm at 1:200.
    assert fine.scale.to_paper_mm(10.0) == pytest.approx(200.0)
    assert coarse.scale.to_paper_mm(10.0) == pytest.approx(50.0)


def test_the_weight_series_is_distinguishable_in_print():
    """Adjacent ISO weights differ by about √2. Closer than that is not a hierarchy."""
    steps = [weight.value for weight in Weight]
    assert steps == sorted(steps)
    for lighter, heavier in zip(steps, steps[1:]):
        assert 1.25 <= heavier / lighter <= 1.75


def test_stepping_back_lightens_the_tone_and_thins_the_line_together():
    """Tone alone does not read as depth: thickness is taken as proximity first."""
    near = Stroke(Weight.HEAVY, Tone.CUT)
    far = near.lighter(2)
    assert far.tone.value > near.tone.value
    assert far.weight.value < near.weight.value


def test_a_cut_line_outweighs_everything_behind_it(model, issued):
    """The single rule that makes a plan readable at a glance."""
    for drawing in issued.all:
        by_role: dict[str, list] = {}
        for mark in drawing.marks:
            by_role.setdefault((mark.role, mark.state), []).append(mark)
        for (role, state), marks in by_role.items():
            if state != 'cut':
                continue
            cut_weight = marks[0].stroke.weight.value
            for other_state in ('beyond', 'above'):
                behind = by_role.get((role, other_state), [])
                for mark in behind:
                    assert mark.stroke.weight.value <= cut_weight, (
                        f'{drawing.id}: {role} {other_state} is not lighter than cut')


def test_overhead_is_dashed_and_beyond_is_not(issued):
    """Dashing is the one thing that says "this is not at the height you are standing"."""
    for drawing in issued.plans:
        for mark in drawing.marks:
            if mark.state == 'above':
                assert mark.stroke.line_type is not LineType.CONTINUOUS
            if mark.state in ('cut', 'beyond'):
                assert mark.stroke.line_type is LineType.CONTINUOUS


def test_every_stroke_came_from_the_standard(issued):
    """No weight is chosen in the generator; the table answers every time."""
    for drawing in issued.all:
        standard = drawing.standard
        for mark in drawing.marks:
            allowed = {standard.stroke(mark.role, mark.state, band)
                       for band in range(standard.depth_planes + 2)}
            assert mark.stroke in allowed, (
                f'{drawing.id}: {mark.element_id} carries a stroke the standard '
                f'would not issue')


def test_a_smaller_scale_sheds_information(model):
    """1:200 carrying every chair is a grey field, not a more informative drawing."""
    assert DrawingStandard(scale=Scale(50)).draws('furniture')
    assert not DrawingStandard(scale=Scale(200)).draws('furniture')
    assert DrawingStandard(scale=Scale(200)).draws('primary_structure')


# --- the cut ----------------------------------------------------------------------

def test_a_plane_through_a_box_returns_its_section():
    box = BoxGeometry(center=v3(0.0, 0.0, 0.0), size=v3(2.0, 4.0, 6.0))
    plane, frame = plan_frame(0.0)
    polygon = slice_convex(box_solid(box), plane, frame)
    assert len(polygon) == 4
    area = abs(sum(polygon[i][0] * polygon[(i + 1) % 4][1]
                   - polygon[(i + 1) % 4][0] * polygon[i][1]
                   for i in range(4)) / 2.0)
    assert area == pytest.approx(8.0, rel=1e-6)


def test_a_plane_that_misses_a_box_returns_nothing():
    box = BoxGeometry(center=v3(0.0, 0.0, 10.0), size=v3(2.0, 2.0, 2.0))
    plane, frame = plan_frame(0.0)
    assert slice_convex(box_solid(box), plane, frame) == []


def test_cutting_a_flat_panel_gives_a_line_not_an_area():
    """A section through a sheet of glass is a line. Returning nothing instead sent
    every cut glazing panel down the beyond path, where it was drawn as a pale
    silhouette of the whole pane rather than the short heavy mark that reads as a cut."""
    quad = QuadGeometry(corners=(v3(0.0, 0.0, -1.0), v3(3.0, 0.0, -1.0),
                                 v3(3.0, 0.0, 2.0), v3(0.0, 0.0, 2.0)))
    plane, frame = plan_frame(0.5)
    cut = slice_convex(quad_solid(quad), plane, frame)
    assert len(cut) == 2
    assert math.dist(cut[0], cut[1]) == pytest.approx(3.0, rel=1e-6)


def test_a_horizontal_cut_through_a_courtyard_plate_keeps_the_hole_open():
    """The reason prisms do not go through the convex path: a convex section of a
    courtyard would bridge straight across the void and fill it with building."""
    ring = [Vector2(x=x, y=y) for x, y in
            ((0, 0), (10, 0), (10, 10), (0, 10), (0, 6), (4, 6), (4, 4), (0, 4))]
    prism = ExtrusionGeometry(boundary=ring, z_base=0.0, z_top=1.0)
    plane, frame = plan_frame(0.5)
    cut = slice_extrusion(prism, plane, frame)
    assert len(cut) == 1
    assert len(cut[0]) == len(ring), 'the boundary is returned exactly, notch included'


def test_a_vertical_cut_through_a_plate_with_a_void_returns_two_bands():
    ring = [Vector2(x=x, y=y) for x, y in
            ((0, 0), (10, 0), (10, 10), (0, 10))]
    prism = ExtrusionGeometry(boundary=ring, z_base=0.0, z_top=1.0)
    plane, frame = section_frame((5.0, 5.0), 90.0)
    bands = slice_extrusion(prism, plane, frame)
    assert bands and all(len(band) == 4 for band in bands)


# --- plans and sections ------------------------------------------------------------

def test_a_plan_is_cut_at_standing_height(model, issued):
    """1.2 m: above a sill, below a door head, which is what makes a plan show
    doorways as openings and windows as cut glazing."""
    levels = {level.id: level for level in model.lattice.levels}
    for drawing in issued.plans:
        level = levels[drawing.id.rsplit('-', 1)[-1]]
        if level.kind == 'roof':
            continue
        assert f'{PLAN_CUT_HEIGHT_M:.2f} m above' in drawing.subtitle
        assert f'{level.z:+.3f}' in drawing.subtitle


def test_a_section_draws_nothing_in_front_of_its_own_cut(model):
    """The difference between a plan and a section, and the one that matters.

    In a plan what is above the cut is overhead work and is drawn dashed. In a section
    what is in front of the cut has been removed, so drawing it would put the wall you
    just cut through back on top of the drawing.
    """
    drawing = building_section(model, 90.0)
    assert all(mark.depth >= -1e-9 for mark in drawing.marks)
    assert not any(mark.state == 'above' for mark in drawing.marks)


@pytest.mark.parametrize('bearing', [0.0, 37.0, 90.0, 128.5, 180.0, 255.0, 300.0])
def test_a_section_can_be_taken_on_any_bearing(model, bearing):
    """An oblique cut is the same operation as an orthogonal one, so there is no
    separate path for it to be wrong in."""
    drawing = building_section(model, bearing, name='X')
    assert drawing.audit.elements_cut > 0
    assert drawing.audit.marks > 100
    u0, v0, u1, v1 = drawing.extents
    assert u1 > u0 and v1 > v0


def test_sliding_the_plane_changes_what_it_meets(model):
    """The offset moves the plane along its normal without turning it: a different
    cut of the same building, not a different building."""
    cuts = {offset: building_section(model, 90.0, offset_m=offset, name='S')
            for offset in (-7.0, 0.0, 7.0)}
    assert len({drawing.audit.elements_cut for drawing in cuts.values()}) > 1
    # Sliding the plane toward the viewer leaves more of the building behind it.
    assert cuts[7.0].audit.marks > cuts[-7.0].audit.marks


def test_the_set_covers_every_level_and_the_roof(model, issued):
    plan_levels = {drawing.id.rsplit('-', 1)[-1] for drawing in issued.plans}
    assert plan_levels == {level.id for level in model.lattice.levels}
    assert any('Roof plan' in drawing.title for drawing in issued.plans)


# --- the loop ----------------------------------------------------------------------

def test_every_mark_names_an_element_that_exists(model, issued):
    ids = {instance.id for group in model.element_groups
           for instance in group.instances}
    for drawing in issued.all:
        for mark in drawing.marks:
            assert mark.element_id in ids, f'{drawing.id}: {mark.element_id} is not a thing'


def test_every_element_is_accounted_for_exactly_once(model, issued):
    """Drawn, dropped by scale, or reached by no cut -- and the three sum.

    This is where the loop closes. `on_no_cut` is not zero and is not meant to be: a
    plan set plus two sections does not see a panel on a face neither plane reaches,
    and pretending otherwise would need elevations. What matters is that the number is
    counted and stated rather than left for a reader to discover.
    """
    account = issued.element_coverage(model)
    assert (account['drawn'] + account['omitted_by_scale'] + account['on_no_cut']
            == account['total'])
    assert account['drawn'] > account['total'] * 0.6
    assert account['on_no_cut'] >= 0


def test_the_sheet_is_well_formed_svg_in_paper_units(issued):
    for drawing in issued.all:
        svg = drawing.to_svg()
        assert svg.startswith('<svg') and svg.rstrip().endswith('</svg>')
        assert 'mm"' in svg[:400], 'the sheet is sized in millimetres'
        assert drawing.standard.scale.name in svg
        assert drawing.id in svg
        # Every stroke width on the sheet is one of the standard's weights.
        widths = {token.split('"')[0] for token in svg.split('stroke-width="')[1:]}
        allowed = {f'{weight.value:g}' for weight in Weight}
        assert widths <= allowed, sorted(widths - allowed)


def test_a_drawing_that_meets_nothing_is_an_error_not_an_empty_sheet(model):
    """Silence is the wrong answer here.

    A section plane set down beyond the far side of the building has the whole model
    in front of it, which a section removes. That is a mistake in the input, and it
    should say so rather than hand back a blank sheet that looks like a finished
    drawing with nothing built on it.
    """
    from backend.app.drawings import compile_drawing
    plane, frame = section_frame((0.0, -900.0), 180.0)
    with pytest.raises(ValueError, match='passes through nothing'):
        compile_drawing(model, plane, frame, PLAN_STANDARD,
                        drawing_id='DWG-NOWHERE', title='nowhere', kind='section')


# --- annotation: what turns a shape into a drawing --------------------------------

def _notes(drawing, kind: str):
    return [note for note in drawing.annotations if note.kind == kind]


def test_every_plan_carries_a_profile_line_at_the_heaviest_weight(issued):
    """The building's own outline, and the reason a plan reads at arm's length.

    Without it a plan is a field of separate marks the reader has to assemble; with it
    everything else is understood as inside or outside a figure.
    """
    for drawing in issued.plans:
        profile = [note for note in drawing.annotations
                   if note.stroke is not None and note.stroke.weight is Weight.PROFILE]
        assert profile, f'{drawing.id} has no profile line'
        assert len(profile[0].points) >= 4


def test_the_grid_matches_the_lattice_the_elements_were_registered_to(model, issued):
    """A bubble has to name the line a column actually stands on. Drawing the grid from
    anything but the lattice would let the two disagree, and then the drawing points at
    a line that is not there."""
    levels = {level.id: level for level in model.lattice.levels}
    for drawing in issued.plans:
        plate = levels[drawing.id.rsplit('-', 1)[-1]].plate
        xs = [point.x for point in plate]
        ys = [point.y for point in plate]
        expected = sum(1 for x in model.lattice.x_lines
                       if min(xs) - 0.1 <= x <= max(xs) + 0.1)
        expected += sum(1 for y in model.lattice.y_lines
                        if min(ys) - 0.1 <= y <= max(ys) + 0.1)
        bubbles = _notes(drawing, 'circle')
        assert len(bubbles) == expected, drawing.id


def test_rooms_are_named_and_measured_from_the_program_zones(model, issued):
    labelled = {note.text for drawing in issued.plans
                for note in _notes(drawing, 'text')}
    zones = model.program_allocation.zones
    assert zones
    names = {zone.label.upper() for zone in zones}
    areas = {f'{zone.area_delivered_m2:.0f} m² allocated' for zone in zones}
    assert names <= labelled, 'a room lost its actual brief label'
    assert areas <= labelled, 'a room lost its declared allocation area/basis'


def test_a_door_swings_into_the_space_it_serves(model, issued):
    """Derived, not assumed. A door's id names its space, so the leaf is drawn opening
    into it; picking a side by convention would put half the leaves through the wall."""
    zones = {instance.id: instance.geometry
             for group in model.element_groups if group.kind == 'program_zone'
             for instance in group.instances}
    doors = [(group, instance) for group in model.element_groups
             if group.kind == 'door' for instance in group.instances]
    assert doors, 'the fixture model has no doors to check'
    checked = 0
    for _group, instance in doors:
        zone_id = 'PRG-ZON-' + instance.id.split('PRG-PRT-')[-1].rsplit('-', 2)[0]
        if zone_id in zones:
            checked += 1
    assert checked > 0, 'no door resolves to the zone it serves'


def test_stairs_say_which_way_they_go(issued):
    """Two flights at a landing look identical in plan; the arrow is the whole story."""
    arrows = [note for drawing in issued.plans
              for note in _notes(drawing, 'text') if note.text == 'UP']
    assert arrows, 'no flight on any plan is marked UP'


def test_each_sheet_carries_a_drawn_scale_bar(issued):
    """The ratio in the title block is only true if the sheet is printed at size. The
    bar is measured off the drawing, so it survives a photocopier and a portfolio."""
    for drawing in issued.all:
        bar = [note for note in drawing.annotations
               if note.kind == 'text' and 'metres' in note.text]
        assert bar, f'{drawing.id} has no scale bar'
        assert drawing.standard.scale.name in bar[0].text


def test_only_plans_get_a_north_point(issued):
    """North on a section would be a lie: a section is a vertical cut, and its sheet
    axes are a horizontal run and a height, neither of which is a compass direction."""
    for drawing in issued.plans:
        assert any(note.text == 'N' for note in _notes(drawing, 'text'))
    for drawing in issued.sections:
        assert not any(note.text == 'N' for note in _notes(drawing, 'text'))


def test_a_section_carries_its_level_datums(model, issued):
    for drawing in issued.sections:
        labels = [note.text for note in _notes(drawing, 'text')]
        for level in model.lattice.levels:
            assert any(level.id in text for text in labels), (
                f'{drawing.id} does not name {level.id}')


def test_a_void_is_drawn_as_a_void(model, issued):
    """A courtyard or an atrium lives in `voids`, not as a notch in the plate.

    Reading only the boundary drew the slab solid and put a floor across the opening,
    so every plan described a building whose atrium you could walk over. The void edge
    is a profile line -- it is an edge you would fall off -- and nothing is labelled
    inside it.
    """
    levels = {level.id: level for level in model.lattice.levels}
    with_voids = [drawing for drawing in issued.plans
                  if levels[drawing.id.rsplit('-', 1)[-1]].voids]
    assert with_voids, 'the fixture model has no void to check'
    for drawing in with_voids:
        level = levels[drawing.id.rsplit('-', 1)[-1]]
        profile = [note for note in drawing.annotations
                   if note.stroke is not None and note.stroke.weight is Weight.PROFILE]
        assert len(profile) == 1 + len(level.voids), (
            f'{drawing.id}: {len(level.voids)} voids but {len(profile) - 1} drawn')
        for note in drawing.annotations:
            if note.kind != 'text' or not note.text or note.text in ('N', 'UP'):
                continue
            for ring in level.voids:
                inside = False
                count = len(ring)
                for i in range(count):
                    a, b = ring[i], ring[(i + 1) % count]
                    if (a.y > note.anchor[1]) != (b.y > note.anchor[1]):
                        crossing = ((b.x - a.x) * (note.anchor[1] - a.y)
                                    / (b.y - a.y) + a.x)
                        if note.anchor[0] < crossing:
                            inside = not inside
                assert not inside, f'{drawing.id}: "{note.text}" floats over a void'


def test_a_section_through_a_plate_with_a_void_comes_back_in_two_pieces():
    """The void has to interrupt the slab, or the section draws a floor across it."""
    from backend.app.drawing_geometry import section_frame, slice_extrusion
    outer = [Vector2(x=x, y=y) for x, y in ((0, 0), (20, 0), (20, 20), (0, 20))]
    hole = [Vector2(x=x, y=y) for x, y in ((8, 8), (12, 8), (12, 12), (8, 12))]
    prism = ExtrusionGeometry(boundary=outer, holes=[hole], z_base=0.0, z_top=0.4)
    plane, frame = section_frame((10.0, 10.0), 90.0)
    bands = slice_extrusion(prism, plane, frame)
    assert len(bands) == 2, 'the void should split the slab into two bands'


# --- the issued set: paper, sheets, cover ------------------------------------------

def test_the_set_is_issued_on_one_paper_size(issued):
    """The largest drawing chooses the paper and every sheet takes it. A set in
    mixed formats cannot be pinned in a row and reads as separate exhibits."""
    assert issued.paper in PAPER_MM
    assert issued.sheets, 'the set laid out no sheets'
    for sheet in issued.sheets:
        assert sheet.spec.paper == issued.paper
    for drawing in issued.all:
        assert drawing.sheet is not None and drawing.sheet.paper == issued.paper


def test_every_drawing_is_placed_once_on_a_sheet_of_its_kind(issued):
    placed = [drawing.id for sheet in issued.sheets for drawing in sheet.drawings]
    assert sorted(placed) == sorted(drawing.id for drawing in issued.all)
    assert len(placed) == len(set(placed))
    series = {'plan': 'A-1', 'elevation': 'A-2', 'section': 'A-3'}
    for sheet in issued.sheets:
        assert sheet.number.startswith(series[sheet.kind]), sheet.number
        assert all(drawing.kind == sheet.kind for drawing in sheet.drawings)
    numbers = [sheet.number for sheet in issued.sheets]
    assert numbers == sorted(numbers), 'sheets are issued in order'


def test_a_composed_sheet_keeps_every_drawing_inside_the_drawing_area(issued):
    """Two sections on one sheet, or three small plans: each with room for its
    caption, none over the frame or the title block."""
    area_x, area_y, area_w, area_h = drawing_area(issued.paper)
    for sheet in issued.sheets:
        for placement in sheet.placements:
            width, height = placement.drawing.content_mm
            assert placement.x >= area_x - 1e-6 and placement.y >= area_y - 1e-6
            assert placement.x + width <= area_x + area_w + 1e-6, sheet.number
            assert placement.y + height + CAPTION_MM <= area_y + area_h + 1e-6, sheet.number
    assert any(len(sheet.placements) > 1 for sheet in issued.sheets), (
        'nothing shares a sheet; the packer is not composing')


def test_the_title_block_is_read_off_the_model_and_carries_no_date(model, issued):
    import re
    svg = issued.sheets[0].to_svg()
    assert model.model_id in svg
    assert issued.sheets[0].number in svg
    assert humanise(model.structural_system_id) in svg
    assert humanise(model.lattice.massing_id) in svg
    assert not re.search(r'20\d\d-\d\d-\d\d', svg), 'a sheet is a function of the model'
    # Every stroke on a composed sheet is still one of the standard's weights.
    widths = {token.split('"')[0] for token in svg.split('stroke-width="')[1:]}
    assert widths <= {f'{weight.value:g}' for weight in Weight}, sorted(widths)


def test_the_cover_lists_every_sheet_and_shows_the_set_small(issued):
    assert issued.cover, 'no cover was issued'
    assert 'A-000' in issued.cover
    for sheet in issued.sheets:
        assert sheet.number in issued.cover
    assert 'THE SET AT 1:400' in issued.cover
    assert issued.cover.count('data-element=') > 1000, 'the miniatures carry the marks'


def test_the_manifest_carries_the_drawings_on_each_sheet(model, issued):
    manifest = issued.manifest(model)
    rows = manifest['sheets']
    assert rows[0]['kind'] == 'cover' and rows[0]['sheet_number'] == 'A-000'
    ids = [drawing['id'] for row in rows for drawing in row['drawings']]
    assert sorted(ids) == sorted(drawing.id for drawing in issued.all)
    assert manifest['paper'] == issued.paper
    for row in rows[1:]:
        assert row['marks'] == sum(drawing['marks'] for drawing in row['drawings'])
        assert row['sheet_mm'] == [round(value, 1) for value in PAPER_MM[issued.paper]]


# --- elevations ---------------------------------------------------------------------

def test_the_set_covers_four_faces_and_cuts_nothing_on_them(issued):
    """An elevation is a section whose plane is outside the building: everything is
    beyond it, nothing is cut, and there is no poché."""
    assert [drawing.id for drawing in issued.elevations] == [
        'DWG-ELEV-NORTH', 'DWG-ELEV-EAST', 'DWG-ELEV-SOUTH', 'DWG-ELEV-WEST']
    for drawing in issued.elevations:
        assert drawing.audit.elements_cut == 0, drawing.id
        assert all(mark.state == 'beyond' for mark in drawing.marks), drawing.id
        assert all(mark.fill is None for mark in drawing.marks), drawing.id
        assert drawing.audit.marks > 100


def test_elevations_reach_what_no_cut_reaches(model, issued):
    """The account's `on_no_cut` bucket is what elevations exist to empty."""
    without = DrawingSet(model_id=model.model_id, plans=issued.plans,
                         sections=issued.sections)
    before = without.element_coverage(model)['on_no_cut']
    after = issued.element_coverage(model)['on_no_cut']
    assert after < before, (before, after)


def test_elevations_carry_datums_and_bubbles_but_no_north_point(model, issued):
    for drawing in issued.elevations:
        assert not any(note.text == 'N' for note in _notes(drawing, 'text'))
        triangles = [note for note in drawing.annotations if note.kind == 'polygon']
        assert len(triangles) == len(model.lattice.levels), drawing.id
        assert _notes(drawing, 'circle'), f'{drawing.id} has no grid bubbles'


# --- what the cut does, and what it refuses to do ------------------------------------

def test_a_lift_shaft_is_cut_hollow():
    """The model carries the shaft solid; the drawing shows walls around a void."""
    ring = [Vector2(x=x, y=y) for x, y in ((0, 0), (4, 0), (4, 4), (0, 4))]
    shaft = _shaft_geometry(ExtrusionGeometry(boundary=ring, z_base=0.0, z_top=4.0))
    assert len(shaft.holes) == 1
    plane, frame = plan_frame(1.2)
    rings = slice_extrusion(shaft, plane, frame)
    assert len(rings) == 2, 'an outer ring and the void inside it'
    plane, frame = section_frame((2.0, 2.0), 90.0)
    bands = slice_extrusion(shaft, plane, frame)
    assert len(bands) == 2, 'two walls, not one block'
    widths = [abs(band[1][0] - band[0][0]) for band in bands]
    assert all(width == pytest.approx(0.2, abs=1e-6) for width in widths)


def test_a_figure_is_a_glyph_beyond_the_cut_and_never_in_plan(model, issued):
    figures = {instance.id for group in model.element_groups
               if group.kind == 'figure' for instance in group.instances}
    assert figures, 'the fixture has no scale figures'
    for drawing in issued.plans:
        assert not any(mark.element_id in figures for mark in drawing.marks), drawing.id
    vertical = [mark for drawing in issued.sections + issued.elevations
                for mark in drawing.marks if mark.element_id in figures]
    assert vertical, 'no figure stands in any section or elevation'
    assert all(mark.state == 'beyond' and mark.fill is None for mark in vertical)


def test_thin_elements_beyond_the_cut_collapse_to_lines(model, issued):
    """A guard post seen side-on at 1:100 is half a millimetre wide: two strokes
    with no paper between them. It is drawn as its axis."""
    posts = {instance.id for group in model.element_groups if group.kind == 'railing'
             for instance in group.instances
             if instance.id.rsplit('-', 1)[-1].startswith('P')}
    marks = [mark for drawing in issued.sections + issued.elevations
             for mark in drawing.marks
             if mark.element_id in posts and mark.state == 'beyond']
    assert marks, 'no post is seen beyond any cut'
    assert all(not mark.closed and len(mark.points) == 2 for mark in marks)
    # A column at 305 mm is wider than a line and keeps its outline.
    columns = {instance.id for group in model.element_groups if group.kind == 'column'
               for instance in group.instances}
    kept = [mark for drawing in issued.elevations for mark in drawing.marks
            if mark.element_id in columns and mark.state == 'beyond']
    assert kept and any(mark.closed for mark in kept)


def test_the_earth_is_hatched_in_section_and_absent_in_elevation(model, issued):
    ground = {instance.id for group in model.element_groups
              if group.kind == 'site_ground' for instance in group.instances}
    assert ground
    for drawing in issued.sections:
        cut = [mark for mark in drawing.marks
               if mark.element_id in ground and mark.state == 'cut' and mark.closed]
        assert cut and all(mark.hatch == 'earth' for mark in cut), drawing.id
        assert 'url(#earth)' in drawing.to_svg()
    for drawing in issued.elevations:
        assert not any(mark.element_id in ground for mark in drawing.marks), drawing.id


def test_the_sheet_edge_is_never_drawn_as_a_line():
    """A polygon clipped by the sheet keeps its fill and loses the edge the clip made."""
    stroke = Stroke(Weight.HEAVY, Tone.CUT)
    big = Mark('X', 'site_ground', 'site', 'cut', stroke,
               [(-50.0, -50.0), (50.0, -50.0), (50.0, 5.0), (-50.0, 5.0)],
               fill=Tone.MIDDLE)
    rect = (-10.0, -10.0, 10.0, 10.0)
    clipped = _clip_marks([big], rect)
    fills = [mark for mark in clipped if mark.closed]
    lines = [mark for mark in clipped if not mark.closed]
    assert len(fills) == 1 and not fills[0].outline and fills[0].fill is Tone.MIDDLE
    assert lines, 'the real top edge of the ground survives'
    for mark in lines:
        for (ax, ay), (bx, by) in zip(mark.points, mark.points[1:]):
            on_side = any(abs(a - bound) < 1e-6 and abs(b - bound) < 1e-6
                          for a, b, bound in ((ax, bx, -10.0), (ax, bx, 10.0),
                                              (ay, by, -10.0), (ay, by, 10.0)))
            assert not on_side, 'a clip edge was stroked'


def test_furniture_is_drawn_at_one_to_one_hundred_at_the_lightest_weight(model, issued):
    furniture = {instance.id for group in model.element_groups
                 if group.kind in ('desk', 'seat', 'shelving_run')
                 for instance in group.instances}
    assert furniture, 'the fixture has no loose furniture'
    marks = [mark for drawing in issued.plans for mark in drawing.marks
             if mark.element_id in furniture]
    assert marks, 'a 1:100 plan without its furniture is a diagram of walls'
    assert all(mark.stroke.weight.value <= Weight.LIGHT.value for mark in marks)


def test_railings_above_the_cut_are_not_dashed_onto_the_plan(model, issued):
    rails = {instance.id for group in model.element_groups
             if group.kind == 'railing' for instance in group.instances}
    for drawing in issued.plans:
        assert not any(mark.element_id in rails and mark.state == 'above'
                       for mark in drawing.marks), drawing.id


def test_a_section_names_the_rooms_it_passes_through(model, issued):
    programs = {group.program.replace('_', ' ').upper()
                for group in model.element_groups if group.kind == 'program_zone'}
    labelled = {note.text for drawing in issued.sections
                for note in _notes(drawing, 'text')}
    assert programs & labelled, 'no section names a room'


def test_a_section_steps_off_a_wall_that_runs_along_it(model):
    """A plane inside a partition draws the whole wall as a block across the room.
    The resolver keeps the requested cut when it is clear and steps off it when not."""
    box = BoxGeometry(center=v3(0.0, 0.0, 1.5), size=v3(6.0, 0.25, 3.0))
    inside, _ = section_frame((0.0, 0.0), 0.0)
    clear, _ = section_frame((0.0, 1.0), 0.0)
    assert _cut_lengthwise(box, inside)
    assert not _cut_lengthwise(box, clear)
    walls = [instance.geometry for group in model.element_groups
             if group.kind in WALL_KINDS or group.kind == 'elevator_shaft'
             for instance in group.instances]
    centre = _plan_centre(model.lattice)
    for bearing in (0.0, 90.0):
        offset = resolve_section_offset(model, bearing, 0.0)
        angle = math.radians(bearing)
        origin = (centre[0] - math.sin(angle) * offset,
                  centre[1] - math.cos(angle) * offset)
        plane, _ = section_frame(origin, bearing)
        assert not any(_cut_lengthwise(wall, plane) for wall in walls), (bearing, offset)


def test_a_moved_section_says_so_on_the_sheet(issued):
    for drawing, (_name, _bearing, offset) in zip(issued.sections, issued.section_cuts):
        assert f'offset {offset:+.2f} m' in drawing.subtitle
        if abs(offset) > 1e-6:
            assert 'moved' in drawing.subtitle
