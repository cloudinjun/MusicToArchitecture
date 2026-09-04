from __future__ import annotations

import math

from .library_config import (
    DESIGN_VERSION,
    FACADE_PROFILE,
    LIBRARY_SPACE_SPECS,
    PROGRAM_RELATION_SPECS,
    REQUIRED_LIBRARY_SPACE_TYPES,
    STRUCTURAL_PROFILE,
)
from .models import (
    ArchitecturalScore,
    AudioFeatures,
    BuildingElement,
    BuildingModel,
    FacadeProfile,
    GenerationParameters,
    GridModel,
    ProgramRelation,
    ScoreBinding,
    SiteModel,
    StructuralProfile,
    ValidationCheck,
    Vector3Value,
)


SITE = SiteModel(width=44.0, length=32.0, max_height=9.0)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _lerp(low: float, high: float, amount: float) -> float:
    return low + (high - low) * _clamp(amount, 0.0, 1.0)


def _binding(source: str, source_value: float, target: str, applied: float, rule: str) -> ScoreBinding:
    return ScoreBinding(
        source_dimension=source,
        source_value=round(source_value, 6),
        target_parameter=target,
        applied_value=round(applied, 6),
        rule_id=rule,
    )


def _dimension_values(score: ArchitecturalScore) -> dict[str, float]:
    return {dimension.id: dimension.value for dimension in score.dimensions}


def _program_spaces(
    energy: float,
    density: float,
    continuity: float,
    tempo: float,
) -> tuple[list[BuildingElement], float, float, int, float]:
    reading_height = _lerp(5.4, 7.2, energy)
    service_depth = _lerp(2.6, 3.4, density)
    spine_width = _lerp(1.8, 2.6, continuity)
    episode_count = int(round(_lerp(4.0, 7.0, tempo)))
    elements: list[BuildingElement] = []

    for spec in LIBRARY_SPACE_SPECS:
        (
            element_id, name, space_type, category, access_class,
            x0, x1, y0, y1, base_height, exterior_faces,
        ) = spec
        if space_type == 'primary_circulation':
            y0, y1 = -2.0 - spine_width / 2.0, -2.0 + spine_width / 2.0
        height = reading_height if space_type in {'adult_reading', 'quiet_reading'} else base_height
        if category == 'circulation':
            binding = _binding(
                'continuity', continuity, 'circulation.spine_width', spine_width,
                'CONTINUITY_TO_SPINE',
            )
        elif category in {'private', 'service'}:
            binding = _binding(
                'density', density, 'program.service_depth', service_depth,
                'DENSITY_TO_SERVICE_DEPTH',
            )
        elif space_type in {
            'adult_reading', 'quiet_reading', 'children_reading', 'open_stacks',
            'periodicals_media',
        }:
            binding = _binding(
                'tension_release', energy, 'program.reading_height', height,
                'ENERGY_TO_READING_HEIGHT',
            )
        else:
            binding = _binding(
                'tempo_of_change', tempo, 'sequence.episode_count', episode_count,
                'TEMPO_TO_EPISODES',
            )
        elements.append(BuildingElement(
            id=element_id,
            kind='massing',
            semantic_layer='circulation' if category == 'circulation' else 'program',
            subsystem='program_massing',
            program=space_type,
            category=category,
            position=Vector3Value(
                x=round((x0 + x1) / 2.0, 4),
                y=round((y0 + y1) / 2.0, 4),
                z=round(height / 2.0, 4),
            ),
            dimensions=Vector3Value(
                x=round(x1 - x0, 4), y=round(y1 - y0, 4), z=round(height, 4),
            ),
            space_type=space_type,
            access_class=access_class,
            material_profile='program_volume',
            exterior_faces=list(exterior_faces),
            program_constraints=[f'program:{space_type}', f'access:{access_class}'],
            rule_refs=['PRG-LIB-CONSTITUTION-001', 'PRG-BASE-SUPPORT-001'],
            reason=f'{name} is required by the integrated library demonstration constitution.',
            validation_status='code_inputs_incomplete',
            score_bindings=[binding],
        ))
    return elements, reading_height, service_depth, episode_count, spine_width


def _program_relations() -> list[ProgramRelation]:
    return [
        ProgramRelation(
            id=relation_id,
            source_id=source_id,
            target_id=target_id,
            relation=relation,
            rule_id=rule_id,
            status='pass',
            reason=reason,
        )
        for relation_id, source_id, target_id, relation, rule_id, reason
        in PROGRAM_RELATION_SPECS
    ]


def _structural_elements(
    spaces: list[BuildingElement],
    density: float,
    reading_height: float,
) -> tuple[list[BuildingElement], GridModel]:
    del spaces  # The accepted row boundaries below are derived from the program fixture.
    target_spacing = _lerp(5.2, 4.4, density)
    bay_count = max(6, min(7, round(30.0 / target_spacing)))
    spacing_x = 30.0 / bay_count
    x_lines = [-15.0 + index * spacing_x for index in range(bay_count + 1)]
    y_lines = [-8.0, -3.4, -0.6, 6.0, 9.0]
    row_heights = [4.8, 5.2, reading_height, reading_height, 3.8]
    column_size = 0.28
    elements: list[BuildingElement] = []
    foundation_ids: dict[tuple[int, int], str] = {}
    column_ids: dict[tuple[int, int], str] = {}
    binding = _binding(
        'density', density, 'structure.bay_spacing', spacing_x, 'DENSITY_TO_GRID',
    )

    for xi, x in enumerate(x_lines):
        for yi, y in enumerate(y_lines):
            foundation_id = f'STR-FDN-X{xi:02d}-Y{yi:02d}'
            column_id = f'STR-COL-X{xi:02d}-Y{yi:02d}'
            foundation_ids[(xi, yi)] = foundation_id
            column_ids[(xi, yi)] = column_id
            category = 'service' if y >= 6.0 else 'public'
            elements.append(BuildingElement(
                id=foundation_id,
                kind='foundation', semantic_layer='structure', subsystem='foundations',
                program='structure', category=category,
                position=Vector3Value(x=round(x, 4), y=y, z=-0.25),
                dimensions=Vector3Value(x=1.15, y=1.15, z=0.5),
                material_profile='reinforced_concrete_foundation_candidate',
                supports_elements=[column_id],
                rule_refs=['STR-LOAD-PATH-FOUNDATION-001'],
                reason='Candidate pad foundation terminates one explicit gravity load path; soils remain unresolved.',
                validation_status='professional_review_required',
                score_bindings=[binding],
            ))
            height = row_heights[yi]
            elements.append(BuildingElement(
                id=column_id,
                kind='column', semantic_layer='structure', subsystem='columns',
                program='structure', category=category,
                position=Vector3Value(x=round(x, 4), y=y, z=round(height / 2.0, 4)),
                dimensions=Vector3Value(x=column_size, y=column_size, z=round(height, 4)),
                material_profile='steel_hss_column_candidate',
                supports=[foundation_id],
                rule_refs=['STR-STEEL-GRAVITY-001', 'STR-COLUMN-BOUNDARY-001'],
                reason='Column lies on a room, circulation, or perimeter datum rather than inside a protected public path.',
                validation_status='professional_review_required',
                score_bindings=[binding],
            ))

    beam_depth = 0.46
    beam_width = 0.24
    beam_ids_by_zone: dict[str, list[str]] = {'south': [], 'spine': [], 'main': [], 'service': []}
    row_zone = ['south', 'south', 'main', 'main', 'service']
    for yi, y in enumerate(y_lines):
        z = row_heights[yi] - beam_depth / 2.0
        for xi in range(bay_count):
            beam_id = f'STR-BEAM-X-X{xi:02d}-Y{yi:02d}'
            beam_ids_by_zone[row_zone[yi]].append(beam_id)
            elements.append(BuildingElement(
                id=beam_id,
                kind='beam', semantic_layer='structure', subsystem='beams',
                program='structure', category='service' if y >= 6.0 else 'public',
                position=Vector3Value(x=round((x_lines[xi] + x_lines[xi + 1]) / 2.0, 4), y=y, z=round(z, 4)),
                dimensions=Vector3Value(x=round(spacing_x, 4), y=beam_width, z=beam_depth),
                material_profile='steel_wide_flange_beam_candidate',
                supports=[column_ids[(xi, yi)], column_ids[(xi + 1, yi)]],
                rule_refs=['STR-STEEL-GRAVITY-001'],
                reason='East-west primary beam spans between explicit steel column nodes.',
                validation_status='professional_review_required',
                score_bindings=[binding],
            ))

    zone_heights = [4.8, 5.2, reading_height, 3.8]
    zone_names = ['south', 'spine', 'main', 'service']
    for xi, x in enumerate(x_lines):
        for zi in range(len(y_lines) - 1):
            y0, y1 = y_lines[zi], y_lines[zi + 1]
            beam_id = f'STR-BEAM-Y-X{xi:02d}-Z{zi:02d}'
            beam_ids_by_zone[zone_names[zi]].append(beam_id)
            elements.append(BuildingElement(
                id=beam_id,
                kind='beam', semantic_layer='structure', subsystem='beams',
                program='structure', category='service' if zi == 3 else 'public',
                position=Vector3Value(x=round(x, 4), y=round((y0 + y1) / 2.0, 4), z=round(zone_heights[zi] - beam_depth / 2.0, 4)),
                dimensions=Vector3Value(x=beam_width, y=round(y1 - y0, 4), z=beam_depth),
                material_profile='steel_wide_flange_beam_candidate',
                supports=[column_ids[(xi, zi)], column_ids[(xi, zi + 1)]],
                rule_refs=['STR-STEEL-GRAVITY-001'],
                reason='North-south secondary beam closes one roof bay and returns to column nodes.',
                validation_status='professional_review_required',
                score_bindings=[binding],
            ))

    roof_zones = (
        ('south', -5.7, 4.6, 4.8),
        ('spine', -2.0, 2.8, 5.2),
        ('main', 2.7, 6.6, reading_height),
        ('service', 7.5, 3.0, 3.8),
    )
    for zone, y, depth, height in roof_zones:
        elements.append(BuildingElement(
            id=f'STR-SLAB-ROOF-{zone.upper()}',
            kind='slab', semantic_layer='structure', subsystem='slabs',
            program='structure', category='service' if zone == 'service' else 'public',
            position=Vector3Value(x=0.0, y=y, z=round(height - 0.11, 4)),
            dimensions=Vector3Value(x=30.0, y=depth, z=0.22),
            material_profile='composite_metal_deck_candidate',
            supports=beam_ids_by_zone[zone],
            rule_refs=['STR-STEEL-DIAPHRAGM-001'],
            reason=f'{zone.title()} roof diaphragm candidate spans to the declared beam graph.',
            validation_status='professional_review_required',
            score_bindings=[binding],
        ))
    elements.append(BuildingElement(
        id='STR-SLAB-GROUND-001',
        kind='slab', semantic_layer='structure', subsystem='slabs',
        program='structure', category='public',
        position=Vector3Value(x=0.0, y=0.5, z=0.1),
        dimensions=Vector3Value(x=30.0, y=17.0, z=0.2),
        material_profile='reinforced_concrete_slab_on_grade_candidate',
        supports=list(foundation_ids.values()),
        rule_refs=['STR-GROUND-SLAB-001'],
        reason='Continuous ground slab coordinates the complete program footprint; soils remain unresolved.',
        validation_status='professional_review_required',
        score_bindings=[binding],
    ))

    for bay_index, xi in enumerate((bay_count - 1, 0), start=1):
        x0, x1 = x_lines[xi], x_lines[xi + 1]
        height = 4.8
        for diagonal, (start_x, end_x) in enumerate(((x0, x1), (x1, x0)), start=1):
            length = math.hypot(end_x - start_x, height - 0.55)
            angle = math.atan2(end_x - start_x, height - 0.55)
            elements.append(BuildingElement(
                id=f'STR-BRACE-SOUTH-{bay_index:02d}-{diagonal:02d}',
                kind='brace', semantic_layer='structure', subsystem='bracing',
                program='structure', category='public',
                position=Vector3Value(x=round((start_x + end_x) / 2.0, 4), y=-7.82, z=round((height + 0.55) / 2.0, 4)),
                dimensions=Vector3Value(x=0.18, y=0.18, z=round(length, 4)),
                rotation=Vector3Value(x=0.0, y=round(angle, 6), z=0.0),
                material_profile='steel_hss_brace_candidate',
                supports=[column_ids[(xi, 0)], column_ids[(xi + 1, 0)]],
                rule_refs=['STR-STEEL-LATERAL-001'],
                reason='Perimeter braced bay provides an inspectable lateral-system candidate outside the entry opening.',
                validation_status='professional_review_required',
                score_bindings=[binding],
            ))

    core_supports = [foundation_ids[(bay_count - 1, 4)], foundation_ids[(bay_count, 4)]]
    for index, (position, dimensions) in enumerate((
        ((10.2, 7.5, 1.9), (0.24, 3.0, 3.8)),
        ((11.2, 7.5, 1.9), (0.24, 3.0, 3.8)),
        ((10.7, 8.86, 1.9), (1.24, 0.24, 3.8)),
    ), start=1):
        elements.append(BuildingElement(
            id=f'STR-CORE-WALL-{index:02d}',
            kind='core', semantic_layer='structure', subsystem='cores',
            program='structure', category='service',
            position=Vector3Value(x=position[0], y=position[1], z=position[2]),
            dimensions=Vector3Value(x=dimensions[0], y=dimensions[1], z=dimensions[2]),
            material_profile='reinforced_concrete_core_candidate',
            supports=core_supports,
            program_constraints=['SP-L01-ELECTRICAL-001', 'SP-L01-MECHANICAL-001'],
            rule_refs=['STR-CORE-SERVICE-COORD-001'],
            reason='Compact service-zone core candidate avoids the public and accessible circulation graph.',
            validation_status='professional_review_required',
            score_bindings=[binding],
        ))

    return elements, GridModel(
        spacing_x=round(spacing_x, 4), spacing_y=round(y_lines[2] - y_lines[1], 4),
        column_size=column_size,
    )


def _face_geometry(space: BuildingElement, face: str, along_center: float, bay_width: float, z: float, depth: float):
    x, y = space.position.x, space.position.y
    dx, dy = space.dimensions.x, space.dimensions.y
    if face == 'south':
        return (along_center, y - dy / 2.0 - depth / 2.0, z), (bay_width, depth, 1.0)
    if face == 'north':
        return (along_center, y + dy / 2.0 + depth / 2.0, z), (bay_width, depth, 1.0)
    if face == 'west':
        return (x - dx / 2.0 - depth / 2.0, along_center, z), (depth, bay_width, 1.0)
    return (x + dx / 2.0 + depth / 2.0, along_center, z), (depth, bay_width, 1.0)


def _facade_elements(
    spaces: list[BuildingElement],
    structure: list[BuildingElement],
    density: float,
    continuity: float,
) -> tuple[list[BuildingElement], int, float]:
    submodule_count = int(round(_lerp(2.0, 5.0, density)))
    datum_offset = _lerp(0.18, 0.04, continuity)
    target_bay = _lerp(3.2, 2.0, density)
    beams = [element for element in structure if element.kind == 'beam']
    elements: list[BuildingElement] = []
    thickness = 0.18

    def nearest_beam_id(position: tuple[float, float, float]) -> str:
        return min(
            beams,
            key=lambda beam: (
                (beam.position.x - position[0]) ** 2
                + (beam.position.y - position[1]) ** 2
                + 0.15 * (beam.position.z - position[2]) ** 2
            ),
        ).id

    for space in spaces:
        for face in space.exterior_faces:
            horizontal = face in {'north', 'south'}
            start = space.position.x - space.dimensions.x / 2.0 if horizontal else space.position.y - space.dimensions.y / 2.0
            length = space.dimensions.x if horizontal else space.dimensions.y
            count = max(1, math.ceil(length / target_bay))
            bay_width = length / count
            host_id = f'host-{space.id}-{face}'
            height = space.dimensions.z
            base_height = 0.72
            head_height = 0.42
            available = height - base_height - head_height
            if space.category == 'service':
                glass_height = min(1.05, available)
            elif space.category == 'private':
                glass_height = min(1.35, available)
            elif space.category == 'circulation':
                glass_height = available * 0.92
            else:
                glass_height = available * 0.78
            mid_height = max(0.0, available - glass_height)

            for index in range(count):
                along_center = start + (index + 0.5) * bay_width
                support_id = f'FCD-SUPPORT-{space.id}-{face}-{index + 1:02d}'
                facade_binding = _binding(
                    'density', density, 'facade.submodule_count', submodule_count,
                    'DENSITY_TO_FACADE',
                )
                panel_binding = _binding(
                    'continuity', continuity, 'facade.datum_offset', datum_offset,
                    'CONTINUITY_TO_DATUM',
                )
                support_position, _ = _face_geometry(
                    space, face, along_center, bay_width, height / 2.0, thickness,
                )
                support_dimensions = (0.10, 0.12, height) if horizontal else (0.12, 0.10, height)
                elements.append(BuildingElement(
                    id=support_id,
                    kind='facade_support', semantic_layer='facade', subsystem='facade',
                    program=space.program, category=space.category,
                    position=Vector3Value(x=round(support_position[0], 4), y=round(support_position[1], 4), z=round(height / 2.0, 4)),
                    dimensions=Vector3Value(x=support_dimensions[0], y=support_dimensions[1], z=round(height, 4)),
                    material_profile='steel_facade_support_candidate',
                    host_surface_id=host_id,
                    supports=[nearest_beam_id(support_position)],
                    program_constraints=[space.id],
                    rule_refs=['IS-INV-06', 'FCD-SUPPORT-PRIMARY-001'],
                    reason='Secondary facade support returns the modular envelope bay to the nearest primary beam candidate.',
                    validation_status='professional_review_required',
                    score_bindings=[facade_binding],
                ))

                pieces = [
                    ('base', 'facade_panel', base_height / 2.0, base_height, 'insulated_aluminum_panel_candidate', panel_binding),
                    ('vision', 'glazing', base_height + glass_height / 2.0, glass_height, 'vision_glass_candidate', facade_binding),
                ]
                if mid_height > 0.08:
                    pieces.append((
                        'opaque', 'facade_panel', base_height + glass_height + mid_height / 2.0,
                        mid_height, 'insulated_aluminum_panel_candidate', panel_binding,
                    ))
                pieces.append((
                    'head', 'facade_panel', height - head_height / 2.0, head_height,
                    'insulated_aluminum_panel_candidate', panel_binding,
                ))
                for role, kind, z, piece_height, material, binding in pieces:
                    position, base_dims = _face_geometry(
                        space, face, along_center, bay_width - 0.035, z, thickness,
                    )
                    elements.append(BuildingElement(
                        id=f'FCD-{role.upper()}-{space.id}-{face}-{index + 1:02d}',
                        kind=kind, semantic_layer='facade', subsystem='facade',
                        program=space.program, category=space.category,
                        position=Vector3Value(x=round(position[0], 4), y=round(position[1], 4), z=round(z, 4)),
                        dimensions=Vector3Value(x=round(base_dims[0], 4), y=round(base_dims[1], 4), z=round(piece_height, 4)),
                        material_profile=material,
                        host_surface_id=host_id,
                        supports=[support_id],
                        program_constraints=[space.id],
                        rule_refs=['IS-INV-01', 'IS-INV-03', 'IS-INV-04'],
                        reason=f'{role.title()} module resolves to the International Style-informed facade datum and its program-owned zone.',
                        validation_status='professional_review_required',
                        score_bindings=[binding],
                    ))

                mullion_positions = [start + index * bay_width]
                if index == count - 1:
                    mullion_positions.append(start + (index + 1) * bay_width)
                for mullion_index, mullion_coord in enumerate(mullion_positions, start=1):
                    position, _ = _face_geometry(
                        space, face, mullion_coord, 0.08, height / 2.0, thickness + 0.04,
                    )
                    mullion_dims = (0.08, thickness + 0.04, height) if horizontal else (thickness + 0.04, 0.08, height)
                    elements.append(BuildingElement(
                        id=f'FCD-MULLION-{space.id}-{face}-{index + 1:02d}-{mullion_index:02d}',
                        kind='mullion', semantic_layer='facade', subsystem='facade',
                        program=space.program, category=space.category,
                        position=Vector3Value(x=round(position[0], 4), y=round(position[1], 4), z=round(height / 2.0, 4)),
                        dimensions=Vector3Value(x=mullion_dims[0], y=mullion_dims[1], z=round(height, 4)),
                        material_profile='aluminum_mullion_candidate',
                        host_surface_id=host_id,
                        supports=[support_id],
                        program_constraints=[space.id],
                        rule_refs=['IS-INV-01', 'IS-INV-03'],
                        reason='Mullion records the recoverable base module and joint datum.',
                        validation_status='professional_review_required',
                        score_bindings=[facade_binding],
                    ))

    entry_space = next(space for space in spaces if space.space_type == 'lobby_welcome_checkout')
    south_position = (
        entry_space.position.x,
        entry_space.position.y - entry_space.dimensions.y / 2.0 - 1.1,
        3.45,
    )
    nearest = nearest_beam_id(south_position)
    canopy_binding = _binding(
        'continuity', continuity, 'facade.datum_offset', datum_offset,
        'CONTINUITY_TO_DATUM',
    )
    elements.append(BuildingElement(
        id='FCD-CANOPY-MAIN-ENTRY-001',
        kind='canopy', semantic_layer='facade', subsystem='facade',
        program=entry_space.program, category='circulation',
        position=Vector3Value(x=round(south_position[0], 4), y=round(south_position[1], 4), z=south_position[2]),
        dimensions=Vector3Value(x=4.2, y=2.2, z=0.24),
        material_profile='painted_steel_canopy_candidate',
        host_surface_id=f'host-{entry_space.id}-south',
        supports=[nearest],
        program_constraints=[entry_space.id],
        rule_refs=['IS-INV-05', 'FCD-ENTRY-HIERARCHY-001'],
        reason='The recessed glazed entry receives a planar canopy, establishing hierarchy without applied ornament.',
        validation_status='professional_review_required',
        score_bindings=[canopy_binding],
    ))

    max_main_height = max(space.dimensions.z for space in spaces if -0.7 <= space.position.y <= 6.0)
    for zone, y, depth, height in (
        ('south', -5.7, 4.6, 4.8), ('spine', -2.0, 2.8, 5.2),
        ('main', 2.7, 6.6, max_main_height), ('service', 7.5, 3.0, 3.8),
    ):
        elements.append(BuildingElement(
            id=f'FCD-ROOF-{zone.upper()}-001',
            kind='facade_panel', semantic_layer='facade', subsystem='facade',
            program='roof_envelope', category='service' if zone == 'service' else 'public',
            position=Vector3Value(x=0.0, y=y, z=round(height + 0.04, 4)),
            dimensions=Vector3Value(x=30.0, y=depth, z=0.08),
            material_profile='single_ply_roof_membrane_candidate',
            host_surface_id=f'host-roof-{zone}',
            supports=[f'STR-SLAB-ROOF-{zone.upper()}'],
            rule_refs=['IS-INV-02', 'FCD-ROOF-CONTINUITY-001'],
            reason='Calm roof plane closes the envelope and remains traceable to its structural deck zone.',
            validation_status='professional_review_required',
            score_bindings=[canopy_binding],
        ))
    return elements, submodule_count, datum_offset


def _interior_sequence(tempo: float, continuity: float) -> tuple[list[BuildingElement], list[str]]:
    episode_count = int(round(_lerp(4.0, 7.0, tempo)))
    bindings = [
        _binding('tempo_of_change', tempo, 'sequence.episode_count', episode_count, 'TEMPO_TO_EPISODES'),
        _binding('continuity', continuity, 'circulation.spine_width', _lerp(1.8, 2.6, continuity), 'CONTINUITY_TO_SPINE'),
    ]
    specs = (
        ('INT-PATH-ARRIVAL-001', (-8.0, -9.2, 0.24), (1.2, 2.4, 0.08), 'arrival'),
        ('INT-PATH-LOBBY-001', (-5.0, -5.7, 0.24), (6.0, 1.0, 0.08), 'orientation'),
        ('INT-PATH-SPINE-001', (0.0, -2.0, 0.24), (22.0, 0.9, 0.08), 'continuous spine'),
        ('INT-PATH-STACKS-001', (-2.5, 0.4, 0.24), (1.0, 4.0, 0.08), 'collection threshold'),
        ('INT-PATH-READING-001', (-11.0, 2.7, 0.24), (7.0, 1.1, 0.08), 'reading-room release'),
    )
    elements = [
        BuildingElement(
            id=element_id,
            kind='interior_floor', semantic_layer='interior', subsystem='interior_sequence',
            program=role, category='circulation',
            position=Vector3Value(x=position[0], y=position[1], z=position[2]),
            dimensions=Vector3Value(x=dimensions[0], y=dimensions[1], z=dimensions[2]),
            material_profile='oak_wayfinding_floor_candidate',
            program_constraints=['SP-L01-VESTIBULE-001', 'SP-L01-LOBBY-001', 'SP-L01-SPINE-001'],
            rule_refs=['INT-SEQUENCE-LIBRARY-001'],
            reason=f'Key interior sequence episode: {role}.',
            validation_status='geometry_valid',
            score_bindings=bindings,
        )
        for element_id, position, dimensions, role in specs
    ]
    for portal_id, x, y, width, height, role in (
        ('INT-THRESHOLD-ENTRY', -8.0, -7.9, 1.8, 3.2, 'entry threshold'),
        ('INT-THRESHOLD-READING', -7.0, -0.5, 2.6, 4.2, 'reading-room threshold'),
    ):
        for suffix, px, pz, dims in (
            ('L', x - width / 2.0, height / 2.0, (0.16, 0.32, height)),
            ('R', x + width / 2.0, height / 2.0, (0.16, 0.32, height)),
            ('H', x, height - 0.08, (width + 0.16, 0.32, 0.16)),
        ):
            elements.append(BuildingElement(
                id=f'{portal_id}-{suffix}',
                kind='threshold_frame', semantic_layer='interior', subsystem='interior_sequence',
                program=role, category='circulation',
                position=Vector3Value(x=round(px, 4), y=y, z=round(pz, 4)),
                dimensions=Vector3Value(x=dims[0], y=dims[1], z=dims[2]),
                material_profile='dark_steel_threshold_candidate',
                rule_refs=['INT-SEQUENCE-HIERARCHY-001'],
                reason=f'Portal makes the {role} spatial episode visible in section.',
                validation_status='geometry_valid',
                score_bindings=bindings,
            ))
    return elements, [spec[0] for spec in specs]


def _validate(
    elements: list[BuildingElement],
    relations: list[ProgramRelation],
    grid: GridModel,
) -> list[ValidationCheck]:
    spaces = [element for element in elements if element.kind == 'massing']
    present_types = {space.space_type for space in spaces}
    missing_types = sorted(REQUIRED_LIBRARY_SPACE_TYPES - present_types)
    missing_categories = sorted(
        {'public', 'private', 'circulation', 'service'} - {space.category for space in spaces}
    )
    out_of_bounds = [
        element.id for element in elements
        if abs(element.position.x) + element.dimensions.x / 2.0 > SITE.width / 2.0 + 1e-6
        or abs(element.position.y) + element.dimensions.y / 2.0 > SITE.length / 2.0 + 1e-6
        or element.position.z + element.dimensions.z / 2.0 > SITE.max_height + 1e-6
    ]
    overlaps: list[str] = []
    for index, first in enumerate(spaces):
        for second in spaces[index + 1:]:
            overlap_x = abs(first.position.x - second.position.x) < (first.dimensions.x + second.dimensions.x) / 2.0 - 1e-6
            overlap_y = abs(first.position.y - second.position.y) < (first.dimensions.y + second.dimensions.y) / 2.0 - 1e-6
            if overlap_x and overlap_y:
                overlaps.extend([first.id, second.id])
    missing_bindings = [element.id for element in elements if not element.score_bindings]
    structure = [element for element in elements if element.semantic_layer == 'structure']
    unsupported = [element.id for element in structure if element.kind != 'foundation' and not element.supports]
    circulation = next(space for space in spaces if space.space_type == 'primary_circulation')
    circulation_conflicts = [
        element.id for element in structure if element.kind == 'column'
        and abs(element.position.x - circulation.position.x) < circulation.dimensions.x / 2.0 - 1e-6
        and abs(element.position.y - circulation.position.y) < circulation.dimensions.y / 2.0 - 1e-6
    ]
    facade = [element for element in elements if element.semantic_layer == 'facade']
    facade_without_host = [element.id for element in facade if not element.host_surface_id]
    facade_without_support = [element.id for element in facade if not element.supports]
    relation_failures = [relation.id for relation in relations if relation.status == 'fail']

    return [
        ValidationCheck(
            id='LIBRARY_REQUIRED_SPACES', status='pass' if not missing_types else 'fail',
            message='Detailed library and base-building support spaces are present.' if not missing_types else f'Missing required space types: {", ".join(missing_types)}.',
            affected_ids=missing_types,
        ),
        ValidationCheck(
            id='PROGRAM_CATEGORY_COVERAGE', status='pass' if not missing_categories else 'fail',
            message='Public, private, circulation, and service categories are represented.' if not missing_categories else f'Missing program categories: {", ".join(missing_categories)}.',
            affected_ids=missing_categories,
        ),
        ValidationCheck(
            id='PROGRAM_NON_OVERLAP', status='pass' if not overlaps else 'fail',
            message='All room-level program volumes are non-overlapping.' if not overlaps else 'Some room-level program volumes overlap.',
            affected_ids=sorted(set(overlaps)),
        ),
        ValidationCheck(
            id='PROGRAM_RELATION_GRAPH', status='pass' if not relation_failures else 'fail',
            message='The public, accessible, service, separation, and daylight relationship records are traceable.' if not relation_failures else 'Some program relations failed.',
            affected_ids=relation_failures,
        ),
        ValidationCheck(
            id='SITE_ENVELOPE', status='pass' if not out_of_bounds else 'fail',
            message='All generated building elements remain inside the test site and height envelope.' if not out_of_bounds else 'Some elements exceed the site or height envelope.',
            affected_ids=sorted(set(out_of_bounds)),
        ),
        ValidationCheck(
            id='STEEL_LOAD_PATH_TOPOLOGY', status='pass' if not unsupported else 'fail',
            message='Every non-foundation structural element names at least one support path.' if not unsupported else 'Some structural elements have no support path.',
            affected_ids=unsupported,
        ),
        ValidationCheck(
            id='CIRCULATION_COLUMN_EXCLUSION', status='pass' if not circulation_conflicts else 'fail',
            message='Primary steel columns remain outside the interior of the public circulation spine.' if not circulation_conflicts else 'Columns intersect the protected public circulation spine.',
            affected_ids=circulation_conflicts,
        ),
        ValidationCheck(
            id='FACADE_HOST_SUPPORT', status='pass' if not facade_without_host and not facade_without_support else 'fail',
            message='Every facade element resolves to a host and a declared primary or secondary support.' if not facade_without_host and not facade_without_support else 'Some facade elements lack host or support references.',
            affected_ids=sorted(set(facade_without_host + facade_without_support)),
        ),
        ValidationCheck(
            id='PROVENANCE_COVERAGE', status='pass' if not missing_bindings else 'warning',
            message='Every generated element records an executed Shared Score binding.' if not missing_bindings else 'Some elements lack score-binding provenance.',
            affected_ids=missing_bindings,
        ),
        ValidationCheck(
            id='FRAME_GRID_RANGE', status='pass' if 4.2 <= grid.spacing_x <= 5.4 else 'fail',
            message=f'Steel frame bay spacing is {grid.spacing_x:.2f} m within the test coordination range.',
        ),
        ValidationCheck(
            id='PROGRAM_CODE_PROFILE', status='warning',
            message='Occupancy, fixture counts, egress, accessibility, fire, and local amendments require a resolved jurisdiction profile.',
        ),
        ValidationCheck(
            id='STRUCTURAL_ENGINEERING_REVIEW', status='warning',
            message='Structural sections, loads, connections, diaphragm, fire protection, and foundations remain candidate geometry requiring professional review.',
        ),
    ]


def compile_building_model(features: AudioFeatures, score: ArchitecturalScore) -> BuildingModel:
    values = _dimension_values(score)
    tempo = values['tempo_of_change']
    energy = values['tension_release']
    density = values['density']
    continuity = values['continuity']

    program, reading_height, service_depth, episode_count, spine_width = _program_spaces(
        energy, density, continuity, tempo,
    )
    del service_depth
    relations = _program_relations()
    structure, grid = _structural_elements(program, density, reading_height)
    facade, facade_submodules, datum_offset = _facade_elements(program, structure, density, continuity)
    interior, sequence_ids = _interior_sequence(tempo, continuity)
    elements = [*program, *structure, *facade, *interior]

    parameters = GenerationParameters(
        module_count=episode_count,
        room_count=len(program),
        bay_spacing=grid.spacing_x,
        module_gap=round(datum_offset, 4),
        primary_height=round(reading_height, 4),
        primary_depth=17.0,
        visual_continuity=round(continuity, 4),
        facade_submodule_count=facade_submodules,
        circulation_spine_width=round(spine_width, 4),
    )
    return BuildingModel(
        model_id=f'building-{features.provenance.sha256[:12]}-{DESIGN_VERSION}',
        score_id=score.score_id,
        typology=score.typology,
        tectonic_system=score.tectonic_system,
        site=SITE,
        grid=grid,
        parameters=parameters,
        structural_profile=StructuralProfile(**STRUCTURAL_PROFILE),
        facade_profile=FacadeProfile(**FACADE_PROFILE),
        program_relations=relations,
        interior_sequence=sequence_ids,
        elements=elements,
        validation=_validate(elements, relations, grid),
    )
