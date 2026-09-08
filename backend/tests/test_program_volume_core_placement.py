"""Program Volume core intents stay indexed, compact, and testable."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from backend.app.compiler_v3 import core_anchors
from backend.app.datums import compile_datum_set
from backend.app.models import ArchitecturalScore, ScoreDimension
from backend.app.program_massing import datums_for, lattice_for
from backend.app.program_volumes import (
    ProgramVolumeCoreIntent,
    _circulation_intent_for,
    organize_program_volumes,
)


DIMENSIONS = (
    'genre_style', 'hierarchy', 'repetition', 'variation', 'density',
    'continuity', 'interruption', 'polyphony', 'tension_release',
    'tempo_of_change',
)


def _score() -> ArchitecturalScore:
    return ArchitecturalScore(
        score_id='program-volume-core-test', source_audio_sha256='1' * 64,
        dimensions=[ScoreDimension(
            id=dimension, value=0.5, source_feature=f'test_{dimension}',
            extraction_method='manual', confidence=1.0,
            architectural_proposal='Core intent contract test.')
                    for dimension in DIMENSIONS],
        mapping_rules=[],
    )


def _model():
    return organize_program_volumes(
        _score(), 'library', grammar_id='PVG-STACKED-BANDS')


def _first_level_spines(model):
    return [volume for volume in model.volumes
            if volume.level_id == model.levels[0].id
            and volume.role == 'circulation_spine']


def _with_cores(model, cores):
    # ``model_copy(update=...)`` intentionally skips Pydantic validation.  Re-run
    # the model boundary here so the negative tests exercise the actual contract.
    payload = model.model_dump(mode='json')
    payload['authored_cores'] = [core.model_dump(mode='json') for core in cores]
    return type(model).model_validate(payload)


def test_authored_core_maps_to_source_volume_centre_and_serves_every_level():
    model = _model()
    source = _first_level_spines(model)[0]
    x0, y0, x1, y1 = model.rect_of(source)
    authored = _with_cores(model, [ProgramVolumeCoreIntent(
        id='CORE-A', kind='stair', source_volume_id=source.id)])

    massing = authored.to_program_massing()

    assert len(massing.cores) == 1
    core = massing.cores[0]
    assert core.id == 'CORE-A'
    assert core.kind == 'stair'
    assert (core.x, core.y) == pytest.approx(((x0 + x1) / 2, (y0 + y1) / 2))
    # Empty is the established MassingCore encoding for every level from grade.
    assert core.serves == []


def test_authored_core_intent_round_trips_and_empty_field_stays_omitted():
    model = _model()
    assert 'authored_cores' not in model.model_dump(mode='json')

    source = _first_level_spines(model)[0]
    authored = _with_cores(model, [ProgramVolumeCoreIntent(
        id='LIFT-1', kind='lift', source_volume_id=source.id)])
    payload = json.loads(authored.model_dump_json())
    restored = type(authored).model_validate_json(json.dumps(payload))

    assert restored.authored_cores == authored.authored_cores
    assert payload['authored_cores'] == [{
        'id': 'LIFT-1', 'kind': 'lift', 'source_volume_id': source.id,
    }]


@pytest.mark.parametrize('axis',['x','y'])
def test_core_run_axis_survives_program_volume_and_massing_contracts(axis):
    model = _model()
    source = _first_level_spines(model)[0]
    authored = _with_cores(model,[ProgramVolumeCoreIntent(
        id='CORE-A',kind='stair',source_volume_id=source.id,run_axis=axis)])
    restored = type(model).model_validate_json(authored.model_dump_json())
    core = restored.to_program_massing().cores[0]
    assert core.run_axis == axis
    assert ('run_axis' in core.model_dump()) == (axis=='x')
    assert restored.authored_cores[0].run_axis == axis


def test_massing_reserves_the_oriented_physical_core_without_resizing():
    from backend.app.program_massing import ProgramMassing, MassingLevel, MassingCore
    from backend.app.compiler_v3 import _core_box
    from backend.app.datums import flight_run
    for axis in ('x','y'):
        massing = ProgramMassing(levels=[MassingLevel(plate=[(0,0),(12,0),(12,12),(0,12)])]*3,
            cores=[MassingCore(id='CORE-A',kind='stair',x=6,y=6,run_axis=axis)],
            datums={'flight_width_m':1.2})
        datums = datums_for(massing,_score())
        lattice = lattice_for(massing,datums)
        expected = _core_box(6,6,1.2,flight_run(1.2),run_axis=axis)
        assert lattice.given_cores[0].run_axis == axis
        for level in lattice.levels:
            assert any(rect==pytest.approx(expected,abs=1e-4) for rect in level.reserved)
        assert (expected[2]-expected[0])*(expected[3]-expected[1]) == pytest.approx(3.04*6.68)


def test_unknown_core_axis_is_rejected():
    with pytest.raises(ValidationError):
        ProgramVolumeCoreIntent(id='A',kind='stair',source_volume_id='PV-A',run_axis='diagonal')


def test_massing_export_preserves_primary_secondary_and_extra_core_axes():
    from types import SimpleNamespace
    from backend.app.program_massing import ProgramMassing, MassingLevel, MassingCore, program_massing_of
    massing = ProgramMassing(levels=[MassingLevel(plate=[(0,0),(32,0),(32,14),(0,14)])]*3,
        cores=[MassingCore(id=f'CORE-{i}',kind='stair',x=x,y=7,run_axis=axis)
               for i,x,axis in [('A',6,'x'),('B',16,'y'),('C',26,'x')]],
        datums={'flight_width_m':1.2})
    datums = datums_for(massing,_score())
    lattice = lattice_for(massing,datums)
    model = SimpleNamespace(lattice=lattice,datum_set=datums,typology='library',
        model_id='axis-contract-test',project_brief=None,structural_system_id=None,facade_grammar_id=None)
    exported = program_massing_of(model)
    assert [c.run_axis for c in exported.cores if c.kind=='stair'] == ['x','y','x']


@pytest.mark.parametrize('cores, message', [
    ([ProgramVolumeCoreIntent(id='CORE-A', kind='stair',
                              source_volume_id='PV-MISSING')], 'unknown Program Volume'),
    ([ProgramVolumeCoreIntent(id='CORE-A', kind='stair',
                              source_volume_id='PV-L01-SP-EXHIBITION-01')],
     'must be a circulation_spine'),
    ([
        ProgramVolumeCoreIntent(id='CORE-A', kind='stair',
                                source_volume_id='PV-L01-CIRCULATION_SPINE-01'),
        ProgramVolumeCoreIntent(id='CORE-A', kind='lift',
                                source_volume_id='PV-L01-CIRCULATION_SPINE-02'),
    ], 'core ids must be unique'),
    ([
        ProgramVolumeCoreIntent(id='CORE-A', kind='stair',
                                source_volume_id='PV-L01-CIRCULATION_SPINE-01'),
        ProgramVolumeCoreIntent(id='LIFT-1', kind='lift',
                                source_volume_id='PV-L01-CIRCULATION_SPINE-01'),
    ], 'cannot share a source'),
])
def test_authored_core_references_are_rejected_at_the_contract_boundary(cores, message):
    with pytest.raises(ValidationError, match=message):
        _with_cores(_model(), cores)


def test_core_anchors_reads_the_authored_centre_without_searching_for_another_point():
    score = _score()
    model = _model()
    source = _first_level_spines(model)[0]
    authored = _with_cores(model, [ProgramVolumeCoreIntent(
        id='CORE-A', kind='stair', source_volume_id=source.id)])
    massing = authored.to_program_massing()
    datums = datums_for(massing, score)
    lattice = lattice_for(massing, datums)

    anchors = core_anchors(lattice, datums)
    x0, y0, x1, y1 = model.rect_of(source)

    assert anchors['primary'] == pytest.approx(((x0 + x1) / 2, (y0 + y1) / 2))
    assert lattice.given_cores[0].id == 'CORE-A'


def test_authored_entry_carrier_is_selected_exactly():
    model = _model()
    spines = _first_level_spines(model)
    assert len(spines) >= 2
    selected = spines[-1]

    intent = _circulation_intent_for(
        grammar=model.grammar_id,
        topology_signature=model.topology_signature,
        volumes=model.volumes,
        levels=model.levels,
        unions=model.level_unions,
        grid=model.grid,
        entry_carrier_id=selected.id,
    )

    assert intent.entry_station.source_volume_id == selected.id


@pytest.mark.parametrize('entry_carrier_id', [
    'PV-MISSING', 'PV-L01-SP-EXHIBITION-01',
])
def test_authored_entry_carrier_rejects_unknown_or_non_spine_ids(entry_carrier_id):
    model = _model()
    with pytest.raises(ValueError, match='first-level circulation_spine'):
        _circulation_intent_for(
            grammar=model.grammar_id,
            topology_signature=model.topology_signature,
            volumes=model.volumes,
            levels=model.levels,
            unions=model.level_unions,
            grid=model.grid,
            entry_carrier_id=entry_carrier_id,
        )
