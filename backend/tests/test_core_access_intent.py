"""Lift access-face intent crosses the three core contracts without changing legacy payloads."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.datums import CoreDatum
from backend.app.models import ArchitecturalScore, ScoreDimension
from backend.app.program_massing import MassingCore, datums_for, lattice_for
from backend.app.program_volumes import ProgramVolumeCoreIntent, organize_program_volumes


DIMENSIONS = (
    'genre_style', 'hierarchy', 'repetition', 'variation', 'density',
    'continuity', 'interruption', 'polyphony', 'tension_release',
    'tempo_of_change',
)


def _score() -> ArchitecturalScore:
    return ArchitecturalScore(
        score_id='core-access-face-test', source_audio_sha256='1' * 64,
        dimensions=[ScoreDimension(
            id=dimension, value=0.5, source_feature=f'test_{dimension}',
            extraction_method='manual', confidence=1.0,
            architectural_proposal='Core access-face contract test.')
                    for dimension in DIMENSIONS],
        mapping_rules=[],
    )


def _volume_model():
    return organize_program_volumes(
        _score(), 'library', grammar_id='PVG-STACKED-BANDS')


def _with_core(model, core):
    payload = model.model_dump(mode='json')
    payload['authored_cores'] = [core.model_dump(mode='json')]
    return type(model).model_validate(payload)


def test_lift_access_face_transfers_program_volume_to_massing_and_core_datum():
    model = _volume_model()
    source = next(volume for volume in model.volumes
                  if volume.level_id == model.levels[0].id
                  and volume.role == 'circulation_spine')
    authored = _with_core(model, ProgramVolumeCoreIntent(
        id='LIFT-1', kind='lift', source_volume_id=source.id,
        access_face='east'))

    massing = authored.to_program_massing()
    assert massing.cores[0].access_face == 'east'

    datums = datums_for(massing, _score())
    lattice = lattice_for(massing, datums)
    assert lattice.given_cores[0].access_face == 'east'


def test_access_face_none_is_legacy_compatible_and_omitted_at_each_boundary():
    model = _volume_model()
    source = next(volume for volume in model.volumes
                  if volume.level_id == model.levels[0].id
                  and volume.role == 'circulation_spine')
    authored = _with_core(model, ProgramVolumeCoreIntent(
        id='LIFT-1', kind='lift', source_volume_id=source.id))
    massing = authored.to_program_massing()
    datums = datums_for(massing, _score())
    lattice = lattice_for(massing, datums)

    for payload in (
        authored.model_dump(mode='json'),
        massing.cores[0].model_dump(mode='json'),
        lattice.given_cores[0].model_dump(mode='json'),
    ):
        assert 'access_face' not in payload


@pytest.mark.parametrize('core_type, factory', [
    ('program_volume', lambda: ProgramVolumeCoreIntent(
        id='CORE-A', kind='stair', source_volume_id='PV-CIRC', access_face='east')),
    ('massing', lambda: MassingCore(
        id='CORE-A', kind='stair', x=0.0, y=0.0, access_face='east')),
    ('datum', lambda: CoreDatum(
        id='CORE-A', kind='stair', x=0.0, y=0.0, access_face='east')),
])
def test_access_face_is_rejected_for_stairs(core_type, factory):
    with pytest.raises(ValidationError, match='only valid for lift'):
        factory()


def test_core_datum_accepts_each_declared_lift_face():
    for face in ('south', 'north', 'east', 'west'):
        datum = CoreDatum(id='LIFT-1', kind='lift', x=0.0, y=0.0,
                          access_face=face)
        assert datum.access_face == face
