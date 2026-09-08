"""Gross sectional airspace remains traceable after floor subtraction."""
from types import SimpleNamespace

import pytest

from backend.app.briefs import brief_for
from backend.app.compiler_v3 import _carve_and_allocate
from backend.app.program_massing import datums_for, lattice_for
from backend.app.program_volumes import organize_program_volumes
from backend.scripts.run_program_volume_study import _union_to_lattice_report
from backend.tests.test_program_volume_circulation import theatre_score


@pytest.fixture
def chain():
    score = theatre_score('couperin')
    volumes = organize_program_volumes(score, 'theater', grammar_id='PVG-TERRACED-WEAVE')
    massing = volumes.to_program_massing()
    datums = datums_for(massing, score)
    lattice = lattice_for(massing, datums)
    _allocation, carve = _carve_and_allocate(
        lattice, datums, 'theater', brief_for('theater', storeys=len(lattice.occupied)))
    assert carve.removed
    return SimpleNamespace(lattice=lattice), volumes


def test_registered_airspace_is_subtracted_from_expected_floor(chain):
    building, volumes = chain
    report = _union_to_lattice_report(building, volumes)
    assert report['verdict'] == 'passed'
    assert report['declared_clearance_area_m2'] > 0
    assert report['unclaimed_floor_difference_m2'] <= report['tolerance_m2']


@pytest.mark.parametrize('damage', ['missing_clearance_authority', 'restored_floor'])
def test_unclaimed_floor_change_stays_failed(chain, damage):
    building, volumes = chain
    if damage == 'missing_clearance_authority':
        volumes.volumes = [v for v in volumes.volumes if v.role != 'sectional_clearance']
    else:
        source = lattice_for(volumes.to_program_massing(), datums_for(
            volumes.to_program_massing(), theatre_score('couperin')))
        building.lattice.levels[2].plate = source.levels[2].plate
        building.lattice.levels[2].voids = source.levels[2].voids
    report = _union_to_lattice_report(building, volumes)
    assert report['verdict'] == 'failed'
    assert report['unclaimed_floor_difference_m2'] > 1


def test_changed_generation_source_cannot_issue_a_completed_candidate(monkeypatch):
    from backend.scripts import run_program_volume_study as study
    monkeypatch.setattr(study, 'compiler_source_fingerprint', lambda: 'new-source')
    study._assert_generation_source('new-source')
    with pytest.raises(RuntimeError, match='Compiler source changed'):
        study._assert_generation_source('old-source')
