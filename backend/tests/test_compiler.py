from backend.app.compiler import compile_building_model
from backend.app.mapping_report import compile_mapping_report
from backend.app.models import AudioFeatures, AudioProvenance, MetricValue, SegmentFeatures
from backend.app.score import compile_architectural_score


def features(tempo: float = 0.5) -> AudioFeatures:
    metric = lambda value, normalized, unit: MetricValue(
        value=value, normalized=normalized, unit=unit, method="fixture", confidence=0.9
    )
    return AudioFeatures(
        provenance=AudioProvenance(
            filename="fixture.mp3", sha256="a" * 64, duration_seconds=12,
            sample_rate_hz=22050, channels=1, extractor="fixture", extractor_version="1",
        ),
        tempo_bpm=metric(120, tempo, "bpm"),
        rms_energy=metric(0.1, 0.45, "rms"),
        onset_density_hz=metric(2.2, 0.4, "onsets_per_second"),
        spectral_centroid_hz=metric(2200, 0.38, "hz"),
        segments=[
            SegmentFeatures(
                id=f"segment-{index:02d}", start_seconds=index * 2,
                end_seconds=(index + 1) * 2, rms_energy=0.1,
                onset_density_hz=2.2, spectral_centroid_hz=2200,
            )
            for index in range(6)
        ],
    )


def test_score_has_four_bounded_dimensions() -> None:
    score = compile_architectural_score(features())
    assert len(score.dimensions) == 4
    assert all(0 <= dimension.value <= 1 for dimension in score.dimensions)
    assert all(rule.source_dimension and rule.target_parameter for rule in score.mapping_rules)
    assert all(len(rule.output_range) == 2 and rule.priority >= 0 and rule.owner for rule in score.mapping_rules)


def test_model_is_valid_deterministic_and_traceable() -> None:
    source = features()
    score = compile_architectural_score(source)
    first = compile_building_model(source, score)
    second = compile_building_model(source, score)
    assert first == second
    assert all(check.status != "fail" for check in first.validation)
    assert {check.id for check in first.validation if check.status == "warning"} == {
        "PROGRAM_CODE_PROFILE", "STRUCTURAL_ENGINEERING_REVIEW"
    }
    assert all(element.score_bindings for element in first.elements)
    assert {element.category for element in first.elements} == {
        "public", "private", "circulation", "service"
    }
    assert first.parameters.room_count == 21
    assert {element.space_type for element in first.elements if element.kind == "massing"} >= {
        "adult_reading", "open_stacks", "public_restroom", "staff_restroom",
        "janitor", "mechanical_room", "loading_receiving",
    }
    assert {element.subsystem for element in first.elements} >= {
        "program_massing", "columns", "beams", "slabs", "foundations",
        "bracing", "cores", "facade", "interior_sequence",
    }


def test_tempo_changes_episode_count_without_changing_grid() -> None:
    slow = compile_building_model(features(0.0), compile_architectural_score(features(0.0)))
    fast = compile_building_model(features(1.0), compile_architectural_score(features(1.0)))
    assert slow.parameters.module_count < fast.parameters.module_count
    assert slow.grid == fast.grid


def test_mapping_report_resolves_shared_score_to_actual_elements() -> None:
    source = features()
    score = compile_architectural_score(source)
    model = compile_building_model(source, score)
    first = compile_mapping_report(source, score, model)
    second = compile_mapping_report(source, score, model)

    assert first == second
    assert len(first.entries) == 7
    assert set(first.automated_dimensions) == {
        "tempo_of_change", "tension_release", "density", "continuity"
    }
    assert first.covered_element_count == first.total_element_count == len(model.elements)
    assert first.coverage_ratio == 1.0
    assert {entry.architectural_target for entry in first.entries} == {
        "sequence.episode_count",
        "program.reading_height",
        "structure.bay_spacing",
        "facade.submodule_count",
        "program.service_depth",
        "circulation.spine_width",
        "facade.datum_offset",
    }
    continuity_entries = [
        entry for entry in first.entries if entry.shared_dimension == "continuity"
    ]
    assert all(entry.extraction_method == "inferred" for entry in continuity_entries)
    assert all(entry.affected_element_ids for entry in first.entries)
