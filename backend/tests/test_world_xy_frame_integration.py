"""World registration reaches real member emission; no full-building approval."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from shapely.geometry import box

from backend.app.compiler_v3 import (
    _Builder, _core_rects, _emit_structure, _frame_the_volumes, _run_sizing,
    _stair_sites,
)
from backend.app.program import ProgramAllocation
from backend.app.program_massing import (
    ProgramMassing, datums_for, lattice_for, neutral_score,
)
from backend.app.tectonics import FRAME_TECTONICS
from backend.app.world_xy_grid import WorldXYGrid


def _massing(origin=(0, 0)):
    return ProgramMassing.model_validate({
        'levels': [
            {'id': name, 'kind': kind, 'z': z,
             'plate': [(0, 0), (24, 0), (24, 18), (0, 18)],
             'voids': [] if kind == 'podium' else [[(7.5, 3.5), (8.5, 3.5), (8.5, 4.5), (7.5, 4.5)]]}
            for name, kind, z in [('L00', 'podium', 0), ('L01', 'occupied', .3),
                                  ('L02', 'occupied', 4.3), ('L03', 'roof', 8.3)]],
        'grid': {'x_lines': [0, 3, 17, 24], 'y_lines': [0, 2, 13, 18]},
        'world_xy_grid': {'origin': origin, 'spacing_x': 4, 'spacing_y': 4},
        'cores': [{'id': 'A', 'kind': 'stair', 'x': 6, 'y': 13},
                  {'id': 'B', 'kind': 'stair', 'x': 19, 'y': 13},
                  {'id': 'LIFT', 'kind': 'lift', 'x': 12, 'y': 14}],
        'datums': {'flight_width_m': 1.2, 'ground_open_height_m': .3},
    })


def _frame(origin=(0, 0), *, massing=None):
    massing = massing or _massing(origin)
    datums = datums_for(massing, neutral_score(massing))
    lattice = lattice_for(massing, datums)
    before = (list(lattice.x_lines), list(lattice.y_lines))
    builder = _Builder(datums, lattice)
    assert before == (lattice.x_lines, lattice.y_lines)
    allocation = ProgramAllocation(zones=[], unplaced=[], usable_area_by_level={},
                                   required_area_m2=0, delivered_area_m2=0)
    builder.program_allocation = allocation
    frame = FRAME_TECTONICS['FRM-STEEL']
    occupancy, sizing = _run_sizing(datums, lattice, allocation, frame)
    _emit_structure(builder, sizing, frame, occupancy)
    return builder


def test_independent_grid_survives_cores_and_sizes_at_its_own_pitch():
    builder = _frame()
    lattice = builder.lattice
    assert lattice.x_lines == [0, 4, 8, 12, 16, 20, 24]
    assert lattice.y_lines == [0, 4, 8, 12, 16, 20]
    assert builder.datums.value('bay_x_m') == builder.datums.value('bay_y_m') == 4
    moved = deepcopy(builder.cores)
    moved['primary'] = (5, 11)
    _frame_the_volumes(lattice, moved, builder.datums)
    assert lattice.x_lines == [0, 4, 8, 12, 16, 20, 24]


@pytest.mark.parametrize('boundary', [False, True])
def test_both_column_sources_respect_shared_entrance_approach(monkeypatch, boundary):
    baseline = _frame()
    columns = [e for group in baseline.groups.values() for e in group.expand()
               if e.kind in ('column','piloti_column')]
    target = next(e for e in columns if e.id.startswith('STR-WXB-COL') == boundary)
    p = target.geometry.path[0]
    protected = box(p.x-.4,p.y-.4,p.x+.4,p.y+.4)
    monkeypatch.setattr('backend.app.envelope.planned_entrance',
        lambda *args: SimpleNamespace(level_id='L01',aperture=protected,
                                     inside_approach=protected,outside_approach=protected))
    revised = _frame()
    remaining = [e for group in revised.groups.values() for e in group.expand()
                 if e.kind in ('column','piloti_column')]
    assert target.id not in {e.id for e in remaining}
    assert revised.lattice.world_xy_grid == baseline.lattice.world_xy_grid


def test_real_columns_and_beams_use_world_nodes_and_avoid_carved_floor():
    builder = _frame()
    elements = [element for group in builder.groups.values() for element in group.expand()]
    columns = [e for e in elements if e.kind in ('column', 'piloti_column')]
    beams = [e for e in elements if e.kind == 'primary_beam']
    assert columns and beams
    for element in columns:
        p = element.geometry.path[0]
        if 'boundary_station' in element.lattice_index:
            station = builder.lattice.world_xy_column_plan.candidates[element.lattice_index['boundary_station']]
            assert (p.x,p.y) == pytest.approx(station.point_xy, abs=1e-5)
            axis = station.grid_line_axis
            value = p.x if axis == 'x' else p.y
            assert value == pytest.approx(builder.lattice.world_xy_grid.coordinate(axis,station.grid_line_index))
        else:
            assert p.x / 4 == pytest.approx(round(p.x / 4))
            assert p.y / 4 == pytest.approx(round(p.y / 4))
        profile = builder.profiles[element.geometry.profile]
        half = max(profile.width_m, profile.depth_m) / 2
        footprint = box(p.x-half, p.y-half, p.x+half, p.y+half)
        assert not footprint.intersects(box(7.5, 3.5, 8.5, 4.5))
        assert all(footprint.intersection(box(*r)).area == 0 for r in _core_rects(builder.cores))
    for element in beams:
        assert len(element.supports) == 2
        assert all(support in builder.element_ids for support in element.supports)


def test_boundary_registry_drives_continuous_real_columns_and_in_floor_spans():
    from shapely.geometry import Polygon, LineString
    from backend.app.compiler_v3 import _opening_rects

    builder = _frame()
    records = {e.id:e for g in builder.groups.values() for e in g.expand()}
    boundary = [e for e in records.values() if e.id.startswith('STR-WXB-COL')]
    spans = [e for e in records.values() if e.id.startswith('STR-WXB-BM')]
    assert boundary and spans
    assert builder.lattice.world_xy_column_plan is not None
    for column in boundary:
        assert column.sizing_status == 'architectural_convention'
        assert column.utilisation is None
        visited, cursor = set(), column
        while cursor.kind != 'footing':
            assert cursor.id not in visited
            visited.add(cursor.id)
            assert len(cursor.supports) == 1
            cursor = records[cursor.supports[0]]
        assert cursor.id.startswith('STR-WXB-FDN')
    for span in spans:
        assert span.sizing_status == 'architectural_convention'
        level = next(lv for lv in builder.lattice.levels if lv.id == span.level_id)
        domain = Polygon([(p.x,p.y) for p in level.plate],
                         holes=[[(p.x,p.y) for p in ring] for ring in level.voids])
        for rect in _core_rects(builder.cores)+_opening_rects(builder.cores,level.id):
            domain = domain.difference(box(*rect))
        width = builder.profiles[span.geometry.profile].width_m
        body = LineString([(p.x,p.y) for p in span.geometry.path]).buffer(width/2,cap_style=2)
        assert domain.buffer(1e-5).covers(body)
        assert len(span.supports) == 2
        for point,host in zip(span.geometry.path,span.supports):
            column = records[host]
            assert (point.x,point.y) == pytest.approx(
                (column.geometry.path[-1].x,column.geometry.path[-1].y))


def test_boundary_beams_exist_before_direct_bearing_slabs_collect_hosts():
    # The retreat has no interior grid row for a regular joist bay. Its slab
    # therefore uses the primary-beam fallback, including new boundary spans.
    massing = _massing()
    massing.levels[-1].plate = [(0,0),(24,0),(24,3),(0,3)]
    massing.levels[-1].voids = []
    for core in massing.cores:
        core.serves = ['L00', 'L01', 'L02']
    builder = _frame(massing=massing)
    slabs = [e for group in builder.groups.values() for e in group.expand()
             if e.kind == 'floor_slab' and e.level_id == 'L03']
    assert slabs
    assert any(any(host.startswith('STR-WXB-BM-') for host in slab.supports)
               for slab in slabs)


@pytest.mark.parametrize('retreat', [10.0, 7.98])
def test_upper_retreat_does_not_duplicate_lower_regular_beam_spans(retreat):
    from itertools import combinations
    from shapely.geometry import LineString

    massing = _massing()
    massing.levels[-1].plate = [(0,0),(24,0),(24,18),(0,18),
                                    (0,9),(retreat,9),(retreat,3),(0,3)]
    massing.levels[-1].voids = []
    builder = _frame(massing=massing)
    beams = [e for g in builder.groups.values() for e in g.expand() if e.kind == 'primary_beam']
    for first,second in combinations(beams,2):
        if first.level_id != second.level_id:
            continue
        a = LineString([(p.x,p.y) for p in first.geometry.path])
        c = LineString([(p.x,p.y) for p in second.geometry.path])
        assert a.intersection(c).length < 1e-4, (first.id,second.id)
    columns = [e for g in builder.groups.values() for e in g.expand()
               if e.kind in ('column','piloti_column')]
    def footprint(column):
        p,d = column.position,column.dimensions
        return box(p.x-d.x/2,p.y-d.y/2,p.x+d.x/2,p.y+d.y/2)
    for first,second in combinations(columns,2):
        if first.level_id == second.level_id:
            assert footprint(first).intersection(footprint(second)).area < 1e-7


def test_grid_phase_changes_members_without_changing_program_plate():
    first, second = _frame(), _frame((1, 1))
    assert [level.plate for level in first.lattice.levels] == [level.plate for level in second.lattice.levels]
    def points(builder):
        return {(i.geometry.path[0].x, i.geometry.path[0].y)
                for g in builder.groups.values() if g.kind == 'column' for i in g.instances}
    assert points(first) and points(second) and points(first) != points(second)


def test_exact_carrier_contact_is_found_without_whole_plan_sampling():
    massing = _massing()
    datums = datums_for(massing, neutral_score(massing))
    lattice = lattice_for(massing, datums)
    from backend.app.compiler_v3 import _core_box
    from backend.app.datums import flight_run
    anchor = (5.1234, 12.9876)
    carrier = box(*_core_box(*anchor, 1.2, flight_run(1.2)))
    sites = _stair_sites(lattice, 1.2, flight_run(1.2), lattice.occupied,
                         allowed_by_level={level.id: carrier for level in lattice.occupied})
    assert any(abs(x-anchor[0]) < 1e-7 and abs(y-anchor[1]) < 1e-7 for x, y in sites)


def test_world_grid_round_trips_as_a_separate_contract():
    massing = _massing()
    restored = ProgramMassing.model_validate_json(massing.model_dump_json())
    assert restored.world_xy_grid == WorldXYGrid(spacing_x=4, spacing_y=4)
    assert restored.grid.x_lines == [0, 3, 17, 24]


@pytest.mark.parametrize('defect', [None, 'plate', 'lift'])
def test_registered_core_faces_share_numeric_identity_but_real_overlap_is_rejected(defect):
    from backend.app.compiler_v3 import core_anchors

    massing = _massing()
    massing.cores[0].x, massing.cores[0].y = 6.25, 15.26
    massing.cores[2].x, massing.cores[2].y = 9.27, 13.42
    for level in massing.levels:
        west = 4.731 if defect == 'plate' else 4.73
        level.plate = [(west,0),(24,0),(24,18.6),(west,18.6)]
    if defect == 'lift':
        massing.cores[2].x -= .001
    datums = datums_for(massing, neutral_score(massing))
    lattice = lattice_for(massing, datums)
    if defect:
        with pytest.raises(ValueError, match='does not stand|stands in stair'):
            core_anchors(lattice, datums)
    else:
        anchors = core_anchors(lattice, datums)
        assert anchors['primary'] == (6.25,15.26)
        assert anchors['lift'][:2] == (9.27,13.42)
