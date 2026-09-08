"""The massing is the contract (decision 0022).

A building is a function of its volumes. Handed a program massing -- plates, grid,
cores, datums -- and nothing else, the compiler builds the same kind of model and
issues the same drawings it does from a recording; the cores stand where the massing
put them and no girder crosses a well; a core that cannot stand where it was put is
refused by name; and a music run's own massing, written out and fed back, rebuilds
the same frame.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.compiler_v3 import (
    _core_rects, compile_building_model_v3, core_anchors,
)
from backend.app.drawings import issue_drawings
from backend.app.models import ArchitecturalScore, AudioFeatures
from backend.app.program_massing import (
    ProgramMassing, compile_from_massing, load_program_massing, program_massing_of,
)

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / 'docs' / 'contracts' / 'program_massing.v1.example.json'
DEMO = ROOT / 'artifacts' / 'v3_demo'
V2_DEMO = (ROOT / 'artifacts' / 'integrated_demo'
           / 'building-b7ad95fa45a6-library-steel-international-v1')


@pytest.fixture(scope='module')
def example() -> ProgramMassing:
    return load_program_massing(EXAMPLE)


@pytest.fixture(scope='module')
def built(example):
    return compile_from_massing(example)


def _note(model, prefix: str) -> str:
    return next((note for note in model.limitations if note.startswith(prefix)), '')


def test_a_hand_drawn_massing_builds_a_building_and_its_drawings(example, built):
    model = built
    levels = [level.id for level in model.lattice.levels]
    # Storeys given from the ground up: the ground storey is the podium level, the
    # rest are occupied, and a roof plate is added over the top one.
    storeys = len(example.levels)
    assert levels == [f'L{index:02d}' for index in range(storeys + 1)]
    assert [level.kind for level in model.lattice.levels] == (
        ['podium'] + ['occupied'] * (storeys - 1) + ['roof'])
    # The grid is drawn to the cores (decision 0022) between the plate's extent lines.
    xs = [x for x, _y in example.levels[0].plate]
    assert model.lattice.x_lines[0] == min(xs) and model.lattice.x_lines[-1] == max(xs)
    assert model.datum_set.value('flight_width_m') == example.datums['flight_width_m']
    assert model.lattice.levels[1].z == example.datums['ground_open_height_m']

    # The cores stand where the massing put them, and were not searched for.
    anchors = core_anchors(model.lattice, model.datum_set)
    given = {core.id: (core.x, core.y) for core in example.cores}
    assert anchors['primary'] == given['CORE-A']
    assert anchors['second'] == given['CORE-B']
    assert anchors['lift'][:2] == given['LIFT-1']
    landings = [inst for group in model.element_groups if group.kind == 'stair_landing'
                for inst in group.instances]
    assert {inst.level_id for inst in landings} >= {
        f'L{index:02d}' for index in range(1, storeys)}

    # The archetype carved its reading room around the given cores, not through them.
    assert model.archetype is not None and model.archetype.refused is None, (
        model.archetype.refused if model.archetype else 'no archetype report')
    reserved = [rect for level in model.lattice.levels for rect in level.reserved]
    assert reserved, 'given cores reserve no floor'
    for group in model.element_groups:
        if group.kind != 'program_zone':
            continue
        for inst in group.instances:
            g = inst.geometry
            if g.type != 'box':
                continue
            zx0, zx1 = g.center.x - g.size.x / 2, g.center.x + g.size.x / 2
            zy0, zy1 = g.center.y - g.size.y / 2, g.center.y + g.size.y / 2
            for rx0, ry0, rx1, ry1 in reserved:
                assert not (min(zx1, rx1) - max(zx0, rx0) > 0.05
                            and min(zy1, ry1) - max(zy0, ry0) > 0.05), (inst.id, 'in a core')

    # Cores in cells: nothing to frame around, and nothing left for review.
    openings = _note(model, 'Stair and lift openings')
    assert 'No girder crosses an opening' in openings, openings
    assert model.dependency_graph.status == 'passed', model.dependency_graph.checks

    # The same issue a music run gets.
    issued = issue_drawings(model)
    assert issued.sheets or issued.all
    assert model.selection.massing_id == 'MAS-GIVEN'
    assert model.model_id.startswith('building-v3-')


def test_a_core_that_cannot_stand_where_it_was_put_is_refused_by_name(example):
    outside = example.model_copy(deep=True)
    outside.cores[0].x = 35.0  # east of a plate that ends at x = 32
    with pytest.raises(ValueError, match='CORE-A'):
        compile_from_massing(outside)

    overlapping = example.model_copy(deep=True)
    overlapping.cores[1].x = example.cores[0].x - 1.0
    overlapping.cores[1].y = 0.5
    with pytest.raises(ValueError, match='overlap'):
        compile_from_massing(overlapping)

    stranded = example.model_copy(deep=True)
    stranded.cores[0].serves = ['L01', 'L02']  # a stair that does not reach grade
    with pytest.raises(ValueError, match='ground level'):
        compile_from_massing(stranded)


def _assert_grid_drawn_to_cores(model):
    """Every core face is a grid line, no column or beam stands inside a core, and
    the core walls chain to a footing."""
    anchors = core_anchors(model.lattice, model.datum_set)
    assert anchors['primary'] is not None
    rects = _core_rects(anchors)
    assert rects
    for x0, y0, x1, y1 in rects:
        for face, lines in ((x0, model.lattice.x_lines), (x1, model.lattice.x_lines),
                            (y0, model.lattice.y_lines), (y1, model.lattice.y_lines)):
            assert any(abs(face - line) <= 0.05 for line in lines), (face, lines)
        for group in model.element_groups:
            if group.kind not in ('column', 'piloti_column', 'primary_beam',
                                  'secondary_joist', 'heavy_joist', 'clt_panel'):
                continue
            for inst in group.instances:
                g = inst.geometry
                if g.type == 'member':
                    xs = [p.x for p in g.path]
                    ys = [p.y for p in g.path]
                    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
                else:
                    mx, my = g.center.x, g.center.y
                assert not (x0 + 0.05 < mx < x1 - 0.05 and y0 + 0.05 < my < y1 - 0.05), (
                    inst.id, 'inside a stair core')
    walls = [inst for group in model.element_groups if group.kind == 'core_wall'
             for inst in group.instances if inst.id.startswith('STR-CWL-')]
    assert walls, 'no core walls'
    footings = {inst.id for group in model.element_groups if group.kind == 'footing'
                for inst in group.instances if inst.id.startswith('STR-FDN-CORE-')}
    assert footings, 'no core footing'
    assert model.dependency_graph.status == 'passed', [
        (c.id, c.message[:200], c.affected_ids[:5])
        for c in model.dependency_graph.checks if c.status not in ('passed', 'not_checked')]
    doors = [inst for group in model.element_groups if group.kind == 'door'
             for inst in group.instances if inst.id.startswith('CIR-COR-')]
    assert doors, 'no exit door into the stair core'


def test_cores_left_to_the_compiler_get_a_grid_drawn_to_them(example):
    unplaced = example.model_copy(deep=True, update={'cores': [], 'grid': None})
    model = compile_from_massing(unplaced)
    _assert_grid_drawn_to_cores(model)


def test_given_cores_get_a_grid_drawn_to_them_too(built):
    _assert_grid_drawn_to_cores(built)


def test_an_unknown_datum_is_refused(example):
    wrong = example.model_copy(deep=True, update={'datums': {'not_a_datum': 1.0}})
    with pytest.raises(ValueError, match='not_a_datum'):
        compile_from_massing(wrong)


def test_a_music_run_round_trips_through_its_massing():
    """What a run built, written out as volumes and fed back, is the same frame."""
    features = AudioFeatures.model_validate(
        json.loads((V2_DEMO / 'music_features.json').read_text(encoding='utf-8')))
    template = ArchitecturalScore.model_validate(
        json.loads((DEMO / 'architectural_score.json').read_text(encoding='utf-8')))
    original = compile_building_model_v3(features, template, massing_id='MAS-SLAB',
                                         typology='library')
    massing = program_massing_of(original)
    assert massing.grid is not None and massing.cores
    assert massing.datums['flight_width_m'] == original.datum_set.value('flight_width_m')

    rebuilt = compile_from_massing(massing)
    assert rebuilt.lattice.x_lines == original.lattice.x_lines
    assert rebuilt.lattice.y_lines == original.lattice.y_lines
    assert len(rebuilt.lattice.apse_nodes) == len(original.lattice.apse_nodes)
    assert [level.z for level in rebuilt.lattice.levels] == [
        level.z for level in original.lattice.levels]

    before = core_anchors(original.lattice, original.datum_set)
    after = core_anchors(rebuilt.lattice, rebuilt.datum_set)
    assert after['primary'] == pytest.approx(before['primary'])
    assert after['second'] == pytest.approx(before['second'])
    assert after['lift'][:2] == pytest.approx(before['lift'][:2])

    assert rebuilt.structural_system_id == original.structural_system_id
    assert rebuilt.facade_grammar_id == original.facade_grammar_id
    for kind in ('column', 'primary_beam', 'stair_tread', 'stair_landing'):
        assert rebuilt.element_counts.get(kind) == original.element_counts.get(kind), kind

# --- given zones (decision 0023): the writer decides, the kernel measures -----------

ZONES = [
    {'label': 'public front', 'level_id': 'L01', 'rect': [-10.0, -13.5, 9.0, 13.5],
     'space_ids': ['SP-LOBBY', 'SP-EXHIBITION', 'SP-FIRE', 'SP-REFUSE']},
    {'label': 'cafe and services', 'level_id': 'L01', 'rect': [9.0, -13.5, 21.0, 13.5],
     'space_ids': ['SP-CAFE', 'SP-WC-PUBLIC', 'SP-GENSTORE']},
    {'label': 'reading floor', 'level_id': 'L02', 'rect': [-10.0, -13.5, 21.0, 13.5],
     'space_ids': ['SP-CHILDREN', 'SP-STACKS']},
    {'label': 'seminar north', 'level_id': 'L04', 'rect': [-10.0, 6.75, 21.0, 13.5],
     'space_ids': ['SP-SEMINAR']},
]


def _zoned(massing, zones):
    from backend.app.program_massing import MassingZone
    # `model_copy(update=...)` does not validate, so the zones are built explicitly.
    return massing.model_copy(deep=True, update={'zones': [MassingZone(**z) for z in zones]})


@pytest.fixture(scope='module')
def zoned(example):
    return compile_from_massing(_zoned(example, ZONES))


def test_a_zone_holds_its_rooms_inside_its_rectangle_and_reports_its_numbers(zoned):
    allocation = zoned.program_allocation
    reports = {report.label: report for report in allocation.zone_reports}
    assert set(reports) == {zone['label'] for zone in ZONES}
    rooms = {zone.space_id: zone for zone in allocation.zones}
    for spec in ZONES:
        report = reports[spec['label']]
        x0, y0, x1, y1 = spec['rect']
        assert report.level_id == spec['level_id']
        assert report.area_usable_m2 <= report.area_rect_m2 + 0.01
        assert report.area_delivered_m2 <= report.area_usable_m2 + 0.01
        for space_id in report.placed:
            room = rooms[space_id]
            assert room.level_id == spec['level_id'], space_id
            assert (x0 - 0.01 <= room.x0 and room.x1 <= x1 + 0.01
                    and y0 - 0.01 <= room.y0 and room.y1 <= y1 + 0.01), (space_id, spec['label'])
        for space_id in report.unplaced:
            assert space_id not in rooms, f'{space_id} was reported unplaced yet stands somewhere'
            assert any(u.space_id == space_id and spec['label'] in u.reason
                       for u in allocation.unplaced)
    # the rooms a zone names are settled by it: none of them was laid out by the
    # general pass, and the general pass still ran for the rest of the brief
    named = {sid for zone in ZONES for sid in zone['space_ids']}
    assert {zone.space_id for zone in allocation.zones} - named, 'nothing outside the zones was placed'
    assert zoned.spatial.status == 'passed', [f.detail for f in zoned.spatial.findings
                                               if f.severity == 'violation']


def test_a_zone_too_small_reports_its_room_by_name_and_spills_nowhere(example):
    tiny = _zoned(example, [
        {'label': 'a cupboard for the stacks', 'level_id': 'L02',
         'rect': [-10.0, -13.5, -3.0, -6.75], 'space_ids': ['SP-STACKS']}])
    model = compile_from_massing(tiny)
    allocation = model.program_allocation
    (report,) = allocation.zone_reports
    assert report.unplaced == ['SP-STACKS'] and not report.placed
    assert 'SP-STACKS' not in {zone.space_id for zone in allocation.zones}
    (unplaced,) = [u for u in allocation.unplaced if u.space_id == 'SP-STACKS']
    assert 'a cupboard for the stacks' in unplaced.reason and 'L02' in unplaced.reason
    assert 'Zone' in next(note for note in model.limitations if note.startswith('Program:'))


def test_a_zone_that_cannot_stand_is_refused_by_name(example):
    in_the_core = _zoned(example, [
        {'label': 'through the stair', 'level_id': 'L01', 'rect': [26.0, -2.0, 31.0, 2.0],
         'space_ids': ['SP-JANITOR']}])
    with pytest.raises(ValueError, match='through the stair'):
        compile_from_massing(in_the_core)
    unknown = _zoned(example, [
        {'label': 'nowhere', 'level_id': 'L01', 'rect': [-10.0, -13.5, 0.0, 0.0],
         'space_ids': ['SP-NOT-A-ROOM']}])
    with pytest.raises(ValueError, match='SP-NOT-A-ROOM'):
        compile_from_massing(unknown)
    twice = _zoned(example, [
        {'label': 'one', 'level_id': 'L01', 'rect': [-10.0, -13.5, 0.0, 0.0],
         'space_ids': ['SP-JANITOR']},
        {'label': 'two', 'level_id': 'L02', 'rect': [-10.0, -13.5, 0.0, 0.0],
         'space_ids': ['SP-JANITOR']}])
    with pytest.raises(ValueError, match='SP-JANITOR'):
        compile_from_massing(twice)


def test_the_brief_export_gives_the_writer_every_number(example):
    from backend.app.program_massing import brief_for_massing
    brief = brief_for_massing(example)
    assert {level['id'] for level in brief['levels']} == {'L01', 'L02', 'L03', 'L04'}
    for level in brief['levels']:
        assert 0 < level['usable_m2'] <= level['plate_m2']
    reading = next(level for level in brief['levels'] if level['id'] == 'L03')
    above = next(level for level in brief['levels'] if level['id'] == 'L04')
    assert reading['carved'] and above['removed'], 'the double height must show on both storeys'
    ids = {space['id'] for space in brief['brief']}
    assert {'SP-LOBBY', 'SP-STACKS', 'SP-ADULT'} <= ids
    assert next(space for space in brief['brief'] if space['id'] == 'SP-ADULT')['settled_by_archetype']

