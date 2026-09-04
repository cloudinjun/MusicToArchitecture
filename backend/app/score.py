"""Audio features -> the ten shared score dimensions.

Decision 0004 defines ten dimensions. The MVP observed four and left six unsupported,
which meant six of the datum set's variables were declared design fixtures and the music
could not reach them. This module now emits all ten, but not on equal terms, and the
difference is the point:

- **observed** -- there is a direct measurement of the thing named. Repetition really is
  a self-similarity measurement; hierarchy really is a dynamic-range measurement.
- **inferred** -- the measurement is a defensible proxy for the thing named, not the
  thing itself. Polyphony is inferred from spectral contrast and harmonic share; nothing
  here counts voices.
- Confidence carries the rest of the honesty. A dimension at 0.35 must not be allowed to
  move a major architectural decision, and the datum layer clamps accordingly.

`genre_style` deserves its own note. Genre classification from raw audio is a trained-
model problem and this project has no model. What is measurable is a **timbral position**
-- bright and percussive against dark and sustained -- so that is what is emitted, at low
confidence, and its architectural proposal is a facade-grammar *weighting* that a human
accepts or rejects. It never selects a grammar, and it is never presented as a genre.

A dimension whose source metric is absent from the audio features is simply not emitted.
The datum layer then records `provenance='design_fixture'`, so a shortened score stays
visible in every downstream report instead of being padded with invented values.
"""

from __future__ import annotations

from .models import ArchitecturalScore, AudioFeatures, MappingRule, ScoreDimension


def _blend(*pairs: tuple[float, float]) -> float:
    """Weighted blend of normalised metrics, clamped to 0..1."""
    total = sum(weight for _, weight in pairs)
    value = sum(metric * weight for metric, weight in pairs) / total
    return max(0.0, min(1.0, value))


def compile_architectural_score(features: AudioFeatures) -> ArchitecturalScore:
    dimensions: list[ScoreDimension] = [
        ScoreDimension(
            id='tempo_of_change',
            value=features.tempo_bpm.normalized,
            source_feature='tempo_bpm',
            extraction_method='observed',
            confidence=features.tempo_bpm.confidence,
            architectural_proposal=(
                'Stack more distinct floor episodes and change the module more often '
                'along the public sequence.'),
        ),
        ScoreDimension(
            id='tension_release',
            value=features.rms_energy.normalized,
            source_feature='rms_energy',
            extraction_method='observed',
            confidence=features.rms_energy.confidence,
            architectural_proposal=(
                'Open the section: more headroom and deeper shading where the music '
                'releases, compression where it does not.'),
        ),
        ScoreDimension(
            id='density',
            value=features.onset_density_hz.normalized,
            source_feature='onset_density_hz',
            extraction_method='observed',
            confidence=features.onset_density_hz.confidence,
            architectural_proposal=(
                'Tighten the structural bay and the tertiary framing rhythm within the '
                'declared span limits.'),
        ),
        ScoreDimension(
            id='continuity',
            value=features.spectral_centroid_hz.normalized,
            source_feature='spectral_centroid_hz',
            extraction_method='inferred',
            confidence=0.72,
            architectural_proposal=(
                'Run the plate past its supports and round the end rather than cutting '
                'it; keep more of the floor for continuous routes.'),
        ),
    ]

    if features.periodicity is not None:
        dimensions.append(ScoreDimension(
            id='repetition',
            value=features.periodicity.normalized,
            source_feature='periodicity',
            extraction_method='observed',
            confidence=features.periodicity.confidence,
            architectural_proposal=(
                'Fix the envelope module and the tertiary rhythms -- mullion spacing, '
                'spandrel band, guard posts -- to a tighter, more regular cadence.'),
        ))

    if features.timbre_variation is not None:
        dimensions.append(ScoreDimension(
            id='variation',
            value=features.timbre_variation.normalized,
            source_feature='timbre_variation',
            extraction_method='observed',
            confidence=features.timbre_variation.confidence,
            architectural_proposal=(
                'Let the upper plates depart from the lower ones: step the plan back '
                'and rotate each level against the one below.'),
        ))

    if features.dynamic_range_db is not None:
        dimensions.append(ScoreDimension(
            id='hierarchy',
            value=features.dynamic_range_db.normalized,
            source_feature='dynamic_range_db',
            extraction_method='observed',
            confidence=features.dynamic_range_db.confidence,
            architectural_proposal=(
                'Make one structural order dominate: a deeper roof truss, a taller open '
                'ground level, a larger entry gesture.'),
        ))

    if features.novelty_peak_rate_per_min is not None:
        dimensions.append(ScoreDimension(
            id='interruption',
            value=features.novelty_peak_rate_per_min.normalized,
            source_feature='novelty_peak_rate_per_min',
            extraction_method='observed',
            confidence=features.novelty_peak_rate_per_min.confidence,
            architectural_proposal=(
                'Break the stack: punch atrium voids through the plates and strip the '
                'envelope from whole levels to make terraces.'),
        ))

    if features.spectral_contrast_db is not None and features.harmonic_ratio is not None:
        dimensions.append(ScoreDimension(
            id='polyphony',
            value=_blend((features.spectral_contrast_db.normalized, 0.6),
                         (features.harmonic_ratio.normalized, 0.4)),
            source_feature='spectral_contrast_db+harmonic_ratio',
            extraction_method='inferred',
            confidence=0.55,
            architectural_proposal=(
                'Separate the orders so each reads on its own: push the envelope further '
                'outboard of the frame, add screen and shading layers, express more '
                'braced bays. This is a layering proxy, not a count of voices.'),
        ))

    if (features.spectral_flatness is not None
            and features.zero_crossing_rate is not None
            and features.harmonic_ratio is not None):
        dimensions.append(ScoreDimension(
            id='genre_style',
            value=_blend((features.spectral_flatness.normalized, 0.3),
                         (features.zero_crossing_rate.normalized, 0.3),
                         (features.spectral_centroid_hz.normalized, 0.2),
                         (1.0 - features.harmonic_ratio.normalized, 0.2)),
            source_feature=(
                'spectral_flatness+zero_crossing_rate+spectral_centroid_hz'
                '+harmonic_ratio'),
            extraction_method='inferred',
            confidence=0.35,
            architectural_proposal=(
                'A timbral position, bright and percussive against dark and sustained. '
                'It proposes a weighting between a light glazed envelope and a heavier '
                'panelled one, and a fin depth to match. It is not a genre label, it '
                'never selects a facade grammar, and a human must accept the weighting.'),
        ))

    # The v2 rules stay.  binds elements to them, 
    # joins on them, and the acceptance chain reads the result: a schema 3.0 addition
    # must never break the massing contract that is already accepted downstream.
    rules = [
        MappingRule(id='TEMPO_TO_EPISODES', source_dimension='tempo_of_change',
                    target_parameter='sequence.episode_count', output_range=(4.0, 7.0),
                    direction='direct', priority=10),
        MappingRule(id='ENERGY_TO_READING_HEIGHT', source_dimension='tension_release',
                    target_parameter='program.reading_height', output_range=(5.4, 7.2),
                    direction='direct', priority=20),
        MappingRule(id='DENSITY_TO_GRID', source_dimension='density',
                    target_parameter='structure.bay_spacing', output_range=(5.2, 4.4),
                    direction='inverse', priority=30),
        MappingRule(id='DENSITY_TO_FACADE', source_dimension='density',
                    target_parameter='facade.submodule_count', output_range=(2.0, 5.0),
                    direction='direct', priority=40),
        MappingRule(id='DENSITY_TO_SERVICE_DEPTH', source_dimension='density',
                    target_parameter='program.service_depth', output_range=(2.6, 3.4),
                    direction='direct', priority=45),
        MappingRule(id='CONTINUITY_TO_SPINE', source_dimension='continuity',
                    target_parameter='circulation.spine_width', output_range=(1.8, 2.6),
                    direction='direct', priority=50),
        MappingRule(id='CONTINUITY_TO_DATUM', source_dimension='continuity',
                    target_parameter='facade.datum_offset', output_range=(0.18, 0.04),
                    direction='inverse', priority=60),
        # --- schema 3.0 datum rules ---
        MappingRule(id='TEMPO_TO_LEVEL_COUNT', source_dimension='tempo_of_change',
                    target_parameter='lattice.level_count', output_range=(4.0, 7.0),
                    direction='direct', priority=10),
        MappingRule(id='TENSION_TO_FLOOR_HEIGHT', source_dimension='tension_release',
                    target_parameter='lattice.floor_to_floor_m', output_range=(3.9, 5.4),
                    direction='direct', priority=20),
        MappingRule(id='DENSITY_TO_BAY_X', source_dimension='density',
                    target_parameter='grid.bay_x_m', output_range=(7.8, 5.6),
                    direction='inverse', priority=30),
        MappingRule(id='DENSITY_TO_JOIST_SPACING', source_dimension='density',
                    target_parameter='structure.joist_spacing_m',
                    output_range=(2.6, 1.5), direction='inverse', priority=35),
        MappingRule(id='CONTINUITY_TO_CANTILEVER', source_dimension='continuity',
                    target_parameter='plate.cantilever_m', output_range=(0.6, 3.6),
                    direction='direct', priority=40),
        MappingRule(id='REPETITION_TO_MULLION', source_dimension='repetition',
                    target_parameter='envelope.mullion_module_m',
                    output_range=(1.55, 1.15), direction='inverse', priority=50),
        MappingRule(id='VARIATION_TO_PLATE_STEP', source_dimension='variation',
                    target_parameter='plate.step_m', output_range=(0.0, 5.5),
                    direction='direct', priority=55),
        MappingRule(id='HIERARCHY_TO_TRUSS_DEPTH', source_dimension='hierarchy',
                    target_parameter='structure.truss_depth_m', output_range=(1.5, 3.0),
                    direction='direct', priority=60),
        MappingRule(id='INTERRUPTION_TO_VOIDS', source_dimension='interruption',
                    target_parameter='plate.void_count', output_range=(0.0, 3.0),
                    direction='direct', priority=65),
        MappingRule(id='POLYPHONY_TO_ENVELOPE_OFFSET', source_dimension='polyphony',
                    target_parameter='envelope.offset_m', output_range=(0.15, 0.90),
                    direction='direct', priority=70),
        MappingRule(id='GENRE_TO_OPAQUE_FRACTION', source_dimension='genre_style',
                    target_parameter='envelope.opaque_fraction',
                    output_range=(0.45, 0.10), direction='inverse', priority=80,
                    owner='architecture'),
    ]

    return ArchitecturalScore(
        score_id=f'score-{features.provenance.sha256[:12]}',
        source_audio_sha256=features.provenance.sha256,
        dimensions=dimensions,
        mapping_rules=rules,
    )
