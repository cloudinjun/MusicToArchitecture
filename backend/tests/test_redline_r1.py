"""Small redline counterexamples, independent of the full demo compiler.

These verify geometry and drawing behaviour, not building-code compliance.
"""
import inspect
import math
from types import SimpleNamespace as NS

import pytest
from shapely.affinity import rotate
from shapely.geometry import Polygon, box

from backend.app.datums import Lattice, LevelDatum, build_lattice
from backend.app.drawing_geometry import plan_frame
from backend.app.drawing_standard import PLAN_STANDARD
from backend.app.drawings import (
    Drawing, DrawingAudit, annotate_doors, annotate_rooms, compile_drawing,
    floor_plans, issue_drawings,
)
from backend.app.geometry import BoxGeometry, ExtrusionGeometry, v2, v3
from backend.app.geometry_review import check_room_support
from backend.app.life_safety import EgressFinding, LifeSafetyGraph, build
from backend.app.plan_regions import rectangular_runs, usable_region
from backend.app.program import AllocatedZone, SpaceRequirement, allocate_program, level_bands


def ring(polygon):
    return [v2(x, y) for x, y in list(polygon.exterior.coords)[:-1]]


def level(polygon, *, holes=(), name='L01', z=0.0, index=0, kind='occupied'):
    return LevelDatum(id=name, index=index, z=z, kind=kind, plate=ring(polygon),
                      voids=[ring(hole) for hole in holes])


def lattice(lv, ys=None):
    return Lattice(levels=[lv], x_lines=[-30, -20, -10, 0, 10, 20, 30],
                   y_lines=ys or [-30, -20, -10, 0, 10, 20, 30], apse_nodes=[],
                   plan_x_m=60.0, plan_y_m=60.0)


def instance(identifier, geometry, level_id='L01'):
    return NS(id=identifier, level_id=level_id, geometry=geometry)


def group(kind, *items, subsystem='test', program='test'):
    return NS(kind=kind, instances=list(items), subsystem=subsystem,
              semantic_layer='program' if kind == 'program_zone' else 'structure',
              program=program)


def model(*groups, grid=None):
    return NS(element_groups=list(groups), profiles={}, lattice=grid)


def empty_drawing():
    return Drawing(id='TEST', title='Test', kind='plan', standard=PLAN_STANDARD,
                   marks=[], annotations=[], extents=(-50, -50, 50, 50),
                   audit=DrawingAudit(0, 0, 0, 0, {}, 0))


@pytest.mark.parametrize('degrees', [0, 3, 12, 37, 89])
def test_whole_bands_fit_rotated_plate_not_just_their_midlines(degrees):
    shape = rotate(box(-20, -15, 20, 15), degrees, origin=(0, 0))
    lv = level(shape)
    shape = usable_region(lv)  # The serialized Vector2 ring is the authority.
    bands = level_bands(lv, lattice(lv))
    assert bands
    for band in bands:
        assert shape.buffer(1e-7).covers(box(band.x0, band.y0, band.x1, band.y1))


def test_full_strip_respects_concavity_and_holes():
    shape = Polygon([(0, 0), (20, 0), (20, 20), (12, 20), (12, 8),
                     (8, 8), (8, 20), (0, 20)])
    region = shape.difference(box(2, 2, 4, 4))
    runs = rectangular_runs(region, 0, 10)
    assert runs
    for x0, x1 in runs:
        assert region.buffer(1e-7).covers(box(x0, 0, x1, 10))
    assert all(not (x0 < 3 < x1 or x0 < 10 < x1) for x0, x1 in runs)


def test_empty_and_invalid_domains_do_not_become_usable_bounding_boxes():
    lv = level(box(0, 0, 10, 10), holes=[box(0, 0, 10, 10)])
    assert level_bands(lv, lattice(lv, [0, 5, 10])) == []
    lv.plate = [v2(0, 0), v2(10, 10), v2(0, 10), v2(10, 0)]
    with pytest.raises(ValueError, match='invalid'):
        usable_region(lv)


def requirement(area=30):
    return SpaceRequirement(id='SP-TEST', space_type='seminar', label='Rehearsal studio',
                            category='public', area_m2=area, min_dimension_m=4,
                            level_preference='any', daylight='none',
                            occupancy_id='office', reason='Test brief')


def test_small_floor_never_waives_core_reservation():
    lv = level(box(0, 0, 10, 10))
    reserve = ((0, 0, 9, 10),)
    result = allocate_program(lattice(lv, [0, 5, 10]), NS(value=lambda key: 0.22),
                              brief=(requirement(),), reserved=reserve)
    assert not result.cores_unreserved
    assert result.unplaced
    assert not result.zones
    assert not result.fits


@pytest.mark.parametrize('degrees', [0, 5, 12, 33])
def test_allocated_serialized_rectangles_fit_real_region(degrees):
    shape = rotate(box(-20, -15, 20, 15), degrees, origin=(0, 0))
    lv = level(shape, holes=[box(-2, -2, 2, 2)])
    reserve = ((-5, -5, 5, 5),)
    result = allocate_program(lattice(lv), NS(value=lambda key: 0.22),
                              brief=(requirement(80),), reserved=reserve)
    assert result.zones, 'The fixture offers ample valid floor; rejection is not enough.'
    usable = usable_region(lv, reserve)
    for zone in result.zones:
        geometry = box(zone.x0, zone.y0, zone.x1, zone.y1)
        assert usable.buffer(1e-7).covers(geometry)
        assert zone.area_delivered_m2 == pytest.approx(round(geometry.area, 2))


def slab(identifier, polygon, holes=()):
    return instance(identifier, ExtrusionGeometry(boundary=ring(polygon),
        holes=[ring(hole) for hole in holes], z_base=-0.3, z_top=0.0))


def room(identifier, polygon):
    x0, y0, x1, y1 = polygon.bounds
    return instance(identifier, BoxGeometry(center=v3((x0+x1)/2, (y0+y1)/2, 0.055),
                                             size=v3(x1-x0, y1-y0, 0.11)))


def test_support_check_unions_split_slabs_without_filling_holes():
    left = slab('SLAB-A', box(0, 0, 5, 10))
    right = slab('SLAB-B', box(5, 0, 10, 10), holes=[box(6, 6, 8, 8)])
    supported = room('ROOM-OK', box(1, 1, 9, 5))
    over_hole = room('ROOM-HOLE', box(6, 6, 8, 8))
    result = check_room_support(model(group('floor_slab', left, right),
                                      group('program_zone', supported, over_hole)))
    assert len(result) == 1
    assert result[0].elements == ('ROOM-HOLE',)
    assert result[0].measure == pytest.approx(4.0, abs=1e-5)


def test_overhang_is_measured_even_when_room_centre_is_supported():
    shape = rotate(box(0, 0, 10, 10), 12, origin=(5, 5))
    footprint = box(0, 0, 10, 10)
    floor = slab('SLAB', shape)
    shape = Polygon([(p.x, p.y) for p in floor.geometry.boundary])
    result = check_room_support(model(group('floor_slab', floor),
                                      group('program_zone', room('ROOM', footprint))))
    assert len(result) == 1 and result[0].severity == 'violation'
    assert result[0].measure == pytest.approx(footprint.difference(shape).area, abs=1e-5)


def test_missing_floor_support_remains_unknown():
    result = check_room_support(model(group('program_zone', room('ROOM', box(0, 0, 2, 2)))))
    assert result and result[0].severity == 'warning'
    assert result[0].unit == 'unevaluated'


@pytest.mark.parametrize('degrees', range(0, 360, 45))
@pytest.mark.parametrize('sense', [-1, 1])
def test_door_arc_is_a_quarter_turn_in_every_orientation(degrees, sense):
    angle = math.radians(degrees)
    across = (-math.sin(angle), math.cos(angle))
    leaf = instance('PRG-PRT-L01-SP-X-N-DR', BoxGeometry(
        center=v3(0, 0, 1), size=v3(1, 0.05, 2), rotation_z=angle))
    zone = instance('PRG-ZON-L01-SP-X', BoxGeometry(
        center=v3(across[0]*sense*3, across[1]*sense*3, 0.05), size=v3(2, 2, 0.1)))
    drawing = empty_drawing()
    annotate_doors(drawing, model(group('door', leaf, subsystem='partitions'),
                                 group('program_zone', zone)), NS(id='L01'))
    hinge = drawing.annotations[0].points[0]
    arc = drawing.annotations[1].points
    angles = [math.atan2(y-hinge[1], x-hinge[0]) for x,y in arc]
    sweep = sum((b-a+math.pi) % (2*math.pi)-math.pi for a,b in zip(angles,angles[1:]))
    assert abs(sweep) == pytest.approx(math.pi/2)
    assert sweep == pytest.approx(-sense*math.pi/2)


def test_lift_landing_is_not_drawn_as_a_hinged_room_door():
    lift_door = instance('CIR-SHF-L01-DR', BoxGeometry(center=v3(0,0,1),size=v3(1,0.2,2)))
    drawing = empty_drawing()
    annotate_doors(drawing, model(group('door',lift_door,subsystem='vertical_core')),NS(id='L01'))
    assert not drawing.annotations


def test_program_zone_does_not_occlude_real_building_marks():
    floor = instance('SLAB', BoxGeometry(center=v3(0,0,-0.15),size=v3(10,10,0.3)))
    zone = room('ROOM',box(-2,-2,2,2))
    plane, frame = plan_frame(1.2)
    drawing = compile_drawing(model(group('floor_slab',floor),group('program_zone',zone)),
        plane,frame,PLAN_STANDARD,drawing_id='T',title='Test',kind='plan',keep=(0,2.1))
    assert drawing.marks
    assert {mark.element_id for mark in drawing.marks} == {'SLAB'}
    assert drawing.audit.elements_considered == 2
    assert drawing.audit.outside_cut == 1


def test_room_label_and_area_come_from_allocation_not_generic_type_or_box():
    zone = room('PRG-ZON-L01-SP-X',box(0,0,10,10))
    m = model(group('program_zone',zone,program='seminar'))
    m.program_allocation = NS(zones=[NS(level_id='L01',space_id='SP-X',
                                        label='Rehearsal studio',area_delivered_m2=37.5)])
    drawing = empty_drawing()
    annotate_rooms(drawing,m,NS(id='L01',voids=[]))
    labels = {note.text for note in drawing.annotations}
    assert 'REHEARSAL STUDIO' in labels and '38 m² allocated' in labels
    assert not any('100' in label for label in labels)


def test_roof_subtitle_uses_the_actual_cut_height():
    lv=level(box(-5,-5,5,5),kind='roof',z=3)
    deck=instance('ROOF',BoxGeometry(center=v3(0,0,2.9),size=v3(10,10,0.2)))
    drawing=floor_plans(model(group('roof_deck',deck),grid=lattice(lv,[-5,0,5])))[0]
    assert 'cut 0.15 m above' in drawing.subtitle
    assert 'cut 1.20' not in drawing.subtitle


def test_default_lattice_is_complete_and_cutaway_issue_requires_opt_in():
    lv=level(box(0,0,10,10))
    grid=lattice(lv)
    assert grid.cutaway is False
    assert inspect.signature(build_lattice).parameters['cutaway'].default is False
    grid.cutaway=True
    with pytest.raises(ValueError,match='cutaway=False'):
        issue_drawings(model(grid=grid))


def test_unevaluated_and_empty_graphs_cannot_claim_compliance():
    args=dict(typology='theater',occupancy_group='unconfirmed',sprinklered=True,nodes=[],edges=[])
    unknown=EgressFinding(clause='test',label='Unknown',status='unevaluated',subject='test',detail='Not measured')
    assert not LifeSafetyGraph(**args,findings=[unknown]).compliant
    assert not LifeSafetyGraph(**args,findings=[]).compliant


def test_vertical_edges_preserve_stair_identity_and_do_not_invent_discharge():
    levels=[level(box(0,0,20,20),name='L01',index=1,z=3),
            level(box(0,0,20,20),name='L02',index=2,z=7)]
    elements=[NS(id=f'CIR-{core}-{lv.id}',kind='stair_landing',level_id=lv.id,
                 position=v3(x,0,lv.z)) for lv in levels for core,x in [('LND',0),('LND2',10)]]
    elements += [NS(id='CIR-LND-ENTRY',kind='stair_landing',level_id='L01',position=v3(2,0,3)),
                 NS(id='RAMP-HIGH',kind='ramp_landing',level_id='L02',position=v3(0,0,7))]
    m=NS(elements=elements,lattice=NS(levels=levels),program_allocation=NS(zones=[]),
         datum_set=NS(value=lambda key:1.2))
    graph=build(m,[],typology='theater',sprinklered=False)
    links={(edge.source,edge.target) for edge in graph.edges if edge.kind=='vertical'}
    assert links=={('EX-CIR-LND-L02','EX-CIR-LND-L01'),('EX-CIR-LND2-L02','EX-CIR-LND2-L01')}
    assert all(edge.distance_m==8 for edge in graph.edges if edge.kind=='vertical')
    assert all(node.kind!='exit_discharge' for node in graph.nodes)
    assert len(graph.exits)==4 and not graph.sprinklered
    assert graph.occupancy_group=='unconfirmed'
    assert all(f.status!='pass' for f in graph.findings)
    assert not graph.compliant


def test_preplaced_archetype_cannot_bypass_floor_coverage():
    lv = level(box(0, 0, 10, 10))
    preset = AllocatedZone(space_id='SP-TEST', space_type='seminar', label='Outside room',
        category='public', occupancy_id='office', level_index=0, level_id='L01',
        band_index=0, x0=8, x1=14, y0=2, y1=8, area_required_m2=36,
        area_delivered_m2=36, daylight_satisfied=True, level_preference_satisfied=True)
    result = allocate_program(lattice(lv, [0,5,10]), NS(value=lambda key:0.22),
        brief=(requirement(36),), preplaced=(preset,))
    assert not result.zones
    assert len(result.unplaced) == 1
    assert 'Preplaced archetype' in result.unplaced[0].reason
    assert not result.fits


def test_archetype_coverage_does_not_ignore_edge_overhang_or_small_holes():
    from backend.app.archetypes import _rect_clear_of, _place_zone
    lv = level(box(0, 0, 10.0004, 10.0004), holes=[box(4, 4, 4.005, 4.005)])
    assert not _rect_clear_of(lv, (0, 0, 10.01, 10.01))
    assert not _rect_clear_of(lv, (0, 0, 10, 10))
    lv.voids = []
    zone = _place_zone(requirement(100), (0,0,10.0004,10.0004), lv, [0,10])
    assert _rect_clear_of(lv, (zone.x0,zone.y0,zone.x1,zone.y1))
    assert zone.area_delivered_m2 == round((zone.x1-zone.x0)*(zone.y1-zone.y0),2)


def test_theatre_fixture_has_no_unsupported_rooms_after_real_compile():
    import json
    from pathlib import Path
    from backend.app.compiler_v3 import compile_building_model_v3
    from backend.app.models import ArchitecturalScore, AudioFeatures
    fixtures = Path(__file__).parent / 'fixtures'
    features = AudioFeatures.model_validate_json(
        (fixtures/'theater_bar_podium_features.json').read_text(encoding='utf-8'))
    score = ArchitecturalScore.model_validate_json(
        (fixtures/'theater_bar_podium_score.json').read_text(encoding='utf-8'))
    result = compile_building_model_v3(features, score,
        typology='theater', massing_id='MAS-BAR-PODIUM')
    assert not result.lattice.cutaway
    assert result.program_allocation.zones
    assert not result.program_allocation.cores_unreserved
    assert check_room_support(result) == []
    assert not result.life_safety.compliant
    assert all(item.status != 'pass' for item in result.life_safety.findings)
    assert result.life_safety.sprinklered == bool(result.site.sprinklered.value)
    # Both placed AND short rooms are honest results, not silent discarded requirements.
    assert result.program_allocation.fits == (
        not result.program_allocation.unplaced and not result.program_allocation.short)
