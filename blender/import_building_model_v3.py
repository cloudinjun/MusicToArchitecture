"""Blender adapter for schema 3.0.

Consumes the four geometry primitives, sweeps the section profiles that the load
calculation chose, and exports a semantic GLB plus study-model renders.

Two decisions worth stating:

- **Meshes are merged per (layer, subsystem, category, material).** A member-level model
  is several thousand elements, and one glTF node per element makes the browser crawl.
  The JSON model stays the element-level authority; the GLB is presentation, and it keeps
  exactly the grouping the web viewport filters on.
- **The palette is a white study model.** The register comes from edge density and
  shadow, not from colour. Only the scale figures and the curtain-wall frame are allowed
  to carry a hue, because those two carry information the geometry cannot.

Authority: presentation only. Nothing this script produces is accepted geometry.

    blender --background --python blender/import_building_model_v3.py -- \
        MODEL_JSON OUT_BLEND OUT_RENDER_DIR [OUT_GLB] [OUT_MANIFEST] [RENDER_MODE]
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import bpy

# Share the exact portable bodies, including concave footprints and their holes.
# Blender's Python dependencies are isolated from its bundled installation.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))
from blender.runtime_dependencies import require_polygon_runtime
_POLYGON_RUNTIME = require_polygon_runtime()
from backend.app.mesh_primitives import box_mesh, member_mesh, extrusion_mesh


MATERIALS = {
    'white':            ((0.900, 0.898, 0.890, 1.0), 0.52, 1.0),
    'white_soft':       ((0.840, 0.838, 0.830, 1.0), 0.62, 1.0),
    'steel_white':      ((0.925, 0.925, 0.920, 1.0), 0.40, 1.0),
    'steel_light':      ((0.870, 0.870, 0.866, 1.0), 0.45, 1.0),
    'steel_dark':       ((0.380, 0.380, 0.385, 1.0), 0.35, 1.0),
    'frame_dark':       ((0.135, 0.138, 0.145, 1.0), 0.40, 1.0),
    'concrete':         ((0.760, 0.756, 0.746, 1.0), 0.78, 1.0),
    # Timber and terracotta arrived with the tectonic families. A study model in
    # basswood is not white, and a mass-timber frame that renders as white steel
    # loses the one cue that says which material was selected.
    'timber':           ((0.792, 0.686, 0.522, 1.0), 0.62, 1.0),
    'timber_light':     ((0.860, 0.780, 0.640, 1.0), 0.58, 1.0),
    'terracotta':       ((0.706, 0.396, 0.278, 1.0), 0.74, 1.0),
    'concrete_light':   ((0.855, 0.852, 0.842, 1.0), 0.70, 1.0),
    'glass':            ((0.700, 0.780, 0.815, 1.0), 0.08, 0.16),
    'accent_red':       ((0.700, 0.098, 0.082, 1.0), 0.55, 1.0),
    'furn':             ((0.700, 0.686, 0.660, 1.0), 0.72, 1.0),
    'prog_public':      ((0.240, 0.510, 0.880, 1.0), 0.72, 1.0),
    'prog_private':     ((0.900, 0.520, 0.220, 1.0), 0.72, 1.0),
    'prog_circulation': ((0.220, 0.700, 0.410, 1.0), 0.72, 1.0),
    'prog_service':     ((0.580, 0.390, 0.760, 1.0), 0.72, 1.0),
    'ground':           ((0.512, 0.516, 0.524, 1.0), 0.90, 1.0),
    'ground_light':     ((0.735, 0.735, 0.730, 1.0), 0.86, 1.0),
}

# The legacy project made the program-volume contract readable with three primary
# colours.  Service is a fourth category in schema 3.0 and remains distinct rather
# than being folded into private.  These are review materials only: canonical GLB
# materials still come from the model's own material table above.
PROGRAM_VOLUME_COLOURS = {
    'private': (1.0, 0.0, 0.0, 0.62),
    'public': (0.0, 0.0, 1.0, 0.62),
    'circulation': (0.0, 1.0, 0.0, 0.62),
    'service': (1.0, 0.55, 0.0, 0.62),
}

PROGRAM_VOLUME_COLLECTION = 'Program_Volumes'
PROGRAM_VOLUME_RENDER = '06_program_volumes.png'
PROGRAM_STRUCTURE_RENDER = '07_program_structure.png'
PROGRAM_FACADE_RENDER = '08_program_facade.png'

# The three protocol renders use one automatically framed camera specification.
# Their only change is layer visibility, so structure/facade comparisons cannot be
# manufactured by choosing a more flattering view for one stage.
PROGRAM_VOLUME_REVIEW_CAMERA = 'program_volume_bounds'

VIEWS = [
    ('01_three_quarter', (62.0, -78.0, 44.0), (0.0, -2.0, 12.0), 62, (1600, 1100)),
    ('02_section_open_side', (58.0, 60.0, 30.0), (-2.0, -1.0, 12.5), 55, (1600, 1100)),
    ('03_structure_closeup', (34.0, 30.0, 20.0), (4.0, 2.0, 14.0), 95, (1600, 1100)),
    ('04_south_elevation', (2.0, -168.0, 15.0), (2.0, 0.0, 15.0), 78, (1700, 950)),
    # From the south-west, where both faces are enclosed. Every other camera here
    # looks at the sectional cut, which is right for reading structure and wrong for
    # reading massing: a building sliced open on the two faces you can see reads as
    # a layer cake whatever its silhouette is. This one shows the volume.
    ('05_massing_south_west', (-86.0, -74.0, 40.0), (-2.0, -1.0, 13.0), 60,
     (1600, 1100)),
]

SEMANTIC_LAYER_VIEWS = [
    # Program evidence includes the separately-owned circulation layer because the
    # architectural question is whether rooms and movement coordinate. The manifest
    # records both layers, so the composite cannot be mistaken for program alone.
    ('01_program', ('program', 'circulation'),
     (70.0, 72.0, 46.0), (-2.0, -1.0, 12.0), 58, (1600, 1100)),
    ('02_facade', ('envelope',),
     (-86.0, -74.0, 40.0), (-2.0, -1.0, 13.0), 60, (1600, 1100)),
    ('03_structure', ('structure',),
     (70.0, 72.0, 44.0), (-2.0, -1.0, 12.5), 58, (1600, 1100)),
]


# ---------------------------------------------------------------------------
# Mesh builders, one per primitive
# ---------------------------------------------------------------------------

class MeshBucket:
    def __init__(self) -> None:
        self.verts: list[tuple[float, float, float]] = []
        self.faces: list[tuple[int, ...]] = []
        self.count = 0

    def push(self, verts, faces) -> None:
        base = len(self.verts)
        self.verts.extend(verts)
        self.faces.extend(tuple(base + i for i in face) for face in faces)
        self.count += 1


def _normalise(vector):
    length = math.sqrt(sum(component ** 2 for component in vector))
    return tuple(c / length for c in vector) if length > 1e-9 else (0.0, 0.0, 1.0)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def add_box(bucket: MeshBucket, geometry) -> None:
    bucket.push(*box_mesh(geometry))


def profile_outline(profile: dict) -> list[tuple[float, float]]:
    shape = profile['shape']
    d, b = profile['depth_m'], profile['width_m']
    if shape == 'i_section':
        tw, tf = profile['web_m'] / 2.0, profile['flange_m']
        hb, hd = b / 2.0, d / 2.0
        return [(-hb, -hd), (hb, -hd), (hb, -hd + tf), (tw, -hd + tf),
                (tw, hd - tf), (hb, hd - tf), (hb, hd), (-hb, hd),
                (-hb, hd - tf), (-tw, hd - tf), (-tw, -hd + tf), (-hb, -hd + tf)]
    if shape == 'chs':
        r, sides = d / 2.0, 10
        return [(math.cos(2 * math.pi * k / sides) * r,
                 math.sin(2 * math.pi * k / sides) * r) for k in range(sides)]
    hb, hd = b / 2.0, d / 2.0
    return [(-hb, -hd), (hb, -hd), (hb, hd), (-hb, hd)]


def add_member(bucket: MeshBucket, geometry, profiles: dict) -> None:
    bucket.push(*member_mesh(geometry, profiles))


def add_extrusion(bucket: MeshBucket, geometry) -> None:
    bucket.push(*extrusion_mesh(geometry))


def add_quad(bucket: MeshBucket, geometry) -> None:
    bucket.push([(c['x'], c['y'], c['z']) for c in geometry['corners']],
                [(0, 1, 2, 3)])


# ---------------------------------------------------------------------------
# Scene assembly
# ---------------------------------------------------------------------------

def clear_scene() -> None:
    for collection in (bpy.data.objects, bpy.data.meshes, bpy.data.materials,
                       bpy.data.cameras, bpy.data.lights, bpy.data.collections):
        for item in list(collection):
            try:
                collection.remove(item)
            except Exception:
                pass


def _from_model(model: dict) -> dict:
    """The model's own material table, as one dict per material.

    The palette below was the authority until the model started carrying one. Two
    renderers each holding their own table meant the same key could mean two different
    things, and neither was wrong about it -- there was nothing to be wrong against.
    Now the model says, and this reads.

    Every value the specification carries comes through, not only colour and roughness.
    `metallic`, `transmission` and `ior` were being dropped here, so steel rendered as a
    rough dielectric and glass as an alpha-blended sheet with no refraction -- the two
    cues that say which material was chosen, discarded at the last step before the
    picture.
    """
    table = {}
    for name, spec in (model.get('materials') or {}).items():
        value = spec['base_color'].lstrip('#')
        rgba = tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4)) + (1.0,)
        table[name] = {
            'rgba': rgba,
            'roughness': float(spec['roughness']),
            'metallic': float(spec.get('metallic', 0.0)),
            'transmission': float(spec.get('transmission', 0.0)),
            'ior': float(spec.get('ior', 1.5)),
        }
    return table


def _as_spec(entry) -> dict:
    """One shape for both tables. The fallback palette is (rgba, roughness, alpha)."""
    if isinstance(entry, dict):
        return entry
    rgba, roughness, alpha = entry
    return {'rgba': rgba, 'roughness': roughness, 'metallic': 0.0,
            'transmission': round(max(0.0, 1.0 - alpha) / 0.82, 4), 'ior': 1.5}


def _set(bsdf, names, value) -> bool:
    """Set the first input the running Blender actually has under these names.

    The Principled BSDF renamed its transmission socket between versions -- 3.x called
    it `Transmission`, 4.x and later `Transmission Weight` -- and a KeyError here would
    lose the whole material rather than one property of it.
    """
    for name in names:
        socket = bsdf.inputs.get(name)
        if socket is not None:
            socket.default_value = value
            return True
    return False


def make_materials(model: dict | None = None) -> dict:
    made = {}
    table = {name: _as_spec(entry) for name, entry in MATERIALS.items()}
    table.update(_from_model(model or {}))
    for name, spec in table.items():
        material = bpy.data.materials.new(name)
        material.use_nodes = True
        bsdf = material.node_tree.nodes['Principled BSDF']
        _set(bsdf, ('Base Color',), spec['rgba'])
        _set(bsdf, ('Roughness',), spec['roughness'])
        _set(bsdf, ('Metallic',), spec['metallic'])
        transmission = spec['transmission']
        if transmission > 0.0:
            # Real transmission where the build has it, with the index of refraction
            # the specification names.
            _set(bsdf, ('IOR', 'Index of Refraction'), spec['ior'])
            refracts = _set(bsdf, ('Transmission Weight', 'Transmission'), transmission)
            if refracts:
                # EEVEE renders refraction only for a material that asks for it, and
                # only outside the blended path -- forcing BLEND here would send the
                # surface down alpha compositing and quietly discard the transmission
                # just set. The two are alternatives, not a belt and braces.
                for attribute in ('use_raytrace_refraction', 'use_screen_refraction'):
                    try:
                        setattr(material, attribute, True)
                    except (AttributeError, TypeError):
                        pass
            else:
                # No transmission socket in this build: a translucent sheet is a poorer
                # glass than a refracting one and a better glass than an opaque panel.
                _set(bsdf, ('Alpha',), 1.0 - transmission * 0.82)
                for attribute, value in (('surface_render_method', 'BLENDED'),
                                         ('blend_method', 'BLEND')):
                    try:
                        setattr(material, attribute, value)
                    except (AttributeError, TypeError):
                        pass
        made[name] = material
    return made


def make_program_volume_materials() -> dict:
    """Transparent category colours for the common Program Volume protocol.

    They intentionally live outside the model material registry.  The full-height
    boxes are an inspectable projection of the contract, not another set of building
    elements, and therefore never enter the canonical GLB.
    """
    made = {}
    for category, rgba in PROGRAM_VOLUME_COLOURS.items():
        material = bpy.data.materials.new(f'PV_{category}')
        material.use_nodes = True
        bsdf = material.node_tree.nodes['Principled BSDF']
        _set(bsdf, ('Base Color',), rgba)
        _set(bsdf, ('Roughness',), 0.68)
        _set(bsdf, ('Alpha',), rgba[3])
        material.diffuse_color = rgba
        # Blender 4.2+ replaced blend_method with surface_render_method.  Supporting
        # both keeps the saved review scene readable in the project's Blender 5 build
        # and in older review installations.
        for attribute, value in (('surface_render_method', 'DITHERED'),
                                 ('blend_method', 'BLEND')):
            try:
                setattr(material, attribute, value)
            except (AttributeError, TypeError):
                pass
        made[category] = material
    return made


def build(model: dict, materials: dict) -> dict:
    profiles = model['profiles']
    buckets: dict[tuple[str, str, str, str], MeshBucket] = {}
    kinds: dict[tuple[str, str, str, str], set] = {}

    for group in model['element_groups']:
        key = (group['semantic_layer'], group['subsystem'],
               group['category'], group['material_profile'])
        bucket = buckets.setdefault(key, MeshBucket())
        kinds.setdefault(key, set()).add(group['kind'])
        for instance in group['instances']:
            geometry = instance['geometry']
            kind = geometry['type']
            if kind == 'box':
                add_box(bucket, geometry)
            elif kind == 'member':
                add_member(bucket, geometry, profiles)
            elif kind == 'extrusion':
                add_extrusion(bucket, geometry)
            elif kind == 'quad':
                add_quad(bucket, geometry)
            else:
                raise ValueError(f'unknown primitive: {kind}')

    root = bpy.data.collections.new('MTA_v3')
    bpy.context.scene.collection.children.link(root)
    layers: dict[str, object] = {}
    stats: dict[str, dict] = {}

    for (layer, subsystem, category, material), bucket in sorted(buckets.items()):
        if not bucket.verts:
            continue
        if layer not in layers:
            collection = bpy.data.collections.new(layer)
            root.children.link(collection)
            layers[layer] = collection
        name = f'{layer}__{subsystem}__{category}'
        mesh = bpy.data.meshes.new(f'{name}_mesh')
        mesh.from_pydata(bucket.verts, [], bucket.faces)
        mesh.validate(verbose=False)
        mesh.update(calc_edges=True)
        mesh.shade_flat()
        obj = bpy.data.objects.new(name, mesh)
        obj.data.materials.append(materials[material])
        obj['mta:model_id'] = model['model_id']
        obj['mta:score_id'] = model['score_id']
        obj['mta:layer'] = layer
        obj['mta:subsystem'] = subsystem
        obj['mta:category'] = category
        obj['mta:kinds'] = ','.join(sorted(kinds[(layer, subsystem, category, material)]))
        obj['mta:element_count'] = bucket.count
        obj['mta:authority'] = 'presentation_only'
        obj['mta:exportable'] = True
        layers[layer].objects.link(obj)
        stats[name] = {'elements': bucket.count, 'faces': len(bucket.faces),
                       'layer': layer, 'subsystem': subsystem, 'category': category}
    return stats


def build_program_volumes(model: dict) -> dict:
    """Build the authoritative volume contract, with legacy allocation as fallback.

    A Program Volume candidate carries ``program_volume_model`` and each review box
    is read exactly from its grid indices and explicit z interval. Older model files
    have no such contract, so their measured allocation is still projected as the
    legacy review view. Invalid authoritative references fail the export loudly.
    """
    contract = model.get('program_volume_model')
    records = []
    if contract:
        grid = contract['grid']
        levels = {level['id']: level for level in contract['levels']}
        for volume in contract['volumes']:
            if volume['level_id'] not in levels:
                raise ValueError(
                    f"Program Volume {volume['id']} names unknown {volume['level_id']}")
            level = levels[volume['level_id']]
            i0, j0, i1, j1 = volume['grid_rect']
            try:
                x0, x1 = grid['x_lines'][i0], grid['x_lines'][i1]
                y0, y1 = grid['y_lines'][j0], grid['y_lines'][j1]
            except IndexError as error:
                raise ValueError(
                    f"Program Volume {volume['id']} has a grid index outside the contract") \
                    from error
            records.append({
                'id': volume['id'], 'level_id': volume['level_id'],
                'category': volume['category'], 'role': volume['role'],
                'space_ids': list(volume.get('space_ids', [])),
                'label': volume['id'], 'space_type': volume['role'],
                'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1,
                'z0': level['z_base'], 'z1': level['z_top'],
                'area_required_m2': volume.get('target_area_m2', 0.0),
                'area_delivered_m2': volume.get('gross_area_m2', 0.0),
                'derived_from': f"program_volume_model.volumes[{volume['id']}]",
            })
        source = ['program_volume_model.volumes', 'program_volume_model.grid',
                  'program_volume_model.levels']
        protocol = contract.get('schema_version', 'mta.program_volumes/1.0')
    else:
        lattice_levels = model['lattice']['levels']
        by_id = {level['id']: (index, level)
                 for index, level in enumerate(lattice_levels)}
        for zone in model['program_allocation']['zones']:
            found = by_id.get(zone['level_id'])
            if found is None:
                continue
            position, level = found
            if position + 1 >= len(lattice_levels):
                continue
            upper = lattice_levels[position + 1]
            records.append({
                'id': zone['space_id'], 'level_id': level['id'],
                'category': zone['category'], 'role': 'program',
                'space_ids': [zone['space_id']], 'label': zone['label'],
                'space_type': zone['space_type'],
                'x0': zone['x0'], 'y0': zone['y0'],
                'x1': zone['x1'], 'y1': zone['y1'],
                'z0': level['z'], 'z1': upper['z'],
                'area_required_m2': zone['area_required_m2'],
                'area_delivered_m2': zone['area_delivered_m2'],
                'derived_from': f"program_allocation.zones[{zone['space_id']}]",
            })
        source = ['program_allocation.zones', 'lattice.levels']
        protocol = 'program_volume/legacy-allocation-projection'

    root = bpy.data.collections.new(PROGRAM_VOLUME_COLLECTION)
    bpy.context.scene.collection.children.link(root)
    root['mta:authority'] = 'presentation_only'
    root['mta:protocol'] = protocol
    root['mta:source_lattice_schema'] = model['lattice'].get('schema_version', '')
    root['mta:source_allocation_schema'] = model['program_allocation'].get(
        'schema_version', '')
    root.hide_render = True

    materials = make_program_volume_materials()
    floors = {}
    categories = {}
    stats = {'source': source, 'objects': 0, 'by_level': {}, 'by_category': {}}
    for record in records:
        width = float(record['x1']) - float(record['x0'])
        depth = float(record['y1']) - float(record['y0'])
        height = float(record['z1']) - float(record['z0'])
        if min(width, depth, height) <= 0.0:
            raise ValueError(f"Program Volume {record['id']} has a non-positive dimension")

        level_id = record['level_id']
        floor = floors.get(level_id)
        if floor is None:
            floor = bpy.data.collections.new(f'Floor_{level_id}')
            root.children.link(floor)
            floor['mta:level_id'] = level_id
            floor['mta:z_base'] = float(record['z0'])
            floor['mta:z_top'] = float(record['z1'])
            floors[level_id] = floor

        category = str(record['category'])
        category_key = (level_id, category)
        group = categories.get(category_key)
        if group is None:
            group = bpy.data.collections.new(f'{level_id}_{category}')
            floor.children.link(group)
            group['mta:level_id'] = level_id
            group['mta:category'] = category
            categories[category_key] = group

        geometry = {
            'type': 'box',
            'center': {
                'x': (float(record['x0']) + float(record['x1'])) / 2.0,
                'y': (float(record['y0']) + float(record['y1'])) / 2.0,
                'z': (float(record['z0']) + float(record['z1'])) / 2.0,
            },
            'size': {'x': width, 'y': depth, 'z': height},
            'rotation_z': 0.0,
        }
        verts, faces = box_mesh(geometry)
        safe_id = ''.join(ch if ch.isalnum() or ch in '-_' else '_'
                          for ch in record['id'])
        name = f'{level_id}_{category}_{safe_id}'
        mesh = bpy.data.meshes.new(f'{name}_mesh')
        mesh.from_pydata(verts, [], faces)
        mesh.validate(verbose=False)
        mesh.update(calc_edges=True)
        mesh.shade_flat()
        obj = bpy.data.objects.new(name, mesh)
        obj.data.materials.append(materials.get(category, materials['service']))
        obj['mta:model_id'] = model['model_id']
        obj['mta:score_id'] = model['score_id']
        obj['mta:authority'] = 'presentation_only'
        obj['mta:exportable'] = False
        obj['mta:review_stage'] = 'program_volume_massing'
        obj['mta:derived_from'] = record['derived_from']
        obj['mta:volume_id'] = record['id']
        obj['mta:space_ids'] = ','.join(record['space_ids'])
        obj['mta:space_type'] = record['space_type']
        obj['mta:role'] = record['role']
        obj['mta:label'] = record['label']
        obj['mta:level_id'] = level_id
        obj['mta:category'] = category
        obj['mta:area_required_m2'] = float(record['area_required_m2'])
        obj['mta:area_delivered_m2'] = float(record['area_delivered_m2'])
        group.objects.link(obj)
        stats['objects'] += 1
        stats['by_level'][level_id] = stats['by_level'].get(level_id, 0) + 1
        stats['by_category'][category] = stats['by_category'].get(category, 0) + 1
    return stats


def point_at(obj, target) -> None:
    from mathutils import Vector
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def setup_scene():
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False
    if scene.world is None:
        scene.world = bpy.data.worlds.new('World')
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes['Background']
    background.inputs[0].default_value = (0.455, 0.462, 0.480, 1.0)
    background.inputs[1].default_value = 1.0
    for attribute, value in (('use_raytracing', True), ('use_shadows', True),
                             ('taa_render_samples', 96)):
        try:
            setattr(scene.eevee, attribute, value)
        except (AttributeError, TypeError):
            pass
    try:
        scene.view_settings.look = 'AgX - Base Contrast'
    except TypeError:
        pass

    sun_data = bpy.data.lights.new('Sun', 'SUN')
    sun_data.energy = 4.6
    sun_data.angle = math.radians(1.4)
    sun = bpy.data.objects.new('Sun', sun_data)
    sun.rotation_euler = (math.radians(52), math.radians(4), math.radians(-38))
    scene.collection.objects.link(sun)

    fill_data = bpy.data.lights.new('Fill', 'AREA')
    fill_data.energy = 14000.0
    fill_data.shape = 'RECTANGLE'
    fill_data.size, fill_data.size_y = 70.0, 45.0
    fill = bpy.data.objects.new('Fill', fill_data)
    fill.location = (-55.0, -70.0, 48.0)
    scene.collection.objects.link(fill)
    point_at(fill, (0.0, 0.0, 14.0))

    camera_data = bpy.data.cameras.new('Camera')
    camera = bpy.data.objects.new('Camera', camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    return camera


def _review_clip_distances(depths) -> tuple[float, float]:
    """Keep all reviewed geometry with useful depth precision at building scale."""
    near, far = min(depths), max(depths)
    if not (math.isfinite(near) and math.isfinite(far) and near > 0):
        raise ValueError('Review geometry must lie in front of its camera')
    # A millimetre near plane wastes almost the entire perspective depth buffer
    # before a building hundreds of metres away. Thin roof layers then z-fight.
    return near * .25, far * 1.25


def _set_review_clipping(camera, corners) -> dict:
    bpy.context.view_layer.update()
    inverse = camera.matrix_world.inverted()
    depths = [-(inverse @ point).z for point in corners]
    camera.data.clip_start, camera.data.clip_end = _review_clip_distances(depths)
    return {'near_m': camera.data.clip_start, 'far_m': camera.data.clip_end,
            'nearest_geometry_m': min(depths), 'farthest_geometry_m': max(depths)}


def _fit_review_camera(camera, scene, layers, location, target, lens, resolution,
                       *, extra_objects=()) -> dict:
    """Fit the selected building layers with Blender's native camera solver."""
    from mathutils import Vector
    from bpy_extras.object_utils import world_to_camera_view

    root = bpy.data.collections['MTA_v3']
    objects = [obj for layer in root.children if layer.name in layers and layer.name != 'site'
               for obj in layer.all_objects if obj.type == 'MESH']
    objects.extend(obj for obj in extra_objects if obj.type == 'MESH')
    corners = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    if not corners:
        raise RuntimeError('No building geometry for the requested review view')
    lows = Vector(tuple(min(p[k] for p in corners) for k in range(3)))
    highs = Vector(tuple(max(p[k] for p in corners) for k in range(3)))
    centre = (lows+highs)/2
    direction = (Vector(location)-Vector(target)).normalized()
    span = (highs-lows).length
    scene.render.resolution_x, scene.render.resolution_y = resolution
    camera.data.type = 'PERSP'
    camera.data.lens = lens
    camera.location = centre+direction*span
    point_at(camera, centre)
    bpy.context.view_layer.update()
    fitted, _ = camera.camera_fit_coords(
        bpy.context.evaluated_depsgraph_get(), [value for p in corners for value in p])
    camera.location = fitted+direction*span*.12
    clipping = _set_review_clipping(camera, corners)
    bpy.context.view_layer.update()
    projected = [world_to_camera_view(scene,camera,p) for p in corners]
    if any(p.z <= 0 or not (0 <= p.x <= 1 and 0 <= p.y <= 1) for p in projected):
        raise RuntimeError('Native review framing leaves building geometry outside the image')
    return {'method':'native_camera_fit_coords', 'location':list(camera.location),
            'target':list(centre), 'lens':lens, 'resolution':list(resolution),
            'bounds':{'minimum':list(lows),'maximum':list(highs)},
            'all_bounds_in_frame':True, 'clipping':clipping}


def render_views(camera, out_dir: Path) -> tuple[list[str], dict, dict]:
    scene = bpy.context.scene
    written, visibility, cameras = [], {}, {}
    all_layers = [layer.name for layer in bpy.data.collections['MTA_v3'].children]
    for name, location, target, lens, (rx, ry) in VIEWS:
        # The legacy filename is retained; its structure-only scope is explicit
        # in the manifest. A complete facade must not hide the entire frame view.
        layers = ['structure'] if name == '03_structure_closeup' else all_layers
        _set_semantic_visibility(layers)
        filename = f'{name}.png'
        cameras[filename] = _fit_review_camera(
            camera, scene, layers, location, target, lens, (rx,ry))
        scene.render.filepath = str(out_dir / filename)
        bpy.ops.render.render(write_still=True)
        written.append(filename)
        visibility[filename] = sorted(layers)
    _set_semantic_visibility(all_layers)
    return written, visibility, cameras


def _set_semantic_visibility(visible_layers, *, program_volumes=False) -> None:
    root = bpy.data.collections.get('MTA_v3')
    if root is None:
        raise RuntimeError('MTA_v3 semantic collection is missing')
    visible = set(visible_layers)
    available = {collection.name for collection in root.children}
    missing = visible - available
    if missing:
        raise RuntimeError(f'missing semantic layers: {sorted(missing)}')
    for collection in root.children:
        collection.hide_render = program_volumes or collection.name not in visible
        for obj in collection.objects:
            obj.hide_render = False
    review = bpy.data.collections.get(PROGRAM_VOLUME_COLLECTION)
    if review is not None:
        review.hide_render = not program_volumes


def _set_program_review_visibility(visible_layers) -> None:
    """Show Program Volumes together with selected semantic layers.

    ``_set_semantic_visibility`` retains the existing standalone/semantic-layer
    behavior.  This small adapter composes the review collection back on top of a
    selected canonical layer, so the protocol overlays share exactly one camera
    and the canonical GLB export flags remain untouched.
    """
    _set_semantic_visibility(visible_layers, program_volumes=False)
    review = bpy.data.collections.get(PROGRAM_VOLUME_COLLECTION)
    if review is None:
        raise RuntimeError('Program Volume review collection is missing')
    review.hide_render = False


def _set_program_volume_review_camera(camera, scene) -> dict:
    """Frame the complete Program Volume stack and return its serialisable spec."""
    from mathutils import Vector

    review = bpy.data.collections.get(PROGRAM_VOLUME_COLLECTION)
    objects = [obj for obj in review.all_objects if obj.type == 'MESH'] if review else []
    corners = [obj.matrix_world @ Vector(corner)
               for obj in objects for corner in obj.bound_box]
    if not corners:
        raise RuntimeError('Program Volume review camera has no volume geometry to frame')
    lows = [min(point[axis] for point in corners) for axis in range(3)]
    highs = [max(point[axis] for point in corners) for axis in range(3)]
    target = tuple((lows[axis] + highs[axis]) / 2.0 for axis in range(3))
    spans = tuple(highs[axis] - lows[axis] for axis in range(3))
    # Use the same native fit and projected-bound verification as the whole-model
    # views. A fixed multiple of the largest span ignores lens and image aspect.
    # Frame every overlay once so the three protocol views retain one camera.
    building = bpy.data.collections['MTA_v3']
    spec = _fit_review_camera(
        camera, scene, [layer.name for layer in building.children if layer.name != 'site'],
        (1.,1.,.45), (0.,0.,0.), 58, (1600,1100), extra_objects=objects)
    return {
        **spec,
        'id': PROGRAM_VOLUME_REVIEW_CAMERA,
        'bounds': {'minimum': lows, 'maximum': highs, 'span': list(spans)},
        'framed_bounds': spec['bounds'],
        'distance': (camera.location-Vector(spec['target'])).length,
    }


def render_semantic_layers(camera, out_dir: Path) -> tuple[list[str], dict[str, list[str]]]:
    scene = bpy.context.scene
    written = []
    visibility = {}
    for name, layers, location, target, lens, (rx, ry) in SEMANTIC_LAYER_VIEWS:
        show_program_volumes = name == '01_program'
        _set_semantic_visibility(layers, program_volumes=show_program_volumes)
        camera.location = location
        camera.data.lens = lens
        point_at(camera, target)
        scene.render.resolution_x, scene.render.resolution_y = rx, ry
        scene.render.filepath = str(out_dir / f'{name}.png')
        bpy.ops.render.render(write_still=True)
        written.append(f'{name}.png')
        visibility[f'{name}.png'] = (
            ['program_volume_contract'] if show_program_volumes else list(layers))
    _set_semantic_visibility(
        collection.name for collection in bpy.data.collections['MTA_v3'].children)
    return written, visibility


def render_program_volumes(camera, out_dir: Path) -> str:
    """Render the mandatory pre-system Program Volume stage."""
    scene = bpy.context.scene
    _set_semantic_visibility((), program_volumes=True)
    _set_program_volume_review_camera(camera, scene)
    scene.render.filepath = str(out_dir / PROGRAM_VOLUME_RENDER)
    bpy.ops.render.render(write_still=True)
    _set_semantic_visibility(
        collection.name for collection in bpy.data.collections['MTA_v3'].children)
    return PROGRAM_VOLUME_RENDER


def render_program_volume_overlays(camera, out_dir: Path) -> tuple[list[str], dict[str, dict]]:
    """Render the two protocol overlays from the standalone Program Volume camera.

    These views are deliberately fixed to the same camera as
    ``06_program_volumes.png``.  The first isolates the structure relationship;
    the second isolates the outboard facade/envelope relationship.  Both retain
    the review boxes as a presentation-only collection and therefore cannot leak
    into the canonical GLB.
    """
    scene = bpy.context.scene
    views = (
        (PROGRAM_STRUCTURE_RENDER, ('structure',), 'structure'),
        (PROGRAM_FACADE_RENDER, ('envelope',), 'envelope'),
    )
    written = []
    metadata = {}
    for filename, layers, relationship in views:
        _set_program_review_visibility(layers)
        camera_spec = _set_program_volume_review_camera(camera, scene)
        scene.render.filepath = str(out_dir / filename)
        bpy.ops.render.render(write_still=True)
        written.append(filename)
        metadata[filename] = {
            'camera': camera_spec,
            'semantic_layers': list(layers),
            'program_volume_contract': PROGRAM_VOLUME_COLLECTION,
            'relationship': relationship,
        }
    _set_semantic_visibility(
        collection.name for collection in bpy.data.collections['MTA_v3'].children)
    return written, metadata


def export_glb(path: Path) -> None:
    for obj in bpy.data.objects:
        obj.select_set(obj.type == 'MESH' and obj.get('mta:exportable', False))
    bpy.ops.export_scene.gltf(
        filepath=str(path), export_format='GLB', use_selection=True,
        export_apply=True, export_extras=True, export_cameras=False,
        export_lights=False, export_yup=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    if len(argv) < 3:
        raise SystemExit(
            'MODEL_JSON OUT_BLEND OUT_RENDER_DIR [OUT_GLB] [OUT_MANIFEST] [RENDER_MODE]')
    model_path = Path(argv[0]).resolve()
    blend_path = Path(argv[1]).resolve()
    render_dir = Path(argv[2]).resolve()
    glb_path = Path(argv[3]).resolve() if len(argv) > 3 and argv[3] != '-' else None
    manifest_path = Path(argv[4]).resolve() if len(argv) > 4 and argv[4] != '-' else None
    render_mode = argv[5] if len(argv) > 5 else 'study'

    render_dir.mkdir(parents=True, exist_ok=True)
    blend_path.parent.mkdir(parents=True, exist_ok=True)
    model = json.loads(model_path.read_text(encoding='utf-8'))
    source_model_sha256 = hashlib.sha256(json.dumps(
        model, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
        allow_nan=False).encode('utf-8')).hexdigest()

    clear_scene()
    materials = make_materials(model)
    stats = build(model, materials)
    program_volume_stats = build_program_volumes(model)
    camera = setup_scene()
    bpy.context.scene['mta:model_id'] = model['model_id']
    bpy.context.scene['mta:source_model_sha256'] = source_model_sha256
    program_volume_review = {}
    review_cameras = {}
    if render_mode == 'study':
        renders, render_visibility, review_cameras = render_views(camera, render_dir)
        program_render = render_program_volumes(camera, render_dir)
        renders.append(program_render)
        render_visibility[program_render] = ['program_volume_contract']
        overlay_renders, program_volume_review = render_program_volume_overlays(
            camera, render_dir)
        renders.extend(overlay_renders)
        render_visibility.update({
            filename: ['program_volume_contract', *metadata['semantic_layers']]
            for filename, metadata in program_volume_review.items()
        })
    elif render_mode == 'semantic_layers':
        renders, render_visibility = render_semantic_layers(camera, render_dir)
    else:
        raise ValueError(f'unknown render mode: {render_mode}')

    if glb_path:
        glb_path.parent.mkdir(parents=True, exist_ok=True)
        export_glb(glb_path)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

    if manifest_path:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps({
            'producer': 'blender_headless_5_v3',
            'blender_version': bpy.app.version_string,
            'authority': 'presentation_only',
            'model_id': model['model_id'],
            'source_model_sha256': source_model_sha256,
            'source_hash_basis': 'canonical_json_sort_keys_utf8',
            'native_blend_path': str(blend_path),
            'native_blend_sha256': sha256(blend_path),
            'score_id': model['score_id'],
            'element_count': sum(len(g['instances']) for g in model['element_groups']),
            'element_groups': len(model['element_groups']),
            'merged_objects': len(stats),
            'total_faces': sum(s['faces'] for s in stats.values()),
            'objects': stats,
            'program_volume_contract': {
                'collection': PROGRAM_VOLUME_COLLECTION,
                'exportable': False,
                'review_camera': PROGRAM_VOLUME_REVIEW_CAMERA,
                'review_renders': program_volume_review,
                **program_volume_stats,
            },
            'renders': renders,
            'render_sha256': {name: sha256(render_dir / name) for name in renders},
            'render_mode': render_mode,
            'render_visibility': render_visibility,
            'review_cameras': review_cameras,
            'glb_sha256': sha256(glb_path) if glb_path else None,
        }, indent=2), encoding='utf-8')

    total = sum(len(g['instances']) for g in model['element_groups'])
    print(f'[v3] elements={total} groups={len(model["element_groups"])} '
          f'merged_objects={len(stats)} '
          f'faces={sum(s["faces"] for s in stats.values())}')


# Guarded so the geometry primitives above can be imported by another script.
# `draw_building.py` reuses `add_box`, `add_member`, `add_extrusion` and
# `add_quad` rather than growing a second copy of them; without the guard the
# import ran the whole exporter and parsed the wrong argv.
if __name__ == '__main__':
    main()
