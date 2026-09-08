"""The grid follows the volumes, and the core is structure (decision 0022).

What these hold, each as a measurement rather than a claim:

- a grid node standing exactly on the plate boundary is on the plate. The ray-casting
  test answered that by which way the edge ran, so every building stood columns on
  three sides and framed nothing along the fourth;
- the grid is drawn to the cores: every face of a stair core is a grid line, the
  module fills the spans between fixed lines, no line is added inside a core, a
  massing's own grid keeps every line, and the operation is idempotent;
- a site whose face leaves a sliver against the plate edge is ranked behind one that
  does not;
- an overhead member is measured as the section it is, at the place it passes;
- the approach landings own their footprint.
"""

from types import SimpleNamespace as NS

import pytest

from backend.app.compiler_v3 import (
    _approach_landing_footprints, _core_box, _core_rects, _frame_the_volumes, _on_plate,
    _sliver_faces,
)
from backend.app.datums import MIN_BAY_M
from backend.app.geometry import BoxGeometry, MemberGeometry, ProfileSpec, v2, v3
from backend.app.geometry_review import check_stair_head_clearance


# ---------------------------------------------------------------------------
# Nodes on the boundary
# ---------------------------------------------------------------------------

def test_a_node_on_the_plate_edge_is_on_the_plate():
    plate = [v2(0.0, 0.0), v2(10.0, 0.0), v2(10.0, 8.0), v2(0.0, 8.0)]
    for x, y in ((5.0, 0.0), (5.0, 8.0), (0.0, 4.0), (10.0, 4.0),
                 (0.0, 0.0), (10.0, 8.0)):
        assert _on_plate(plate, x, y), (x, y)
    assert _on_plate(plate, 5.0, 4.0)
    assert not _on_plate(plate, 5.0, 8.05)
    assert not _on_plate(plate, -0.05, 4.0)


# ---------------------------------------------------------------------------
# The grid follows the volumes
# ---------------------------------------------------------------------------

def _lattice(x_lines, y_lines, carved=None, grid_given=False):
    return NS(x_lines=list(x_lines), y_lines=list(y_lines), carved=carved or {},
              grid_given=grid_given)


def _datums(bay_x=6.0, bay_y=7.0):
    return NS(value=lambda name: {'bay_x_m': bay_x, 'bay_y_m': bay_y}[name])


def _anchors(primary, second=None, width=1.8):
    from backend.app.datums import flight_run
    return {'width': width, 'run': flight_run(width), 'primary': primary,
            'second': second, 'extras': [], 'lift': None}


def test_every_core_face_is_a_grid_line_and_no_line_runs_through_a_core():
    lattice = _lattice([0.0, 6.0, 12.0, 18.0, 24.0, 30.0], [0.0, 7.0, 14.0, 21.0])
    anchors = _anchors((20.0, 10.0))
    _frame_the_volumes(lattice, anchors, _datums())
    (x0, y0, x1, y1), = _core_rects(anchors)
    for face, lines in ((x0, lattice.x_lines), (x1, lattice.x_lines),
                        (y0, lattice.y_lines), (y1, lattice.y_lines)):
        assert any(abs(face - line) <= 0.05 for line in lines), (face, lines)
    assert not any(x0 + 0.05 < line < x1 - 0.05 for line in lattice.x_lines)
    assert not any(y0 + 0.05 < line < y1 - 0.05 for line in lattice.y_lines)
    # The plate extents stay, and the module fills the rest at roughly its pitch.
    assert lattice.x_lines[0] == 0.0 and lattice.x_lines[-1] == 30.0
    gaps = [b - a for a, b in zip(lattice.x_lines, lattice.x_lines[1:])]
    assert all(gap <= 6.0 * 1.5 + 1e-6 for gap in gaps), gaps


def test_drawing_the_grid_to_the_cores_is_idempotent():
    lattice = _lattice([0.0, 6.0, 12.0, 18.0, 24.0, 30.0], [0.0, 7.0, 14.0, 21.0])
    anchors = _anchors((20.0, 10.0), (5.0, 4.5))
    _frame_the_volumes(lattice, anchors, _datums())
    once = (list(lattice.x_lines), list(lattice.y_lines))
    _frame_the_volumes(lattice, anchors, _datums())
    assert (lattice.x_lines, lattice.y_lines) == once


def test_a_given_grid_keeps_its_lines_except_a_sliver_from_a_core_face():
    given_x, given_y = [0.0, 6.3, 12.6, 18.9, 25.2], [0.0, 9.0, 18.0]
    lattice = _lattice(given_x, given_y, grid_given=True)
    anchors = _anchors((15.75, 4.5))
    _frame_the_volumes(lattice, anchors, _datums())
    (x0, y0, x1, y1), = _core_rects(anchors)
    # 12.6 and 18.9 stand under a metre from the core faces: the volume outranks
    # the module there, and they go. Every other given line stays.
    assert 0.05 < x0 - 12.6 < MIN_BAY_M and 0.05 < 18.9 - x1 < MIN_BAY_M
    assert 12.6 not in lattice.x_lines and 18.9 not in lattice.x_lines
    assert {0.0, 6.3, 25.2} <= set(lattice.x_lines)
    assert {round(x0, 4), round(x1, 4)} <= set(lattice.x_lines)
    # Likewise 9.0, half a metre from the core's north face; 0.0 and 18.0 stay.
    assert 0.05 < 9.0 - y1 < MIN_BAY_M
    assert 9.0 not in lattice.y_lines and {0.0, 18.0} <= set(lattice.y_lines)
    assert {round(y0, 4), round(y1, 4)} <= set(lattice.y_lines)


def test_carved_room_edges_stay_fixed_lines():
    lattice = _lattice([0.0, 6.0, 12.0, 18.0, 24.0], [0.0, 7.0, 14.0, 21.0],
                       carved={2: [(6.0, 0.0, 18.0, 14.0)]})
    _frame_the_volumes(lattice, _anchors((21.0, 17.5)), _datums())
    assert {6.0, 18.0} <= set(lattice.x_lines)
    assert 14.0 in lattice.y_lines


def test_a_face_a_sliver_from_the_plate_edge_is_penalised():
    lattice = _lattice([0.0, 30.0], [0.0, 21.0])
    width, run = 1.8, 4.32
    clean = _core_box(15.0, 10.5, width, run)
    assert _sliver_faces(lattice, clean, ()) == 0
    # A core whose west face stands 0.8 m inside the plate edge leaves a 0.8 m bay.
    x0 = clean[0]
    sliver = _core_box(15.0 - (x0 - 0.8), 10.5, width, run)
    assert 0.05 < sliver[0] < MIN_BAY_M
    assert _sliver_faces(lattice, sliver, ()) == 1
    # Flush with the edge is not a sliver: the wall is the perimeter there.
    flush = _core_box(15.0 - x0, 10.5, width, run)
    assert abs(flush[0]) < 0.05
    assert _sliver_faces(lattice, flush, ()) == 0


# ---------------------------------------------------------------------------
# Head clearance against real sections
# ---------------------------------------------------------------------------

def _model(*members):
    tread = NS(kind='stair_tread', instances=[NS(
        id='CIR-TRD-A00-S003', level_id='L01',
        geometry=BoxGeometry(center=v3(5.0, 5.0, 1.0), size=v3(1.2, 0.3, 0.05)))])
    groups = [tread] + [NS(kind=kind, instances=[NS(id=name, level_id='L01', geometry=geometry)])
                        for name, kind, geometry in members]
    profiles = {'BEAM': ProfileSpec(id='BEAM', shape='i_section', depth_m=0.4,
                                    width_m=0.2, web_m=0.01, flange_m=0.015)}
    return NS(element_groups=groups, profiles=profiles)


def _violations(model):
    return [f for f in check_stair_head_clearance(model) if f.severity == 'violation']


def _warnings(model):
    return [f for f in check_stair_head_clearance(model) if f.severity == 'warning']


def test_a_beam_low_over_a_tread_is_a_measured_violation():
    model = _model(('STR-BMX-X00-Y00-L02', 'primary_beam',
                    MemberGeometry(path=[v3(0.0, 5.0, 2.6), v3(10.0, 5.0, 2.6)],
                                   profile='BEAM')))
    findings = _violations(model)
    assert len(findings) == 1
    assert findings[0].measure == pytest.approx(1.375, abs=1e-3)
    assert not _warnings(model)


def test_a_beam_clear_over_a_tread_is_no_finding_and_no_warning():
    model = _model(('STR-BMX-X00-Y00-L02', 'primary_beam',
                    MemberGeometry(path=[v3(0.0, 5.0, 3.6), v3(10.0, 5.0, 3.6)],
                                   profile='BEAM')))
    assert not _violations(model)
    assert not _warnings(model), 'a declared section is measured, not warned about'


def test_a_diagonal_is_measured_where_it_crosses_the_tread():
    model = _model(('STR-BRC-X00-L01-D1', 'brace',
                    MemberGeometry(path=[v3(0.0, 5.0, 0.5), v3(10.0, 5.0, 6.5)],
                                   profile='BEAM')))
    assert not _violations(model)


def test_a_post_beside_the_stair_is_not_overhead():
    model = _model(('ENV-FRM-L01-S000', 'frame_expression',
                    MemberGeometry(path=[v3(5.0, 5.0, 0.0), v3(5.0, 5.0, 4.0)],
                                   profile='BEAM')))
    assert not _violations(model)
    assert not _warnings(model)


def test_a_member_without_a_declared_section_stays_a_warning():
    model = _model(('STR-BMX-X00-Y00-L02', 'primary_beam',
                    MemberGeometry(path=[v3(0.0, 5.0, 2.6), v3(10.0, 5.0, 2.6)],
                                   profile='UNDECLARED')))
    assert not _violations(model)
    assert _warnings(model), 'an unknown section is not silently a pass'


# ---------------------------------------------------------------------------
# Approach landings own their footprint
# ---------------------------------------------------------------------------

def test_approach_footprints_are_cut_on_the_podium_only():
    approach = {'podium_id': 'L01', 'entry': (1.0, 2.0, 3.0, 4.0),
                'access': None, 'ramp_top': (5.0, 6.0, 7.0, 8.0)}
    assert _approach_landing_footprints(approach, 'L01') == [
        (1.0, 2.0, 3.0, 4.0), (5.0, 6.0, 7.0, 8.0)]
    assert _approach_landing_footprints(approach, 'L02') == []
