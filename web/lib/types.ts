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

export interface Lattice {
  schema_version: string;
  levels: LevelDatum[];
  x_lines: number[];
  y_lines: number[];
  apse_nodes: unknown[];
  plan_x_m: number;
  plan_y_m: number;
  plan: { x_min: number; x_max: number; y_min: number; y_max: number };
  massing_id: string;
  cutaway: boolean;
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

export interface ProgramAllocation {
  schema_version: string;
  zones: AllocatedZone[];
  unplaced: UnplacedSpace[];
  usable_area_by_level: Record<string, number>;
  required_area_m2: number;
  delivered_area_m2: number;
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
  corrected: string | null;
}

export interface RampRun {
  index: number;
  x_start: number; x_end: number; y: number;
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
  width_mm: number;
}

export interface EgressEdge {
  source: string;
  target: string;
  distance_m: number;
  kind: 'within_floor' | 'vertical';
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
  profiles: Record<string, ProfileSpec>;
  sizing: MemberSizingRecord[];
  element_groups: ElementGroupSummary[];
  element_counts: Record<string, number>;
  layer_counts: Record<string, number>;
  element_count: number;
  sized_element_count: number;
  facade_gates: FacadeGateReport | null;
  accessible_route: RampPlan | null;
  accessible_route_unresolved: string | null;
  constitution: ConstitutionReport | null;
  archetype?: ArchetypeReport | null;
  spatial?: SpatialReport | null;
  materials?: Record<string, MaterialSpec>;
  life_safety: LifeSafetyGraph | null;
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

export interface DrawingOnSheetRef {
  id: string;
  title: string;
  kind: 'plan' | 'section' | 'elevation';
  scale: string;
  subtitle: string;
  content_mm: number[];
  marks: number;
  elements_cut: number;
  elements_drawn: number;
  omitted_by_scale: Record<string, number>;
}

export interface DrawingSheetRef {
  id: string;
  title: string;
  kind: 'plan' | 'section' | 'elevation' | 'cover';
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
  audio_features: AudioFeatures;
  architectural_score: ArchitecturalScore;
  building_model: BuildingModel;
  mapping_report: MappingReport;
  facade_handoff: FacadeHostHandoff;
  model_asset: ModelAsset | null;
  pipeline_manifest: PipelineRunManifest;
  model_asset_v3?: ModelAssetV3 | null;
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
