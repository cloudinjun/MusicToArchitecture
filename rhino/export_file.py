"""Standalone OpenNURBS .3dm candidate export; no Rhino application or licence use.

    python -m rhino.export_file --model MODEL_JSON --run-id RUN_ID --output NEW_DIR

Uses the official rhino3dm file SDK and the same contracts as the RhinoCommon adapter.
File validation is distinct from a Rhino application review and geometry acceptance.
"""
from __future__ import annotations

import argparse
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

from . import import_building_model_v3 as shared


def _encoded_hash(body):
    return hashlib.sha256(json.dumps(body.Encode(), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _exact_prism_contract(contract):
    """Recognize a constant-width source polyhedron without approximating its faces.

    Planar ramp runs are side-profile prisms even though their travel paths bend.
    Both caps and every connecting face must match that extrusion exactly.
    """
    from shapely.geometry import Polygon, MultiPoint
    from shapely.ops import unary_union
    vertices = contract['vertices']
    tolerance = shared.TOLERANCE_M / 10
    triangles = shared.primitive.triangulate_faces(vertices, contract['faces'])
    dot = lambda a,b: sum(x*y for x,y in zip(a,b))
    subtract = lambda a,b: tuple(x-y for x,y in zip(a,b))
    for face in contract['faces']:
        for start,end in zip(face,face[1:]+face[:1]):
            difference = subtract(vertices[end],vertices[start])
            length = math.sqrt(dot(difference,difference))
            if length <= tolerance:
                continue
            axis = tuple(value/length for value in difference)
            offsets = [dot(point,axis) for point in vertices]
            low, high = min(offsets),max(offsets)
            if high-low <= tolerance or any(min(abs(value-low),abs(value-high))>tolerance for value in offsets):
                continue
            origin = vertices[offsets.index(low)]
            up = next((subtract(point,origin) for point,value in zip(vertices,offsets)
                       if abs(value-low)<=tolerance and math.dist(point,origin)>tolerance),None)
            if up is None:
                continue
            up = shared.primitive._unit(up)
            u = shared.primitive._cross(up,axis)
            projected = [(dot(subtract(point,origin),u),dot(subtract(point,origin),up)) for point in vertices]
            caps = [[],[]]; sides = []
            for triangle in triangles:
                values = [offsets[index] for index in triangle]
                points = [projected[index] for index in triangle]
                if max(values)-min(values)<=tolerance:
                    caps[0 if abs(values[0]-low)<=tolerance else 1].append(Polygon(points))
                else:
                    sides.append(MultiPoint(points).convex_hull)
            if not all(caps):
                continue
            first,second = (unary_union(cap) for cap in caps)
            if (first.geom_type != 'Polygon' or not first.is_valid or
                first.symmetric_difference(second).area > tolerance*tolerance or
                any(side.area>tolerance*tolerance or side.difference(first.boundary.buffer(tolerance)).length>tolerance for side in sides)):
                continue
            volume = first.area*(high-low)
            if abs(volume-contract['expected_volume_m3']) > max(1e-8,volume*1e-8):
                continue
            return {**contract, 'recipe':'profile_extrusion',
                    'outer':shared._ring(list(first.exterior.coords)),
                    'holes':[shared._ring(list(ring.coords),positive=False) for ring in first.interiors],
                    'hole_count':len(first.interiors), 'path':[origin,tuple(origin[i]+axis[i]*(high-low) for i in range(3))],
                    'up':up, 'conversion':'exact_constant_width_source_polyhedron'}
    return None


def build_file_geometry(r, contract):
    recipe = contract['recipe']
    if recipe == 'profile_extrusion':
        from shapely.geometry import Polygon
        polygon = Polygon(contract['outer'], contract['holes'])
        if polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
            raise ValueError('Invalid outer profile or architectural opening; no repair is applied')
        return shared._set_extrusion(r, contract, shared._curve(r, contract['outer']),
                                     [shared._curve(r, ring) for ring in contract['holes']])
    if recipe == 'box_brep':
        vertices = contract['vertices']
        origin = vertices[0]
        axes = [tuple(vertices[index][i]-origin[i] for i in range(3)) for index in (1,3,4)]
        dimensions = [math.sqrt(sum(v*v for v in axis)) for axis in axes]
        body = r.Brep.CreateFromBoundingBox(r.BoundingBox(r.Point3d(0,0,0), r.Point3d(*dimensions)))
        plane = r.Plane(r.Point3d(*origin), r.Vector3d(*axes[0]), r.Vector3d(*axes[1]))
        if body is None or not body.Transform(r.Transform.PlaneToPlane(r.Plane.WorldXY(), plane)):
            raise ValueError('OpenNURBS could not construct the rotated box Brep')
        return body
    if recipe != 'member_faceted_brep':
        raise ValueError(f'Unsupported native recipe: {recipe}')
    prism = _exact_prism_contract(contract)
    if prism is not None:
        return build_file_geometry(r,prism)
    # The SDK conversion must still satisfy native validity; no tolerance patch.
    mesh = r.Mesh()
    mesh.Vertices.UseDoublePrecisionVertices = True
    for point in contract['vertices']:
        mesh.Vertices.Add(*point)
    for face in shared.primitive.triangulate_faces(contract['vertices'], contract['faces']):
        mesh.Faces.AddFace(*face)
    if not mesh.IsValid or not mesh.IsClosed:
        raise ValueError('Source member tessellation does not form a closed conversion body')
    body = r.Brep.CreateFromMesh(mesh, True)
    if body is None:
        raise ValueError('OpenNURBS could not convert the member to a native Brep')
    return body


def validate_file_geometry(r, body, contract):
    if not isinstance(body, (r.Brep, r.Extrusion)):
        raise ValueError('Expected editable native Brep/Extrusion, not mesh geometry')
    if not body.IsValid or not body.IsSolid:
        raise ValueError(f'Native file geometry is invalid or open: {body.IsValidWithLog}')
    box = body.GetTightBoundingBox()
    bounds = [[box.Min.X,box.Min.Y,box.Min.Z], [box.Max.X,box.Max.Y,box.Max.Z]]
    if any(abs(a-b) > 5*shared.TOLERANCE_M for actual, expected in zip(bounds,contract['expected_bounds_m']) for a,b in zip(actual,expected)):
        raise ValueError('Native file geometry bounds differ from source geometry')
    if isinstance(body, r.Extrusion):
        if body.ProfileCount != contract['hole_count']+1 or not body.IsCappedAtTop or not body.IsCappedAtBottom:
            raise ValueError('Native extrusion lost a profile, architectural opening or cap')
    return {'native_type':type(body).__name__, 'valid':True, 'closed':True,
            'bounds_m':bounds, 'hole_count':contract['hole_count'],
            'conversion':('exact_constant_width_source_polyhedron'
                          if contract['recipe']=='member_faceted_brep' and isinstance(body,r.Extrusion)
                          else contract['recipe']),
            'source_expected_volume_m3':contract['expected_volume_m3'],
            'native_volume_verification':'not_checked', 'geometry_serialization_sha256':_encoded_hash(body)}


def _file_layer(r, file, cache, path, visible, locked=False):
    if path in cache:
        return cache[path]
    parent, _, name = path.rpartition('::')
    layer = r.Layer()
    layer.Name = name
    layer.Visible = visible
    layer.Locked = locked
    if parent:
        layer.ParentLayerId = file.Layers[_file_layer(r,file,cache,parent,True)].Id
    index = file.Layers.Add(layer)
    cache[path] = index
    return index


def validate_file(path, records, document_metadata, before=None,
                  program_volume_references=None, reference_before=None):
    """Read the actual persisted .3dm, then check every native body and source ID."""
    import rhino3dm as r
    file = r.File3dm.Read(str(path))
    if file is None:
        raise ValueError('OpenNURBS cannot reopen the saved .3dm')
    if file.Settings.ModelUnitSystem != r.UnitSystem.Meters:
        raise ValueError('Saved model units are not metres')
    for key,value in document_metadata.items():
        if file.Strings['mta:'+key] != value:
            raise ValueError(f'Saved document metadata mismatch: {key}')
    expected = {record['id']:record for record in records}
    expected_references = {
        reference['volume_id']: reference
        for reference in (program_volume_references or [])}
    found = {}
    found_references = {}
    for obj in file.Objects:
        if obj.Attributes.GetUserString('mta:reference_kind') == shared.PROGRAM_VOLUME_REFERENCE_KIND:
            identifier = obj.Attributes.GetUserString('mta:volume_id')
            if identifier not in expected_references or identifier in found_references:
                raise ValueError('Saved .3dm contains an unrelated or duplicate Program Volume reference')
            reference = expected_references[identifier]
            values = {**document_metadata, **reference['metadata']}
            for key,value in values.items():
                if value is not None:
                    encoded = value if isinstance(value,str) else json.dumps(value,sort_keys=True)
                    if obj.Attributes.GetUserString('mta:'+key) != encoded:
                        raise ValueError(f'Saved Program Volume {identifier} lost metadata: {key}')
            layer = file.Layers[obj.Attributes.LayerIndex]
            if (layer.FullPath != reference['layer_path'] or layer.Visible or
                    not layer.Locked):
                raise ValueError(f'Saved Program Volume {identifier} lost its hidden locked reference layer')
            expected_id = shared.program_volume_reference_object_id(
                document_metadata['model_id'],identifier)
            if (obj.Attributes.Name != identifier or obj.Attributes.Id != expected_id or
                    obj.Attributes.Mode != r.ObjectMode.Locked):
                raise ValueError(f'Saved Program Volume {identifier} lost its stable locked identity')
            result = validate_file_geometry(r,obj.Geometry,reference['contract'])
            if (reference_before and
                    result['geometry_serialization_sha256'] !=
                    reference_before[identifier]['geometry_serialization_sha256']):
                raise ValueError(
                    f'Program Volume geometry serialization changed on readback: {identifier}')
            result.update(object_id=str(obj.Attributes.Id), layer_index=obj.Attributes.LayerIndex,
                          layer_path=layer.FullPath, visible=False, locked=True)
            found_references[identifier] = result
            continue
        identifier = obj.Attributes.GetUserString('mta:id')
        if identifier not in expected or identifier in found:
            raise ValueError('Saved .3dm contains an unrelated or duplicate source element')
        for key,value in document_metadata.items():
            if obj.Attributes.GetUserString('mta:'+key) != value:
                raise ValueError(f'Saved object {identifier} has mismatched {key}')
        source_metadata = expected[identifier]['metadata']
        for key,value in {**source_metadata,**document_metadata}.items():
            if value is not None:
                encoded = value if isinstance(value,str) else json.dumps(value,sort_keys=True)
                if obj.Attributes.GetUserString('mta:'+key) != encoded:
                    raise ValueError(f'Saved object {identifier} lost source metadata: {key}')
        names = ['MTA',source_metadata['level_id'],source_metadata['semantic_layer'],source_metadata['subsystem'],source_metadata['kind']]
        layer_path = '::'.join(re.sub(r'[^A-Za-z0-9_-]', '_', str(name)) for name in names)
        if file.Layers[obj.Attributes.LayerIndex].FullPath != layer_path:
            raise ValueError(f'Saved object {identifier} has the wrong semantic layer')
        expected_groups = {str(source_metadata[key]) for key in ('group_id','assembly_id') if source_metadata.get(key)}
        actual_groups = {file.Groups[index].Name for index in obj.Attributes.GetGroupList()}
        if actual_groups != expected_groups:
            raise ValueError(f'Saved object {identifier} lost its source group or assembly')
        if (obj.Attributes.Name != identifier or
            obj.Attributes.Id != uuid.uuid5(uuid.NAMESPACE_URL,document_metadata['model_id']+'/'+identifier)):
            raise ValueError(f'Saved object {identifier} lost its stable native identity')
        result = validate_file_geometry(r,obj.Geometry,expected[identifier]['contract'])
        if before and result['geometry_serialization_sha256'] != before[identifier]['geometry_serialization_sha256']:
            raise ValueError(f'Native geometry serialization changed on readback: {identifier}')
        result['object_id'] = str(obj.Attributes.Id)
        result['layer_index'] = obj.Attributes.LayerIndex
        found[identifier] = result
    if set(found) != set(expected):
        raise ValueError('Saved .3dm omits source geometry')
    if set(found_references) != set(expected_references):
        raise ValueError('Saved .3dm omits Program Volume references')
    if program_volume_references is not None:
        return found, found_references
    return found


def export_file(model_path: Path, destination: Path, *, run_id: str) -> dict:
    import rhino3dm as r
    import shapely
    if not run_id or not run_id.strip():
        raise ValueError('The exact pipeline run ID is required')
    model_path = Path(model_path).resolve(strict=True)
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError(f'Refusing to overwrite {destination}')
    source_sha = shared._hash(model_path)
    model = json.loads(model_path.read_text(encoding='utf-8-sig'))
    records = shared.prepare_model(model)
    program_volume_references = shared.prepare_program_volume_references(model)
    tracked = [model_path,Path(__file__),Path(shared.__file__),Path(shared.primitive.__file__)]
    input_hashes = {str(path):shared._hash(path) for path in tracked}
    file = r.File3dm()
    file.ApplicationName = 'MusicToArchitecture rhino3dm_file'
    file.ApplicationDetails = 'Editable full v3 candidate; Rhino GUI review and acceptance are pending.'
    file.Settings.ModelUnitSystem = r.UnitSystem.Meters
    file.Settings.ModelAbsoluteTolerance = shared.TOLERANCE_M
    metadata = {'model_id':model['model_id'], 'run_id':run_id, 'source_sha256':source_sha,
                'producer':'rhino3dm_file', 'authority':'candidate', 'representation':'complete',
                'coordinate_system':'right_handed_z_up', 'adapter_version':shared.ADAPTER_VERSION}
    for key,value in metadata.items():
        file.Strings['mta:'+key] = value
    layers = {}; groups = {}; before = {}; reference_before = {}
    for record in records:
        try:
            body = build_file_geometry(r,record['contract'])
            before[record['id']] = validate_file_geometry(r,body,record['contract'])
        except (ValueError,RuntimeError,TypeError) as error:
            raise ValueError(f'{record["id"]}: {error}') from error
        values = {**record['metadata'], **metadata}
        names = ['MTA',values['level_id'],values['semantic_layer'],values['subsystem'],values['kind']]
        layer_path = '::'.join(re.sub(r'[^A-Za-z0-9_-]', '_', str(name)) for name in names)
        attributes = r.ObjectAttributes()
        attributes.Name = record['id']
        attributes.Id = uuid.uuid5(uuid.NAMESPACE_URL,model['model_id']+'/'+record['id'])
        attributes.LayerIndex = _file_layer(r,file,layers,layer_path,values['kind'] != 'program_zone')
        for key,value in values.items():
            if value is not None:
                attributes.SetUserString('mta:'+key,value if isinstance(value,str) else json.dumps(value,sort_keys=True))
        for name in [values.get('group_id'),values.get('assembly_id')]:
            if name:
                if name not in groups:
                    group = r.Group(); group.Name = str(name)
                    file.Groups.Add(group)
                    groups[name] = len(file.Groups)-1
                attributes.AddToGroup(groups[name])
        identifier = (file.Objects.AddExtrusion(body,attributes) if isinstance(body,r.Extrusion)
                      else file.Objects.AddBrep(body,attributes))
        if identifier.int == 0:
            raise ValueError(f'OpenNURBS failed to store {record["id"]}')
    for reference in program_volume_references:
        try:
            body = build_file_geometry(r,reference['contract'])
            reference_before[reference['volume_id']] = validate_file_geometry(
                r,body,reference['contract'])
        except (ValueError,RuntimeError,TypeError) as error:
            raise ValueError(f'{reference["volume_id"]}: {error}') from error
        values = {**metadata, **reference['metadata']}
        attributes = r.ObjectAttributes()
        attributes.Name = reference['volume_id']
        attributes.Id = shared.program_volume_reference_object_id(
            model['model_id'],reference['volume_id'])
        attributes.LayerIndex = _file_layer(
            r,file,layers,reference['layer_path'],False,True)
        attributes.Mode = r.ObjectMode.Locked
        for key,value in values.items():
            if value is not None:
                attributes.SetUserString(
                    'mta:'+key,
                    value if isinstance(value,str) else json.dumps(value,sort_keys=True))
        identifier = (file.Objects.AddExtrusion(body,attributes)
                      if isinstance(body,r.Extrusion)
                      else file.Objects.AddBrep(body,attributes))
        if identifier.int == 0:
            raise ValueError(
                f'OpenNURBS failed to store Program Volume {reference["volume_id"]}')
    destination.parent.mkdir(parents=True,exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.mta-rhino-file-',dir=destination.parent))
    try:
        path = staging/'model.3dm'
        if not file.Write(str(path),8):
            raise ValueError('OpenNURBS failed to write .3dm')
        found, found_references = validate_file(
            path,records,metadata,before,program_volume_references,reference_before)
        shutil.copyfile(model_path,staging/'building_model_v3.json')
        if shared._hash(staging/'building_model_v3.json') != source_sha or any(shared._hash(p)!=digest for p,digest in input_hashes.items()):
            raise RuntimeError('Source model or exporter changed during file generation')
        report = {'schema_version':'mta.rhino_candidate/0.1', 'status':'geometry_candidate', **metadata,
                  'geometry_sha256':shared._hash(path), 'geometry_file':'model.3dm', 'source_file':'building_model_v3.json',
                  'source_files':input_hashes, 'sdk_versions':{'rhino3dm':r.__version__,'shapely':shapely.__version__},
                  'object_count':len(found), 'source_element_count':len(records),
                  'file_object_count':len(found) + len(found_references),
                  'program_volume_reference_count':len(found_references),
                  'program_volume_digest':(
                      program_volume_references[0]['metadata']['program_volume_digest']
                      if program_volume_references else None),
                  'native_types':dict(Counter(item['native_type'] for item in found.values())),
                  'native_conversions':dict(Counter(item['conversion'] for item in found.values())),
                  'program_volume_reference_native_types':dict(Counter(
                      item['native_type'] for item in found_references.values())),
                  'verification':{'file_geometry':'passed', 'saved_file_reopened':'passed', 'source_identity':'passed',
                      'geometry_serialization':'passed', 'native_volume':'not_checked', 'rhino_gui_review':'not_checked',
                      'program_volume_references':(
                          'passed' if program_volume_references else 'not_applicable'),
                      'architectural_review':'not_checked', 'rhino_acceptance':'not_recorded', 'revit_import':'not_checked'},
                  'objects':found,
                  'program_volume_references':found_references,
                  'limitations':['Official standalone OpenNURBS file SDK; no Rhino application was launched for this export.',
                      'Rhino GUI review remains unavailable while the application reports License Not Found.',
                      'The SDK exposes no mass-properties calculator. Source expected volumes are not native measured volumes.',
                      'File validity, closure, bounds and exact serialization do not establish architectural or code acceptance.',
                      'Source outer-solid section conventions are retained; no hollow profile or design repair is invented.',
                      'Constant-width polyline members use an exactly matched side-profile extrusion; other curves require valid faceted Breps. No mesh-only elements are written.',
                      'Program-zone semantic volumes and Program Volume reference objects remain outside source building-solid counts.']}
        (staging/'candidate_manifest.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        staging.rename(destination)
        return report
    except BaseException:
        shutil.rmtree(staging)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(argv)
    try:
        report = export_file(args.model,args.output,run_id=args.run_id)
    except (OSError,ValueError,RuntimeError) as error:
        print(f'Rhino file export blocked: {error}',file=sys.stderr)
        return 2
    print(json.dumps({key:report[key] for key in ('status','producer','model_id','run_id','source_sha256','geometry_sha256','object_count','native_types','verification')},indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
