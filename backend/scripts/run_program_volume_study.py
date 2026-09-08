"""Generate comparable Program Volume candidates from one stored music response.

Example:

    .venv/Scripts/python.exe -m backend.scripts.run_program_volume_study \
      --response artifacts/.../response.json --typology museum \
      --out artifacts/skill_runs/.../program_volume_protocol \
      --grammars PVG-TERRACED-WEAVE --compile --render

Without ``--compile`` the command writes all form contracts in under a second. A
compiled run uses the shared v3 tail and can optionally issue drawings and the existing
Blender review package.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from backend.app.models import ArchitecturalScore
from backend.app.version import compiler_source_fingerprint
from backend.app.program_volumes import (
    ProgramVolumeGrammarId,
    compile_program_volume_candidate,
    organize_program_volumes,
)

GRAMMARS: tuple[ProgramVolumeGrammarId, ...] = (
    'PVG-STACKED-BANDS',
    'PVG-TERRACED-WEAVE',
    'PVG-SPLIT-BRIDGE',
)


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(value, 'model_dump'):
        value = value.model_dump(mode='json')
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_generation_source(expected: str) -> None:
    if compiler_source_fingerprint() != expected:
        raise RuntimeError('Compiler source changed during Program Volume study; '
                           'no completed candidate may be claimed from this run')


def _polygon(boundary, voids=()) -> Polygon:
    """Build one report-only plan polygon from a model ring."""
    return Polygon(
        [(float(point[0]), float(point[1])) for point in boundary],
        [[(float(point[0]), float(point[1])) for point in ring]
         for ring in voids],
    )


def _program_volume_phantom_levels(volumes) -> dict:
    """Report occupied volume levels that have no actual brief volume.

    Circulation spines and connectors are intentionally not counted as program
    occupancy.  A level is real for this protocol only when at least one named
    brief space is present, including a carver-owned archetype volume.
    """
    phantom = [
        level.id for level in volumes.levels
        if not any(
            volume.level_id == level.id
            and volume.role in ('program', 'archetype')
            and volume.space_ids
            for volume in volumes.volumes
        )
    ]
    return {
        'verdict': 'passed' if not phantom else 'failed',
        'level_ids': phantom,
        'count': len(phantom),
    }


def _allocated_phantom_levels(building) -> dict:
    """Report occupied lattice levels with no detailed allocation zones."""
    occupied = [level.id for level in building.lattice.levels
                if level.kind == 'occupied']
    allocated = {zone.level_id for zone in building.program_allocation.zones}
    phantom = [level_id for level_id in occupied if level_id not in allocated]
    return {
        'verdict': 'passed' if not phantom else 'failed',
        'level_ids': phantom,
        'count': len(phantom),
        'occupied_level_ids': occupied,
        'allocated_level_ids': sorted(allocated),
    }


def _union_to_lattice_report(building, volumes) -> dict:
    """Measure floor material against gross volume minus authored sectional airspace.

    Edge-connected clearances can change a floor's exterior without changing the
    gross facade envelope. Only explicit upstream clearance volumes justify that
    difference; a downstream carve cannot authorize its own removal. Raw gross/floor
    differences remain visible alongside the unexplained material difference.
    """
    lattice_by_id = {level.id: level for level in building.lattice.levels}
    level_rows = []
    missing = []
    for union in volumes.level_unions:
        level = lattice_by_id.get(union.level_id)
        if level is None:
            missing.append(union.level_id)
            continue
        union_exterior = _polygon(union.boundary)
        union_material = _polygon(union.boundary, union.voids)
        lattice_exterior = _polygon([(point.x, point.y) for point in level.plate])
        lattice_material = _polygon(
            [(point.x, point.y) for point in level.plate],
            [[(point.x, point.y) for point in ring] for ring in level.voids])
        clearance_volumes = [volume for volume in volumes.volumes
                             if volume.level_id == union.level_id
                             and volume.role == 'sectional_clearance']
        clearance = unary_union([box(*volumes.rect_of(volume))
                                 for volume in clearance_volumes])
        expected_material = union_material.difference(clearance)
        unclaimed_difference = expected_material.symmetric_difference(lattice_material)
        exterior_difference = union_exterior.symmetric_difference(lattice_exterior)
        material_difference = union_material.symmetric_difference(lattice_material)
        union_area = float(union_exterior.area)
        lattice_area = float(lattice_exterior.area)
        denominator = max(union_area, lattice_area, 1.0)
        level_rows.append({
            'level_id': union.level_id,
            'union_exterior_area_m2': round(union_area, 6),
            'lattice_exterior_area_m2': round(lattice_area, 6),
            'exterior_symmetric_difference_m2': round(
                float(exterior_difference.area), 6),
            'exterior_symmetric_difference_ratio': round(
                float(exterior_difference.area) / denominator, 8),
            'material_floor_symmetric_difference_m2': round(
                float(material_difference.area), 6),
            'declared_clearance_ids': [volume.id for volume in clearance_volumes],
            'declared_clearance_area_m2': round(
                float(union_material.intersection(clearance).area), 6),
            'expected_floor_area_m2': round(float(expected_material.area), 6),
            'unclaimed_floor_difference_m2': round(float(unclaimed_difference.area), 6),
            'downstream_void_area_m2': round(
                float(union_exterior.difference(lattice_material).area), 6),
            'union_valid': bool(union_material.is_valid),
            'lattice_valid': bool(lattice_material.is_valid),
        })
    total_difference = sum(row['exterior_symmetric_difference_m2'] for row in level_rows)
    total_material_difference = sum(
        row['material_floor_symmetric_difference_m2'] for row in level_rows)
    total_unclaimed_difference = sum(row['unclaimed_floor_difference_m2'] for row in level_rows)
    total_union_area = sum(row['union_exterior_area_m2'] for row in level_rows)
    total_lattice_area = sum(row['lattice_exterior_area_m2'] for row in level_rows)
    denominator = max(total_union_area, total_lattice_area, 1.0)
    measurable = not missing and len(level_rows) == len(volumes.level_unions)
    total_ratio = total_difference / denominator
    return {
        'verdict': ('unevaluated' if not measurable else
                    ('passed' if total_unclaimed_difference <= 1e-6 else 'failed')),
        'basis': 'Compiled floor equals Program Volume union minus explicit upstream '
                 'sectional_clearance volumes. Raw gross/floor differences are '
                 'descriptive; any unclaimed material difference fails.',
        'exterior_symmetric_difference_m2': round(total_difference, 6),
        'exterior_symmetric_difference_ratio': round(total_ratio, 8),
        'material_floor_symmetric_difference_m2': round(
            total_material_difference, 6),
        'declared_clearance_area_m2': round(sum(
            row['declared_clearance_area_m2'] for row in level_rows), 6),
        'unclaimed_floor_difference_m2': round(total_unclaimed_difference, 6),
        'levels': level_rows,
        'missing_lattice_levels': missing,
        'tolerance_m2': 1e-6,
    }


def _facade_gate_summary(report) -> dict:
    """Preserve the gates' passed/failed/unevaluated three-valued result."""
    if report is None:
        return {
            'verdict': 'unevaluated',
            'passed': 0,
            'failed': 0,
            'unevaluated': 0,
            'total': 0,
            'summary': 'No facade gate report was emitted.',
        }
    counts = {
        'passed': sum(gate.verdict == 'passed' for gate in report.gates),
        'failed': sum(gate.verdict == 'failed' for gate in report.gates),
        'unevaluated': sum(gate.verdict == 'unevaluated' for gate in report.gates),
    }
    verdict = ('failed' if counts['failed'] else
               ('unevaluated' if counts['unevaluated'] else 'passed'))
    return {
        'verdict': verdict,
        **counts,
        'total': len(report.gates),
        'grammar_id': report.grammar_id,
        'grammar_label': report.grammar_label,
        'summary': report.summary(),
    }


def _plan_reference(geometry):
    """Plan geometry a boundary protocol can measure without guessing a 3-D sweep."""
    if geometry.type == 'member':
        points = list(dict.fromkeys((point.x, point.y) for point in geometry.path))
        return LineString(points) if len(points) > 1 else Point(points[0])
    if geometry.type == 'box':
        cx, cy = geometry.center.x, geometry.center.y
        hx, hy = abs(geometry.size.x) / 2.0, abs(geometry.size.y) / 2.0
        cosine, sine = math.cos(geometry.rotation_z), math.sin(geometry.rotation_z)
        return Polygon([
            (cx + cosine * x - sine * y, cy + sine * x + cosine * y)
            for x, y in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy))])
    if geometry.type == 'extrusion':
        return Polygon(
            [(point.x, point.y) for point in geometry.boundary],
            [[(point.x, point.y) for point in ring] for ring in geometry.holes])
    if geometry.type == 'quad':
        points = list(dict.fromkeys((point.x, point.y) for point in geometry.corners))
        if len(points) >= 3:
            return Polygon(points).convex_hull
        return LineString(points) if len(points) == 2 else Point(points[0])
    return None


def _internal_reference_containment(building, volumes) -> dict:
    """Measure program solids and structural axes against each volume union."""
    plates = {union.level_id: _polygon(union.boundary, union.voids)
              for union in volumes.level_unions}
    checked = skipped = 0
    unknown = []
    offenders = []
    by_layer = {}
    for group in building.element_groups:
        if group.semantic_layer not in {'program', 'structure'}:
            continue
        for instance in group.instances:
            plate = plates.get(instance.level_id)
            if plate is None:
                skipped += 1
                continue
            reference = _plan_reference(instance.geometry)
            if reference is None or reference.is_empty:
                unknown.append(instance.id)
                continue
            checked += 1
            by_layer[group.semantic_layer] = by_layer.get(group.semantic_layer, 0) + 1
            if not plate.buffer(1e-5, join_style=2).covers(reference):
                offenders.append({
                    'element_id': instance.id,
                    'kind': group.kind,
                    'layer': group.semantic_layer,
                    'outside_measure': round(
                        reference.difference(plate).length
                        if reference.geom_type in {'LineString', 'Point'} else
                        reference.difference(plate).area, 6),
                })
    verdict = ('failed' if offenders else 'unevaluated' if unknown else 'passed')
    return {
        'verdict': verdict,
        'checked': checked,
        'checked_by_layer': by_layer,
        'offender_count': len(offenders),
        'offenders': offenders[:50],
        'unknown_count': len(unknown),
        'unknown_element_ids': unknown[:50],
        'skipped_outside_program_storeys': skipped,
        'basis': ('Exact box/extrusion/quad plan solids and member centre-lines. '
                  'Member profile sweeps are reported by the separate unresolved check.'),
    }


def _facade_reference_outboard(building, volumes) -> dict:
    """Check primary facade carriers remain on or outside the volume boundary."""
    plates = {union.level_id: _polygon(union.boundary, union.voids)
              for union in volumes.level_unions}
    collar_subsystems = {'roof', 'edge_closure', 'entrance', 'canopy'}
    checked = skipped = 0
    unknown = []
    offenders = []
    for group in building.element_groups:
        if group.semantic_layer != 'envelope':
            continue
        for instance in group.instances:
            plate = plates.get(instance.level_id)
            if plate is None or group.subsystem in collar_subsystems:
                skipped += 1
                continue
            reference = _plan_reference(instance.geometry)
            if reference is None or reference.is_empty:
                unknown.append(instance.id)
                continue
            checked += 1
            deep_interior = plate.buffer(-0.02, join_style=2)
            if not deep_interior.is_empty and reference.intersects(deep_interior):
                offenders.append({
                    'element_id': instance.id,
                    'kind': group.kind,
                    'subsystem': group.subsystem,
                })
    verdict = ('failed' if offenders else 'unevaluated' if unknown else 'passed')
    return {
        'verdict': verdict,
        'checked': checked,
        'offender_count': len(offenders),
        'offenders': offenders[:50],
        'unknown_count': len(unknown),
        'unknown_element_ids': unknown[:50],
        'skipped_collar_or_non_program_storey': skipped,
        'inboard_tolerance_m': 0.02,
        'collar_subsystems': sorted(collar_subsystems),
        'basis': ('Primary facade carrier references must remain on or outboard of '
                  'the Program Volume boundary. Returns, entrance reveals, roof '
                  'closures and canopies are separate collar assemblies.'),
    }


def _unevaluated_protocol_checks() -> dict:
    """Checks that need emitted member-to-volume relations not in this payload."""
    return {
        'internal_reference_containment': {
            'verdict': 'unevaluated',
            'reason': 'Compilation is required to provide emitted internal elements.',
        },
        'facade_reference_outboard': {
            'verdict': 'unevaluated',
            'reason': 'Compilation is required to provide emitted facade elements.',
        },
        'full_swept_solid_containment': {
            'verdict': 'unevaluated',
            'reason': ('Member centre-lines are measured, while rolled-profile fillets, '
                       'facade thickness bodies and connection hardware do not yet '
                       'publish a complete volume-containment role.'),
        },
    }


def _base_protocol_report(volumes) -> dict:
    phantom = _program_volume_phantom_levels(volumes)
    checks = _unevaluated_protocol_checks()
    checks.update({
        'union_to_lattice': {
            'verdict': 'unevaluated',
            'reason': 'Compilation is required to provide the downstream lattice.',
        },
        'program_volume_phantom_levels': phantom,
        'allocated_phantom_levels': {
            'verdict': 'unevaluated',
            'reason': 'Compilation is required to provide detailed allocation.',
        },
    })
    return {
        'program_volume_phantom_levels': phantom,
        'allocated_phantom_levels': checks['allocated_phantom_levels'],
        'checks': checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--response', type=Path, required=True,
                        help='Stored response.json containing architectural_score')
    parser.add_argument('--typology', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--grammars', nargs='+', choices=GRAMMARS, default=list(GRAMMARS))
    parser.add_argument('--facade-grammar')
    parser.add_argument('--structural-system')
    parser.add_argument('--compile', action='store_true')
    parser.add_argument(
        '--reuse-compiled', action='store_true',
        help=('Reuse a matching building_model_v3.json when iterating presentation '
              'renders; refuses stale score, topology, structure or facade inputs.'))
    parser.add_argument('--drawings', action='store_true')
    parser.add_argument('--render', action='store_true')
    args = parser.parse_args()
    if args.reuse_compiled and not args.compile:
        parser.error('--reuse-compiled requires --compile')

    payload = json.loads(args.response.read_text(encoding='utf-8'))
    score = ArchitecturalScore.model_validate(payload['architectural_score'])
    source_hash = _sha256(args.response)
    generation_source = compiler_source_fingerprint()
    held_constant = {
        'facade_grammar_id': args.facade_grammar,
        'structural_system_id': args.structural_system,
    }
    study_path = args.out / 'study.json'
    study_by_grammar = {}
    if study_path.is_file():
        existing = json.loads(study_path.read_text(encoding='utf-8'))
        identity = (existing.get('source_response_sha256'), existing.get('score_id'),
                    existing.get('typology'), existing.get('held_constant'))
        expected = (source_hash, score.score_id, args.typology, held_constant)
        if identity != expected:
            raise ValueError(
                'refusing to merge Program Volume studies with different source, '
                'score, typology, facade or structure inputs')
        if existing.get('compiler_source_fingerprint') != generation_source:
            raise ValueError('refusing stale Program Volume study from a different '
                             'or unrecorded compiler source; use a new output directory')
        study_by_grammar = {
            row['grammar_id']: row for row in existing.get('candidates', [])}
    for grammar in args.grammars:
        started = time.perf_counter()
        slug = grammar.removeprefix('PVG-').lower().replace('_', '-').replace('--', '-')
        directory = args.out / slug
        volumes = organize_program_volumes(
            score, args.typology, grammar_id=grammar)
        massing = volumes.to_program_massing(
            facade_grammar_id=args.facade_grammar,
            structural_system_id=args.structural_system)
        volume_path = directory / 'program_volume_model.json'
        massing_path = directory / 'program_massing.json'
        _write(volume_path, volumes)
        _write(massing_path, massing)
        row = {
            'compiler_source_fingerprint': generation_source,
            'grammar_id': grammar,
            'topology_signature': volumes.topology_signature,
            'program_volume_digest': volumes.digest(),
            'levels': len(volumes.levels),
            'volumes': len(volumes.volumes),
            'program_volumes': sum(v.role in ('program', 'archetype')
                                   for v in volumes.volumes),
            'level_union_area_m2': {union.level_id: union.gross_area_m2
                                    for union in volumes.level_unions},
            'program_volume_model': str(volume_path),
            'program_massing': str(massing_path),
        }
        row.update(_base_protocol_report(volumes))

        if args.compile:
            model_path = directory / 'building_model_v3.json'
            if args.reuse_compiled and model_path.is_file():
                if study_by_grammar.get(grammar, {}).get('compiler_source_fingerprint') != generation_source:
                    raise ValueError('refusing compiled model without matching generation-source evidence')
                from backend.app.models_v3 import BuildingModelV3
                building = BuildingModelV3.model_validate_json(
                    model_path.read_text(encoding='utf-8'))
                embedded = building.program_volume_model
                mismatches = []
                if building.score_id != score.score_id:
                    mismatches.append('score_id')
                if building.typology != args.typology:
                    mismatches.append('typology')
                if embedded is None or embedded.digest() != volumes.digest():
                    mismatches.append('program_volume_digest')
                if (args.facade_grammar
                        and building.facade_grammar_id != args.facade_grammar):
                    mismatches.append('facade_grammar_id')
                if (args.structural_system
                        and building.structural_system_id != args.structural_system):
                    mismatches.append('structural_system_id')
                if mismatches:
                    raise ValueError(
                        'refusing stale compiled model; mismatched ' + ', '.join(mismatches))
            else:
                building, volumes = compile_program_volume_candidate(
                    score, typology=args.typology, volume_grammar_id=grammar,
                    facade_grammar_id=args.facade_grammar,
                    structural_system_id=args.structural_system)
            _assert_generation_source(generation_source)
            _write(model_path, building)
            planned = {space_id: volume.level_id for volume in volumes.volumes
                       for space_id in volume.space_ids}
            delivered = {zone.space_id: zone.level_id
                         for zone in building.program_allocation.zones}
            assignment_changes = [
                {'space_id': space_id, 'volume_level': level_id,
                 'allocated_level': delivered.get(space_id)}
                for space_id, level_id in sorted(planned.items())
                if delivered.get(space_id) != level_id
            ]
            union_to_lattice = _union_to_lattice_report(building, volumes)
            volume_phantom = _program_volume_phantom_levels(volumes)
            allocated_phantom = _allocated_phantom_levels(building)
            facade_summary = _facade_gate_summary(building.facade_gates)
            protocol_checks = _unevaluated_protocol_checks()
            protocol_checks.update({
                'union_to_lattice': union_to_lattice,
                'program_volume_phantom_levels': volume_phantom,
                'allocated_phantom_levels': allocated_phantom,
                'internal_reference_containment':
                    _internal_reference_containment(building, volumes),
                'facade_reference_outboard':
                    _facade_reference_outboard(building, volumes),
            })
            row.update({
                'model_id': building.model_id,
                'building_model': str(model_path),
                'elements': building.element_count,
                'program_fulfilment': building.program_allocation.fulfilment,
                'program_fits': building.program_allocation.fits,
                'unplaced': [item.model_dump(mode='json')
                             for item in building.program_allocation.unplaced],
                'unplaced_space_ids': [item.space_id
                                       for item in building.program_allocation.unplaced],
                'level_assignment_changes': assignment_changes,
                'spatial_status': building.spatial.status if building.spatial else None,
                'dependency_status': building.dependency_graph.status,
                'facade_gate_status': facade_summary,
                'facade_gate_summary': facade_summary,
                'program_volume_phantom_levels': volume_phantom,
                'allocated_phantom_levels': allocated_phantom,
                'checks': protocol_checks,
                'protocol_checks': protocol_checks,
            })
            if args.drawings:
                from backend.app.drawings import issue_drawings, write_drawing_set
                issued = issue_drawings(building)
                write_drawing_set(issued, building, directory=directory / 'drawings')
                row['drawing_sheets'] = len(issued.sheets) or len(issued.all)
            if args.render:
                from backend.app import blender_export_v3
                blender_export_v3.WEB_ASSET_DIRECTORY = (directory / 'models').resolve()
                blender_export_v3.BLEND_DIRECTORY = (directory / 'native').resolve()
                blender_export_v3.RENDER_DIRECTORY = (directory / 'geometry').resolve()
                asset = blender_export_v3.export_blender_web_model_v3(
                    building, render=True)
                row['model_asset'] = asset.model_dump(mode='json')

        row['seconds'] = round(time.perf_counter() - started, 2)
        protocol_path = directory / 'program_volume_protocol.json'
        row['artifacts'] = {
            'response_sha256': source_hash,
            'program_volume_model_sha256': _sha256(volume_path),
            'program_massing_sha256': _sha256(massing_path),
        }
        if args.compile:
            row['artifacts']['building_model_v3_sha256'] = _sha256(model_path)
        _assert_generation_source(generation_source)
        _write(protocol_path, row)
        study_by_grammar[grammar] = row
        print(json.dumps(row, ensure_ascii=False))

    _write(study_path, {
        'schema_version': 'mta.program_volume_study/1.0',
        'compiler_source_fingerprint': generation_source,
        'source_response': str(args.response),
        'source_response_sha256': source_hash,
        'score_id': score.score_id,
        'typology': args.typology,
        'held_constant': held_constant,
        'candidates': [study_by_grammar[grammar] for grammar in GRAMMARS
                       if grammar in study_by_grammar],
    })


if __name__ == '__main__':
    main()
