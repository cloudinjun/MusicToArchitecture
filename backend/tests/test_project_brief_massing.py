"""The normalized brief survives the massing boundary; no giant fallback brief."""
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.app.project_brief import ProjectBrief
from backend.app.program_massing import ProgramMassing, lattice_for, datums_for, neutral_score


@pytest.fixture
def massing():
    brief = ProjectBrief.model_validate({
        'brief_id': 'compact-fixture', 'typology': 'library',
        'site': {'polygon': [[0, 0], [25, 0], [25, 20], [0, 20]]},
        'occupied_storeys': 2, 'target_gross_area_m2': 800,
        'circulation_budget_m2': 100,
        'provenance': {'provider_type': 'external', 'generated_at': 'fixture'},
        'spaces': [{'id': 'SP-ADULT', 'space_type': 'adult_reading', 'label': 'Reading',
                    'category': 'public', 'area_m2': 80, 'min_dimension_m': 4,
                    'level_preference': 'low', 'daylight': 'preferred',
                    'occupancy_id': 'library_reading', 'reason': 'Test requirement'}]})
    plate = [[1, 1], [23, 1], [23, 18], [1, 18]]
    return ProgramMassing.model_validate({
        'typology': 'library', 'project_brief': brief,
        'levels': [{'id': f'L{i:02d}', 'kind': kind, 'z': z, 'plate': plate}
                   for i, (kind, z) in enumerate([
                       ('podium', 0), ('occupied', .3), ('occupied', 4.3), ('roof', 8.3)])]})


def lattice(massing):
    return lattice_for(massing, datums_for(massing, neutral_score(massing)))


def test_site_area_is_not_total_floor_area(massing):
    grid = lattice(massing)
    assert len(grid.occupied) == 2
    assert massing.project_brief.site.area_m2 == 500
    assert sum(374 for _ in grid.occupied) == 748
    assert [(p.x,p.y) for p in grid.site_boundary] == list(massing.project_brief.site.polygon[:-1])


def test_outside_plate_rejected_before_compile(massing):
    massing.levels[2].plate[0] = (-1, 1)
    with pytest.raises(ValueError, match='L02.*outside'):
        lattice(massing)


def test_gross_budget_rejected_before_compile(massing):
    massing.project_brief.target_gross_area_m2 = 700
    with pytest.raises(ValueError, match='exceeds brief gross budget'):
        lattice(massing)


def test_floor_budget_excludes_declared_upper_airspace_without_changing_envelope(massing):
    from backend.app.program_massing import MassingGrid
    from backend.app.program_volume_contracts import ProgramVolumeRegion
    massing.project_brief.target_gross_area_m2 = 700
    massing.grid = MassingGrid(x_lines=[1, 11, 23], y_lines=[1, 11, 18])
    massing.program_volume_regions = [ProgramVolumeRegion(
        id='UPPER-AIR', level_id='L02', category='public', role='sectional_clearance',
        grid_rect=(0, 0, 1, 1), z_base=4.3, z_top=8.3)]
    grid = lattice(massing)
    # 748 m² envelope projection; 648 m² prospective floor after the declared carve.
    # This is area accounting only, not evidence that an archetype can use the cut.
    assert [(p.x, p.y) for p in grid.occupied[1].plate] == massing.levels[2].plate
    massing.project_brief.target_gross_area_m2 = 640
    with pytest.raises(ValueError, match='exceeds brief gross budget'):
        lattice(massing)


def test_typology_and_floor_count_cannot_silently_change(massing):
    data = massing.model_dump()
    data['typology'] = 'museum'
    with pytest.raises(ValidationError, match='typology must match'):
        ProgramMassing.model_validate(data)
    massing.project_brief.occupied_storeys = 3
    with pytest.raises(ValueError, match='level count'):
        lattice(massing)


def test_given_brief_reaches_allocation_and_shared_tail(massing, monkeypatch):
    from backend.app import compiler_v3
    from backend.app.program_massing import compile_from_massing
    captured = {}

    def carve(grid, datums, typology, brief, **kwargs):
        captured['brief'] = brief
        return SimpleNamespace(), None

    monkeypatch.setattr(compiler_v3, '_carve_and_allocate', carve)
    monkeypatch.setattr(compiler_v3, '_compile_from_lattice', lambda **kwargs: kwargs)
    output = compile_from_massing(massing)
    assert captured['brief'] == massing.project_brief.resolved_spaces()
    assert output['project_brief'] is massing.project_brief
    assert output['identity_token'] == massing.digest()
    assert next(s.area_m2 for s in captured['brief'] if s.id == 'SP-ADULT') == 80
    changed = massing.model_copy(deep=True)
    changed.project_brief.spaces[0].area_m2 = 90
    assert changed.digest() != massing.digest()
