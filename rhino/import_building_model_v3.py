"""Full v3 source -> editable native Rhino candidate, without design reinterpretation.

Run inside an isolated, empty Rhino MCP slot using its injected ``__rhino_doc__``::

    import runpy
    adapter = runpy.run_path(r'D:/.../rhino/import_building_model_v3.py')
    result = adapter['export_to_document'](__rhino_doc__, MODEL_JSON, NEW_DIRECTORY,
                                           run_id=EXACT_RUN_ID)

No mesh fallback, acceptance record, current-document lookup or source-model mutation.
RhinoCommon imports are local so the portable source contract is testable offline.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import mesh_primitives as primitive

TOLERANCE_M = 1e-6
ADAPTER_VERSION = '0.2.0'
PROGRAM_VOLUME_REFERENCE_KIND = 'program_volume'
PROGRAM_VOLUME_LAYER_ROOT = 'MTA::Reference::Program_Volumes'


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _point(value):
    return primitive._xyz(value)


def _area(ring):
    return sum(a[0]*b[1] - b[0]*a[1] for a, b in zip(ring, ring[1:]+ring[:1])) / 2


def _ring(values, *, positive=True):
    points = [tuple(float(p[k]) for k in 'xy') if isinstance(p, dict) else tuple(p) for p in values]
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    if len(points) < 3 or any(not math.isfinite(v) for p in points for v in p):
        raise ValueError('A profile needs at least three finite points')
    area = _area(points)
    if abs(area) <= 1e-12:
        raise ValueError('Zero-area or crossed profile')
    return points if (area > 0) == positive else list(reversed(points))


def _bounds(vertices):
    return [[min(p[i] for p in vertices) for i in range(3)],
            [max(p[i] for p in vertices) for i in range(3)]]


def _signed_mesh_volume(vertices, faces):
    # Signed fans integrate concave planar caps correctly without filling their recesses.
    total = 0.0
    for face in faces:
        a = vertices[face[0]]
        for i in range(1, len(face)-1):
            b, c = vertices[face[i]], vertices[face[i+1]]
            cross = primitive._cross(b, c)
            total += sum(x*y for x, y in zip(a, cross)) / 6
    return abs(total)


def primitive_contract(geometry, profiles, thickness_m=None):
    """Native recipes and independent source dimensions, using the shared v3 vertices."""
    kind = geometry['type']
    if kind == 'box':
        vertices, faces = primitive.box_mesh(geometry)
        return {'recipe': 'box_brep', 'vertices': vertices,
                'expected_volume_m3': math.prod(geometry['size'].values()),
                'expected_bounds_m': _bounds(vertices), 'hole_count': 0}
    if kind == 'member':
        vertices, faces = primitive.member_mesh(geometry, profiles)
        path = [_point(p) for p in geometry['path']]
        outline = primitive.profile_outline(profiles[geometry['profile']])
        contract = {'recipe': 'member_faceted_brep', 'vertices': vertices, 'faces': faces,
                    'expected_volume_m3': _signed_mesh_volume(vertices, faces),
                    'expected_bounds_m': _bounds(vertices), 'hole_count': 0}
        if len(path) == 2:
            axis = primitive._unit(tuple(b-a for a, b in zip(*path)))
            up = primitive._unit(_point(geometry.get('roll') or {'x': 0, 'y': 0, 'z': 1}))
            dot = sum(a*b for a, b in zip(axis, up))
            up = tuple(up[i] - axis[i]*dot for i in range(3))
            if sum(v*v for v in up) < 1e-12:
                seed = min(((1.,0.,0.), (0.,1.,0.), (0.,0.,1.)),
                           key=lambda e: abs(sum(a*b for a, b in zip(e, axis))))
                dot = sum(a*b for a, b in zip(seed, axis))
                up = tuple(seed[i] - axis[i]*dot for i in range(3))
            contract.update(recipe='profile_extrusion', outer=_ring(outline), holes=[],
                            path=path, up=primitive._unit(up))
        return contract
    if kind == 'extrusion':
        outer = _ring(geometry['boundary'])
        holes = [_ring(h, positive=False) for h in geometry.get('holes', [])]
        z0, z1 = float(geometry['z_base']), float(geometry['z_top'])
        net_area = _area(outer) + sum(_area(h) for h in holes)
        if not all(math.isfinite(z) for z in (z0, z1)) or z1 <= z0 or net_area <= 1e-12:
            raise ValueError('Extrusion requires positive height and net profile area')
        vertices = [(x,y,z) for x,y in outer for z in (z0,z1)]
        return {'recipe': 'profile_extrusion', 'outer': outer, 'holes': holes,
                'path': [(0,0,z0), (0,0,z1)], 'up': (0,1,0),
                'expected_volume_m3': net_area*(z1-z0),
                'expected_bounds_m': _bounds(vertices), 'hole_count': len(holes)}
    if kind == 'quad':
        if thickness_m is None or not math.isfinite(thickness_m) or thickness_m <= 0:
            raise ValueError('Quad has no declared positive construction thickness')
        points = [_point(p) for p in geometry['corners']]
        if len(points) != 4:
            raise ValueError('Quad requires four corners')
        origin = points[0]
        u = primitive._unit(tuple(points[1][i]-origin[i] for i in range(3)))
        normal = primitive._unit(primitive._cross(u, tuple(points[2][i]-origin[i] for i in range(3))))
        up = primitive._cross(normal, u)
        if any(abs(sum((p[i]-origin[i])*normal[i] for i in range(3))) > TOLERANCE_M for p in points):
            raise ValueError('Non-planar quad has no approved solid construction')
        outer = _ring([(sum((p[i]-origin[i])*u[i] for i in range(3)),
                        sum((p[i]-origin[i])*up[i] for i in range(3))) for p in points])
        vertices = [tuple(p[i]+side*thickness_m/2*normal[i] for i in range(3))
                    for p in points for side in (-1,1)]
        return {'recipe': 'profile_extrusion', 'outer': outer, 'holes': [],
                'path': [tuple(origin[i]+side*thickness_m/2*normal[i] for i in range(3)) for side in (-1,1)],
                'up': up, 'expected_volume_m3': _area(outer)*thickness_m,
                'expected_bounds_m': _bounds(vertices), 'hole_count': 0}
    raise ValueError(f'Unsupported source primitive: {kind}')


def prepare_model(model):
    if str(model.get('schema_version', '')).split('.')[0] != '3':
        raise ValueError('Expected the full schema 3 model JSON')
    if model.get('units') != 'meters' or model.get('coordinate_system') != 'right_handed_z_up':
        raise ValueError('Expected the source metre / right-handed Z-up contract')
    if model.get('lattice', {}).get('cutaway') is not False:
        raise ValueError('Full Rhino delivery requires an explicit cutaway=False model')
    if not model.get('model_id') or not model.get('element_groups'):
        raise ValueError('Missing model identity or complete element groups')
    records = []
    seen = set()
    for group in model['element_groups']:
        if 'instances' not in group:
            raise ValueError('Web analysis summaries omit geometry; use the portable full model')
        shared = {k:v for k,v in group.items() if k != 'instances'}
        for item in group['instances']:
            identifier = item['id']
            if not identifier or identifier in seen:
                raise ValueError(f'Duplicate or empty source identity: {identifier}')
            seen.add(identifier)
            try:
                contract = primitive_contract(item['geometry'], model.get('profiles', {}), group.get('thickness_m'))
            except (ValueError, KeyError, TypeError) as error:
                raise ValueError(f'{identifier}: {error}') from error
            if contract['expected_volume_m3'] <= 1e-12:
                raise ValueError(f'{identifier}: source solid has zero volume')
            metadata = {**shared, **{k:v for k,v in item.items() if k != 'geometry'}}
            metadata.update(model_id=model['model_id'], authority='candidate')
            records.append({'id': identifier, 'metadata': metadata, 'contract': contract})
    if not records:
        raise ValueError('No source elements to export')
    return records


def _program_volume_digest(payload):
    """Hash the exact portable Program Volume contract without importing Pydantic.

    This digest binds the reference geometry to the nested JSON delivered with the
    building model.  Sorting keys keeps it stable across JSON writers while retaining
    every authored value.
    """
    encoded = json.dumps(
        payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
        allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _program_volume_layer(role):
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', str(role))
    if not safe:
        raise ValueError('Program Volume role cannot produce an empty Rhino layer name')
    return f'{PROGRAM_VOLUME_LAYER_ROOT}::{safe}'


def program_volume_reference_object_id(model_id, volume_id):
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        str(model_id)+'/reference/program-volume/'+str(volume_id))


def prepare_program_volume_references(model):
    """Convert the authored Program Volumes into separate Rhino reference records.

    Reference records deliberately omit ``id``/``mta:id``.  Those keys belong to the
    emitted building elements whose count and identity the candidate manifest audits.
    Program Volumes carry their own ``volume_id`` namespace and therefore cannot
    silently inflate the source-building solid count.
    """
    payload = model.get('program_volume_model')
    if payload is None:
        return []
    if not isinstance(payload, dict):
        raise ValueError('program_volume_model must be an object or null')
    if payload.get('schema_version') != 'mta.program_volumes/1.0':
        raise ValueError('Unsupported Program Volume reference schema')
    grammar = payload.get('grammar_id')
    grid = payload.get('grid')
    levels = payload.get('levels')
    volumes = payload.get('volumes')
    if not isinstance(grammar, str) or not grammar.strip():
        raise ValueError('Program Volume reference is missing its grammar')
    if not isinstance(grid, dict) or not isinstance(levels, list) or not isinstance(volumes, list):
        raise ValueError('Program Volume reference is missing grid, levels or volumes')
    x_lines, y_lines = grid.get('x_lines'), grid.get('y_lines')
    if (not isinstance(x_lines, list) or len(x_lines) < 2 or
            not isinstance(y_lines, list) or len(y_lines) < 2 or
            any(not isinstance(value, (int, float)) or not math.isfinite(value)
                for value in [*x_lines, *y_lines])):
        raise ValueError('Program Volume reference grid must contain finite axis lines')
    if (any(b <= a for a,b in zip(x_lines,x_lines[1:])) or
            any(b <= a for a,b in zip(y_lines,y_lines[1:]))):
        raise ValueError('Program Volume reference grid lines must increase')
    level_by_id = {}
    for level in levels:
        if not isinstance(level, dict) or not isinstance(level.get('id'), str):
            raise ValueError('Program Volume reference has an invalid level')
        if level['id'] in level_by_id:
            raise ValueError(f'Duplicate Program Volume level: {level["id"]}')
        z0, z1 = level.get('z_base'), level.get('z_top')
        if (not isinstance(z0, (int, float)) or not isinstance(z1, (int, float)) or
                not math.isfinite(z0) or not math.isfinite(z1) or z1 <= z0):
            raise ValueError(f'Program Volume level {level["id"]} has invalid vertical bounds')
        level_by_id[level['id']] = level
    digest = _program_volume_digest(payload)
    references = []
    seen = set()
    for volume in volumes:
        if not isinstance(volume, dict):
            raise ValueError('Program Volume reference contains a non-object volume')
        identifier = volume.get('id')
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ValueError('Program Volume reference has an empty or duplicate volume id')
        seen.add(identifier)
        level_id = volume.get('level_id')
        level = level_by_id.get(level_id)
        if level is None:
            raise ValueError(f'Program Volume {identifier} references an unknown level')
        if volume.get('level_index') != level.get('index'):
            raise ValueError(f'Program Volume {identifier} has a mismatched level index')
        rect = volume.get('grid_rect')
        if (not isinstance(rect, (list, tuple)) or len(rect) != 4 or
                any(not isinstance(index, int) or isinstance(index, bool) for index in rect)):
            raise ValueError(f'Program Volume {identifier} has an invalid grid rectangle')
        i0, j0, i1, j1 = rect
        if not (0 <= i0 < i1 < len(x_lines) and 0 <= j0 < j1 < len(y_lines)):
            raise ValueError(f'Program Volume {identifier} exceeds its reference grid')
        role = volume.get('role')
        space_ids = volume.get('space_ids')
        if not isinstance(role, str) or not role:
            raise ValueError(f'Program Volume {identifier} has no role')
        if (not isinstance(space_ids, list) or
                any(not isinstance(space_id, str) or not space_id for space_id in space_ids)):
            raise ValueError(f'Program Volume {identifier} has invalid space ids')
        geometry = {
            'type': 'extrusion',
            'boundary': [
                {'x': x_lines[i0], 'y': y_lines[j0]},
                {'x': x_lines[i1], 'y': y_lines[j0]},
                {'x': x_lines[i1], 'y': y_lines[j1]},
                {'x': x_lines[i0], 'y': y_lines[j1]},
            ],
            'holes': [],
            'z_base': level['z_base'],
            'z_top': level['z_top'],
        }
        references.append({
            'volume_id': identifier,
            'layer_path': _program_volume_layer(role),
            'metadata': {
                'reference_kind': PROGRAM_VOLUME_REFERENCE_KIND,
                'volume_id': identifier,
                'grammar_id': grammar,
                'program_volume_digest': digest,
                'role': role,
                'space_ids': space_ids,
                'category': volume.get('category'),
                'level_id': level_id,
                'authority': 'program_volume_reference',
            },
            'contract': primitive_contract(geometry, {}),
        })
    if not references:
        raise ValueError('Program Volume model contains no reference volumes')
    return references


def _curve(rg, points):
    points = list(points)
    return rg.PolylineCurve([rg.Point3d(*(tuple(p)+(0,)*(3-len(p)))) for p in points+[points[0]]])


def _extrusion(rg, contract):
    outer = _curve(rg, contract['outer'])
    holes = [_curve(rg, ring) for ring in contract['holes']]
    for curve in [outer, *holes]:
        intersections = rg.Intersect.Intersection.CurveSelf(curve, TOLERANCE_M)
        if intersections is not None and intersections.Count:
            raise ValueError('Source profile self-intersects')
    for index, hole in enumerate(holes):
        relation = rg.Curve.PlanarClosedCurveRelationship(hole, outer, rg.Plane.WorldXY, TOLERANCE_M)
        if relation != rg.RegionContainment.AInsideB:
            raise ValueError('Source opening crosses or lies outside its outer profile')
        if any(rg.Curve.PlanarClosedCurveRelationship(hole, previous, rg.Plane.WorldXY, TOLERANCE_M)
               != rg.RegionContainment.Disjoint for previous in holes[:index]):
            raise ValueError('Source opening profiles overlap or contain one another')
    return _set_extrusion(rg, contract, outer, holes)


def _set_extrusion(rg, contract, outer, holes):
    """Shared OpenNURBS profile construction after the host-specific planar check."""
    body = rg.Extrusion()
    if not body.SetPathAndUp(rg.Point3d(*contract['path'][0]), rg.Point3d(*contract['path'][1]), rg.Vector3d(*contract['up'])):
        raise ValueError('Rhino rejected the declared extrusion axis')
    if not body.SetOuterProfile(outer, True):
        raise ValueError('Rhino rejected the outer profile')
    for hole in holes:
        if not body.AddInnerProfile(hole):
            raise ValueError('Rhino rejected a source opening; it was not filled')
    if body.ProfileCount != contract['hole_count']+1:
        raise ValueError('Native extrusion lost an opening profile')
    return body


def build_native(rg, contract):
    if contract['recipe'] == 'box_brep':
        return rg.Brep.CreateFromBox([rg.Point3d(*p) for p in contract['vertices']])
    if contract['recipe'] == 'profile_extrusion':
        return _extrusion(rg, contract)
    # Curved-member station rings retain the shared source's piecewise planar body.
    # These are native trimmed surfaces joined into a Brep, never a Rhino Mesh.
    surfaces = []
    vertices = contract['vertices']
    for face in contract['faces']:
        points = [vertices[i] for i in face]
        if len(points) == 4:
            for indices in primitive.triangulate_quad(vertices, face):
                corners = [rg.Point3d(*vertices[i]) for i in indices]
                surface = rg.Brep.CreateFromCornerPoints(*corners, TOLERANCE_M)
                if surface is None:
                    raise ValueError('Rhino rejected a member side surface')
                surfaces.append(surface)
        else:
            caps = rg.Brep.CreatePlanarBreps(_curve(rg, points), TOLERANCE_M)
            if caps is None or len(caps) != 1:
                raise ValueError('Rhino could not create one exact member cap')
            surfaces.extend(caps)
    joined = rg.Brep.JoinBreps(surfaces, TOLERANCE_M)
    if joined is None or len(joined) != 1:
        raise ValueError('Member surfaces do not join into one native body')
    return joined[0]


def validate_native(rg, body, contract):
    if body is None or not isinstance(body, (rg.Brep, rg.Extrusion)) or not body.IsValid:
        raise ValueError('Native object is absent, invalid or is not a Brep/extrusion')
    brep = body.ToBrep() if isinstance(body, rg.Extrusion) else body
    if not brep.IsSolid:
        raise ValueError('Native object has naked edges or is not closed')
    if brep.SolidOrientation == rg.BrepSolidOrientation.Inward:
        if isinstance(body, rg.Extrusion):
            raise ValueError('Native extrusion has inward orientation')
        body.Flip()
    measure = rg.VolumeMassProperties.Compute(brep)
    if measure is None or measure.Volume <= 0:
        raise ValueError('Native volume cannot be measured as positive')
    expected = contract['expected_volume_m3']
    if not math.isclose(measure.Volume, expected, rel_tol=1e-6, abs_tol=1e-8):
        raise ValueError(f'Native volume {measure.Volume} differs from source volume {expected}')
    box = body.GetBoundingBox(True)
    actual = [[box.Min.X,box.Min.Y,box.Min.Z], [box.Max.X,box.Max.Y,box.Max.Z]]
    if any(abs(a-b) > 5*TOLERANCE_M for row, target in zip(actual, contract['expected_bounds_m']) for a,b in zip(row,target)):
        raise ValueError('Native bounds differ from the source geometry')
    if isinstance(body, rg.Extrusion) and body.ProfileCount != contract['hole_count']+1:
        raise ValueError('Native body lost an architectural opening')
    return {'native_type': body.GetType().Name, 'closed': True, 'valid': True,
            'volume_m3': measure.Volume, 'bounds_m': actual, 'hole_count': contract['hole_count']}


def _layer(doc, Rhino, full_path, *, visible=True, locked=False):
    index = doc.Layers.FindByFullPath(full_path, -1)
    if index >= 0:
        existing = doc.Layers[index]
        if existing.IsVisible != visible or existing.IsLocked != locked:
            existing.IsVisible = visible
            existing.IsLocked = locked
            if not doc.Layers.Modify(existing, index, True):
                raise ValueError(f'Rhino could not apply reference layer state to {full_path}')
        return index
    parent_path, _, name = full_path.rpartition('::')
    layer = Rhino.DocObjects.Layer()
    layer.Name = name
    layer.IsVisible = visible
    layer.IsLocked = locked
    if parent_path:
        parent = _layer(doc, Rhino, parent_path)
        layer.ParentLayerId = doc.Layers[parent].Id
    index = doc.Layers.Add(layer)
    if index < 0:
        raise ValueError(f'Rhino could not create semantic layer {full_path}')
    return index


def validate_saved_file(path, records, *, model_id, source_sha256, run_id,
                        program_volume_references=None):
    """Reopen actual .3dm bytes with RhinoCommon and remeasure every source object."""
    import Rhino
    rg = Rhino.Geometry
    reopened = Rhino.FileIO.File3dm.Read(str(path))
    if reopened is None:
        raise ValueError('Rhino cannot reopen the saved .3dm')
    try:
        if reopened.Settings.ModelUnitSystem != Rhino.UnitSystem.Meters:
            raise ValueError('Saved Rhino model has changed units')
        expected = {record['id']: record for record in records}
        expected_references = {
            reference['volume_id']: reference
            for reference in (program_volume_references or [])}
        found = {}
        found_references = {}
        for obj in reopened.Objects:
            if obj.Attributes.GetUserString('mta:reference_kind') == PROGRAM_VOLUME_REFERENCE_KIND:
                identifier = obj.Attributes.GetUserString('mta:volume_id')
                if identifier not in expected_references or identifier in found_references:
                    raise ValueError('Saved Rhino model has an unrelated or duplicate Program Volume reference')
                reference = expected_references[identifier]
                values = {
                    'model_id': model_id, 'source_sha256': source_sha256,
                    'run_id': run_id, **reference['metadata']}
                for key, value in values.items():
                    encoded = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
                    if obj.Attributes.GetUserString('mta:'+key) != encoded:
                        raise ValueError(f'Saved Program Volume {identifier} lost metadata: {key}')
                layer = reopened.Layers[obj.Attributes.LayerIndex]
                if (layer.FullPath != reference['layer_path'] or layer.IsVisible or
                        not layer.IsLocked):
                    raise ValueError(f'Saved Program Volume {identifier} lost its hidden locked reference layer')
                expected_id = program_volume_reference_object_id(model_id,identifier)
                if (obj.Attributes.Name != identifier or str(obj.Attributes.Id) != str(expected_id) or
                        obj.Attributes.Mode != Rhino.DocObjects.ObjectMode.Locked):
                    raise ValueError(f'Saved Program Volume {identifier} lost its stable locked identity')
                result = validate_native(rg, obj.Geometry, reference['contract'])
                result.update(object_id=str(obj.Attributes.Id),
                              layer_path=layer.FullPath, visible=False, locked=True)
                found_references[identifier] = result
                continue
            identifier = obj.Attributes.GetUserString('mta:id')
            if identifier not in expected or identifier in found:
                raise ValueError('Saved Rhino model has missing, duplicate or unrelated source identity')
            for key, value in {'model_id':model_id, 'source_sha256':source_sha256, 'run_id':run_id, 'authority':'candidate'}.items():
                if obj.Attributes.GetUserString('mta:'+key) != value:
                    raise ValueError(f'Saved object {identifier} has stale {key}')
            found[identifier] = validate_native(rg, obj.Geometry, expected[identifier]['contract'])
        if set(found) != set(expected):
            raise ValueError('Saved Rhino model is missing source elements')
        if set(found_references) != set(expected_references):
            raise ValueError('Saved Rhino model is missing Program Volume references')
        if program_volume_references is not None:
            return found, found_references
        return found
    finally:
        reopened.Dispose()


def export_to_document(doc, model_path, output_directory, *, run_id):
    """Build in the explicitly supplied empty slot and publish a candidate directory."""
    import Rhino
    from System import Guid
    if doc is None or not run_id or not str(run_id).strip():
        raise ValueError('Explicit Rhino slot document and exact run ID are required')
    if list(doc.Objects.GetObjectList(Rhino.DocObjects.ObjectType.AnyObject)):
        raise ValueError('Use an isolated empty Rhino slot; an existing document will not be cleared')
    model_path = Path(model_path).resolve(strict=True)
    destination = Path(output_directory).resolve()
    if destination.exists():
        raise FileExistsError(f'Refusing to overwrite {destination}')
    source_sha = _hash(model_path)
    model = json.loads(model_path.read_text(encoding='utf-8-sig'))
    records = prepare_model(model)
    program_volume_references = prepare_program_volume_references(model)
    source_files = {str(p): _hash(p) for p in (Path(__file__), Path(primitive.__file__))}
    source_files[str(model_path)] = source_sha
    rg = Rhino.Geometry
    bodies = []
    for record in records:
        try:
            body = build_native(rg, record['contract'])
            validation = validate_native(rg, body, record['contract'])
        except ValueError as error:
            raise ValueError(f'{record["id"]}: {error}') from error
        bodies.append((record, body, validation))
    reference_bodies = []
    for reference in program_volume_references:
        try:
            body = build_native(rg, reference['contract'])
            validation = validate_native(rg, body, reference['contract'])
        except ValueError as error:
            raise ValueError(f'{reference["volume_id"]}: {error}') from error
        reference_bodies.append((reference, body, validation))
    doc.ModelUnitSystem = Rhino.UnitSystem.Meters
    doc.ModelAbsoluteTolerance = TOLERANCE_M
    doc.ModelAngleToleranceRadians = math.radians(.1)
    document_metadata = {'model_id':model['model_id'], 'run_id':str(run_id), 'source_sha256':source_sha,
                         'authority':'candidate', 'adapter_version':ADAPTER_VERSION,
                         'coordinate_system':'right_handed_z_up', 'representation':'complete'}
    for key, value in document_metadata.items():
        doc.Strings.SetString('mta:'+key, value)
    groups = {}
    added = []
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.mta-rhino-', dir=destination.parent))
    try:
        for record, body, _ in bodies:
            metadata = {**record['metadata'], **document_metadata}
            layer_parts = ['MTA', metadata['level_id'], metadata['semantic_layer'], metadata['subsystem'], metadata['kind']]
            layer_path = '::'.join(re.sub(r'[^A-Za-z0-9_-]', '_', str(p)) for p in layer_parts)
            attributes = Rhino.DocObjects.ObjectAttributes()
            attributes.Name = record['id']
            attributes.ObjectId = Guid(str(uuid.uuid5(uuid.NAMESPACE_URL, model['model_id']+'/'+record['id'])))
            attributes.LayerIndex = _layer(doc, Rhino, layer_path, visible=metadata['kind'] != 'program_zone')
            for key, value in metadata.items():
                if value is not None:
                    attributes.SetUserString('mta:'+key, value if isinstance(value,str) else json.dumps(value, sort_keys=True))
            for label in [metadata.get('group_id'), metadata.get('assembly_id')]:
                if label:
                    if label not in groups:
                        groups[label] = doc.Groups.Add(str(label))
                    attributes.AddToGroup(groups[label])
            identifier = (doc.Objects.AddExtrusion(body, attributes) if isinstance(body, rg.Extrusion)
                          else doc.Objects.AddBrep(body, attributes))
            if identifier == Guid.Empty:
                raise ValueError(f'Rhino failed to add {record["id"]}')
            added.append(identifier)
        for reference, body, _ in reference_bodies:
            metadata = {**document_metadata, **reference['metadata']}
            attributes = Rhino.DocObjects.ObjectAttributes()
            attributes.Name = reference['volume_id']
            attributes.ObjectId = Guid(str(program_volume_reference_object_id(
                model['model_id'],reference['volume_id'])))
            attributes.LayerIndex = _layer(
                doc, Rhino, reference['layer_path'], visible=False, locked=True)
            attributes.Mode = Rhino.DocObjects.ObjectMode.Locked
            for key, value in metadata.items():
                if value is not None:
                    attributes.SetUserString(
                        'mta:'+key,
                        value if isinstance(value, str) else json.dumps(value, sort_keys=True))
            identifier = (doc.Objects.AddExtrusion(body, attributes)
                          if isinstance(body, rg.Extrusion)
                          else doc.Objects.AddBrep(body, attributes))
            if identifier == Guid.Empty:
                raise ValueError(f'Rhino failed to add Program Volume {reference["volume_id"]}')
            added.append(identifier)
        path = staging / 'model.3dm'
        options = Rhino.FileIO.FileWriteOptions()
        options.SuppressDialogBoxes = True
        options.SuppressAllInput = True
        options.UpdateDocumentPath = False
        options.WriteSelectedObjectsOnly = False
        if not doc.WriteFile(str(path), options):
            raise ValueError('Rhino failed to save candidate .3dm')
        reopened, reopened_references = validate_saved_file(
            path, records, model_id=model['model_id'], source_sha256=source_sha,
            run_id=str(run_id), program_volume_references=program_volume_references)
        if any(_hash(p) != digest for p,digest in source_files.items()):
            raise RuntimeError('Source model or adapter changed during native export')
        shutil.copyfile(model_path, staging / 'building_model_v3.json')
        report = {'schema_version':'mta.rhino_candidate/0.1', 'status':'geometry_candidate', 'authority':'candidate',
                  **{k:v for k,v in document_metadata.items() if k != 'authority'},
                  'geometry_sha256':_hash(path), 'source_files':source_files,
                  'geometry_file':'model.3dm', 'source_file':'building_model_v3.json',
                  'object_count':len(reopened), 'source_element_count':len(records),
                  'file_object_count':len(reopened) + len(reopened_references),
                  'program_volume_reference_count':len(reopened_references),
                  'program_volume_digest':(
                      program_volume_references[0]['metadata']['program_volume_digest']
                      if program_volume_references else None),
                  'native_types':dict(Counter(item['native_type'] for item in reopened.values())),
                  'program_volume_reference_native_types':dict(Counter(
                      item['native_type'] for item in reopened_references.values())),
                  'verification':{'native_geometry':'passed', 'saved_file_reopened':'passed', 'source_identity':'passed',
                                  'program_volume_references':(
                                      'passed' if program_volume_references else 'not_applicable'),
                                  'architectural_review':'not_checked', 'rhino_acceptance':'not_recorded', 'revit_import':'not_checked'},
                  'objects':reopened,
                  'program_volume_references':reopened_references,
                  'limitations':['Native solids and source parity do not certify architectural interfaces or code compliance.',
                                 'Source box/CHS outer-solid profiles are retained; no hollow construction is invented.',
                                 'Program-zone overlays and Program Volume control references remain separate from source building-solid counts.',
                                 'Repeated elements remain individually editable native objects in semantic and assembly groups.']}
        (staging / 'candidate_manifest.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        staging.rename(destination)
        doc.Views.Redraw()
        return report
    except BaseException:
        for identifier in added:
            doc.Objects.Delete(identifier, True)
        shutil.rmtree(staging)
        raise
