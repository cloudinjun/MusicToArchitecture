"""PV plan scale and music proportion reach one roof recipe without sizing claims."""
import pytest
from shapely.affinity import scale, translate
from shapely.geometry import box
from shapely.ops import unary_union

from backend.app.datums import compile_datum_set
from backend.app.program_massing import datums_for
from backend.app.program_volumes import organize_program_volumes
from backend.app.roof import RoofControl, roof_plan_span, score_roof_control
from backend.tests.test_program_volumes import _score


def control(shape, score=None):
    datum = compile_datum_set(score or _score()).by_id('truss_depth_m')
    return score_roof_control(list(shape.exterior.coords)[:-1],
        [list(r.coords)[:-1] for r in shape.interiors],
        datum_z=12.0, hierarchy_datum=datum)


def test_roof_scale_changes_depth_but_not_construction_layer_thickness():
    shape = box(0, 0, 12, 16)
    full, small = control(shape), control(scale(shape, xfact=.5, yfact=.5, origin=(0, 0)))
    assert small.profile.truss_depth_m == pytest.approx(full.profile.truss_depth_m / 2)
    assert small.span_proportion.span_m == pytest.approx(8)
    for field in type(full.profile).model_fields:
        if field != 'truss_depth_m':
            assert getattr(small.profile, field) == getattr(full.profile, field)
    assert full.physical_top_z-small.physical_top_z == pytest.approx(
        full.profile.truss_depth_m-small.profile.truss_depth_m)


def test_plan_span_does_not_fill_concavities_or_join_separate_intervals():
    shape = unary_union([box(0, 0, 6, 4), box(4, 4, 10, 8), box(8, 8, 14, 12)])
    assert shape.bounds[3]-shape.bounds[1] == 12
    assert roof_plan_span(list(shape.exterior.coords)[:-1], []) == pytest.approx(8)
    shifted = translate(shape, xoff=103, yoff=-29)
    assert control(shifted).profile == control(shape).profile


def test_music_moves_only_inside_the_guide_ratio_and_low_confidence_nudges():
    shape = box(0, 0, 12, 12)
    assert control(shape, _score(hierarchy=0)).profile.truss_depth_m == pytest.approx(1)
    assert control(shape, _score(hierarchy=1)).profile.truss_depth_m == pytest.approx(1.5)
    score = _score(hierarchy=1)
    score.dimensions = [d.model_copy(update={'confidence': .1}) if d.id == 'hierarchy'
                        else d for d in score.dimensions]
    weak = control(shape, score)
    assert 1.25 < weak.profile.truss_depth_m < 1.5
    assert weak.span_proportion.hierarchy_position == pytest.approx(round(.5 + .5*.1/.75, 4))


@pytest.mark.parametrize('known', [True, False])
def test_datum_propagation_preserves_source_confidence_and_unknown_coverage(known):
    score = _score(hierarchy=.8)
    if not known:
        score.dimensions = [d for d in score.dimensions if d.id != 'hierarchy']
    base = compile_datum_set(score)
    volumes = organize_program_volumes(score, 'museum', grammar_id='PVG-STACKED-BANDS')
    derived = datums_for(volumes.to_program_massing(), score)
    before, after = base.by_id('truss_depth_m'), derived.by_id('truss_depth_m')
    assert after.value == volumes.roof_control.profile.truss_depth_m
    assert after.provenance == before.provenance
    assert after.dimension_confidence == before.dimension_confidence
    assert after.dimension_value == before.dimension_value
    assert derived.coverage == base.coverage
    assert derived.variable_coverage == base.variable_coverage
    assert after.score_driven is known


def test_inconsistent_serialized_roof_span_or_depth_is_rejected():
    original = control(box(0, 0, 12, 12)).model_dump()
    original['span_proportion']['span_m'] = 20
    with pytest.raises(ValueError, match='measured plan span'):
        RoofControl.model_validate(original)
    with pytest.raises(ValueError, match='too short'):
        control(box(0, 0, 1, 1))


def test_an_explicit_depth_cannot_silently_override_the_volume_roof_contract():
    score = _score()
    massing = organize_program_volumes(score, 'museum').to_program_massing()
    massing.datums['truss_depth_m'] = massing.roof_control.profile.truss_depth_m + .5
    with pytest.raises(ValueError, match='conflicts'):
        datums_for(massing, score)
