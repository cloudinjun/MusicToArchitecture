"""The translation health check: what it claims, and what it refuses to claim."""

from pathlib import Path

import pytest

from backend.app.audio import extract_audio_features
from backend.app.compiler_v3 import compile_building_model_v3
from backend.app.models import ArchitecturalScore, AudioFeatures
from backend.app.score import compile_architectural_score
from backend.app.translation_report import (
    DIMENSION_LABELS, compile_translation_report,
)

MP3 = (Path(__file__).parents[2] / 'fixtures' / 'audio'
       / 'gemini_music_to_architecture_44s.mp3')


@pytest.fixture(scope='module')
def features() -> AudioFeatures:
    return extract_audio_features(MP3, MP3.name)


@pytest.fixture(scope='module')
def score(features) -> ArchitecturalScore:
    return compile_architectural_score(features)


@pytest.fixture(scope='module')
def report(features, score):
    model = compile_building_model_v3(features, score)
    return compile_translation_report(features, score, model)


def test_every_dimension_appears_whether_or_not_it_is_supported(report):
    assert [d.id for d in report.dimensions] == list(DIMENSION_LABELS)
    assert report.dimensions_total == 10


def test_a_measured_dimension_names_the_metric_behind_it(report):
    repetition = next(d for d in report.dimensions if d.id == 'repetition')
    assert repetition.evidence == 'measured'
    assert repetition.source_features
    source = repetition.source_features[0]
    assert source.id == 'periodicity'
    assert 'self-similarity' in source.method


def test_proxies_are_never_graded_as_measured(report):
    for name in ('polyphony', 'genre_style'):
        dimension = next(d for d in report.dimensions if d.id == name)
        assert dimension.evidence == 'proxy'
        assert dimension.grade in ('proxy', 'proxy_clamped')


def test_the_lowest_confidence_dimension_is_graded_as_clamped(report):
    timbral = next(d for d in report.dimensions if d.id == 'genre_style')
    assert timbral.grade == 'proxy_clamped'
    assert timbral.travel is not None and timbral.travel < 0.6
    assert all(datum.clamped for datum in timbral.datums)


def test_travel_matches_the_confidence_clamp(report):
    for dimension in report.dimensions:
        if not dimension.present or dimension.confidence is None:
            continue
        expected = min(1.0, dimension.confidence / 0.75)
        assert dimension.travel == pytest.approx(expected)
        for datum in dimension.datums:
            assert datum.travel == pytest.approx(expected)


def test_reach_is_counted_from_the_elements_that_reference_the_datum(report):
    for dimension in report.dimensions:
        assert dimension.element_count == sum(d.element_count for d in dimension.datums)


def test_a_dimension_that_moves_nothing_is_not_graded_strong(report):
    for dimension in report.dimensions:
        if dimension.grade == 'strong':
            assert dimension.element_count >= 20, dimension.id


def test_every_datum_reports_its_declared_range_and_where_it_landed(report):
    for dimension in report.dimensions:
        for datum in dimension.datums:
            assert datum.range_low != datum.range_high
            assert 0.0 <= datum.applied_position <= 1.0
            assert datum.label and datum.reason


def test_coverage_is_reported_both_ways(report):
    assert report.variable_coverage > report.coverage
    assert report.variable_coverage == pytest.approx(1.0)
    assert report.datum_count > report.variable_datum_count


def test_tectonic_constants_are_listed_separately_from_the_dimensions(report):
    assert report.constants
    constant_ids = {constant.id for constant in report.constants}
    driven_ids = {datum.id for dimension in report.dimensions
                  for datum in dimension.datums}
    assert not (constant_ids & driven_ids)


def test_the_report_carries_the_run_limitations(report):
    text = ' '.join(report.limitations)
    assert 'Gravity only' in text
    assert 'professional_review_required' in text


def test_a_shortened_score_grades_the_missing_dimensions_unsupported(features):
    trimmed = features.model_copy(update={
        name: None for name in
        ('periodicity', 'timbre_variation', 'dynamic_range_db',
         'novelty_peak_rate_per_min', 'spectral_contrast_db', 'harmonic_ratio',
         'spectral_flatness', 'zero_crossing_rate')})
    short_score = compile_architectural_score(trimmed)
    model = compile_building_model_v3(trimmed, short_score)
    short_report = compile_translation_report(trimmed, short_score, model)

    assert short_report.dimensions_emitted == 4
    unsupported = [d for d in short_report.dimensions if d.grade == 'unsupported']
    assert {d.id for d in unsupported} == {
        'repetition', 'variation', 'hierarchy', 'interruption', 'polyphony',
        'genre_style'}
    for dimension in unsupported:
        assert not dimension.datums
        assert dimension.element_count == 0
        assert 'design fixtures' in dimension.note
    assert short_report.variable_coverage < 1.0
