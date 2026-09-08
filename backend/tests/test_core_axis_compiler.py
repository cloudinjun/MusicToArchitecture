"""Authored stair orientation propagates into physical geometry and its floor claims."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from shapely.affinity import rotate
from shapely.geometry import Polygon, box

from backend.app.compiler_v3 import (
    CORE_DOOR_H_M, CORE_DOOR_W_M, _Builder, _core_box, _core_layout,
    _core_rects, _emit_circulation, _emit_core_walls, _landing_footprints,
    _opening_rects, core_anchors,
)
from backend.app.geometry import v2
from backend.app.program_massing import datums_for, lattice_for, load_program_massing, neutral_score


def _lattice(axis='y'):
    source = Path(__file__).resolve().parents[2] / 'docs/contracts/program_massing.v1.example.json'
    massing = load_program_massing(source)
    massing.levels = massing.levels[:2]
    for level in massing.levels:
        level.plate = [(-20., -20.), (20., -20.), (20., 20.), (-20., 20.)]
    core = massing.cores[0].model_copy(update={'x': 2., 'y': 2., 'run_axis': axis, 'serves': []})
    massing.cores = [core]
    datums = datums_for(massing, neutral_score(massing))
    return datums, lattice_for(massing, datums)


def _parts(builder):
    return {instance.id: (group, instance) for group in builder.groups.values()
            for instance in group.instances}


def _plan(geometry):
    rect = box(geometry.center.x-geometry.size.x/2, geometry.center.y-geometry.size.y/2,
               geometry.center.x+geometry.size.x/2, geometry.center.y+geometry.size.y/2)
    return rotate(rect, geometry.rotation_z, origin=(geometry.center.x, geometry.center.y),
                  use_radians=True)


@pytest.fixture(scope='module')
def oriented_builders():
    result = {}
    for axis in ('y', 'x'):
        datums, lattice = _lattice(axis)
        builder = _Builder(datums, lattice)
        # The stair comparison excludes the independent lift and entry assemblies.
        builder.cores['lift'] = None
        for lower, upper in zip(lattice.levels, lattice.levels[1:]):
            _emit_core_walls(builder, lower, upper, _core_rects(builder.cores),
                             datums.value('slab_thickness_m'), SimpleNamespace(live_kpa=4.),
                             3., 'concrete')
        _emit_circulation(builder)
        result[axis] = builder
    return result


def test_authored_axis_rotates_reservation_openings_and_complete_landings(oriented_builders):
    old, new = (oriented_builders[axis] for axis in ('y', 'x'))
    centre = old.cores['primary']
    assert new.cores['primary_run_axis'] == 'x'
    assert _core_layout(old.cores)[0][-1] == _core_layout(new.cores)[0][-1]
    for getter in (_core_rects,):
        assert rotate(box(*getter(old.cores)[0]), -90, origin=centre).symmetric_difference(
            box(*getter(new.cores)[0])).area < 1e-8
    for level in new.lattice.levels[1:]:
        plate = Polygon([(p.x, p.y) for p in level.plate])
        for getter in (_opening_rects, _landing_footprints):
            expected = rotate(box(*getter(old.cores, level.id)[0]), -90, origin=centre)
            actual = box(*getter(new.cores, level.id)[0])
            assert expected.symmetric_difference(actual).area < 1e-8
            assert plate.covers(actual)
        _, landing = _parts(new)[f'CIR-LND-{level.id}']
        assert _plan(landing.geometry).symmetric_difference(
            box(*_landing_footprints(new.cores, level.id)[0])).area < 1e-8
        assert landing.geometry.center.z + landing.geometry.size.z/2 == pytest.approx(level.z)


def test_real_flights_turns_landings_and_guards_rotate_without_resizing(oriented_builders):
    old, new = (oriented_builders[axis] for axis in ('y', 'x'))
    centre = old.cores['primary']
    new_parts = _parts(new)
    checked = set()
    for ident, (group, instance) in _parts(old).items():
        if not ident.startswith(('CIR-TRD-A', 'CIR-TRD-B', 'CIR-STG-A', 'CIR-STG-B',
                                 'CIR-HLF-A', 'CIR-LND-L', 'CIR-RAL-CORE-LND',
                                 'CIR-RAL-A', 'CIR-RAL-B')):
            continue
        checked.add(group.kind)
        source, target = instance.geometry, new_parts[ident][1].geometry
        if source.type == 'box':
            expected = rotate(_plan(source), -90, origin=centre)
            assert expected.symmetric_difference(_plan(target)).area < 1e-7, ident
            assert target.size.z == source.size.z
            assert target.center.z == source.center.z
        else:
            assert source.type == target.type == 'member'
            assert target.profile == source.profile
            for a, b in zip(source.path, target.path):
                assert (b.x, b.y, b.z) == pytest.approx(
                    (centre[0]+a.y-centre[1], centre[1]-a.x+centre[0], a.z), abs=1e-5)
    assert checked >= {'stair_tread', 'stair_stringer', 'stair_half_landing',
                       'stair_landing', 'railing'}


@pytest.mark.parametrize('axis,face', [('y', 'S'), ('x', 'W')])
def test_door_aperture_threshold_and_wall_head_share_the_oriented_face(oriented_builders, axis, face):
    builder = oriented_builders[axis]
    parts = _parts(builder)
    level = builder.lattice.levels[1]
    door = parts[f'CIR-COR-LND-{level.id}-DR'][1].geometry
    threshold = parts[f'CIR-LND-{level.id}-THR'][1].geometry
    head = parts[f'STR-CWL-LND-{face}-{level.id}-HD'][1].geometry
    assert (door.size.y if axis == 'x' else door.size.x) == CORE_DOOR_W_M
    assert door.size.z == CORE_DOOR_H_M
    assert _plan(threshold).buffer(1e-7).covers(_plan(door))
    assert head.center.z-head.size.z/2 == pytest.approx(level.z+CORE_DOOR_H_M)
    assert (door.center.x, door.center.y) == (head.center.x, head.center.y)
    for ident, (group, instance) in parts.items():
        if group.kind == 'core_wall' and instance.level_id == level.id:
            g = instance.geometry
            if g.center.z-g.size.z/2 < level.z+CORE_DOOR_H_M-1e-5:
                assert _plan(g).intersection(_plan(door)).area < 1e-8, ident


def test_x_core_is_rejected_if_its_full_landing_envelope_leaves_a_served_plate():
    datums, lattice = _lattice('x')
    width = datums.value('flight_width_m')
    from backend.app.datums import flight_run
    extent = _core_box(2., 2., width, flight_run(width), 'x')
    # The flights still fit; the east landing and clearance do not.
    lattice.levels[1].plate = [v2(-20, -20), v2(extent[2]-.4, -20),
                                v2(extent[2]-.4, 20), v2(-20, 20)]
    with pytest.raises(ValueError, match='CORE-A.*inside'):
        core_anchors(lattice, datums)


def test_mixed_authored_axes_keep_world_xy_frame_independent():
    from backend.tests.test_world_xy_frame_integration import _frame, _massing
    massing = _massing()
    massing.cores[0].run_axis = 'x'
    builder = _frame(massing=massing)
    assert builder.lattice.x_lines == [0, 4, 8, 12, 16, 20, 24]
    assert builder.lattice.y_lines == [0, 4, 8, 12, 16, 20]
    assert builder.cores['primary_run_axis'] == 'x'
    assert builder.cores['second_run_axis'] == 'y'
    for group in builder.groups.values():
        if group.kind != 'primary_beam':
            continue
        for instance in group.instances:
            assert len(instance.supports) == 2
            assert all(support in builder.element_ids for support in instance.supports)


def test_x_core_faces_its_supported_gallery_when_the_lift_blocks_the_remote_door():
    from backend.app.compiler_v3 import _core_route_radius, _core_terminal
    from backend.app.datums import CoreDatum
    from backend.app.plan_regions import usable_region
    from shapely.geometry import Point

    datums, lattice = _lattice('x')
    lattice.given_cores.extend([
        CoreDatum(id='CORE-B', kind='stair', x=14., y=2., run_axis='x'),
        CoreDatum(id='LIFT', kind='lift', x=-4., y=2.),
    ])
    builder = _Builder(datums, lattice)
    layout = _core_layout(builder.cores)
    assert [row[-1] for row in layout] == [-1.0, 1.0]
    level = lattice.levels[1]
    _emit_core_walls(builder, level, lattice.levels[2], _core_rects(builder.cores),
                     datums.value('slab_thickness_m'), SimpleNamespace(live_kpa=4.),
                     3., 'concrete')
    _emit_circulation(builder)
    parts = _parts(builder)
    door = parts[f'CIR-COR-LND-{level.id}-DR'][1].geometry
    threshold = parts[f'CIR-LND-{level.id}-THR'][1].geometry
    primary = builder.cores['primary']
    assert door.center.x > primary[0]
    assert _plan(threshold).buffer(1e-7).covers(_plan(door))
    radius = _core_route_radius()
    terminal = _core_terminal(builder.cores, primary, layout[0][-1], radius)
    assert terminal[0] > door.center.x
    domain = usable_region(level, _core_rects(builder.cores)+[(-5.3, .7, -2.7, 3.3)])
    assert domain.buffer(1e-7).covers(Point(*terminal).buffer(radius))


def test_archetype_terminal_uses_full_program_owner_when_carve_is_rounded():
    from backend.app.compiler_v3 import _preplaced_terminal_points
    from shapely.geometry import Point
    zone = SimpleNamespace(x0=15.397, y0=1.4, x1=19.396, y1=8.9)
    owner = box(15.3967, 1.4, 19.3967, 8.9)
    radius = .745
    terminal = _preplaced_terminal_points(zone, radius, owner=owner)[3]
    assert not owner.buffer(radius, join_style='mitre').covers(Point(*terminal))
    assert terminal == pytest.approx((20.14171, 5.15))
    legacy = _preplaced_terminal_points(zone, radius)[3]
    assert owner.buffer(radius, join_style='mitre').covers(Point(*legacy))
    # Auditorium front stations are retained only within the registered owner.
    assert _preplaced_terminal_points(zone, radius, owner=owner, front_x=17.)[0][0] == 17.
    assert _preplaced_terminal_points(zone, radius, owner=owner, front_x=25.)[0][0] == pytest.approx(
        (owner.bounds[0]+owner.bounds[2])/2)
