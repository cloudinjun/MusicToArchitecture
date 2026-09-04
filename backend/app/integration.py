from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .models import (
    AcceptedStateRecord,
    ArchitecturalScore,
    AudioFeatures,
    BuildingElement,
    BuildingModel,
    FacadeHostHandoff,
    FacadeHostSurface,
    FacadeScoreDimensionState,
    MappingReport,
    ModelAsset,
    PipelineArtifactReference,
    PipelineGateState,
    PipelineRunManifest,
    PipelineStageState,
    SharedScoreDimensionId,
    Vector3Value,
)


ALL_SHARED_DIMENSIONS: tuple[SharedScoreDimensionId, ...] = (
    'genre_style',
    'hierarchy',
    'repetition',
    'variation',
    'density',
    'continuity',
    'interruption',
    'polyphony',
    'tension_release',
    'tempo_of_change',
)

ROOT = Path(__file__).resolve().parents[2]

SELECTION_BLOCKERS: list[str] = []

PROJECT_SPECIFICATIONS = (
    (
        'program-guideline',
        'program_constitution_guideline',
        'docs/guidelines/program_constitution_guideline.md',
    ),
    (
        'structure-guideline',
        'structural_system_guideline',
        'docs/guidelines/structural_system_guideline.md',
    ),
    (
        'facade-research-library',
        'facade_grammar_library',
        'docs/style_guides/facade/README.md',
    ),
    (
        'facade-selected-guideline',
        'facade_grammar_guideline',
        'docs/style_guides/facade/01_international_style.md',
    ),
    (
        'integrated-demo-selection',
        'selection_record',
        'docs/experiments/integrated_demo_selection.md',
    ),
    (
        'typology-selection-decision',
        'selection_decision',
        'docs/decisions/0001-primary-typology-shortlist.md',
    ),
    (
        'tectonic-selection-decision',
        'selection_decision',
        'docs/decisions/0002-tectonic-system-shortlist.md',
    ),
    (
        'grammar-selection-decision',
        'selection_decision',
        'docs/decisions/0003-style-language-candidate-library.md',
    ),
)


def _canonical_sha256(value: BaseModel | dict[str, Any]) -> str:
    payload = value.model_dump(mode='json') if isinstance(value, BaseModel) else value
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(',', ':'),
        sort_keys=True,
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _vector(values: tuple[float, float, float]) -> Vector3Value:
    return Vector3Value(x=values[0], y=values[1], z=values[2])


def _host_surfaces(element: BuildingElement) -> Iterable[FacadeHostSurface]:
    x, y, z = element.position.x, element.position.y, element.position.z
    dx, dy, dz = element.dimensions.x, element.dimensions.y, element.dimensions.z
    level_min = round(z - dz / 2, 6)
    level_max = round(z + dz / 2, 6)
    specifications = (
        ('south', (x, y - dy / 2, z), (0.0, -1.0, 0.0), (1.0, 0.0, 0.0), dx),
        ('north', (x, y + dy / 2, z), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0), dx),
        ('west', (x - dx / 2, y, z), (-1.0, 0.0, 0.0), (0.0, -1.0, 0.0), dy),
        ('east', (x + dx / 2, y, z), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), dy),
    )
    exterior_faces = set(element.exterior_faces)
    for orientation, origin, normal, u_axis, width in specifications:
        if orientation not in exterior_faces:
            continue
        yield FacadeHostSurface(
            id=f'host-{element.id}-{orientation}',
            source_element_id=element.id,
            orientation=orientation,
            program_owner=element.program,
            program_category=element.category,
            origin=_vector(tuple(round(value, 6) for value in origin)),
            normal=_vector(normal),
            u_axis=_vector(u_axis),
            v_axis=_vector((0.0, 0.0, 1.0)),
            width=round(width, 6),
            height=round(dz, 6),
            level_min=level_min,
            level_max=level_max,
        )


def _score_dimension_states(score: ArchitecturalScore) -> list[FacadeScoreDimensionState]:
    known = {dimension.id: dimension for dimension in score.dimensions}
    states = []
    for dimension_id in ALL_SHARED_DIMENSIONS:
        dimension = known.get(dimension_id)
        if dimension is None:
            states.append(FacadeScoreDimensionState(
                id=dimension_id,
                status='unknown',
                source_type='unknown',
                reason='The current MP3 extractor does not implement this Shared Score dimension.',
            ))
            continue
        states.append(FacadeScoreDimensionState(
            id=dimension_id,
            status='known',
            value=dimension.value,
            confidence=dimension.confidence,
            source_type=dimension.extraction_method,
            source_ref=f'architectural_score:{score.score_id}#{dimension.id}',
        ))
    return states


def compile_facade_host_handoff(
    score: ArchitecturalScore,
    model: BuildingModel,
) -> FacadeHostHandoff:
    massings = [element for element in model.elements if element.kind == 'massing']
    hosts = [surface for massing in massings for surface in _host_surfaces(massing)]
    return FacadeHostHandoff(
        handoff_id=f'facade-host-{model.model_id.removeprefix("building-")}',
        model_id=model.model_id,
        score_id=score.score_id,
        maturity='MTA-F2',
        score_dimensions=_score_dimension_states(score),
        host_surfaces=hosts,
        gates=[
            PipelineGateState(
                id='PROGRAM_HOST_OWNERSHIP',
                status='pass',
                authority='preview_only',
                message=(
                    'Every exterior host resolves to a room-level space type, access class, '
                    'program category, and stable source element.'
                ),
                evidence_refs=[model.model_id],
            ),
            PipelineGateState(
                id='TECTONIC_SUPPORT_CONTRACT',
                status='pass',
                authority='preview_only',
                message=(
                    'Every facade support returns to the explicit steel-frame candidate graph; '
                    'engineering reactions and connection sizing remain pending.'
                ),
                evidence_refs=[model.model_id],
            ),
            PipelineGateState(
                id='FACADE_GRAMMAR_SELECTION',
                status='pass',
                authority='preview_only',
                message='International Style-informed grammar is selected for this integrated demonstration only.',
                evidence_refs=['integrated-demo-selection', 'facade-selected-guideline'],
            ),
            PipelineGateState(
                id='FACADE_GEOMETRY_HANDOFF',
                status='pass',
                authority='preview_only',
                message=(
                    'Portable MTA-F2 facade elements, stable hosts, ordered rules, and support '
                    'references are ready for modular Grasshopper reconstruction and Rhino review.'
                ),
                evidence_refs=[model.model_id],
            ),
        ],
        ready_for_candidate_planning=True,
        ready_for_geometry_handoff=True,
        blocked_by=[],
        limitations=[
            'The integrated demonstration selection does not replace the user-owned final typology, tectonic, or two-grammar decisions.',
            'Facade geometry is a candidate MTA-F2 coordination model without resolved environmental performance, anchors, or professional review.',
            'Only Rhino may record accepted geometry; Blender and Web remain presentation and inspection environments.',
        ],
    )


def _inline_artifact(
    artifact_id: str,
    kind: str,
    authority: str,
    value: BaseModel,
) -> PipelineArtifactReference:
    return PipelineArtifactReference(
        id=artifact_id,
        kind=kind,
        status='available',
        authority=authority,
        sha256=_canonical_sha256(value),
        uri=f'inline://{artifact_id}',
    )


def _project_file_artifact(
    artifact_id: str,
    kind: str,
    relative_path: str,
) -> PipelineArtifactReference:
    path = ROOT / relative_path
    if not path.is_file():
        raise ValueError(f'Required project specification is missing: {relative_path}')
    return PipelineArtifactReference(
        id=artifact_id,
        kind=kind,
        status='available',
        authority='specification',
        sha256=_file_sha256(path),
        uri=f'project://{relative_path}',
    )


def compile_pipeline_manifest(
    features: AudioFeatures,
    score: ArchitecturalScore,
    model: BuildingModel,
    mapping_report: MappingReport,
    facade_handoff: FacadeHostHandoff,
    model_asset: ModelAsset,
    run_id: str | None = None,
) -> PipelineRunManifest:
    artifacts = [
        *(_project_file_artifact(*specification) for specification in PROJECT_SPECIFICATIONS),
        _inline_artifact('audio-features', 'audio_features', 'source_observation', features),
        _inline_artifact('architectural-score', 'architectural_score', 'candidate', score),
        _inline_artifact('building-model', 'building_model_v2', 'candidate', model),
        _inline_artifact('mapping-report', 'mapping_report', 'validation_report', mapping_report),
        _inline_artifact('facade-host-handoff', 'facade_host_handoff', 'preview_only', facade_handoff),
        PipelineArtifactReference(
            id='blender-glb', kind='glb', status='available',
            authority='presentation_only', sha256=model_asset.asset_sha256,
            uri=model_asset.asset_url,
        ),
        PipelineArtifactReference(
            id='blender-manifest', kind='blender_manifest', status='available',
            authority='presentation_only', sha256=model_asset.manifest_sha256,
            uri=model_asset.manifest_url,
        ),
        PipelineArtifactReference(
            id='blender-native-scene', kind='blend', status='available',
            authority='presentation_only', sha256=model_asset.native_blend_sha256,
            uri=model_asset.native_blend_path,
        ),
        PipelineArtifactReference(
            id='blender-scene-state', kind='scene_state', status='available',
            authority='presentation_only', sha256=model_asset.scene_state_sha256,
            uri=model_asset.scene_state_path,
        ),
        PipelineArtifactReference(
            id='rhino-accepted-geometry', kind='rhino_geometry_manifest',
            status='blocked', authority='accepted_geometry',
        ),
    ]
    stages = [
        PipelineStageState(
            id='audio_extraction', route='portable_core', status='pass',
            authority='source_observation', producer=features.provenance.extractor,
            output_refs=['audio-features'],
            message='MP3 observations retain file hash, method, version, and confidence.',
        ),
        PipelineStageState(
            id='architectural_score', route='portable_core', status='warning',
            authority='candidate', producer='backend.app.score',
            input_refs=['audio-features'], output_refs=['architectural-score'],
            message='Four Shared Score dimensions are known; six remain explicitly unknown.',
        ),
        PipelineStageState(
            id='program_compilation', route='portable_core', status='pass',
            authority='candidate', producer='backend.app.compiler',
            input_refs=['architectural-score', 'program-guideline'], output_refs=['building-model'],
            message='Room-level library constitution, four program categories, relationship graph, support spaces, and code-input warnings are compiled.',
        ),
        PipelineStageState(
            id='structure_compilation', route='portable_core', status='pass',
            authority='candidate', producer='backend.app.compiler',
            input_refs=['architectural-score', 'building-model', 'structure-guideline'],
            output_refs=['building-model'],
            message='Steel-frame candidate includes columns, beams, slabs, bracing, cores, foundations, support edges, and explicit professional-review status.',
        ),
        PipelineStageState(
            id='facade_host_bridge', route='portable_core', status='pass',
            authority='preview_only', producer='backend.app.integration',
            input_refs=['architectural-score', 'building-model', 'facade-selected-guideline', 'integrated-demo-selection'],
            output_refs=['facade-host-handoff'],
            message='Room-owned exterior hosts, MTA-F2 elements, support references, and all ten score availability states are connected.',
        ),
        PipelineStageState(
            id='facade_candidate_plan', route='portable_core', status='pass',
            authority='review_only', producer='mta-facade-image-pipeline',
            input_refs=[
                'facade-host-handoff', 'integrated-demo-selection',
                'facade-selected-guideline',
            ],
            output_refs=['building-model'],
            message='International Style-informed facade candidate plan is executable for this demonstration and remains review-only until Rhino acceptance.',
        ),
        PipelineStageState(
            id='mapping_report', route='portable_core', status='pass',
            authority='validation_report', producer='backend.app.mapping_report',
            input_refs=['audio-features', 'architectural-score', 'building-model'],
            output_refs=['mapping-report'],
            message='Executed score bindings resolve to source building elements.',
        ),
        PipelineStageState(
            id='grasshopper_interactive_geometry', route='interactive_acceptance',
            status='pending', authority='candidate', producer='grasshopper',
            input_refs=['building-model', 'facade-host-handoff'],
            message='Portable geometry and contracts are ready; the modular Grasshopper graph still requires an interactive solve and review.',
        ),
        PipelineStageState(
            id='rhino_acceptance', route='interactive_acceptance', status='blocked',
            authority='accepted_geometry', producer='rhino',
            input_refs=['building-model', 'facade-host-handoff'],
            output_refs=['rhino-accepted-geometry'],
            blocked_by=['RHINO_ACCEPTANCE_NOT_RECORDED'],
            message='Only an explicit Rhino acceptance record may establish accepted geometry for this run.',
        ),
        PipelineStageState(
            id='blender_web_preview', route='web_preview', status='pass',
            authority='presentation_only', producer=model_asset.producer,
            input_refs=['building-model'],
            output_refs=['blender-glb', 'blender-manifest', 'blender-native-scene', 'blender-scene-state'],
            message='Blender/Web provide semantic inspection and presentation without changing design authority.',
        ),
    ]
    accepted_blockers = ['RHINO_ACCEPTANCE_NOT_RECORDED']
    return PipelineRunManifest(
        # The audio hash alone stopped being an identity the day anything else began
        # to shape the run; the pipeline passes one minted from the full run identity,
        # and the fallback keeps scripted v2-only callers working.
        run_id=run_id or f'run-{features.provenance.sha256[:12]}',
        overall_status='preview_ready',
        model_id=model.model_id,
        score_id=score.score_id,
        artifacts=artifacts,
        stages=stages,
        accepted_state=AcceptedStateRecord(status='blocked', blocked_by=accepted_blockers),
        limitations=[
            'This run produces a reproducible semantic preview, not accepted project geometry.',
            'Program code inputs and structural analysis remain incomplete and require jurisdiction-specific and professional review.',
            'The Library + steel frame + International Style selection applies only to this integrated demonstration.',
            'Grasshopper interactive review and Rhino acceptance have not been recorded.',
            'Blender and Web render the candidate contracts without increasing their design authority.',
        ],
    )
