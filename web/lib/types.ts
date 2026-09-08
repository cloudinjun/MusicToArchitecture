/**
 * The wire contract, mirrored from `backend/app/models.py`, `models_v3.py` and
 * `analysis_bundle.py`.
 *
 * The rule this file follows: a field the backend computes gets a name here, even
 * where the UI does not draw it yet. Half the reports in this project were invisible
 * for months because the response typed four audio features out of twelve, and the
 * page could only show what it could name.
 */

export interface Vector3Value { x: number; y: number; z: number }
export interface Point2Value { x: number; y: number }

export interface MetricValue {
  value: number;
  normalized: number;
  unit: string;
  method: string;
  confidence: number;
}

export interface SegmentFeatures {
  id: string;
  start_seconds: number;
  end_seconds: number;
  rms_energy: number;
  onset_density_hz: number;
  spectral_centroid_hz: number;
}

export interface AudioProvenance {
  filename: string;
  sha256: string;
  duration_seconds: number;
  sample_rate_hz: number;
  channels: number;
  extractor: string;
  extractor_version: string;
}

/** Twelve measured features and six temporal segments. All of them, not the first four. */
/** A recording the client can decode and play: the upload itself, or the copy a run kept. */
export interface AudioSource {
  url: string;
  name: string;
}

export interface AudioFeatures {
  schema_version?: string;
  provenance: AudioProvenance;
  tempo_bpm: MetricValue;
  rms_energy: MetricValue;
  onset_density_hz: MetricValue;
  spectral_centroid_hz: MetricValue;
  periodicity: MetricValue;
  timbre_variation: MetricValue;
  dynamic_range_db: MetricValue;
  novelty_peak_rate_per_min: MetricValue;
  spectral_contrast_db: MetricValue;
  harmonic_ratio: MetricValue;
  spectral_flatness: MetricValue;
  zero_crossing_rate: MetricValue;
  segments: SegmentFeatures[];
}

export type SharedScoreDimensionId =
  | 'genre_style' | 'hierarchy' | 'repetition' | 'variation' | 'density'
  | 'continuity' | 'interruption' | 'polyphony' | 'tension_release'
  | 'tempo_of_change';

export type ExtractionMethod = 'observed' | 'inferred' | 'model_assisted' | 'manual';

export interface ScoreDimension {
  id: SharedScoreDimensionId;
  value: number;
  source_feature: string;
  extraction_method: ExtractionMethod;
  confidence: number;
  architectural_proposal: string;
}

export interface MappingRule {
  id: string;
  source_dimension: string;
  target_parameter: string;
  output_range: [number, number];
  direction: 'direct' | 'inverse';
  priority: number;
  owner: string;
}

export interface ArchitecturalScore {
  schema_version: string;
  score_id: string;
  source_audio_sha256: string;
  typology: string;
  tectonic_system: string;
  dimensions: ScoreDimension[];
  mapping_rules: MappingRule[];
}

export interface ScoreBinding {
  source_dimension: string;
  source_value: number;
  target_parameter: string;
  applied_value: number;
  rule_id: string;
}

export type ProgramCategory = 'public' | 'private' | 'circulation' | 'service';

export interface BuildingElement {
  id: string;
  kind: string;
  semantic_layer: 'program' | 'circulation' | 'structure' | 'facade' | 'interior';
  subsystem: string;
  program: string;
  category: ProgramCategory;
  position: Vector3Value;
  dimensions: Vector3Value;
  rotation?: Vector3Value | null;
  space_type?: string | null;
  access_class?: string | null;
  level_id?: string | null;
  material_profile?: string | null;
  host_surface_id?: string | null;
  exterior_faces?: string[];
  supports?: string[];
  rule_refs?: string[];
  reason?: string | null;
  authority?: string | null;
  validation_status?: string | null;
  score_bindings?: ScoreBinding[];
}

export interface ValidationCheck {
  id: string;
  status: 'pass' | 'warning' | 'fail';
  message: string;
  affected_ids?: string[];
}

/** One required adjacency in the v2 brief, and whether the massing honoured it. */
export interface ProgramRelation {
  id: string;
  source_id: string;
  target_id: string;
  relation: string;
  rule_id: string;
  status: 'pass' | 'warning' | 'fail' | string;
  reason: string;
}

/**
 * A declared system candidate on the v2 contract. Fields vary between the structural
 * and facade profiles, so the shape stays open apart from the three every profile
 * carries — including `limitations`, which is the half a reader must not skip.
 */
export interface SystemProfile {
  id: string;
  authority: string;
  limitations: string[];
  [field: string]: string | string[] | undefined;
}

export interface BuildingModel {
  schema_version: string;
  model_id: string;
  score_id?: string;
  typology?: string;
  tectonic_system?: string;
  units: 'meters';
  coordinate_system?: string;
  site?: { width: number; length: number; max_height: number };
  grid?: { spacing_x: number; spacing_y: number; column_size: number };
  parameters?: {
    module_count: number;
    room_count: number;
    facade_submodule_count: number;
    bay_spacing: number;
    module_gap: number;
    primary_height: number;
    primary_depth: number;
    visual_continuity: number;
    circulation_spine_width: number;
  };
  structural_profile?: SystemProfile;
  facade_profile?: SystemProfile;
  program_relations?: ProgramRelation[];
  interior_sequence?: string[];
  elements: BuildingElement[];
  validation?: ValidationCheck[];
}

// --- facade handoff ----------------------------------------------------------

export interface FacadeScoreDimensionState {
  id: SharedScoreDimensionId;
  status: 'known' | 'unknown';
  value: number | null;
  confidence: number | null;
  source_type: string;
  source_ref: string | null;
  reason: string | null;
  required_for_handoff: boolean;
}

export interface FacadeHostSurface {
  id: string;
  source_element_id: string;
  source_element_kind: 'massing';
  orientation: 'north' | 'south' | 'east' | 'west';
  program_owner: string;
  program_category: ProgramCategory;
  origin: Vector3Value;
  normal: Vector3Value;
  u_axis: Vector3Value;
  v_axis: Vector3Value;
  width: number;
  height: number;
  level_min: number;
  level_max: number;
  authority_status: 'preview_host';
}

export interface PipelineGateState {
  id: string;
  status: 'pass' | 'warning' | 'fail' | 'blocked' | 'pending' | 'not_applicable';
  authority: string;
  message: string;
  blocked_by: string[];
  evidence_refs: string[];
}

export interface FacadeHostHandoff {
  schema_version: 'mta.facade_host_handoff/1.0';
  handoff_id: string;
  model_id: string;
  score_id: string;
  authority_status: 'preview_only';
  maturity: 'MTA-F0' | 'MTA-F1' | 'MTA-F2';
  score_dimensions: FacadeScoreDimensionState[];
  host_surfaces: FacadeHostSurface[];
  gates: PipelineGateState[];
  ready_for_candidate_planning: boolean;
  ready_for_geometry_handoff: boolean;
  blocked_by: string[];
  limitations: string[];
}

// --- viewport ----------------------------------------------------------------

export type ModelViewMode = 'overall' | 'program' | 'facade' | 'structure';
export type StructureSubsystem =
  | 'columns' | 'beams' | 'slabs' | 'foundations' | 'bracing' | 'roof_truss' | 'cores';
export type SemanticLayer = 'structure' | 'envelope' | 'circulation' | 'program' | 'site';
export type SectionAxis = 'x' | 'y' | 'z';

export interface ClippingSettings {
  enabled: boolean;
  axis: SectionAxis;
  offset: number;
  inverted: boolean;
}

/** One merged GLB object, as `<model_id>.manifest.json` records it. */
export interface GlbObjectRecord {
  elements: number;
  faces: number;
  layer: string;
  subsystem: string;
  category: string;
}

export interface GlbManifest {
  producer: string;
  authority: string;
  model_id: string;
  score_id: string;
  element_count: number;
  element_groups: number;
  merged_objects: number;
  total_faces: number;
  objects: Record<string, GlbObjectRecord>;
  renders: string[];
  glb_sha256: string;
}

// --- assets and manifests ----------------------------------------------------

export interface ModelAsset {
  producer: 'blender_headless_5';
  format: 'glb';
  asset_url: string;
  manifest_url: string;
  native_blend_path: string;
  scene_state_path: string;
  asset_sha256: string;
  manifest_sha256: string;
  native_blend_sha256: string;
  scene_state_sha256: string;
  authority_status: 'presentation_only';
  semantic_layers: string[];
}

export interface ModelAssetV3 {
  producer: 'blender_headless_5_v3';
  format: 'glb';
  asset_schema_version: '3.0';
  asset_url: string;
  manifest_url: string;
  native_blend_path: string;
  model_json_path: string;
  asset_sha256: string;
  manifest_sha256: string;
  native_blend_sha256: string;
  source_model_sha256: string;
  source_hash_basis: 'canonical_json_sort_keys_utf8';
  element_count: number;
  merged_object_count: number;
  face_count: number;
  semantic_layers: string[];
  renders: string[];
  authority_status: 'presentation_only';
}

export interface PipelineArtifactReference {
  id: string;
  kind: string;
  status: 'available' | 'blocked' | 'pending';
  authority: string;
  sha256: string | null;
  uri: string | null;
}

export interface PipelineStageState {
  id: string;
  route: 'portable_core' | 'interactive_acceptance' | 'web_preview';
  status: 'pass' | 'warning' | 'fail' | 'blocked' | 'pending' | 'not_applicable';
  authority: string;
  producer: string;
  input_refs: string[];
  output_refs: string[];
  blocked_by: string[];
  message: string;
}

export interface PipelineRunManifest {
  schema_version: 'mta.pipeline_run_manifest/1.0';
  run_id: string;
  overall_status: 'preview_ready' | 'blocked' | 'accepted';
  model_id: string;
  score_id: string;
  artifacts: PipelineArtifactReference[];
  stages: PipelineStageState[];
  accepted_state: {
    status: 'blocked' | 'pending' | 'accepted';
    authority_owner: 'rhino';
    accepted_model_id: string | null;
    geometry_manifest_ref: string | null;
    blocked_by: string[];
  };
  limitations: string[];
}

// --- mapping report ----------------------------------------------------------

export interface MappingReportEntry {
  id: string;
  rule_id: string;
  music_feature: string;
  music_feature_label: string;
  music_value: number;
  music_normalized: number;
  music_unit: string;
  music_method: string;
  music_confidence: number;
  shared_dimension: string;
  shared_dimension_label: string;
  score_value: number;
  extraction_method: ExtractionMethod;
  score_confidence: number;
  architectural_proposal: string;
  architectural_target: string;
  architectural_target_label: string;
  mapping_direction: 'direct' | 'inverse';
  declared_output_range: [number, number];
  applied_min: number;
  applied_max: number;
  applied_unit: string;
  outcome: string;
  negotiation: string;
  affected_element_ids: string[];
  affected_element_kinds: string[];
  affected_programs: string[];
}

export interface MappingReport {
  schema_version: '1.0';
  report_id: string;
  score_id: string;
  model_id: string;
  source_audio_filename: string;
  typology: string;
  tectonic_system: string;
  automated_dimensions: string[];
  unsupported_dimensions: string[];
  covered_element_count: number;
  total_element_count: number;
  coverage_ratio: number;
  entries: MappingReportEntry[];
  limitations: string[];
}

// --- translation health ------------------------------------------------------

export type TranslationGrade =
  | 'strong' | 'working' | 'constrained' | 'proxy' | 'proxy_clamped' | 'unsupported';

export interface MeasuredFeature {
  id: string;
  value: number;
  unit: string;
  normalized: number;
  method: string;
  confidence: number;
}

export interface DrivenDatum {
  id: string;
  label: string;
  value: number;
  unit: string;
  range_low: number;
  range_high: number;
  applied_position: number;
  travel: number;
  clamped: boolean;
  element_count: number;
  element_kinds: string[];
  reason: string;
}

export interface DimensionHealth {
  id: string;
  label: string;
  present: boolean;
  evidence: 'measured' | 'proxy' | 'absent';
  grade: TranslationGrade;
  value?: number | null;
  extraction_method?: string | null;
  confidence?: number | null;
  travel?: number | null;
  source_features: MeasuredFeature[];
  proposal?: string | null;
  datums: DrivenDatum[];
  element_count: number;
  note: string;
}

export interface TectonicConstant {
  id: string;
  label: string;
  value: number;
  unit: string;
  reason: string;
}

export interface TranslationReport {
  schema_version: 'mta.translation_report/1.0';
  score_id: string;
  model_id: string;
  source_filename: string;
  duration_seconds: number;
  dimensions_emitted: number;
  dimensions_total: number;
  datum_count: number;
  variable_datum_count: number;
  coverage: number;
  variable_coverage: number;
  clamped_datum_count: number;
  element_count: number;
  element_kind_count: number;
  dimensions: DimensionHealth[];
  constants: TectonicConstant[];
  program_fulfilment: number;
  program_fits: boolean;
  program_unplaced: string[];
  limitations: string[];
}

// --- schema 3.0 analysis bundle ---------------------------------------------

export interface Datum {
  id: string;
  value: number;
  unit: string;
  provenance: 'score_driven' | 'design_fixture' | 'tectonic_constant' | string;
  driving_dimension: string | null;
  dimension_value: number | null;
  dimension_confidence: number | null;
  applied_position: number | null;
  output_range: [number, number] | null;
  rule_id: string | null;
  reason: string;
}

export interface DatumSet {
  schema_version: string;
  score_id: string;
  datums: Datum[];
}

export interface LevelDatum {
  index: number;
  id: string;
  z: number;
  kind: 'podium' | 'occupied' | 'roof' | string;
  plate: Point2Value[];
  voids: Point2Value[][];
  is_terrace: boolean;
}

export interface WorldXYGrid {
  origin: [number, number];
  spacing_x: number;
  spacing_y: number;
}

export interface GridBounds {
  x_min: number;
  y_min: number;
  x_max: number;
  y_max: number;
}

export interface ColumnFootprint {
  width_m: number;
  depth_m: number;
}

export interface ColumnCandidate {
  id: string;
  floor_id: string;
  point_xy: [number, number];
  grid_source: string;
  grid_node_id: string | null;
  grid_line_axis: string | null;
  grid_line_index: number | null;
  raw_boundary_anchor: [number, number] | null;
  boundary_provenance: string | null;
  inset_distance_m: number;
  fits_whole_footprint: boolean;
  fits_status: string;
  support_status: string;
  supporting_floor_ids: string[];
  reason: string;
}

export interface WorldXYColumnPlan {
  grid: WorldXYGrid;
  bounds: GridBounds;
  footprint: ColumnFootprint;
  candidates: ColumnCandidate[];
  inset_policy: string;
}

export interface HallSupportGrid {
  x: Record<string, number>;
  y: Record<string, number>;
  source_volume_ids: string[];
  pier_envelope_m: number;
  basis: string;
}

export interface Lattice {
  schema_version: string;
  levels: LevelDatum[];
  x_lines: number[];
  y_lines: number[];
  world_xy_grid?: WorldXYGrid;
  site_boundary?: { x: number; y: number }[];
  world_xy_column_plan?: WorldXYColumnPlan;
  hall_support_grid?: HallSupportGrid;
  apse_nodes: unknown[];
  plan_x_m: number;
  plan_y_m: number;
  plan: { x_min: number; x_max: number; y_min: number; y_max: number };
  massing_id: string;
  cutaway: boolean;
  roof_control?: RoofControl | null;
  facade_control?: FacadeControl;
  program_volume_grammar_id?: string | null;
  program_volume_source_digest?: string | null;
  program_volume_x_lines?: number[];
  program_volume_y_lines?: number[];
  program_volume_regions?: ProgramVolumeRegion[];
  circulation_intent?: ProgramCirculationIntent | null;
}

export interface RoofSectionProfile {
  truss_depth_m: number;
  chord_depth_m: number;
  purlin_depth_m: number;
  deck_thickness_m: number;
  parapet_upstand_m: number;
}

export interface RoofControl {
  schema_version: 'mta.roof_control/1.0';
  boundary: [number, number][];
  voids: [number, number][][];
  datum_z: number;
  physical_top_z: number;
  profile: RoofSectionProfile;
  span_proportion?: {
    span_m: number;
    depth_to_span: number;
    hierarchy_position: number;
    method: 'longest_interior_world_y_chord';
    basis: string;
  } | null;
  review_status: 'professional_review_required';
}

export type FacadeCanonicalRole =
  | 'weather_skin'
  | 'recessed_infill'
  | 'return_tie'
  | 'outboard_screen';

export interface FacadeLevelControl {
  level_id: string;
  z_base: number;
  z_top: number;
  source_boundary: [number, number][];
  source_voids: [number, number][][];
  weather_boundary: [number, number][];
  weather_voids: [number, number][][];
}

export interface FacadeControl {
  schema_version: 'mta.facade_control/1.0';
  program_volume_source_digest: string;
  grammar_id: string;
  tectonic_id: string;
  score_offset_m: number;
  tectonic_multiplier: number;
  multiplied_offset_m: number;
  grammar_depth_range_m: [number, number] | null;
  resolved_offset_m: number;
  resolution_status: 'resolved' | 'provisional_unevaluated';
  resolution_reason: string;
  outboard_screen_allowance_m: number;
  levels: FacadeLevelControl[];
  canonical_roles: FacadeCanonicalRole[];
  review_status: 'professional_review_required';
}

export interface ProgramVolumeLevel {
  index: number;
  id: string;
  z_base: number;
  z_top: number;
}

export interface AuthoredProgramVolume {
  id: string;
  level_index: number;
  level_id: string;
  category: ProgramCategory;
  role: 'program' | 'archetype' | 'circulation_spine' | 'connector' | 'sectional_clearance';
  space_ids: string[];
  shared_route_volume_ids?: string[];
  grid_rect: [number, number, number, number];
  target_area_m2: number;
  gross_area_m2: number;
  reason: string;
}

export interface ProgramVolumeCoreIntent {
  id: string;
  kind: 'stair' | 'lift';
  source_volume_id: string;
}

export interface ProgramVolumeRegion {
  id: string;
  level_id: string;
  category: ProgramCategory;
  role: AuthoredProgramVolume['role'];
  space_ids: string[];
  shared_route_volume_ids?: string[];
  grid_rect: [number, number, number, number];
  z_base: number;
  z_top: number;
}

export interface GridBoundaryStation {
  level_id: string;
  source_volume_id: string;
  grid_edge: [number, number, number, number];
  fraction: number;
}

export interface ArrivalAssembly {
  entry_rect: [number, number, number, number];
  stair_width_m: number;
  stair_start_v: number;
  stair_end_v: number;
  stair_family: string;
  facade_allowance_m: number;
  ramp: RampPlan;
  link_rect: [number, number, number, number];
  reserved_rects: [number, number, number, number][];
  basis: string;
}

export interface ProgramCirculationIntent {
  source_volume_digest: string;
  carrier_volume_ids: string[];
  connector_volume_ids: string[];
  entry_station: GridBoundaryStation;
  public_stair_family: 'broad_straight' | 'terraced_cascade' | 'bridge_split';
  ramp_preference: 'edge_parallel' | 'terrace_return' | 'notch_switchback';
  entry_floor_elevation_m: number;
  approach_depth_m: number;
  approach_depth_provenance: string;
  arrival_assembly?: ArrivalAssembly | null;
  reason: string;
}

export interface CirculationFinding {
  id: string;
  status: 'passed' | 'failed' | 'unevaluated';
  subject: string;
  detail: string;
}

export interface ResolvedCirculationPlan {
  intent: ProgramCirculationIntent;
  primary_core_ids: string[];
  public_stair_ids: string[];
  ramp_plan: RampPlan | null;
  attachment_portal_id: string | null;
  exterior_exception_ids: string[];
  findings: CirculationFinding[];
}

export interface ProgramVolumeUnion {
  level_index: number;
  level_id: string;
  boundary: [number, number][];
  voids: [number, number][][];
  gross_area_m2: number;
  source_volume_ids: string[];
}

export interface ProjectBrief {
  schema_version: 'project-brief.v1';
  brief_id: string;
  typology: 'library' | 'theater' | 'museum';
  site: { polygon: [number, number][]; units: 'm' };
  site_setbacks?: { setback_m: number; facade_projection_m: number; provenance: string;
                    reason: string; needs_review: boolean } | null;
  occupied_storeys: number;
  target_gross_area_m2: number;
  support_sizing?: {
    source: ProjectBrief['provenance']['provider_type'];
    basis: string;
    needs_review: true;
    sizes: Record<string, { area_m2: number; min_dimension_m: number }>;
  } | null;
  circulation_fraction: number | null;
  circulation_budget_m2: number | null;
  spaces: {
    id: string; space_type: string; label: string; category: string;
    area_m2: number; min_dimension_m: number; level_preference: string;
    daylight: string; occupancy_id: string; adjacency: string[];
    reason: string; area_tolerance: number;
  }[];
  provenance: {
    provider_type: 'random' | 'agent_llm' | 'local_llm' | 'openai' | 'external' | 'manual';
    model: string | null; seed: string | number | null;
    prompt_template_version: string | null; raw_response_hash: string | null;
    source_ref: string | null; generated_at: string; normalizer_version: string;
  };
  assumptions: string[];
}

export interface ProgramVolumeModel {
  schema_version: 'mta.program_volumes/1.0';
  project_brief?: ProjectBrief | null;
  score_id: string;
  typology: string;
  grammar_id: 'PVG-STACKED-BANDS' | 'PVG-TERRACED-WEAVE' | 'PVG-SPLIT-BRIDGE' | 'PVG-LEGACY-ELLIPSE';
  grammar_reason: string[];
  levels: ProgramVolumeLevel[];
  grid: { x_lines: number[]; y_lines: number[]; band_lines: number[]; apse_nodes: [number, number][] };
  world_xy_grid?: WorldXYGrid;
  volumes: AuthoredProgramVolume[];
  level_unions: ProgramVolumeUnion[];
  topology_signature: string;
  design_datums?: Record<string, number>;
  authored_cores?: ProgramVolumeCoreIntent[];
  program_volume_regions: ProgramVolumeRegion[];
  circulation_intent: ProgramCirculationIntent | null;
  roof_control: RoofControl | null;
  note: string;
}

export interface AllocatedZone {
  space_id: string;
  space_type: string;
  label: string;
  category: ProgramCategory | string;
  occupancy_id: string;
  level_index: number;
  level_id: string;
  band_index: number;
  x0: number; y0: number; x1: number; y1: number;
  area_required_m2: number;
  area_delivered_m2: number;
  daylight_satisfied: boolean;
  level_preference_satisfied: boolean;
}

export interface UnplacedSpace {
  space_id: string;
  label: string;
  area_required_m2: number;
  reason: string;
}

export interface PublicCirculationPlan {
  clear_width_m: number;
  wall_allowance_m: number;
  paths: { level_id: string; target_id: string; points: [number, number][] }[];
  aprons: Record<string, [number, number][][]>;
  unresolved: Record<string, string>;
  basis: string;
}

export interface ProgramAllocation {
  schema_version: string;
  zones: AllocatedZone[];
  unplaced: UnplacedSpace[];
  usable_area_by_level: Record<string, number>;
  required_area_m2: number;
  delivered_area_m2: number;
  cores_unreserved: string[];
  public_circulation: PublicCirculationPlan | null;
}

export interface ProfileSpec {
  id: string;
  shape: string;
  depth_m: number;
  width_m: number;
  web_m: number;
  flange_m: number;
  source: string;
}

export interface MemberSizingRecord {
  role: string;
  section_id: string;
  material_id: string;
  span_m: number;
  tributary_width_m: number;
  governing_check: string;
  utilisation: number;
  load_combination: string;
  factored_load_kn_m: number;
  element_count: number;
  assumptions: string[];
}

export interface LinearLoad {
  factored_kn_m: number;
  service_total_kn_m: number;
  service_live_kn_m: number;
  combination: string;
  tributary_width_m: number;
}

export interface Utilisation {
  label: string;
  demand: number;
  capacity: number;
  ratio: number;
  unit: string;
  passes: boolean;
  basis: string;
}

export interface ClauseCheck {
  clause: string;
  standard: string;
  label: string;
  status: 'pass' | 'fail' | 'unevaluated';
  demand: number | null;
  capacity: number | null;
  unit: string;
  basis: string;
}

export interface MemberValidation {
  member_id: string;
  role: string;
  designation: string;
  material_id: string;
  load_combination: string;
  checks: ClauseCheck[];
}

export interface MemberCheck {
  member_id: string;
  role: 'beam' | 'girder' | 'column' | 'slab';
  section_id: string;
  material_id: string;
  span_m: number;
  tributary_width_m: number;
  load: LinearLoad;
  utilisations: Utilisation[];
  governing: string;
  max_ratio: number;
  passes: boolean;
  self_weight_kn: number;
  assumptions: string[];
  validation: MemberValidation | null;
  validation_status: 'professional_review_required';
}

export interface SelectionResult {
  member_id: string;
  selected: boolean;
  check: MemberCheck | null;
  candidates_tried: number;
  reason: string;
}

export interface TransferLoad {
  node: number;
  y: number;
  dead_kn: number;
  live_kn: number;
  roof_live_kn: number;
  tributary_area_by_level: Record<string, number>;
}

export interface TransferMember {
  id: string;
  role: string;
  node_a: number;
  node_b: number;
  length_m: number;
  unbraced_length_m: number;
  section_id: string | null;
  analysis_section_id: string;
  axial_kn: Record<string, number>;
  tension_capacity_kn: number;
  compression_capacity_kn: number;
  utilisation: number | null;
  compression_check: MemberCheck | null;
  selected: boolean;
}

export interface TransferPier {
  id: string;
  x_index: number;
  y_index: number;
  level_index: number;
  dead_kn: number;
  live_kn: number;
  roof_live_kn: number;
  check: MemberCheck | null;
}

export interface TransferFrame {
  id: string;
  x_index: number;
  x: number;
  level_index: number;
  level_id: string;
  y_indices: number[];
  span_m: number;
  top_z: number;
  bottom_z: number;
  clear_top_z: number;
  nodes: [number, number][];
  node_loads: TransferLoad[];
  beam_trial: SelectionResult | null;
  members: TransferMember[];
  reactions_kn: Record<string, number[]>;
  piers: TransferPier[];
  equilibrium_residual_kn: number | null;
  total_deflection_mm: number | null;
  live_deflection_mm: number | null;
  status: 'failed' | 'review_required';
  activated: boolean;
  findings: string[];
}

export interface TransferEdge {
  x: number;
  x_bay_index: number;
  y_indices: number[];
  y_coordinates: Record<string, number>;
  regular_x_index: number | null;
  level_index: number;
  check: MemberCheck | null;
  dead_kn: number;
  live_kn: number;
  roof_live_kn: number;
}

export interface HallEnclosureReport {
  status: 'failed' | 'review_required';
  level_id: string | null;
  roof_bottom_z: number | null;
  clear_top_z: number | null;
  roof_area_m2: number;
  support_grid: HallSupportGrid | null;
  roof_dead_kn: number;
  roof_live_kn: number;
  framing_dead_kn: number;
  uncovered_area_m2: number | null;
  open_wall_head_length_m: number | null;
  primary: SelectionResult | null;
  secondary: SelectionResult | null;
  roof_ids: string[];
  framing_ids: string[];
  findings: string[];
  unevaluated: string[];
}

export interface TransferReport {
  status: 'not_required' | 'failed' | 'review_required';
  method: string;
  basis: string;
  frames: TransferFrame[];
  edges: TransferEdge[];
  boundary_piers: TransferPier[];
  hall_enclosure: HallEnclosureReport | null;
  findings: string[];
  unevaluated: string[];
}

export interface AxisReading {
  axis: string;
  value: number;
  sources: string[];
  reason: string;
}

export interface RankedOption {
  system_id: string;
  grammar_id: string;
  affinity: number;
}

export interface SelectionRecord {
  program_id: string;
  typology: string;
  massing_id: string;
  massing_label: string;
  massing_reason: string[];
  system_id: string;
  grammar_id: string;
  frame_tectonic_id: string;
  envelope_tectonic_id: string;
  preferred_system_id: string;
  preferred_grammar_id: string;
  overruled_by_screen: boolean;
  overrule_reason: string | null;
  axes: AxisReading[];
  grammar_affinity: number;
  system_affinity: number;
  runner_up_grammar_id: string | null;
  runner_up_margin: number | null;
  ranked_options: RankedOption[];
  sizing_fallback: string | null;
  admissible_systems: string[];
  admissible_grammars: string[];
  unbuildable_systems: Record<string, string>;
  required_structural_capabilities: string[];
  compiler_capability_exclusions: Record<string, string[]>;
  jurisdiction_resolved: boolean;
  note: string;
}

export interface GateResult {
  id: string;
  invariant_ref: string;
  verdict: 'passed' | 'failed' | 'unevaluated';
  measured: number | null;
  required: string;
  detail: string;
}

export interface FacadeGateReport {
  grammar_id: string;
  grammar_label: string;
  guide_ref: string;
  gates: GateResult[];
  status: 'passed' | 'failed' | 'unevaluated';
  corrected: string | null;
}

export interface RampRun {
  index: number;
  x_start: number; x_end: number; y: number;
  y_start?: number | null;
  y_end?: number | null;
  z_start: number; z_end: number;
  direction: number;
}

export interface RampLanding {
  index: number;
  x: number; y: number; z: number;
  size_x: number; size_y: number;
  kind: string;
}

export interface RampPlan {
  rise_m: number;
  width_m: number;
  runs: RampRun[];
  landings: RampLanding[];
  footprint_x_m: number;
  footprint_y_m: number;
  handrails_required: boolean;
  citations: string[];
}

export interface ConstitutionFinding {
  requirement_id: string;
  label: string;
  necessity: string;
  status: 'satisfied' | 'missing' | 'unresolved';
  matched_space_id: string | null;
  detail: string;
}

export interface ConstitutionReport {
  typology: string;
  findings: ConstitutionFinding[];
}

export interface EgressNode {
  id: string;
  kind: string;
  label: string;
  level_id: string;
  level_index: number;
  x: number;
  y: number;
  occupants: number;
  occupant_basis: string;
  width_mm: number;
}

export interface EgressEdge {
  source: string;
  target: string;
  distance_m: number;
  kind: 'within_floor' | 'vertical';
  points: [number, number][];
  points_3d: [number, number, number][];
  step_count: number;
  source_surface_ids: string[];
  sample_id: string | null;
  basis: string;
}

export interface NavigationReport {
  schema_version: string;
  body_width_m: number;
  head_height_m: number;
  step_review_m: number;
  basis: string;
  samples: { id: string; space_id: string; level_id: string; point: [number, number]; floor_z_m: number; origin: 'floor' | 'seat_row_access' | 'stage'; source_surface_ids: string[]; reachable_exits: string[] }[];
  routes: { sample_id: string; source: string; target: string; level_id: string; distance_m: number; points: [number, number][]; points_3d: [number, number, number][]; step_count: number; source_surface_ids: string[] }[];
  findings: { id: string; status: 'passed' | 'failed' | 'unevaluated'; subject: string; detail: string }[];
  limitations: string[];
}

export interface PortalSide {
  region: [number, number][];
  support_ids: string[];
  unsupported_m2: number;
  elevation_mismatch_m: number | null;
  clash_ids: string[];
}

export interface PortalReport {
  schema_version: string;
  status: 'passed' | 'failed' | 'unevaluated';
  basis: string;
  portals: {
    id: string; door_ids: string[]; level_id: string; kind: 'room' | 'entrance' | 'lift';
    center: [number, number]; tangent: [number, number]; normal: [number, number];
    aperture: [number, number][]; floor_z: number; width_m: number; height_m: number;
    wall_depth_m: number; host_wall_ids: string[]; side_a: PortalSide; side_b: PortalSide;
    aperture_clear: boolean; passable: boolean; reasons: string[];
  }[];
  findings: { rule_id: string; portal_id: string; elements: string[]; detail: string; measure: number; unit: string }[];
}

export interface RoomLayoutPlan {
  schema_version: string;
  spaces: {
    space_id: string; space_type: string; level_id: string; proposed_counts: Record<string, number>;
    required_counts: Record<string, number> | null; count_basis: string;
    omitted: Record<string, string>; unresolved: string[];
  }[];
  assemblies: {
    assembly_id: string; space_id: string; level_id: string; recipe: string;
    required_roles: string[]; floor_roles: string[]; floor_z_m: number;
  }[];
  reservations: {
    id: string; space_id: string; level_id: string;
    purpose: 'fixture_use' | 'equipment_service' | 'longitudinal_aisle' | 'cross_aisle' | 'seat_row_access' | 'wheelchair_position';
    polygon: [number, number][]; floor_z_m: number; clear_height_m: number; basis: string;
  }[];
}

export interface RoomLayoutReport {
  schema_version: string;
  status: 'passed' | 'failed' | 'unevaluated';
  assembly_count: number; counts_by_recipe: Record<string, number>; reservation_count: number;
  findings: { check_id: string; status: 'failed' | 'unevaluated'; space_id: string; element_ids: string[]; detail: string }[];
  checks_run: string[]; quantity_adequacy: 'unevaluated'; basis: string;
}

export interface EgressFinding {
  clause: string;
  label: string;
  status: 'pass' | 'fail' | 'unevaluated';
  subject: string;
  demand: number | null;
  capacity: number | null;
  unit: string;
  detail: string;
}

export interface LifeSafetyGraph {
  typology: string;
  occupancy_group: string;
  sprinklered: boolean;
  nodes: EgressNode[];
  edges: EgressEdge[];
  findings: EgressFinding[];
  navigation?: NavigationReport | null;
}

export interface DependencyRoot {
  id: string;
  kind: string;
  topology_status: string;
  capacity_status: string;
  reason: string;
}

export interface DependencyEdge {
  dependent_id: string;
  host_id: string;
}

export interface DependencyRelationGroup {
  group_id: string;
  relation: string;
  role: string;
  connection_family: string;
  topology_status: string;
  capacity_status: string;
  basis: string;
  edges: DependencyEdge[];
}

export interface DependencyExemption {
  element_id: string;
  reason: string;
}

export interface DependencyCheck {
  id: string;
  status: 'passed' | 'failed' | 'not_checked';
  message: string;
  affected_ids: string[];
}

export interface DependencyGraph {
  schema_version: string;
  status: 'passed' | 'failed';
  roots: DependencyRoot[];
  relation_groups: DependencyRelationGroup[];
  exemptions: DependencyExemption[];
  checks: DependencyCheck[];
  required_element_count: number;
  connected_element_count: number;
  gravity_path_count: number;
  connection_design_status: string;
}

export interface AxisReport {
  schema_version: string;
  status: 'passed' | 'failed';
  node_count: number;
  segment_count: number;
  checks: DependencyCheck[];
}

export interface SourcedValue<T = number | string | boolean> {
  value: T;
  source: 'manual' | 'verified_lookup' | 'code_lookup' | 'llm_proposed' | string;
  basis: string;
  set_by: string | null;
  needs_review: boolean;
}

export interface SiteLocation {
  country: string;
  region: string;
  city: string;
  latitude: number;
  longitude: number;
  source: string;
  set_by: string | null;
  rationale: string;
}

export interface SiteParameters {
  location: SiteLocation;
  basic_wind_speed_ms: SourcedValue<number>;
  wind_exposure_category: SourcedValue<string>;
  topographic_factor_kzt: SourcedValue<number>;
  mapped_ss: SourcedValue<number>;
  mapped_s1: SourcedValue<number>;
  site_class: SourcedValue<string>;
  seismic_design_category: SourcedValue<string>;
  ground_snow_kpa: SourcedValue<number>;
  snow_exposure_ce: SourcedValue<number>;
  thermal_factor_ct: SourcedValue<number>;
  adopted_building_code: SourcedValue<string>;
  adopted_load_standard: SourcedValue<string>;
  risk_category: SourcedValue<string>;
  sprinklered: SourcedValue<boolean>;
}

export interface LoadResult {
  action: string;
  value: number;
  unit: string;
  clause: string;
  basis: string;
  inputs: string[];
  design_ready: boolean;
}

export interface SiteLoadSet {
  snow: LoadResult;
  wind: LoadResult;
  seismic: LoadResult;
}

/** One archetype gate the built geometry disagreed with. */
export interface ArchetypeFinding {
  gate_id: string;
  severity: 'violation' | 'warning';
  elements: string[];
  measure: number;
  unit: string;
  detail: string;
}

export interface SightlineRecord {
  row: number;
  distance_m: number;
  floor_m: number;
  c_measured_m: number | null;
}

/** One thing the spatial rules saw: two systems overlapping, a step that is not
 *  flush, a gap you could fall through, a thing standing over a void. */
export interface SpatialFinding {
  rule_id: string;
  severity: 'violation' | 'warning';
  elements: string[];
  measure: number;
  unit: string;
  detail: string;
}

export interface SpatialReport {
  schema_version: string;
  status: 'passed' | 'failed' | 'unevaluated';
  findings: SpatialFinding[];
  counts: Record<string, number>;
  /** What each rule watches for, carried so a passing check says what it checked. */
  watches: Record<string, string>;
}

/** A material as the exporter paints it, with the reason it was chosen. */
export interface MaterialSpec {
  id: string;
  family: string;
  finish: string;
  base_color: string;
  roughness: number;
  metallic: number;
  transmission: number;
  ior: number;
  reason: string;
}

/** What the spatial archetype promised, audited against the built model. */
export interface ArchetypeReport {
  archetype_id: string;
  typology: string;
  refused: string | null;
  clear_house_m: number | null;
  clear_stage_m: number | null;
  sightlines: SightlineRecord[];
  findings: ArchetypeFinding[];
  notes: string[];
}

export interface ElementGroupSummary {
  group_id: string;
  kind: string;
  semantic_layer: string;
  subsystem: string;
  category: string;
  program: string;
  material_profile: string | null;
  section_id: string | null;
  thickness_m: number | null;
  sizing_status: 'sized_by_calculation' | 'architectural_convention' | 'not_applicable' | string;
  utilisation: number | null;
  governing_check: string | null;
  datum_refs: string[];
  rule_refs: string[];
  reason: string;
  validation_status: string | null;
  instance_count: number;
  level_ids: string[];
}

export interface StatusTally {
  source: string;
  label: string;
  authority: string;
  /** The building these checks describe, when it is not the model in view. */
  building?: string | null;
  passed: number;
  failed: number;
  unevaluated: number;
  blockers: string[];
}

export interface ComplianceRollup {
  schema_version: string;
  tallies: StatusTally[];
  /** Checks the run also ran, on a building that is not this one -- the v2 massing
   *  contract when its typed identity diverges from the v3 selection. Never summed
   *  into the totals above. */
  foreign_tallies?: StatusTally[];
  passed_total: number;
  failed_total: number;
  unevaluated_total: number;
  blockers: string[];
}

export type BimDeliveryStrategy =
  | 'native_candidate'
  | 'room_candidate'
  | 'direct_shape_preview'
  | 'omit_presentation_only';

export interface BimStrategySummary {
  strategy: BimDeliveryStrategy;
  label: string;
  mapping_rule_count: number;
  taxonomy_kind_count: number;
  emitted_kind_count: number;
  element_count: number;
}

export interface BimCategorySummary {
  revit_category: string;
  built_in_category: string | null;
  strategy: BimDeliveryStrategy;
  /** Materials that land in this category, so a takeoff can be scoped to it. */
  material_profiles?: string[];
  mapping_rule_ids: string[];
  taxonomy_kind_count: number;
  emitted_kind_count: number;
  element_count: number;
  review_gate: string;
}

export interface BimMaterialBinding {
  profile: string;
  family: string;
  finish: string;
  /** Revit categories this material lands in. */
  categories: string[];
  /** How many of its instances land in a category Revit can schedule. */
  schedulable_element_count: number;
  base_color: string;
  roughness: number;
  metallic: number;
  transmission: number;
  ior: number;
  element_count: number;
  revit_class: string;
  reason: string;
}

/** What the receiving team gets, in the terms they price the work in. */
export interface BimReceivingSummary {
  native_element_count: number;
  room_element_count: number;
  direct_shape_element_count: number;
  omitted_element_count: number;
  mapped_element_count: number;
  schedulable_share: number;
  remodel_note: string;
  takeoff_note: string;
}

export interface BimIdentityParameter {
  name: string;
  guid: string;
  purpose: string;
}

export interface BimEvidenceCheck {
  id: string;
  label: string;
  status: 'passed' | 'failed' | 'pending';
  detail: string;
}

export interface BimHandoffReport {
  schema_version: 'mta.revit_dynamo_handoff_report/0.1';
  report_id: string;
  source_model_id: string;
  source_model_sha256: string;
  source_schema_version: string;
  source_units: string;
  source_coordinate_system: string;
  contract_version: string;
  contract_sha256: string;
  contract_status: string;
  target_host: string;
  orchestrator: string;
  handoff_readiness: 'ready_for_dry_run' | 'blocked';
  live_validation_status: 'pending';
  taxonomy_kind_count: number;
  mapped_taxonomy_kind_count: number;
  contract_coverage: number;
  emitted_kind_count: number;
  mapped_emitted_kind_count: number;
  emitted_element_count: number;
  mapped_element_count: number;
  target_element_count: number;
  omitted_element_count: number;
  emitted_coverage: number;
  mapping_rule_count: number;
  strategy_summaries: BimStrategySummary[];
  category_summaries: BimCategorySummary[];
  parameter_count: number;
  required_parameter_count: number;
  identity_parameters: BimIdentityParameter[];
  material_bindings?: BimMaterialBinding[];
  receiving?: BimReceivingSummary | null;
  review_queue?: BimCategorySummary[];
  sync_operations: string[];
  safeguards: string[];
  evidence_checks: BimEvidenceCheck[];
  live_validation_blockers: string[];
  limitations: string[];
}

export interface AnalysisBundle {
  schema_version: 'mta.analysis_bundle/1.0';
  model_id: string;
  score_id: string;
  typology: string;
  tectonic_system: string;
  structural_system_id: string;
  facade_grammar_id: string;
  envelope_tectonic_id: string;
  selection: SelectionRecord | null;
  datum_set: DatumSet;
  lattice: Lattice;
  program_allocation: ProgramAllocation;
  program_volume_model?: ProgramVolumeModel | null;
  project_brief?: ProjectBrief | null;
  profiles: Record<string, ProfileSpec>;
  sizing: MemberSizingRecord[];
  transfer_structure?: TransferReport | null;
  element_groups: ElementGroupSummary[];
  element_counts: Record<string, number>;
  layer_counts: Record<string, number>;
  element_count: number;
  sized_element_count: number;
  facade_gates: FacadeGateReport | null;
  accessible_route: RampPlan | null;
  accessible_route_unresolved: string | null;
  circulation_plan?: ResolvedCirculationPlan | null;
  constitution: ConstitutionReport | null;
  archetype?: ArchetypeReport | null;
  spatial?: SpatialReport | null;
  materials?: Record<string, MaterialSpec>;
  life_safety: LifeSafetyGraph | null;
  portals?: PortalReport | null;
  room_layout_plan?: RoomLayoutPlan | null;
  room_layouts?: RoomLayoutReport | null;
  dependency_graph: DependencyGraph | null;
  axis_report: AxisReport | null;
  site: SiteParameters | null;
  site_loads: SiteLoadSet | null;
  bim_handoff: BimHandoffReport | null;
  /** One reasoning chain per element family, keyed by `group_id`. */
  derivation: Record<string, DerivationChain>;
  /** The instance each chain was assembled from, so the sample is stated. */
  derivation_element_ids: Record<string, string>;
  compliance: ComplianceRollup;
  limitations: string[];
}

// --- drawings, renders, runs -------------------------------------------------

export interface DetailCheck {
  id: string;
  label: string;
  status: 'passed' | 'failed' | 'unevaluated';
  evidence: string;
}

export interface DetailMaterialRole {
  material_profile: string;
  drawing_roles: string[];
  element_kinds: string[];
  element_ids: string[];
}

export interface DetailAssemblyAudit {
  assembly_id: string;
  element_ids: string[];
  part_roles: string[];
  host_element_ids: string[];
  unresolved_interfaces: string[];
}

export interface DetailViewAudit {
  schema_version: 'mta.detail_view_audit/1.0';
  detail_id: string;
  spec_id: string;
  detail_kind: 'roof_edge' | 'facade_floor' | 'entry_circulation' | 'landing_access';
  scale: string;
  bearing_deg: number;
  target_point_m: number[];
  crop_m: number[];
  cut_bbox_m: number[];
  cut_element_bboxes_m: Record<string, number[]>;
  key_dimensions_m: Record<string, number>;
  target_element_ids: string[];
  target_elements_drawn: string[];
  model_element_ids: string[];
  assembly_ids: string[];
  assemblies: DetailAssemblyAudit[];
  facade_roles: string[];
  material_roles: DetailMaterialRole[];
  host_element_ids: string[];
  unresolved_interfaces: string[];
  elements_considered: number;
  elements_drawn: number;
  elements_cut: number;
  marks: number;
  source: 'compiled_model_projection';
  projection_verified: boolean;
}

export interface DetailReadinessReport {
  schema_version: 'mta.detail_readiness/1.0';
  detail_id: string;
  audience: 'student_design_review';
  status: 'ready_with_limitations' | 'blocked';
  drawing_status: 'generated';
  d3_status: 'ready_with_limitations' | 'blocked';
  professional_review_required: true;
  construction_document_status: 'not_evaluated';
  permit_status: 'not_evaluated';
  checks: DetailCheck[];
  missing_layers: string[];
  unresolved: string[];
  limitations: string[];
}

export interface DrawingOnSheetRef {
  id: string;
  title: string;
  kind: 'plan' | 'section' | 'elevation' | 'detail';
  scale: string;
  subtitle: string;
  content_mm: number[];
  marks: number;
  elements_cut: number;
  elements_drawn: number;
  omitted_by_scale: Record<string, number>;
  detail_audit?: DetailViewAudit | null;
  detail_readiness?: DetailReadinessReport | null;
}

export interface DrawingSheetRef {
  id: string;
  title: string;
  kind: 'plan' | 'section' | 'elevation' | 'detail' | 'cover';
  scale: string;
  subtitle: string;
  url: string;
  /** Number in the set (A-101 …) and the paper every sheet of the set shares. */
  sheet_number: string;
  paper: string;
  sheet_mm: number[];
  content_mm: number[];
  marks: number;
  elements_cut: number;
  elements_drawn: number;
  omitted_by_scale: Record<string, number>;
  /** The drawings composed on this sheet; the cover carries none. */
  drawings: DrawingOnSheetRef[];
}

export interface RenderRef {
  id: string;
  filename: string;
  url: string;
  authority_status: 'presentation_only';
}

export interface DrawingIndex {
  schema_version: string;
  model_id: string;
  paper: string;
  sheets: Array<Record<string, unknown>>;
  element_account: { drawn: number; omitted_by_scale: number; on_no_cut: number; total: number };
  accounted_for: boolean;
  limitation: string;
}

export interface RunSummary {
  run_id: string;
  model_id: string;
  score_id: string;
  generated_at: string;
  source_filename: string;
  typology: string;
  massing_id: string;
  structural_system_id: string;
  facade_grammar_id: string;
  element_count: number;
  variable_coverage: number | null;
  failed_checks: number;
  unevaluated_checks: number;
  overall_status: string;
}

export interface GenerationResponse {
  run_id: string;
  generated_at: string;
  compiler_source_sha256: string;
  elapsed_seconds?: number | null;
  /** Where the recording can be fetched back; absent when a run kept no audio. */
  audio_url?: string | null;
  audio_features: AudioFeatures;
  architectural_score: ArchitecturalScore;
  building_model: BuildingModel;
  mapping_report: MappingReport;
  facade_handoff: FacadeHostHandoff;
  model_asset: ModelAsset | null;
  pipeline_manifest: PipelineRunManifest;
  model_asset_v3?: ModelAssetV3 | null;
  stage_errors?: Record<string, string>;
  project_brief?: Record<string, unknown> | null;
  translation_report?: TranslationReport | null;
  datum_coverage?: number | null;
  datum_waiting_on?: string[];
  drawing_index?: DrawingIndex | null;
  drawing_sheets: DrawingSheetRef[];
  renders: RenderRef[];
  analysis?: AnalysisBundle | null;
}

/** One step of an element's reasoning, in the order a person would have reasoned it. */
export interface DerivationStep {
  stage: string;
  label: string;
  value: string;
  source: string;
  why: string;
}

/**
 * How one element family came to be, assembled from what the model already carries.
 *
 * `reaches_audio` is the honest half: not every element is driven by the music — a fire
 * stair is required by code whatever the piece sounds like — and those chains say so
 * rather than inventing a musical cause.
 */
export interface DerivationChain {
  schema_version: string;
  element_id: string;
  kind: string;
  level_id: string;
  steps: DerivationStep[];
  reaches_solid: boolean;
  starts_located: boolean;
  reaches_audio: boolean;
  rule_refs: string[];
  summary: string;
}

/** Which workspace the stage is showing. */
export type WorkspaceId =
  | 'overview' | 'audio' | 'score' | 'selection' | 'model' | 'drawings'
  | 'structure' | 'program' | 'compliance' | 'bim' | 'dependencies' | 'site'
  | 'derivation' | 'artifacts';
