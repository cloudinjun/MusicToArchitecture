from backend.app.compiler import compile_building_model
from backend.app.integration import compile_facade_host_handoff, compile_pipeline_manifest
from backend.app.mapping_report import compile_mapping_report
from backend.app.models import (
    AudioFeatures,
    AudioProvenance,
    MetricValue,
    ModelAsset,
    SegmentFeatures,
)
from backend.app.score import compile_architectural_score


def features() -> AudioFeatures:
    def metric(value: float, normalized: float, unit: str) -> MetricValue:
        return MetricValue(
            value=value,
            normalized=normalized,
            unit=unit,
            method='fixture',
            confidence=0.9,
        )

    return AudioFeatures(
        provenance=AudioProvenance(
            filename='fixture.mp3',
            sha256='b' * 64,
            duration_seconds=12,
            sample_rate_hz=22050,
            channels=1,
            extractor='fixture',
            extractor_version='1',
        ),
        tempo_bpm=metric(120, 0.5, 'bpm'),
        rms_energy=metric(0.1, 0.45, 'rms'),
        onset_density_hz=metric(2.2, 0.4, 'onsets_per_second'),
        spectral_centroid_hz=metric(2200, 0.38, 'hz'),
        segments=[
            SegmentFeatures(
                id=f'segment-{index:02d}',
                start_seconds=index * 2,
                end_seconds=(index + 1) * 2,
                rms_energy=0.1,
                onset_density_hz=2.2,
                spectral_centroid_hz=2200,
            )
            for index in range(6)
        ],
    )


def model_asset() -> ModelAsset:
    return ModelAsset(
        asset_url='/models/generated/fixture.glb',
        manifest_url='/models/generated/fixture.manifest.json',
        native_blend_path='blender/generated/fixture.blend',
        scene_state_path='artifacts/native_models/generated/fixture.scene.json',
        asset_sha256='1' * 64,
        manifest_sha256='2' * 64,
        native_blend_sha256='3' * 64,
        scene_state_sha256='4' * 64,
        semantic_layers=[
            'program_massing', 'facade', 'columns', 'beams', 'slabs',
            'foundations', 'bracing', 'cores', 'interior_sequence',
            'site', 'site_context', 'context_tree',
            'context_vehicle', 'context_person',
        ],
    )


def test_facade_bridge_exposes_hosts_and_preserves_unknown_score_dimensions() -> None:
    source = features()
    score = compile_architectural_score(source)
    model = compile_building_model(source, score)
    handoff = compile_facade_host_handoff(score, model)

    massings = [element for element in model.elements if element.kind == 'massing']
    expected_host_ids = {
        f"host-{element.id}-{face}"
        for element in massings for face in element.exterior_faces
    }
    massing_ids = {element.id for element in massings if element.exterior_faces}
    assert {host.id for host in handoff.host_surfaces} == expected_host_ids
    assert len({host.id for host in handoff.host_surfaces}) == len(handoff.host_surfaces)
    assert {host.source_element_id for host in handoff.host_surfaces} == massing_ids
    assert {host.orientation for host in handoff.host_surfaces} == {
        'north', 'south', 'east', 'west'
    }

    dimensions = {dimension.id: dimension for dimension in handoff.score_dimensions}
    assert len(dimensions) == 10
    assert {key for key, value in dimensions.items() if value.status == 'known'} == {
        'tempo_of_change', 'tension_release', 'density', 'continuity'
    }
    assert all(
        dimension.value is None and dimension.reason
        for dimension in dimensions.values()
        if dimension.status == 'unknown'
    )
    assert handoff.ready_for_candidate_planning is True
    assert handoff.ready_for_geometry_handoff is True
    assert {gate.id: gate.status for gate in handoff.gates}[
        'FACADE_GRAMMAR_SELECTION'
    ] == 'pass'


def test_pipeline_manifest_is_deterministic_and_keeps_preview_authority_bounded() -> None:
    source = features()
    score = compile_architectural_score(source)
    model = compile_building_model(source, score)
    report = compile_mapping_report(source, score, model)
    handoff = compile_facade_host_handoff(score, model)
    asset = model_asset()

    first = compile_pipeline_manifest(source, score, model, report, handoff, asset)
    second = compile_pipeline_manifest(source, score, model, report, handoff, asset)
    assert first == second
    assert first.overall_status == 'preview_ready'
    assert first.accepted_state.status == 'blocked'
    assert first.accepted_state.authority_owner == 'rhino'

    stages = {stage.id: stage for stage in first.stages}
    assert stages['facade_candidate_plan'].status == 'pass'
    assert not stages['facade_candidate_plan'].blocked_by
    assert stages['rhino_acceptance'].status == 'blocked'
    assert stages['blender_web_preview'].status == 'pass'
    assert stages['blender_web_preview'].authority == 'presentation_only'

    artifacts = {artifact.id: artifact for artifact in first.artifacts}
    assert artifacts['building-model'].authority == 'candidate'
    assert artifacts['facade-host-handoff'].authority == 'preview_only'
    assert artifacts['blender-glb'].sha256 == asset.asset_sha256
    assert artifacts['rhino-accepted-geometry'].status == 'blocked'
    assert all(
        len(artifact.sha256) == 64
        for artifact in first.artifacts
        if artifact.status == 'available'
    )
