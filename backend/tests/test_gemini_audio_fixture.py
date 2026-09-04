from pathlib import Path

from backend.app.audio import extract_audio_features
from backend.app.compiler import compile_building_model
from backend.app.mapping_report import compile_mapping_report
from backend.app.score import compile_architectural_score


FIXTURE = Path(__file__).parents[2] / "fixtures" / "audio" / "gemini_music_to_architecture_44s.mp3"


def test_gemini_music_fixture_runs_full_pipeline() -> None:
    features = extract_audio_features(FIXTURE, FIXTURE.name)
    score = compile_architectural_score(features)
    model = compile_building_model(features, score)
    report = compile_mapping_report(features, score, model)

    assert 43.0 < features.provenance.duration_seconds < 45.0
    assert all(0.0 <= dimension.value <= 1.0 for dimension in score.dimensions)
    assert model.elements
    assert all(element.score_bindings for element in model.elements)
    assert all(check.status != "fail" for check in model.validation)
    assert report.coverage_ratio == 1.0
    assert len(report.entries) == 7
    assert any(entry.extraction_method == "inferred" for entry in report.entries)
