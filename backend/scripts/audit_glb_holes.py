"""Audit exported GLB floor surfaces against holes declared by the JSON model.

This is a presentation-boundary check.  The Blender glTF exporter maps the source
model axes ``(x, y, z)`` to raw GLB coordinates ``(x, z, -y)``; the adapter below
projects both the decoded mesh and each declared hole into that same ``(x, -y)``
plan.  It unions horizontal GLB triangles at each target's two z surfaces and
measures their exact overlap with each declared hole.  A non-zero overlap means the
exported surface covers part of a hole, even when the source JSON has zero solid
intersection.  Use ``--target-kind floor_slab`` and ``--target-kind ceiling`` for
the two semantic surfaces.

The reader uses only the Python standard library for GLB decoding.  Shapely is used
for the small 2-D triangle/rectangle (or arbitrary polygon) area intersections, as it
is already a runtime geometry dependency in the backend.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import struct
from typing import Any, Iterable, Mapping, Sequence

from shapely.geometry import Polygon
from shapely.ops import unary_union


GLB_MAGIC = 0x46546C67
GLB_VERSION = 2
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
TRIANGLES_MODE = 4

PLAN_EPS_M2 = 1.0e-7
PARITY_EPS_M2 = 1.0e-4
Z_EPS_M = 1.0e-4
FILLED_RATIO = 0.98

_COMPONENT_FORMATS = {
    5120: ('b', 1),       # BYTE
    5121: ('B', 1),       # UNSIGNED_BYTE
    5122: ('h', 2),       # SHORT
    5123: ('H', 2),       # UNSIGNED_SHORT
    5125: ('I', 4),       # UNSIGNED_INT
    5126: ('f', 4),       # FLOAT
}
_TYPE_ARITY = {
    'SCALAR': 1,
    'VEC2': 2,
    'VEC3': 3,
    'VEC4': 4,
    'MAT2': 4,
    'MAT3': 9,
    'MAT4': 16,
}


@dataclass(frozen=True)
class _Glb:
    document: dict[str, Any]
    binary: bytes


def _read_glb(path: Path) -> _Glb:
    data = path.read_bytes()
    if len(data) < 12:
        raise ValueError(f'{path} is shorter than a GLB header.')
    magic, version, length = struct.unpack_from('<III', data, 0)
    if magic != GLB_MAGIC or version != GLB_VERSION:
        raise ValueError(f'{path} is not a version 2 GLB.')
    if length != len(data):
        raise ValueError(f'{path} header length {length} does not match {len(data)} bytes.')

    document: dict[str, Any] | None = None
    binary = b''
    offset = 12
    while offset < length:
        if offset + 8 > length:
            raise ValueError(f'{path} has a truncated chunk header.')
        chunk_length, chunk_type = struct.unpack_from('<II', data, offset)
        offset += 8
        end = offset + chunk_length
        if end > length:
            raise ValueError(f'{path} has a chunk outside its declared length.')
        chunk = data[offset:end]
        offset = end
        if chunk_type == JSON_CHUNK:
            document = json.loads(chunk.rstrip(b' \t\r\n\0'))
        elif chunk_type == BIN_CHUNK:
            binary = chunk
    if document is None:
        raise ValueError(f'{path} has no JSON chunk.')
    return _Glb(document=document, binary=binary)


def _accessor_values(document: Mapping[str, Any], binary: bytes,
                     accessor_index: int) -> list[Any]:
    accessor = document['accessors'][accessor_index]
    if accessor.get('sparse'):
        raise ValueError('Sparse glTF accessors are not supported by this audit.')
    view_index = accessor.get('bufferView')
    if view_index is None:
        raise ValueError(f'Accessor {accessor_index} has no bufferView.')
    view = document['bufferViews'][view_index]
    component = _COMPONENT_FORMATS.get(accessor['componentType'])
    arity = _TYPE_ARITY.get(accessor['type'])
    if component is None or arity is None:
        raise ValueError(f'Unsupported accessor {accessor_index} format.')
    format_code, component_size = component
    item_size = component_size * arity
    stride = view.get('byteStride', item_size)
    if stride < item_size:
        raise ValueError(f'Accessor {accessor_index} has a short byteStride.')
    base = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
    count = accessor['count']
    out: list[Any] = []
    for index in range(count):
        offset = base + index * stride
        values = struct.unpack_from(f'<{arity}{format_code}', binary, offset)
        out.append(values[0] if arity == 1 else values)
    return out


def _node_matrix(node: Mapping[str, Any]) -> tuple[float, ...]:
    """Return a glTF column-major node matrix for the uncommon transformed node."""

    if 'matrix' in node:
        matrix = tuple(float(value) for value in node['matrix'])
        if len(matrix) != 16:
            raise ValueError('A glTF node matrix must contain 16 values.')
        return matrix

    tx, ty, tz = (float(value) for value in node.get('translation', (0.0, 0.0, 0.0)))
    sx, sy, sz = (float(value) for value in node.get('scale', (1.0, 1.0, 1.0)))
    qx, qy, qz, qw = (float(value) for value in node.get(
        'rotation', (0.0, 0.0, 0.0, 1.0)))
    # glTF quaternions are x, y, z, w.  This is the column-major matrix used by
    # glTF's node transform convention.
    xx, yy, zz = qx * qx, qy * qy, qz * qz
    xy, xz, yz = qx * qy, qx * qz, qy * qz
    wx, wy, wz = qw * qx, qw * qy, qw * qz
    return (
        (1 - 2 * (yy + zz)) * sx, (2 * (xy + wz)) * sx, (2 * (xz - wy)) * sx, 0.0,
        (2 * (xy - wz)) * sy, (1 - 2 * (xx + zz)) * sy, (2 * (yz + wx)) * sy, 0.0,
        (2 * (xz + wy)) * sz, (2 * (yz - wx)) * sz, (1 - 2 * (xx + yy)) * sz, 0.0,
        tx, ty, tz, 1.0,
    )


def _apply_matrix(matrix: Sequence[float], point: Sequence[float]) -> tuple[float, float, float]:
    x, y, z = point
    w = matrix[3] * x + matrix[7] * y + matrix[11] * z + matrix[15]
    values = (
        matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12],
        matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13],
        matrix[2] * x + matrix[6] * y + matrix[10] * z + matrix[14],
    )
    return values if abs(w - 1.0) <= 1.0e-9 or abs(w) <= 1.0e-12 \
        else tuple(value / w for value in values)


def _node_triangles(document: Mapping[str, Any], binary: bytes,
                    node_index: int) -> Iterable[tuple[tuple[float, float, float], ...]]:
    node = document['nodes'][node_index]
    mesh_index = node.get('mesh')
    if mesh_index is None:
        return
    matrix = _node_matrix(node)
    mesh = document['meshes'][mesh_index]
    for primitive in mesh.get('primitives', ()):
        if primitive.get('mode', TRIANGLES_MODE) != TRIANGLES_MODE:
            continue
        position_index = primitive.get('attributes', {}).get('POSITION')
        if position_index is None:
            continue
        positions = _accessor_values(document, binary, position_index)
        if 'indices' in primitive:
            indices = _accessor_values(document, binary, primitive['indices'])
        else:
            indices = list(range(len(positions)))
        for offset in range(0, len(indices) - 2, 3):
            raw = (positions[indices[offset]], positions[indices[offset + 1]],
                   positions[indices[offset + 2]])
            yield tuple(_apply_matrix(matrix, point) for point in raw)


def _identity_matrix(matrix: Sequence[float]) -> bool:
    return all(abs(value - expected) <= 1.0e-9
               for value, expected in zip(
                   matrix,
                   (1.0, 0.0, 0.0, 0.0,
                    0.0, 1.0, 0.0, 0.0,
                    0.0, 0.0, 1.0, 0.0,
                    0.0, 0.0, 0.0, 1.0)))


def _hole_polygon(hole: Sequence[Mapping[str, Any]]) -> Polygon:
    # Blender's glTF export is x,z,-y.  A source XY hole therefore projects to
    # (x,-y) in the raw GLB horizontal plane (x,z).
    polygon = Polygon([(float(point['x']), -float(point['y'])) for point in hole])
    if polygon.is_empty or polygon.area <= PLAN_EPS_M2 or not polygon.is_valid:
        raise ValueError('declared hole is not a valid positive-area polygon')
    return polygon


def _geometry_polygon(geometry: Mapping[str, Any]) -> Polygon:
    """Map one JSON extrusion footprint into the raw GLB horizontal coordinates."""

    boundary = [(float(point['x']), -float(point['y']))
                for point in geometry['boundary']]
    holes = [[(float(point['x']), -float(point['y'])) for point in hole]
             for hole in geometry.get('holes') or []]
    polygon = Polygon(boundary, holes)
    if polygon.is_empty or polygon.area <= PLAN_EPS_M2 or not polygon.is_valid:
        raise ValueError('declared floor slab is not a valid positive-area polygon')
    return polygon


def _triangle_polygon(triangle: Sequence[Sequence[float]]) -> Polygon | None:
    polygon = Polygon([(point[0], point[2]) for point in triangle])
    if polygon.is_empty or polygon.area <= PLAN_EPS_M2:
        return None
    return polygon


def _surface_union(triangles: Sequence[tuple[tuple[float, float, float], ...]],
                   z_base: float, z_top: float) -> tuple[Any | None, int]:
    """Union horizontal triangles on either declared slab surface."""

    polygons = []
    surface_count = 0
    for triangle in triangles:
        heights = [point[1] for point in triangle]
        if max(heights) - min(heights) > Z_EPS_M:
            continue
        z = sum(heights) / 3.0
        if abs(z - z_base) > Z_EPS_M and abs(z - z_top) > Z_EPS_M:
            continue
        surface_count += 1
        polygon = _triangle_polygon(triangle)
        if polygon is not None:
            polygons.append(polygon)
    return (unary_union(polygons) if polygons else None), surface_count


def _coverage(hole: Polygon, triangles: Sequence[tuple[tuple[float, float, float], ...]],
              z_base: float, z_top: float) -> tuple[float, int, int]:
    """Return covered plan area, count of intersecting triangles, and z-surface count."""

    intersections = []
    surface_count = 0
    for triangle in triangles:
        heights = [point[1] for point in triangle]
        if max(heights) - min(heights) > Z_EPS_M:
            continue
        z = sum(heights) / 3.0
        if abs(z - z_base) > Z_EPS_M and abs(z - z_top) > Z_EPS_M:
            continue
        surface_count += 1
        polygon = _triangle_polygon(triangle)
        if polygon is None:
            continue
        intersection = polygon.intersection(hole)
        if not intersection.is_empty and intersection.area > PLAN_EPS_M2:
            intersections.append(intersection)
    if not intersections:
        return 0.0, 0, surface_count
    return unary_union(intersections).area, len(intersections), surface_count


def _json_target_instances(model: Mapping[str, Any], target_kind: str) -> list[Mapping[str, Any]]:
    return [instance
            for group in model.get('element_groups', ())
            if group.get('kind') == target_kind
            for instance in group.get('instances', ())]


def _surface_parity(model: Mapping[str, Any],
                    triangles: Sequence[tuple[tuple[float, float, float], ...]],
                    has_unsupported_nodes: bool,
                    target_kind: str) -> list[dict[str, Any]]:
    """Compare JSON footprints with the exported mesh per level."""

    target_instances = _json_target_instances(model, target_kind)
    if not target_instances:
        return [{
            'target_kind': target_kind,
            'level_id': None,
            'element_ids': [],
            'z_base': None,
            'z_top': None,
            'status': 'unevaluated',
            'expected_area_m2': None,
            'actual_area_m2': None,
            'missing_area_m2': None,
            'extra_area_m2': None,
            'symmetric_difference_area_m2': None,
            'tolerance_m2': None,
            'horizontal_triangle_count': 0,
            'reason': (
                f'model declares no {target_kind} source surfaces; '
                'surface parity cannot be proven.'),
        }]

    levels: dict[tuple[Any, float, float], dict[str, Any]] = {}
    for instance in target_instances:
        geometry = instance.get('geometry') or {}
        try:
            key = (instance.get('level_id'), float(geometry['z_base']),
                   float(geometry['z_top']))
            footprint = _geometry_polygon(geometry)
        except (KeyError, TypeError, ValueError) as error:
            key = (instance.get('level_id'), geometry.get('z_base'), geometry.get('z_top'))
            row = levels.setdefault(key, {'element_ids': [], 'footprints': [],
                                          'error': str(error)})
            row['element_ids'].append(instance.get('id'))
            continue
        row = levels.setdefault(key, {'element_ids': [], 'footprints': [], 'error': None})
        row['element_ids'].append(instance.get('id'))
        row['footprints'].append(footprint)

    records: list[dict[str, Any]] = []
    for (level_id, z_base, z_top), row in levels.items():
        record: dict[str, Any] = {
            'target_kind': target_kind,
            'level_id': level_id,
            'element_ids': row['element_ids'],
            'z_base': z_base,
            'z_top': z_top,
            'status': 'unevaluated',
            'expected_area_m2': None,
            'actual_area_m2': None,
            'missing_area_m2': None,
            'extra_area_m2': None,
            'symmetric_difference_area_m2': None,
            'tolerance_m2': None,
            'horizontal_triangle_count': 0,
        }
        if row['error'] is not None:
            record['reason'] = row['error']
            records.append(record)
            continue
        if has_unsupported_nodes:
            record['reason'] = f'one or more {target_kind} GLB nodes have an unsupported transform.'
            records.append(record)
            continue
        expected = unary_union(row['footprints'])
        record['expected_area_m2'] = expected.area
        actual, surface_count = _surface_union(triangles, z_base, z_top)
        record['horizontal_triangle_count'] = surface_count
        if actual is None or surface_count == 0:
            record['reason'] = 'no horizontal GLB slab triangles at the declared z.'
            records.append(record)
            continue
        record['actual_area_m2'] = actual.area
        missing = expected.difference(actual).area
        extra = actual.difference(expected).area
        symmetric = missing + extra
        record['missing_area_m2'] = missing
        record['extra_area_m2'] = extra
        record['symmetric_difference_area_m2'] = symmetric
        tolerance = max(PARITY_EPS_M2, expected.area * 1.0e-6)
        record['tolerance_m2'] = tolerance
        record['status'] = 'passed' if symmetric <= tolerance else 'failed'
        records.append(record)
    return records


def audit_glb_holes(model_json: str | Path | Mapping[str, Any],
                    glb_path: str | Path,
                    target_kind: str = 'floor_slab') -> dict[str, Any]:
    """Measure exported horizontal surfaces for one semantic element kind.

    ``floor_slab`` is the default target for backwards-compatible CLI use.  Pass
    ``target_kind='ceiling'`` to run the same audit against the presentation ceiling
    surfaces; both checks are intentionally separate because the exporter can fail
    one semantic node while exporting the other correctly.
    """

    if not isinstance(target_kind, str) or not target_kind.strip():
        raise ValueError('target_kind must be a non-empty semantic kind')
    target_kind = target_kind.strip()

    if isinstance(model_json, Mapping):
        model = model_json
        model_path = None
    else:
        model_path = Path(model_json)
        model = json.loads(model_path.read_text(encoding='utf-8'))
    glb = _read_glb(Path(glb_path))
    document, binary = glb.document, glb.binary
    target_instances = _json_target_instances(model, target_kind)

    target_nodes: list[int] = []
    unsupported_transform_nodes: list[int] = []
    triangles: list[tuple[tuple[float, float, float], ...]] = []
    for index, node in enumerate(document.get('nodes', ())):
        kinds = {kind.strip() for kind in str(node.get('extras', {}).get('mta:kinds', '')).split(',')}
        if target_kind not in kinds:
            continue
        matrix = _node_matrix(node)
        target_nodes.append(index)
        if _identity_matrix(matrix):
            triangles.extend(_node_triangles(document, binary, index))
        else:
            unsupported_transform_nodes.append(index)

    parity_records = _surface_parity(
        model, triangles, bool(unsupported_transform_nodes), target_kind)

    records: list[dict[str, Any]] = []
    for instance in target_instances:
        geometry = instance.get('geometry') or {}
        holes = geometry.get('holes') or []
        for hole_index, raw_hole in enumerate(holes):
            record: dict[str, Any] = {
                'element_id': instance.get('id'),
                'level_id': instance.get('level_id'),
                'hole_index': hole_index,
                'status': 'unevaluated',
                'declared_area_m2': 0.0,
                'covered_area_m2': 0.0,
                'coverage_ratio': None,
                'intersecting_triangle_count': 0,
                'horizontal_triangle_count': 0,
            }
            try:
                hole = _hole_polygon(raw_hole)
                record['declared_area_m2'] = hole.area
                z_base = float(geometry['z_base'])
                z_top = float(geometry['z_top'])
                if not target_nodes:
                    record['reason'] = f'no GLB node is tagged {target_kind}.'
                elif unsupported_transform_nodes:
                    record['reason'] = f'{target_kind} node transform could not be evaluated.'
                else:
                    covered, intersecting, surface_count = _coverage(
                        hole, triangles, z_base, z_top)
                    record['covered_area_m2'] = covered
                    record['coverage_ratio'] = covered / hole.area
                    record['intersecting_triangle_count'] = intersecting
                    record['horizontal_triangle_count'] = surface_count
                    if surface_count == 0:
                        record['reason'] = (
                            f'no horizontal GLB {target_kind} triangles at the declared z.')
                    elif record['coverage_ratio'] <= PLAN_EPS_M2 / hole.area:
                        record['status'] = 'empty'
                    elif record['coverage_ratio'] >= FILLED_RATIO:
                        record['status'] = 'filled'
                    else:
                        record['status'] = 'partial'
            except (KeyError, TypeError, ValueError) as error:
                record['reason'] = str(error)
            records.append(record)

    hole_failed = [record for record in records if record['status'] in {'filled', 'partial'}]
    hole_unknown = [record for record in records if record['status'] == 'unevaluated']
    parity_failed = [record for record in parity_records if record['status'] == 'failed']
    parity_unknown = [record for record in parity_records if record['status'] == 'unevaluated']
    failed = hole_failed + parity_failed
    unknown = hole_unknown + parity_unknown
    result_status = 'failed' if failed else 'unevaluated' if unknown else 'passed'
    declared = sum(record['declared_area_m2'] for record in records)
    covered = sum(record['covered_area_m2'] for record in records)
    return {
        'schema_version': 'mta.glb_hole_parity/1.0',
        'status': result_status,
        'model_id': model.get('model_id'),
        'model_json': str(model_path) if model_path is not None else None,
        'glb_path': str(glb_path),
        'coordinate_contract': 'blender_glTF: model (x,y,z) -> GLB (x,z,-y)',
        'target_kind': target_kind,
        'source_target_instance_count': len(target_instances),
        'glb_target_node_count': len(target_nodes),
        'declared_hole_count': len(records),
        'evaluated_hole_count': len(records) - len(hole_unknown),
        'empty_hole_count': sum(record['status'] == 'empty' for record in records),
        'partial_hole_count': sum(record['status'] == 'partial' for record in records),
        'filled_hole_count': sum(record['status'] == 'filled' for record in records),
        'unevaluated_hole_count': len(hole_unknown),
        'surface_parity_level_count': len(parity_records),
        'surface_parity_failed_level_count': len(parity_failed),
        'surface_parity_unevaluated_level_count': len(parity_unknown),
        'declared_area_m2': declared,
        'covered_area_m2': covered,
        'coverage_ratio': covered / declared if declared > PLAN_EPS_M2 else None,
        'holes': records,
        'surface_parity': parity_records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model_json', type=Path)
    parser.add_argument('glb', type=Path)
    parser.add_argument('--target-kind', default='floor_slab',
                        help='semantic element kind to audit (default: floor_slab)')
    parser.add_argument('--indent', type=int, default=2)
    args = parser.parse_args()
    try:
        result = audit_glb_holes(args.model_json, args.glb, target_kind=args.target_kind)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=args.indent))
    return 1 if result['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
