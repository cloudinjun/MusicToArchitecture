"""Counterexamples for a roof label that does not actually close an indoor hall."""
from types import SimpleNamespace as NS

import pytest
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from backend.app.geometry import BoxGeometry, MemberGeometry, v2, v3
from backend.app.hall_enclosure import enclosure_geometry, prepare_hall, emit_hall, inspect_hall
from backend.app.loads import OCCUPANCY_LIVE
from backend.app.registry import catalogue


def test_roof_bearing_uses_real_flange_area_and_matching_height_not_axis_crossing():
    from backend.app.hall_enclosure import roof_bearings
    beam = BoxGeometry(center=v3(0,5,-.25),size=v3(.2,10,.5))
    # This cap has bearing on the flange, although it never crosses the beam axis.
    cap = box(.07,1,.09,8)
    assert roof_bearings(cap,0.,{'BEAM':beam},{}) == ['BEAM']
    assert not roof_bearings(box(.11,1,.13,8),0.,{'BEAM':beam},{})
    assert not roof_bearings(cap,.02,{'BEAM':beam},{})
    assert not roof_bearings(cap,0.,{},{})


def setup_hall():
    plate=[v2(0,0),v2(20,0),v2(20,20),v2(0,20)]
    tower=[v2(0,0),v2(10,0),v2(10,10),v2(0,10)]
    hole=[v2(4,4),v2(6,4),v2(6,6),v2(4,6)]
    levels=[NS(index=i,id=f'L{i:02d}',z=float(i*4),plate=plate if i<4 else tower,
               voids=[] if i<4 else [hole]) for i in range(5)]
    lattice=NS(levels=levels,occupied=levels[1:-1],x_lines=[0.,5.,10.,15.,20.],y_lines=[0.,5.,10.,15.,20.])
    carve=NS(house=(2.,2.,12.,18.),stage=(12.,2.,20.,18.),clear_house_m=7.,clear_stage_m=8.)
    b=NS(lattice=lattice,datums=NS(value=lambda k: {'slab_thickness_m':.3,'joist_spacing_m':1.5}[k]),
         groups={},element_ids=set(),profiles={})
    return b,carve


def test_cap_uses_actual_slab_difference_including_holes_and_never_the_tower_outline():
    b,carve=setup_hall()
    g=enclosure_geometry(b.lattice,carve,.3)
    assert g.level.id=='L04' and g.roof_bottom_z==pytest.approx(15.7)
    assert g.missing.intersection(Polygon([(4,4),(6,4),(6,6),(4,6)])).area==pytest.approx(4.)
    assert g.missing.intersection(Polygon([(12,2),(20,2),(20,18),(12,18)])).area==pytest.approx(128.)
    assert not g.missing.intersection(Polygon([(7,7),(9,7),(9,9),(7,9)])).area


def test_absent_registered_cap_remains_unresolved():
    b,carve=setup_hall()
    b.lattice.levels=b.lattice.levels[:-1]
    assert enclosure_geometry(b.lattice,carve,.3) is None


def test_roof_reactions_and_real_framing_weight_reach_boundary_supports():
    b,carve=setup_hall()
    prepare_hall(b,OCCUPANCY_LIVE['stage'],carve)
    report=b.hall_enclosure
    assert not report.findings
    assert sum(v[1] for v in b.hall_reactions.values())==pytest.approx(report.roof_live_kn)
    assert sum(v[0] for v in b.hall_reactions.values())==pytest.approx(report.roof_dead_kn+report.framing_dead_kn)
    assert report.framing_dead_kn>0 and b.hall_reactions[4,1][0]>0
    sections={s.id:s for s in catalogue('steel_w_shape')}
    primary=sections[report.primary.check.section_id]
    secondary=sections[report.secondary.check.section_id]
    assert b.hall_primary_z+primary.depth_mm/2000==pytest.approx(b.hall_secondary_z-secondary.depth_mm/2000)
    assert b.hall_secondary_z+secondary.depth_mm/2000==pytest.approx(b.hall_geometry.roof_bottom_z)


@pytest.mark.parametrize('opening', ['full', 'corner', 'diagonal', 'islands'])
def test_wall_face_cap_load_preserves_force_and_both_first_moments(opening):
    b, carve = setup_hall()
    # Align all four hall edges with support axes so the actual wall-face cap
    # projects beyond them. Retained slabs leave asymmetric/fragmented roof loads.
    carve.house, carve.stage = (0., 0., 10., 20.), (10., 0., 20., 20.)
    slab = {
        'full': box(30, 30, 35, 35),
        'corner': box(0, 0, 13, 17),
        'diagonal': Polygon([(0, 0), (20, 0), (20, 20)]),
        'islands': box(-1, -1, 21, 21),
    }[opening]
    b.lattice.levels[-1].plate = [v2(*p) for p in list(slab.exterior.coords)[:-1]]
    holes = [box(1, 1, 4, 9), box(12, 11, 19, 18)] if opening == 'islands' else []
    b.lattice.levels[-1].voids = [
        [v2(*p) for p in list(hole.exterior.coords)[:-1]] for hole in holes]
    g = prepare_hall(b, OCCUPANCY_LIVE['stage'], carve)
    assert not b.hall_enclosure.findings
    # Roof live is a clean load channel, independent of framing self weight.
    live = OCCUPANCY_LIVE['roof_ordinary'].live_kpa
    total = g.missing.area * live
    assert sum(v[1] for v in b.hall_reactions.values()) == pytest.approx(total)
    for axis, lines in enumerate((b.lattice.x_lines, b.lattice.y_lines)):
        moment = sum(lines[key[axis]] * value[1] for key, value in b.hall_reactions.items())
        expected = total * (g.missing.centroid.x if axis == 0 else g.missing.centroid.y)
        assert moment == pytest.approx(expected, abs=1e-8)


def test_named_roof_on_other_level_does_not_cover_hall_and_low_wall_heads_fail():
    b,carve=setup_hall()
    g=prepare_hall(b,OCCUPANCY_LIVE['stage'],carve)
    from backend.app.geometry import ExtrusionGeometry
    wrong=ExtrusionGeometry(boundary=[v2(*p) for p in list(g.footprint.exterior.coords)[:-1]],
        z_base=g.roof_bottom_z+4,z_top=g.roof_bottom_z+4.3)
    b.groups={'roof':NS(kind='roof_deck',instances=[NS(geometry=wrong)])}
    inspect_hall(b)
    assert b.hall_enclosure.status=='failed'
    assert b.hall_enclosure.uncovered_area_m2==pytest.approx(g.footprint.area)
    assert b.hall_enclosure.open_wall_head_length_m==pytest.approx(g.footprint.length)


def test_emitter_rejects_a_missing_real_column_instead_of_naming_a_fake_support():
    b,carve=setup_hall()
    prepare_hall(b,OCCUPANCY_LIVE['stage'],carve)
    b.transfer_structure=NS(status='review_required',frames=[])
    with pytest.raises(ValueError,match='absent support'):
        emit_hall(b)


def test_native_partition_kind_reaches_cap_and_is_measured_from_real_solids():
    b,carve=setup_hall()
    g=prepare_hall(b,OCCUPANCY_LIVE['stage'],carve)
    from backend.app.geometry import ExtrusionGeometry
    roof=ExtrusionGeometry(boundary=[v2(*p) for p in list(g.footprint.exterior.coords)[:-1]],
        z_base=g.roof_bottom_z,z_top=g.level.z)
    x0,y0,x1,y1=g.footprint.bounds
    height=g.roof_bottom_z-b.lattice.occupied[0].z
    z=g.roof_bottom_z-height/2
    walls=[BoxGeometry(center=v3((x0+x1)/2,y,z),size=v3(x1-x0,.25,height)) for y in (y0,y1)]
    walls += [BoxGeometry(center=v3(x,(y0+y1)/2,z),size=v3(.25,y1-y0,height)) for x in (x0,x1)]
    b.groups={'roof':NS(kind='roof_deck',instances=[NS(geometry=roof)]),
              'walls':NS(kind='partition',instances=[NS(geometry=w) for w in walls])}
    inspect_hall(b)
    assert b.hall_enclosure.uncovered_area_m2==pytest.approx(0)
    assert b.hall_enclosure.open_wall_head_length_m==pytest.approx(0)


def test_stage_deck_and_adjacent_restraints_keep_the_same_clear_height():
    from backend.app.transfer_structure import frame_clear_top
    from backend.app.archetypes import STAGE_RISE_M
    b,carve=setup_hall()
    base=b.lattice.occupied[0].z
    assert frame_clear_top(b.lattice,carve,1)==pytest.approx(base+carve.clear_stage_m)
    assert frame_clear_top(b.lattice,carve,2)==pytest.approx(base+STAGE_RISE_M+carve.clear_stage_m)
    assert frame_clear_top(b.lattice,carve,3)==pytest.approx(base+STAGE_RISE_M+carve.clear_stage_m)
