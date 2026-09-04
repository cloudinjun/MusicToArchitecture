"""The music-to-architecture translation health check.

A mapping report says what was mapped. A health check says whether the mapping is
load-bearing, and that is a different question. For each of the ten shared dimensions it
answers four things:

    evidence   is there a direct measurement of the thing named, or a proxy for it?
    travel     how much of its declared range was the datum allowed to cross, given how
               well the dimension is known?
    reach      how many elements does it actually touch?
    outcome    what did it do to the building, in the building's own units?

The point of separating them is that a dimension can look present and be inert. A proxy
at 0.35 confidence, clamped to a fifth of its range, touching thirty panels, is not the
same claim as a measured dynamic range moving a roof truss through its full depth --
even though both appear in a mapping table as "driven". The grade makes that visible
rather than leaving it to be inferred from a confidence column nobody reads.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .datums import FULL_CONFIDENCE, DatumSet, confidence_factor
from .models import ArchitecturalScore, AudioFeatures, MetricValue
from .models_v3 import BuildingModelV3

Evidence = Literal['measured', 'proxy', 'absent']
Grade = Literal['strong', 'working', 'constrained', 'proxy', 'proxy_clamped',
                'unsupported']

DIMENSION_LABELS: dict[str, str] = {
    'tempo_of_change': 'Tempo of change',
    'tension_release': 'Tension and release',
    'density': 'Density',
    'continuity': 'Continuity',
    'repetition': 'Repetition',
    'variation': 'Variation',
    'hierarchy': 'Hierarchy',
    'interruption': 'Interruption',
    'polyphony': 'Polyphony',
    'genre_style': 'Timbral position',
}

DATUM_LABELS: dict[str, str] = {
    'level_count': 'occupied levels',
    'floor_to_floor_m': 'floor to floor',
    'shading_rows': 'shading rows',
    'shading_depth_m': 'shading depth',
    'bay_x_m': 'bay, long axis',
    'bay_y_m': 'bay, short axis',
    'joist_spacing_m': 'joist spacing',
    'transom_rows': 'transom rows',
    'cantilever_m': 'plate cantilever',
    'apse_radius_m': 'apse radius',
    'circulation_allowance': 'plate kept for routes',
    'flight_width_m': 'stair width',
    'mullion_module_m': 'mullion module',
    'spandrel_height_m': 'spandrel band',
    'rail_post_spacing_m': 'guard post spacing',
    'plate_step_m': 'plate step-back',
    'plate_rotation_deg': 'plate rotation',
    'truss_depth_m': 'roof truss depth',
    'truss_panels': 'truss panels',
    'ground_open_height_m': 'open ground level',
    'entry_canopy_span_m': 'entry canopy span',
    'void_count': 'atrium voids',
    'void_scale': 'void scale',
    'terrace_count': 'terrace levels',
    'envelope_offset_m': 'envelope stand-off',
    'envelope_layer_count': 'envelope layers',
    'braced_bay_count': 'braced bays',
    'opaque_fraction': 'opaque share',
    'fin_depth_m': 'fin depth',
    'slab_thickness_m': 'slab thickness',
    'edge_fascia_m': 'plate edge',
    'riser_m': 'stair riser',
    'rail_height_m': 'guard height',
    'figure_height_m': 'scale figure',
}


class MeasuredFeature(BaseModel):
    id: str
    value: float
    unit: str
    normalized: float
    method: str
    confidence: float


class DrivenDatum(BaseModel):
    id: str
    label: str
    value: float
    unit: str
    range_low: float
    range_high: float
    applied_position: float
    travel: float = Field(ge=0.0, le=1.0)
    clamped: bool
    element_count: int
    element_kinds: list[str]
    reason: str


class DimensionHealth(BaseModel):
    id: str
    label: str
    present: bool
    evidence: Evidence
    grade: Grade
    value: float | None = None
    extraction_method: str | None = None
    confidence: float | None = None
    travel: float | None = None
    source_features: list[MeasuredFeature] = Field(default_factory=list)
    proposal: str | None = None
    datums: list[DrivenDatum] = Field(default_factory=list)
    element_count: int = 0
    note: str


class TectonicConstant(BaseModel):
    id: str
    label: str
    value: float
    unit: str
    reason: str


class TranslationReport(BaseModel):
    """What the run did with the music, dimension by dimension."""

    schema_version: Literal['mta.translation_report/1.0'] = 'mta.translation_report/1.0'
    score_id: str
    model_id: str
    source_filename: str
    duration_seconds: float

    dimensions_emitted: int
    dimensions_total: int = 10
    datum_count: int
    variable_datum_count: int
    coverage: float
    variable_coverage: float
    clamped_datum_count: int
    element_count: int
    element_kind_count: int

    # The four decisions the score makes before any datum is applied: which brief,
    # which silhouette, which facade grammar, which structural system. They were
    # module constants when this report was designed, which is why a health check
    # of the translation could once be complete without mentioning them.
    typology: str = 'library'
    massing_id: str = 'MAS-SLAB'
    massing_label: str = 'Stacked slab'
    facade_grammar_id: str = 'FCD-01-INTERNATIONAL-STYLE'
    structural_system_id: str = 'STR-SYS-STEEL-FRAME'
    selection_reasoning: list[str] = Field(default_factory=list)
    facade_gates_passed: int = 0
    facade_gates_total: int = 0
    facade_gates_unevaluated: int = 0
    facade_gate_correction: str | None = None

    dimensions: list[DimensionHealth]
    constants: list[TectonicConstant]
    program_fulfilment: float
    program_fits: bool
    program_unplaced: list[str]
    limitations: list[str]

    @property
    def grades(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for dimension in self.dimensions:
            counts[dimension.grade] = counts.get(dimension.grade, 0) + 1
        return counts


def _feature(features: AudioFeatures, name: str) -> MeasuredFeature | None:
    metric = getattr(features, name, None)
    if not isinstance(metric, MetricValue):
        return None
    return MeasuredFeature(
        id=name, value=metric.value, unit=metric.unit,
        normalized=metric.normalized, method=metric.method,
        confidence=metric.confidence)


def _grade(
    present: bool, evidence: Evidence, travel: float, element_count: int,
) -> tuple[Grade, str]:
    """Four inputs, one honest label.

    `reach` matters as much as confidence: a dimension that is measured perfectly but
    touches nothing has not translated anything.
    """
    if not present:
        return 'unsupported', ('No audio metric supports this dimension, so its datums '
                               'are declared design fixtures and the music does not '
                               'reach them.')
    if evidence == 'proxy' and travel < 0.6:
        return 'proxy_clamped', ('Inferred from a proxy and clamped hard. It nudges the '
                              'design; it must not be presented as having shaped it.')
    if evidence == 'proxy':
        return 'proxy', ('A defensible proxy, not a direct measurement of the thing '
                         'named. Treat the result as a proposal.')
    if travel < 1.0:
        return 'constrained', ('Measured, but not confidently enough to cross its full '
                               'range. It moves the design within a narrowed band.')
    if element_count < 20:
        return 'working', ('Fully measured and fully free to move, but it reaches only a '
                           'small part of the model.')
    return 'strong', ('Directly measured, free to cross its declared range, and reaching '
                      'a substantial part of the model.')


# Which raw metrics stand behind each dimension, for the evidence column.
_SOURCES: dict[str, tuple[str, ...]] = {
    'tempo_of_change': ('tempo_bpm',),
    'tension_release': ('rms_energy',),
    'density': ('onset_density_hz',),
    'continuity': ('spectral_centroid_hz',),
    'repetition': ('periodicity',),
    'variation': ('timbre_variation',),
    'hierarchy': ('dynamic_range_db',),
    'interruption': ('novelty_peak_rate_per_min',),
    'polyphony': ('spectral_contrast_db', 'harmonic_ratio'),
    'genre_style': ('spectral_flatness', 'zero_crossing_rate',
                    'spectral_centroid_hz', 'harmonic_ratio'),
}


def compile_translation_report(
    features: AudioFeatures, score: ArchitecturalScore, model: BuildingModelV3,
) -> TranslationReport:
    datum_set: DatumSet = model.datum_set

    # element reach, resolved from the groups rather than counted per element
    reach: dict[str, int] = {}
    kinds: dict[str, set[str]] = {}
    for group in model.element_groups:
        for ref in group.datum_refs:
            reach[ref] = reach.get(ref, 0) + len(group.instances)
            kinds.setdefault(ref, set()).add(group.kind)

    by_dimension: dict[str, list] = {}
    for datum in datum_set.datums:
        if datum.driving_dimension:
            by_dimension.setdefault(datum.driving_dimension, []).append(datum)

    emitted = {dimension.id: dimension for dimension in score.dimensions}
    dimensions: list[DimensionHealth] = []

    for dimension_id, label in DIMENSION_LABELS.items():
        emitted_dimension = emitted.get(dimension_id)
        sources = [f for f in (_feature(features, name)
                               for name in _SOURCES.get(dimension_id, ()))
                   if f is not None]

        if emitted_dimension is None:
            grade, note = _grade(False, 'absent', 0.0, 0)
            dimensions.append(DimensionHealth(
                id=dimension_id, label=label, present=False, evidence='absent',
                grade=grade, source_features=sources, note=note))
            continue

        travel = confidence_factor(emitted_dimension.confidence)
        evidence: Evidence = (
            'measured' if emitted_dimension.extraction_method == 'observed'
            else 'proxy')
        driven: list[DrivenDatum] = []
        total_reach = 0
        for datum in by_dimension.get(dimension_id, []):
            low, high = datum.output_range or (0.0, 0.0)
            count = reach.get(datum.id, 0)
            total_reach += count
            driven.append(DrivenDatum(
                id=datum.id, label=DATUM_LABELS.get(datum.id, datum.id),
                value=datum.value, unit=datum.unit,
                range_low=low, range_high=high,
                applied_position=datum.applied_position or 0.5,
                travel=travel, clamped=datum.clamped,
                element_count=count, element_kinds=sorted(kinds.get(datum.id, set())),
                reason=datum.reason))

        grade, note = _grade(True, evidence, travel, total_reach)
        dimensions.append(DimensionHealth(
            id=dimension_id, label=label, present=True, evidence=evidence, grade=grade,
            value=emitted_dimension.value,
            extraction_method=emitted_dimension.extraction_method,
            confidence=emitted_dimension.confidence, travel=travel,
            source_features=sources, proposal=emitted_dimension.architectural_proposal,
            datums=driven, element_count=total_reach, note=note))

    constants = [
        TectonicConstant(id=datum.id, label=DATUM_LABELS.get(datum.id, datum.id),
                         value=datum.value, unit=datum.unit, reason=datum.reason)
        for datum in datum_set.datums if datum.provenance == 'tectonic_constant'
    ]
    variables = [d for d in datum_set.datums if d.provenance != 'tectonic_constant']

    gates = model.facade_gates
    selection = model.selection
    return TranslationReport(
        typology=model.typology,
        massing_id=selection.massing_id if selection else 'MAS-SLAB',
        massing_label=selection.massing_label if selection else 'Stacked slab',
        facade_grammar_id=model.facade_grammar_id,
        structural_system_id=model.structural_system_id,
        selection_reasoning=(list(selection.massing_reason) if selection else []),
        facade_gates_passed=(sum(1 for g in gates.gates if g.verdict == 'passed')
                             if gates else 0),
        facade_gates_total=len(gates.gates) if gates else 0,
        facade_gates_unevaluated=(
            sum(1 for g in gates.gates if g.verdict == 'unevaluated')
            if gates else 0),
        facade_gate_correction=gates.corrected if gates else None,
        score_id=score.score_id, model_id=model.model_id,
        source_filename=features.provenance.filename,
        duration_seconds=features.provenance.duration_seconds,
        dimensions_emitted=len(score.dimensions),
        datum_count=len(datum_set.datums), variable_datum_count=len(variables),
        coverage=datum_set.coverage, variable_coverage=datum_set.variable_coverage,
        clamped_datum_count=len(datum_set.clamped_datums),
        element_count=model.element_count,
        element_kind_count=len(model.element_counts),
        dimensions=dimensions, constants=constants,
        program_fulfilment=model.program_allocation.fulfilment,
        program_fits=model.program_allocation.fits,
        program_unplaced=[space.label for space in model.program_allocation.unplaced],
        limitations=model.limitations)
