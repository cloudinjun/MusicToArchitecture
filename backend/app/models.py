from __future__ import annotations

from typing import Literal

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from .translation_report import TranslationReport


SharedScoreDimensionId = Literal[
    'genre_style', 'hierarchy', 'repetition', 'variation', 'density',
    'continuity', 'interruption', 'polyphony', 'tension_release',
    'tempo_of_change',
]


class Vector3Value(BaseModel):
    x: float
    y: float
    z: float


class MetricValue(BaseModel):
    value: float
    normalized: float = Field(ge=0.0, le=1.0)
    unit: str
    method: str
    confidence: float = Field(ge=0.0, le=1.0)


class SegmentFeatures(BaseModel):
    id: str
    start_seconds: float
    end_seconds: float
    rms_energy: float
    onset_density_hz: float
    spectral_centroid_hz: float


class AudioProvenance(BaseModel):
    filename: str
    sha256: str
    duration_seconds: float
    sample_rate_hz: int
    channels: int
    extractor: str
    extractor_version: str


class AudioFeatures(BaseModel):
    """Measured audio evidence.

    The first four metrics are the MVP set. The rest were added to give the remaining
    six shared score dimensions real evidence instead of a design fixture, and they are
    **optional on purpose**: an artifact produced before they existed must still
    validate, and `score.py` must still be able to emit a shortened score rather than
    inventing values. A missing metric propagates all the way to
    `Datum.provenance='design_fixture'`, where it is visible in the report.
    """

    schema_version: Literal['1.0'] = '1.0'
    provenance: AudioProvenance
    tempo_bpm: MetricValue
    rms_energy: MetricValue
    onset_density_hz: MetricValue
    spectral_centroid_hz: MetricValue
    # --- extended set, optional ---
    periodicity: MetricValue | None = None
    timbre_variation: MetricValue | None = None
    dynamic_range_db: MetricValue | None = None
    novelty_peak_rate_per_min: MetricValue | None = None
    spectral_contrast_db: MetricValue | None = None
    harmonic_ratio: MetricValue | None = None
    spectral_flatness: MetricValue | None = None
    zero_crossing_rate: MetricValue | None = None
    segments: list[SegmentFeatures]


class ScoreDimension(BaseModel):
    id: SharedScoreDimensionId
    value: float = Field(ge=0.0, le=1.0)
    source_feature: str
    extraction_method: Literal['observed', 'inferred', 'model_assisted', 'manual']
    confidence: float = Field(ge=0.0, le=1.0)
    architectural_proposal: str


class MappingRule(BaseModel):
    id: str
    source_dimension: str
    target_parameter: str
    output_range: tuple[float, float]
    direction: Literal['direct', 'inverse']
    priority: int = Field(ge=0)
    owner: Literal['music', 'architecture'] = 'music'


class ArchitecturalScore(BaseModel):
    schema_version: Literal['1.0'] = '1.0'
    score_id: str
    source_audio_sha256: str
    typology: Literal['library'] = 'library'
    tectonic_system: Literal['frame'] = 'frame'
    dimensions: list[ScoreDimension]
    mapping_rules: list[MappingRule]


class ScoreBinding(BaseModel):
    source_dimension: str
    source_value: float
    target_parameter: str
    applied_value: float
    rule_id: str


class BuildingElement(BaseModel):
    id: str
    kind: Literal[
        'massing', 'column', 'beam', 'slab', 'foundation', 'brace', 'core',
        'facade_panel', 'glazing', 'mullion', 'canopy', 'facade_support',
        'interior_floor', 'threshold_frame',
    ]
    semantic_layer: Literal['program', 'circulation', 'structure', 'facade', 'interior']
    subsystem: str
    program: str
    category: Literal['public', 'private', 'circulation', 'service']
    position: Vector3Value
    dimensions: Vector3Value
    rotation: Vector3Value | None = None
    space_type: str | None = None
    access_class: str | None = None
    level_id: str = 'L01'
    material_profile: str | None = None
    host_surface_id: str | None = None
    exterior_faces: list[Literal['north', 'south', 'east', 'west']] = Field(default_factory=list)
    supports: list[str] = Field(default_factory=list)
    supports_elements: list[str] = Field(default_factory=list)
    program_constraints: list[str] = Field(default_factory=list)
    rule_refs: list[str] = Field(default_factory=list)
    reason: str | None = None
    authority: Literal['generated_candidate', 'preview_only'] = 'generated_candidate'
    validation_status: Literal[
        'geometry_valid', 'rule_checked', 'code_inputs_incomplete',
        'professional_review_required',
    ] = 'geometry_valid'
    score_bindings: list[ScoreBinding] = Field(default_factory=list)


class ProgramRelation(BaseModel):
    id: str
    source_id: str
    target_id: str
    relation: Literal[
        'must_connect', 'preferred_near', 'must_separate', 'service_connect',
        'public_connect', 'accessible_connect', 'visual_connect',
        'daylight_edge', 'column_exclusion',
    ]
    rule_id: str
    status: Literal['pass', 'warning', 'fail']
    reason: str


class StructuralProfile(BaseModel):
    id: str
    tectonic_family: Literal['frame'] = 'frame'
    material_system: Literal['structural_steel'] = 'structural_steel'
    gravity_system: str
    lateral_system: str
    foundation_system: str
    code_profile_status: Literal['unresolved'] = 'unresolved'
    authority: Literal['candidate'] = 'candidate'
    limitations: list[str]


class FacadeProfile(BaseModel):
    id: str
    grammar_id: Literal['international_style_informed'] = 'international_style_informed'
    qualified_name: str
    maturity: Literal['MTA-F2'] = 'MTA-F2'
    assembly_system: str
    authority: Literal['candidate'] = 'candidate'
    limitations: list[str]


class SiteModel(BaseModel):
    width: float
    length: float
    max_height: float


class GridModel(BaseModel):
    spacing_x: float
    spacing_y: float
    column_size: float


class ValidationCheck(BaseModel):
    id: str
    status: Literal['pass', 'warning', 'fail']
    message: str
    affected_ids: list[str] = Field(default_factory=list)


class GenerationParameters(BaseModel):
    module_count: int
    room_count: int
    bay_spacing: float
    module_gap: float
    primary_height: float
    primary_depth: float
    visual_continuity: float
    facade_submodule_count: int
    circulation_spine_width: float


class BuildingModel(BaseModel):
    schema_version: Literal['2.0'] = '2.0'
    model_id: str
    score_id: str
    typology: str
    tectonic_system: str
    units: Literal['meters'] = 'meters'
    coordinate_system: Literal['right_handed_z_up'] = 'right_handed_z_up'
    site: SiteModel
    grid: GridModel
    parameters: GenerationParameters
    structural_profile: StructuralProfile
    facade_profile: FacadeProfile
    program_relations: list[ProgramRelation]
    interior_sequence: list[str]
    elements: list[BuildingElement]
    validation: list[ValidationCheck]


class FacadeScoreDimensionState(BaseModel):
    id: SharedScoreDimensionId
    status: Literal['known', 'unknown']
    value: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_type: Literal[
        'observed', 'inferred', 'model_assisted', 'manual', 'design_fixture',
        'unknown',
    ]
    source_ref: str | None = None
    reason: str | None = None
    required_for_handoff: bool = False


class FacadeHostSurface(BaseModel):
    id: str
    source_element_id: str
    source_element_kind: Literal['massing'] = 'massing'
    orientation: Literal['north', 'south', 'east', 'west']
    program_owner: str
    program_category: Literal['public', 'private', 'circulation', 'service']
    origin: Vector3Value
    normal: Vector3Value
    u_axis: Vector3Value
    v_axis: Vector3Value
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    level_min: float
    level_max: float
    authority_status: Literal['preview_host'] = 'preview_host'


class PipelineGateState(BaseModel):
    id: str
    status: Literal['pass', 'warning', 'fail', 'blocked', 'pending', 'not_applicable']
    authority: Literal[
        'source_observation', 'candidate', 'preview_only', 'review_only',
        'accepted_geometry', 'validation_report',
    ]
    message: str
    blocked_by: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class FacadeHostHandoff(BaseModel):
    schema_version: Literal['mta.facade_host_handoff/1.0'] = 'mta.facade_host_handoff/1.0'
    handoff_id: str
    model_id: str
    score_id: str
    authority_status: Literal['preview_only'] = 'preview_only'
    maturity: Literal['MTA-F0', 'MTA-F1', 'MTA-F2'] = 'MTA-F0'
    score_dimensions: list[FacadeScoreDimensionState]
    host_surfaces: list[FacadeHostSurface]
    gates: list[PipelineGateState]
    ready_for_candidate_planning: bool = False
    ready_for_geometry_handoff: bool = False
    blocked_by: list[str]
    limitations: list[str]


class MappingReportEntry(BaseModel):
    id: str
    rule_id: str
    music_feature: str
    music_feature_label: str
    music_value: float
    music_normalized: float = Field(ge=0.0, le=1.0)
    music_unit: str
    music_method: str
    music_confidence: float = Field(ge=0.0, le=1.0)
    shared_dimension: str
    shared_dimension_label: str
    score_value: float = Field(ge=0.0, le=1.0)
    extraction_method: Literal['observed', 'inferred', 'model_assisted', 'manual']
    score_confidence: float = Field(ge=0.0, le=1.0)
    architectural_proposal: str
    architectural_target: str
    architectural_target_label: str
    mapping_direction: Literal['direct', 'inverse']
    declared_output_range: tuple[float, float]
    applied_min: float
    applied_max: float
    applied_unit: str
    outcome: str
    negotiation: str
    affected_element_ids: list[str]
    affected_element_kinds: list[str]
    affected_programs: list[str]


class MappingReport(BaseModel):
    schema_version: Literal['1.0'] = '1.0'
    report_id: str
    score_id: str
    model_id: str
    source_audio_filename: str
    typology: str
    tectonic_system: str
    automated_dimensions: list[str]
    unsupported_dimensions: list[str]
    covered_element_count: int
    total_element_count: int
    coverage_ratio: float = Field(ge=0.0, le=1.0)
    entries: list[MappingReportEntry]
    limitations: list[str]


class ModelAsset(BaseModel):
    producer: Literal['blender_headless_5'] = 'blender_headless_5'
    format: Literal['glb'] = 'glb'
    asset_url: str
    manifest_url: str
    native_blend_path: str
    scene_state_path: str
    asset_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    manifest_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    native_blend_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    scene_state_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    authority_status: Literal['presentation_only'] = 'presentation_only'
    semantic_layers: list[str]


class PipelineArtifactReference(BaseModel):
    id: str
    kind: str
    status: Literal['available', 'blocked', 'pending']
    authority: Literal[
        'source_observation', 'candidate', 'preview_only', 'review_only',
        'accepted_geometry', 'presentation_only', 'validation_report',
        'specification',
    ]
    sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    uri: str | None = None


class PipelineStageState(BaseModel):
    id: str
    route: Literal['portable_core', 'interactive_acceptance', 'web_preview']
    status: Literal['pass', 'warning', 'fail', 'blocked', 'pending', 'not_applicable']
    authority: Literal[
        'source_observation', 'candidate', 'preview_only', 'review_only',
        'accepted_geometry', 'presentation_only', 'validation_report',
    ]
    producer: str
    input_refs: list[str] = Field(default_factory=list)
    output_refs: list[str] = Field(default_factory=list)
    blocked_by: list[str] = Field(default_factory=list)
    message: str


class AcceptedStateRecord(BaseModel):
    status: Literal['blocked', 'pending', 'accepted']
    authority_owner: Literal['rhino'] = 'rhino'
    accepted_model_id: str | None = None
    geometry_manifest_ref: str | None = None
    blocked_by: list[str] = Field(default_factory=list)


class PipelineRunManifest(BaseModel):
    schema_version: Literal['mta.pipeline_run_manifest/1.0'] = 'mta.pipeline_run_manifest/1.0'
    run_id: str
    overall_status: Literal['preview_ready', 'blocked', 'accepted']
    model_id: str
    score_id: str
    artifacts: list[PipelineArtifactReference]
    stages: list[PipelineStageState]
    accepted_state: AcceptedStateRecord
    limitations: list[str]


class ModelAssetV3(BaseModel):
    """The member-level GLB. Presentation only, like its v2 sibling."""

    producer: Literal['blender_headless_5_v3'] = 'blender_headless_5_v3'
    format: Literal['glb'] = 'glb'
    asset_schema_version: Literal['3.0'] = '3.0'
    asset_url: str
    manifest_url: str
    native_blend_path: str
    model_json_path: str
    asset_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    manifest_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    element_count: int
    merged_object_count: int
    face_count: int
    semantic_layers: list[str]
    renders: list[str] = Field(default_factory=list)
    authority_status: Literal['presentation_only'] = 'presentation_only'


class DrawingOnSheetRef(BaseModel):
    """One drawing placed on a sheet, with the audit that belongs to that cut."""

    id: str
    title: str
    kind: Literal['plan', 'section', 'elevation']
    scale: str
    subtitle: str = ''
    content_mm: list[float] = Field(default_factory=list)
    marks: int = 0
    elements_cut: int = 0
    elements_drawn: int = 0
    omitted_by_scale: dict[str, int] = Field(default_factory=dict)


class DrawingSheetRef(BaseModel):
    """One issued sheet, and where the client can fetch it.

    The audit numbers ride along with the reference rather than sitting in a separate
    index, because a sheet a reader can open without being told what it left out is a
    picture rather than a drawing.
    """

    id: str
    title: str
    kind: Literal['plan', 'section', 'elevation', 'cover']
    scale: str
    subtitle: str = ''
    url: str
    # The paper the sheet is issued on and its number in the set. Both come from the
    # set's layout, so every sheet of one issue shares a paper size.
    sheet_number: str = ''
    paper: str = ''
    sheet_mm: list[float] = Field(default_factory=list)
    content_mm: list[float] = Field(default_factory=list)
    marks: int = 0
    elements_cut: int = 0
    elements_drawn: int = 0
    omitted_by_scale: dict[str, int] = Field(default_factory=dict)
    # The drawings composed on this sheet. A sheet with two sections carries two;
    # the cover carries none.
    drawings: list[DrawingOnSheetRef] = Field(default_factory=list)


class RenderRef(BaseModel):
    """A Blender still from the run. Presentation only, like everything Blender makes."""

    id: str
    filename: str
    url: str
    authority_status: Literal['presentation_only'] = 'presentation_only'


class RunSummary(BaseModel):
    """One stored run, as the run library lists it."""

    run_id: str
    model_id: str
    score_id: str
    generated_at: str
    source_filename: str
    typology: str
    massing_id: str
    structural_system_id: str
    facade_grammar_id: str
    element_count: int
    variable_coverage: float | None = None
    failed_checks: int = 0
    unevaluated_checks: int = 0
    overall_status: str


class GenerationResponse(BaseModel):
    run_id: str = ''
    generated_at: str = ''
    compiler_source_sha256: str = ''
    elapsed_seconds: float | None = None
    audio_features: AudioFeatures
    architectural_score: ArchitecturalScore
    building_model: BuildingModel
    mapping_report: MappingReport
    facade_handoff: FacadeHostHandoff
    model_asset: ModelAsset | None
    pipeline_manifest: PipelineRunManifest
    # Schema 3.0 runs in parallel with v2. v2 remains the massing contract the
    # Grasshopper watcher, the facade handoff, and the acceptance manifest already read;
    # v3 is the member-level model the viewport draws. Neither derives from the other,
    # so a v3 failure never blocks the accepted-state chain.
    model_asset_v3: ModelAssetV3 | None = None
    translation_report: 'TranslationReport | None' = None
    datum_coverage: float | None = None
    datum_waiting_on: list[str] = Field(default_factory=list)
    # The drawing set's index: which sheets were issued, what each one cut, and the
    # account of every element as drawn, dropped by scale, or reached by no cut. The
    # sheets themselves are files; this is the record of what they claim, and it
    # travels with the response so a caller can check the set without opening it.
    drawing_index: dict | None = None
    # The same sheets as fetchable references, so a client can display the set rather
    # than only report on it.
    drawing_sheets: list[DrawingSheetRef] = Field(default_factory=list)
    renders: list[RenderRef] = Field(default_factory=list)
    # Everything the schema 3.0 compile decided and checked. Absent only if the v3
    # compile itself failed, which the v2 acceptance chain above survives by design.
    analysis: 'AnalysisBundle | None' = None


# Resolved after import so `translation_report` can reference the model without a cycle.
from .translation_report import TranslationReport  # noqa: E402
from .analysis_bundle import AnalysisBundle  # noqa: E402

GenerationResponse.model_rebuild()
