"""Offline brief intent boundary; no API call or architectural-fit claim."""
import json

import pytest

from backend.scripts import generate_small_site_brief as generator


@pytest.fixture
def selection(monkeypatch):
    monkeypatch.setattr(generator.ArchitecturalScore, 'model_validate', lambda value: value)
    def install(typology):
        monkeypatch.setattr(generator, 'select_massing',
                            lambda score: (None, typology, ['recorded score decision']))
    return install


@pytest.mark.parametrize('typology', generator.SUPPORTED_TYPOLOGIES)
def test_default_follows_score_and_uses_own_catalog(selection, typology):
    selection(typology)
    request = generator.brief_request({'dimensions': []})
    assert request['typology'] == typology
    assert request['authority'] == 'score_selection'
    prompt = generator.prompt_for({'dimensions': []}, request)
    assert 'Couperin' not in prompt
    assert generator.BRIEFS[typology][0].id in prompt
    if typology != 'theater':
        assert 'SP-AUDITORIUM' not in prompt


def test_pin_is_explicit_and_keeps_original_choice(selection):
    selection('museum')
    request = generator.brief_request({}, 'theater')
    assert request['typology'] == 'theater'
    assert request['score_selected_typology'] == 'museum'
    assert request['authority'] == 'experiment_pin'


def test_unsupported_selection_is_not_silently_reclassified(selection):
    selection('pavilion')
    with pytest.raises(ValueError, match='no silent fallback'):
        generator.brief_request({})


@pytest.mark.parametrize('defect', ['type', 'missing', 'identity'])
def test_invalid_proposal_cannot_emit_brief(tmp_path, defect):
    spaces = [s.model_dump(mode='json') for s in generator.BRIEFS['library']]
    if defect == 'missing':
        spaces = spaces[1:]
    if defect == 'identity':
        spaces[0]['space_type'] = 'auditorium'
    proposal = dict(label='test', typology='museum' if defect == 'type' else 'library',
                    site_boundary=[dict(x=0,y=0),dict(x=20,y=0),dict(x=20,y=20),dict(x=0,y=20)],
                    occupied_storeys=4, target_gross_area_m2=1000,
                    circulation_budget_m2=200, spaces=spaces,
                    assumptions=[], floor_strategy=[])
    for name, value in [('proposal', proposal), ('request', {'typology':'library'}),
                        ('provider', {'prompt_version':generator.PROMPT_VERSION})]:
        (tmp_path / f'{name}.json').write_text(json.dumps(value), encoding='utf-8')
    with pytest.raises(ValueError, match='typology differs|Typology program mismatch'):
        generator.normalize_saved(tmp_path)
    assert not (tmp_path / 'project_brief.json').exists()
