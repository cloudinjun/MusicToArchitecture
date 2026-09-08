"""Named shared public-floor claims stay narrow at the Program Volume boundary."""

import json

import pytest
from pydantic import ValidationError

from backend.app.program_massing import MassingGrid
from backend.app.program_volume_contracts import ProgramVolumeRegion
from backend.app.program_volumes import (
    ProgramVolume,
    ProgramVolumeCoreIntent,
    ProgramVolumeLevel,
    ProgramVolumeModel,
    ProgramVolumeUnion,
    _program_volume_regions,
)


def _volume(*, volume_id, role, category, rect, space_ids=(), shared=()):
    return ProgramVolume(
        id=volume_id,
        level_index=1,
        level_id='L01',
        category=category,
        role=role,
        space_ids=list(space_ids),
        shared_route_volume_ids=list(shared),
        grid_rect=rect,
        target_area_m2=4.0 if space_ids else 0.0,
        gross_area_m2=4.0,
        reason='Shared-route contract test.',
    )


def _model(*, shared=('PV-SPINE',), owner_rect=(0, 0, 2, 1), target='spine'):
    levels = [ProgramVolumeLevel(index=1, id='L01', z_base=0.0, z_top=4.0)]
    volumes = [
        _volume(
            volume_id='PV-FOYER', role='program', category='circulation',
            space_ids=('SP-FOYER',), shared=shared, rect=owner_rect),
        _volume(
            volume_id='PV-SPINE', role='circulation_spine', category='circulation',
            rect=(1, 0, 3, 1)),
        _volume(
            volume_id='PV-CONNECTOR', role='connector', category='circulation',
            rect=(0, 1, 1, 2)),
        _volume(
            volume_id='PV-CORE', role='circulation_spine', category='circulation',
            rect=(3, 2, 4, 3)),
    ]
    if target == 'missing':
        volumes[0] = volumes[0].model_copy(
            update={'shared_route_volume_ids': ['PV-MISSING']})
    elif target == 'connector':
        volumes[0] = volumes[0].model_copy(
            update={'shared_route_volume_ids': ['PV-CONNECTOR']})
    elif target == 'core':
        volumes[0] = volumes[0].model_copy(
            update={'shared_route_volume_ids': ['PV-CORE']})
    elif target == 'clearance':
        volumes.append(_volume(
            volume_id='PV-CLEARANCE', role='sectional_clearance',
            category='circulation', rect=(0, 0, 1, 1)))
        volumes[0] = volumes[0].model_copy(
            update={'shared_route_volume_ids': ['PV-CLEARANCE']})
    regions = _program_volume_regions(volumes, levels)
    grid = MassingGrid(
        x_lines=[0.0, 2.0, 4.0, 6.0, 8.0],
        y_lines=[0.0, 2.0, 4.0, 6.0],
        band_lines=[0.0, 2.0, 4.0, 6.0],
    )
    return ProgramVolumeModel(
        score_id='shared-route-contract',
        typology='museum',
        grammar_id='PVG-STACKED-BANDS',
        grammar_reason=['focused contract test'],
        levels=levels,
        grid=grid,
        volumes=volumes,
        level_unions=[ProgramVolumeUnion(
            level_index=1, level_id='L01',
            boundary=[(0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0)],
            gross_area_m2=48.0,
            source_volume_ids=[volume.id for volume in volumes],
        )],
        topology_signature='shared-route-contract',
        program_volume_regions=regions,
        authored_cores=[ProgramVolumeCoreIntent(
            id='CORE-1', kind='stair', source_volume_id='PV-CORE')],
    )


def test_shared_route_claim_round_trips_and_omits_empty_fields():
    model = _model()
    payload = json.loads(model.model_dump_json())

    assert payload['volumes'][0]['shared_route_volume_ids'] == ['PV-SPINE']
    assert payload['program_volume_regions'][0]['shared_route_volume_ids'] == ['PV-SPINE']
    assert 'shared_route_volume_ids' not in payload['volumes'][1]
    assert 'shared_route_volume_ids' not in payload['program_volume_regions'][1]

    restored = ProgramVolumeModel.model_validate_json(json.dumps(payload))
    assert restored.volumes[0].shared_route_volume_ids == ['PV-SPINE']
    assert restored.program_volume_regions[0].shared_route_volume_ids == ['PV-SPINE']


@pytest.mark.parametrize('target, message', [
    ('missing', 'unknown'),
    ('clearance', 'must be a circulation_spine or connector'),
    ('core', 'cannot be an authored core source'),
])
def test_shared_route_targets_are_named_connected_noncore_carriers(target, message):
    with pytest.raises(ValidationError, match=message):
        _model(target=target)


def test_shared_route_target_must_physically_overlap_owner():
    with pytest.raises(ValidationError, match='must physically overlap'):
        _model(target='connector')


def test_shared_route_owner_cannot_overlap_authored_core_through_another_carrier():
    # PV-SPINE remains the named carrier, while the owner also covers PV-CORE.
    with pytest.raises(ValidationError, match='overlaps authored core source'):
        _model(owner_rect=(2, 1, 4, 3))


@pytest.mark.parametrize('kwargs, message', [
    ({'role': 'connector', 'category': 'circulation', 'space_ids': ('SP-FOYER',)},
     'require a circulation program volume'),
    ({'role': 'program', 'category': 'public', 'space_ids': ('SP-FOYER',)},
     'require a circulation program volume'),
    ({'role': 'program', 'category': 'circulation', 'space_ids': ()},
     'no brief space'),
    ({'role': 'program', 'category': 'circulation', 'space_ids': ('A', 'B')},
     'require a circulation program volume'),
])
def test_shared_route_claim_requires_one_circulation_program_owner(kwargs, message):
    with pytest.raises(ValidationError, match=message):
        _volume(volume_id='BAD', rect=(0, 0, 1, 1), shared=('PV-SPINE',), **kwargs)


def test_shared_route_claim_target_ids_must_be_unique():
    with pytest.raises(ValidationError, match='must be unique'):
        _volume(
            volume_id='BAD', role='program', category='circulation',
            space_ids=('SP-FOYER',), rect=(0, 0, 1, 1),
            shared=('PV-SPINE', 'PV-SPINE'))


def test_region_contract_has_the_same_local_owner_guard():
    with pytest.raises(ValidationError, match='require a circulation program volume'):
        ProgramVolumeRegion(
            id='BAD', level_id='L01', category='public', role='program',
            space_ids=['SP-FOYER'], shared_route_volume_ids=['PV-SPINE'],
            grid_rect=(0, 0, 1, 1), z_base=0.0, z_top=4.0)
