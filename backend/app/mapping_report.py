from __future__ import annotations

from collections import defaultdict

from .models import (
    ArchitecturalScore,
    AudioFeatures,
    BuildingElement,
    BuildingModel,
    MappingReport,
    MappingReportEntry,
    ScoreBinding,
)


FEATURE_LABELS = {
    "tempo_bpm": "Tempo",
    "rms_energy": "Energy",
    "onset_density_hz": "Onset density",
    "spectral_centroid_hz": "Spectral continuity proxy",
}

DIMENSION_LABELS = {
    "tempo_of_change": "Tempo of change",
    "tension_release": "Tension / release",
    "density": "Density",
    "continuity": "Continuity",
}

TARGET_LABELS = {
    "sequence.episode_count": "Interior sequence episode count",
    "program.reading_height": "Reading-room spatial climax height",
    "structure.bay_spacing": "Structural bay spacing",
    "facade.submodule_count": "Facade submodule count",
    "program.service_depth": "Service-zone depth proposal",
    "circulation.spine_width": "Primary circulation spine width",
    "facade.datum_offset": "Facade datum offset",
}

APPLIED_UNITS = {
    "sequence.episode_count": "count",
    "program.reading_height": "m",
    "structure.bay_spacing": "m",
    "facade.submodule_count": "count",
    "program.service_depth": "m",
    "circulation.spine_width": "m",
    "facade.datum_offset": "m",
}

NEGOTIATION_NOTES = {
    "sequence.episode_count": "Rounded to a whole episode count; required library rooms remain invariant.",
    "program.reading_height": "Clamped by the site envelope and applied only to declared reading-space hierarchy.",
    "structure.bay_spacing": "Higher density proposes a tighter frame; the fixed footprint negotiates an integer bay count.",
    "facade.submodule_count": "Facade subdivision changes only inside the selected orthogonal grammar and host boundaries.",
    "program.service_depth": "The proposal is recorded on service spaces while the fixed demonstration constitution preserves their required footprint.",
    "circulation.spine_width": "Continuity widens the protected public route within the reserved non-overlap band.",
    "facade.datum_offset": "Higher continuity reduces the legal offset while preserving one recoverable facade datum.",
}

UNSUPPORTED_DIMENSIONS = [
    "genre_style",
    "hierarchy",
    "repetition",
    "variation",
    "interruption",
    "polyphony",
]


def _outcome(target: str, low: float, high: float, affected_count: int) -> str:
    if target == "sequence.episode_count":
        return f"{round(low)} linked interior and facade sequence episodes"
    if target == "program.reading_height":
        return f"{low:.2f}–{high:.2f} m reading-space hierarchy"
    if target == "structure.bay_spacing":
        return f"{low:.2f} m steel-frame bay spacing across {affected_count} structural elements"
    if target == "facade.submodule_count":
        return f"{round(low)} orthogonal facade submodules per controlled family"
    if target == "program.service_depth":
        return f"{low:.2f} m service-depth proposal retained with the detailed support constitution"
    if target == "circulation.spine_width":
        return f"{low:.2f} m continuous public spine and linked interior path"
    if target == "facade.datum_offset":
        return f"{low:.2f} m facade datum offset across {affected_count} envelope elements"
    return f"{low:.2f}–{high:.2f} applied to {affected_count} elements"


def _binding_groups(model: BuildingModel) -> dict[tuple[str, str], list[tuple[BuildingElement, ScoreBinding]]]:
    groups: dict[tuple[str, str], list[tuple[BuildingElement, ScoreBinding]]] = defaultdict(list)
    for element in model.elements:
        for binding in element.score_bindings:
            groups[(binding.rule_id, binding.target_parameter)].append((element, binding))
    return groups


def compile_mapping_report(
    features: AudioFeatures,
    score: ArchitecturalScore,
    model: BuildingModel,
) -> MappingReport:
    dimensions = {dimension.id: dimension for dimension in score.dimensions}
    rules = {rule.id: rule for rule in score.mapping_rules}
    groups = _binding_groups(model)
    entries = []

    ordered_groups = sorted(
        groups.items(),
        key=lambda item: (rules[item[0][0]].priority, item[0][1]),
    )
    for index, ((rule_id, target), linked) in enumerate(ordered_groups, start=1):
        rule = rules[rule_id]
        dimension = dimensions[rule.source_dimension]
        metric = getattr(features, dimension.source_feature)
        elements = [element for element, _ in linked]
        values = [binding.applied_value for _, binding in linked]
        applied_min, applied_max = min(values), max(values)
        entries.append(MappingReportEntry(
            id=f"translation-{index:02d}",
            rule_id=rule_id,
            music_feature=dimension.source_feature,
            music_feature_label=FEATURE_LABELS[dimension.source_feature],
            music_value=metric.value,
            music_normalized=metric.normalized,
            music_unit=metric.unit,
            music_method=metric.method,
            music_confidence=metric.confidence,
            shared_dimension=dimension.id,
            shared_dimension_label=DIMENSION_LABELS[dimension.id],
            score_value=dimension.value,
            extraction_method=dimension.extraction_method,
            score_confidence=dimension.confidence,
            architectural_proposal=dimension.architectural_proposal,
            architectural_target=target,
            architectural_target_label=TARGET_LABELS.get(target, target),
            mapping_direction=rule.direction,
            declared_output_range=rule.output_range,
            applied_min=round(applied_min, 6),
            applied_max=round(applied_max, 6),
            applied_unit=APPLIED_UNITS.get(target, "value"),
            outcome=_outcome(target, applied_min, applied_max, len(elements)),
            negotiation=NEGOTIATION_NOTES.get(target, "Applied through the accepted architectural rule."),
            affected_element_ids=sorted({element.id for element in elements}),
            affected_element_kinds=sorted({element.kind for element in elements}),
            affected_programs=sorted({element.program for element in elements}),
        ))

    covered_ids = {element_id for entry in entries for element_id in entry.affected_element_ids}
    total = len(model.elements)
    return MappingReport(
        report_id=f"mapping-{model.model_id.removeprefix('building-')}",
        score_id=score.score_id,
        model_id=model.model_id,
        source_audio_filename=features.provenance.filename,
        typology=model.typology,
        tectonic_system=model.tectonic_system,
        automated_dimensions=[dimension.id for dimension in score.dimensions],
        unsupported_dimensions=UNSUPPORTED_DIMENSIONS,
        covered_element_count=len(covered_ids),
        total_element_count=total,
        coverage_ratio=round(len(covered_ids) / total, 6) if total else 0.0,
        entries=entries,
        limitations=[
            "Only four of the ten Shared Score dimensions are automated in the MVP.",
            "Spectral centroid is an inferred continuity proxy, not a direct musical continuity measurement.",
            "Program, structure, facade, and interior elements are candidate contracts; code review, structural analysis, Grasshopper review, and Rhino acceptance remain separate.",
        ],
    )
