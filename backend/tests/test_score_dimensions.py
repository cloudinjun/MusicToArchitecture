"""All ten shared score dimensions, and the honesty rules that keep them usable."""

from pathlib import Path

import pytest

from backend.app.audio import extract_audio_features
from backend.app.compiler_v3 import compile_building_model_v3
from backend.app.datums import FULL_CONFIDENCE, compile_datum_set, confidence_factor
from backend.app.models import ArchitecturalScore, AudioFeatures
from backend.app.score import compile_architectural_score

MP3 = (Path(__file__).parents[2] / 'fixtures' / 'audio'
       / 'gemini_music_to_architecture_44s.mp3')

TEN = {'tempo_of_change', 'tension_release', 'density', 'continuity', 'repetition',
       'variation', 'hierarchy', 'interruption', 'polyphony', 'genre_style'}

EXTENDED = ('periodicity', 'timbre_variation', 'dynamic_range_db',
            'novelty_peak_rate_per_min', 'spectral_contrast_db', 'harmonic_ratio',
            'spectral_flatness', 'zero_crossing_rate')

# The four v2 metrics belong in the saturation check too. Leaving them out of EXTENDED
# is what let `tempo_bpm` pin at 0.000 on this very fixture after the first calibration
# pass: the corpus bottomed out near 80 BPM, the fitted floor landed at 74, and the
# 64.6 BPM fixture fell off the end with no test to notice.
ALL_METRICS = ('tempo_bpm', 'rms_energy', 'onset_density_hz',
               'spectral_centroid_hz') + EXTENDED


@pytest.fixture(scope='module')
def features() -> AudioFeatures:
    return extract_audio_features(MP3, MP3.name)


@pytest.fixture(scope='module')
def score(features) -> ArchitecturalScore:
    return compile_architectural_score(features)


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

def test_every_extended_metric_is_measured(features):
    for name in EXTENDED:
        metric = getattr(features, name)
        assert metric is not None, name
        assert metric.method and metric.unit
        assert 0.0 <= metric.normalized <= 1.0


def test_no_metric_saturates_its_normalisation_range(features):
    """A metric pinned at 0 or 1 is a range error, not a measurement."""
    for name in ALL_METRICS:
        metric = getattr(features, name)
        assert 0.0 < metric.normalized < 1.0, f'{name} saturated at {metric.normalized}'


def test_no_metric_sits_against_an_endpoint_on_out_of_corpus_material(features):
    """The stronger claim, and the one that matters for reuse.

    The ranges are calibrated on a 14-track corpus; this fixture is not in it. A reading
    within 0.02 of an endpoint is not yet clipped, but it has stopped discriminating --
    every recording in that neighbourhood produces the same building parameter. Holding
    the margin against material the calibration never saw is what stops the ranges being
    fitted to the corpus rather than to music.
    """
    for name in ALL_METRICS:
        value = getattr(features, name).normalized
        assert 0.02 < value < 0.98, f'{name} sits at {value:.3f}, too close to an end'


def test_all_ten_dimensions_are_emitted(score):
    assert {d.id for d in score.dimensions} == TEN


def test_each_dimension_names_a_distinct_source(score):
    sources = [d.source_feature for d in score.dimensions]
    assert len(sources) == len(set(sources))


def test_repetition_and_variation_do_not_share_a_source(score):
    repetition = next(d for d in score.dimensions if d.id == 'repetition')
    variation = next(d for d in score.dimensions if d.id == 'variation')
    assert repetition.source_feature != variation.source_feature
    assert repetition.extraction_method == 'observed'
    assert variation.extraction_method == 'observed'


def test_proxies_are_declared_as_inferred_not_observed(score):
    for name in ('polyphony', 'genre_style'):
        dimension = next(d for d in score.dimensions if d.id == name)
        assert dimension.extraction_method == 'inferred'
        assert dimension.confidence < 0.6


def test_genre_style_never_claims_to_be_a_genre(score):
    dimension = next(d for d in score.dimensions if d.id == 'genre_style')
    proposal = dimension.architectural_proposal
    assert 'not a genre label' in proposal
    assert 'never selects a facade grammar' in proposal
    assert dimension.confidence <= 0.4


def test_a_shortened_feature_set_yields_a_shortened_score(features):
    """An artifact from before the extended extractor must still compile, and must not
    be padded with invented dimensions."""
    trimmed = features.model_copy(update={name: None for name in EXTENDED})
    shortened = compile_architectural_score(trimmed)
    assert {d.id for d in shortened.dimensions} == {
        'tempo_of_change', 'tension_release', 'density', 'continuity'}


def test_the_v2_mapping_rules_survive(score):
    """Schema 3.0 is additive: compiler.py and mapping_report.py bind to these."""
    ids = {rule.id for rule in score.mapping_rules}
    assert {'TEMPO_TO_EPISODES', 'ENERGY_TO_READING_HEIGHT', 'DENSITY_TO_GRID',
            'DENSITY_TO_FACADE', 'DENSITY_TO_SERVICE_DEPTH', 'CONTINUITY_TO_SPINE',
            'CONTINUITY_TO_DATUM'} <= ids


# ---------------------------------------------------------------------------
# The confidence clamp
# ---------------------------------------------------------------------------

def test_confidence_factor_scales_travel_not_direction():
    assert confidence_factor(FULL_CONFIDENCE) == pytest.approx(1.0)
    assert confidence_factor(1.0) == pytest.approx(1.0)
    assert confidence_factor(0.35) == pytest.approx(0.35 / FULL_CONFIDENCE)
    assert confidence_factor(0.0) == 0.0


def _override(score: ArchitecturalScore, **updates) -> ArchitecturalScore:
    return ArchitecturalScore(
        score_id=score.score_id, source_audio_sha256=score.source_audio_sha256,
        mapping_rules=score.mapping_rules,
        dimensions=[d.model_copy(update=updates[d.id]) if d.id in updates else d
                    for d in score.dimensions])


def test_a_low_confidence_dimension_cannot_reach_the_end_of_its_range(score):
    """genre_style at 0.35 confidence must stay near the middle of every range it
    drives, however extreme the reading."""
    datums = compile_datum_set(_override(score, genre_style={'value': 1.0}))
    opaque = datums.by_id('opaque_fraction')
    low, high = opaque.output_range
    assert opaque.applied_position < 0.75
    assert abs(opaque.value - high) > abs(high - low) * 0.2
    assert 'confidence' in opaque.reason
    assert opaque.clamped


def test_a_high_confidence_dimension_reaches_its_range(score):
    datums = compile_datum_set(
        _override(score, hierarchy={'value': 1.0, 'confidence': 0.95}))
    truss = datums.by_id('truss_depth_m')
    assert truss.applied_position == pytest.approx(1.0)
    assert truss.value == pytest.approx(truss.output_range[1])
    assert not truss.clamped


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------

def test_every_variable_datum_is_score_driven(score):
    datums = compile_datum_set(score)
    assert datums.variable_coverage == pytest.approx(1.0)
    assert not datums.waiting_on
    assert set(datums.dimensions_used) == TEN


def test_tectonic_constants_are_never_score_driven(score):
    datums = compile_datum_set(score)
    constants = [d for d in datums.datums if d.provenance == 'tectonic_constant']
    assert constants
    for datum in constants:
        assert datum.driving_dimension is None
        assert datum.output_range is None


# ---------------------------------------------------------------------------
# The new dimensions actually change the building
# ---------------------------------------------------------------------------

def _with(score: ArchitecturalScore, **values) -> ArchitecturalScore:
    return _override(score, **{key: {'value': value} for key, value in values.items()})


def test_polyphony_separates_the_envelope_from_the_frame(features, score):
    thin = compile_building_model_v3(features, _with(score, polyphony=0.0))
    thick = compile_building_model_v3(features, _with(score, polyphony=1.0))
    assert (thick.datum_set.value('envelope_offset_m')
            > thin.datum_set.value('envelope_offset_m'))
    # Which element carries the second voice depends on the grammar: a framed skin
    # gets a screen fin standing off it, an overlay grammar gets its lattice or its
    # panel field. What must hold across all of them is that more polyphony produces
    # more of the envelope standing clear of the frame.
    second_voice = ('screen_fin', 'lattice_mullion', 'lattice_transom', 'field_panel',
                    'brise_soleil', 'external_strut')
    assert (sum(thick.element_counts.get(k, 0) for k in second_voice)
            > sum(thin.element_counts.get(k, 0) for k in second_voice))
    assert (thick.element_counts.get('brace', 0)
            >= thin.element_counts.get('brace', 0))


def test_interruption_breaks_the_stack(features, score):
    whole = compile_building_model_v3(features, _with(score, interruption=0.0))
    broken = compile_building_model_v3(features, _with(score, interruption=1.0))
    assert broken.datum_set.integer('void_count') > whole.datum_set.integer('void_count')
    assert (sum(1 for level in broken.lattice.levels if level.is_terrace)
            >= sum(1 for level in whole.lattice.levels if level.is_terrace))


def test_hierarchy_announces_the_entrance(features, score):
    level = compile_building_model_v3(features, _with(score, hierarchy=0.0))
    steep = compile_building_model_v3(features, _with(score, hierarchy=1.0))
    assert steep.datum_set.value('truss_depth_m') > level.datum_set.value('truss_depth_m')
    assert steep.element_counts.get('entry_canopy', 0) > 0
    assert level.element_counts.get('entry_canopy', 0) == 0


def test_repetition_tightens_every_tertiary_rhythm(features, score):
    """Repetition tightens the module, and the module is what the mullion count follows.

    Everything except the module is pinned, because `repetition` reaches further than
    it looks: it drives the regularity axis, which the envelope tree branches on *and*
    the massing tree branches on. Left free, the loose case became Deconstructivism on
    one silhouette and the tight one International Style on another, and a mullion count
    across two different perimeters with two different subdivisions measures neither the
    module nor anything else.
    """
    pin = dict(grammar_id='FCD-01-INTERNATIONAL-STYLE', massing_id='MAS-SLAB',
               typology='library')
    loose = compile_building_model_v3(features, _with(score, repetition=0.0), **pin)
    tight = compile_building_model_v3(features, _with(score, repetition=1.0), **pin)
    for datum in ('mullion_module_m', 'spandrel_height_m', 'rail_post_spacing_m'):
        assert tight.datum_set.value(datum) < loose.datum_set.value(datum), datum
    assert tight.element_counts['mullion'] > loose.element_counts['mullion']


def test_variation_stops_the_stack_being_an_extrusion(features, score):
    flat = compile_building_model_v3(features, _with(score, variation=0.0))
    stepped = compile_building_model_v3(features, _with(score, variation=1.0))
    assert flat.datum_set.value('plate_rotation_deg') == pytest.approx(0.0)
    assert stepped.datum_set.value('plate_rotation_deg') > 0.5
    top_flat = flat.lattice.levels[-1].plate
    top_stepped = stepped.lattice.levels[-1].plate
    assert [(p.x, p.y) for p in top_flat] != [(p.x, p.y) for p in top_stepped]


def test_genre_style_moves_the_opaque_share_but_only_a_little(features, score):
    light = compile_building_model_v3(features, _with(score, genre_style=1.0))
    heavy = compile_building_model_v3(features, _with(score, genre_style=0.0))
    assert (heavy.datum_set.value('opaque_fraction')
            > light.datum_set.value('opaque_fraction'))
    for model in (light, heavy):
        value = model.datum_set.value('opaque_fraction')
        assert 0.15 < value < 0.42


def test_columns_still_stack_under_rotation_and_step_back(features, score):
    """Rotation and step-back must never leave a column without a continuation."""
    model = compile_building_model_v3(features, _with(
        score, variation=1.0, interruption=1.0, tempo_of_change=1.0))
    by_node: dict[tuple, list[int]] = {}
    for element in model.elements:
        if element.kind not in ('column', 'piloti_column'):
            continue
        index = element.lattice_index
        key = (index.get('x'), index.get('y'), index.get('apse'))
        by_node.setdefault(key, []).append(index['level'])
    assert by_node
    for key, levels in by_node.items():
        ordered = sorted(levels)
        assert ordered == list(range(ordered[0], ordered[0] + len(ordered))), key
        assert ordered[0] == 0, key
