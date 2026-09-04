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
    cx, cy, cz = (geometry['center'][k] for k in 'xyz')
    sx, sy, sz = (geometry['size'][k] for k in 'xyz')
    hx, hy, hz = sx / 2.0, sy / 2.0, sz / 2.0
    angle = geometry.get('rotation_z', 0.0)
    c, s = math.cos(angle), math.sin(angle)
    local = [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
             (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]
    bucket.push(
        [(cx + x * c - y * s, cy + x * s + y * c, cz + z) for x, y, z in local],
        [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])


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
    path = [(p['x'], p['y'], p['z']) for p in geometry['path']]
    outline = profile_outline(profiles[geometry['profile']])
    roll = geometry.get('roll') or {'x': 0.0, 'y': 0.0, 'z': 1.0}
    up = (roll['x'], roll['y'], roll['z'])
    n = len(outline)

    rings: list[list[tuple[float, float, float]]] = []
    for index, point in enumerate(path):
        nxt = path[min(index + 1, len(path) - 1)]
        prev = path[max(index - 1, 0)]
        axis = _normalise((nxt[0] - prev[0], nxt[1] - prev[1], nxt[2] - prev[2]))
        dot = sum(axis[i] * up[i] for i in range(3))
        v = (up[0] - axis[0] * dot, up[1] - axis[1] * dot, up[2] - axis[2] * dot)
        if abs(v[0]) + abs(v[1]) + abs(v[2]) < 1e-6:
            v = (1.0, 0.0, 0.0)
        v = _normalise(v)
        u = _normalise(_cross(v, axis))
        rings.append([(point[0] + u[0] * pu + v[0] * pv,
                       point[1] + u[1] * pu + v[1] * pv,
                       point[2] + u[2] * pu + v[2] * pv) for pu, pv in outline])

    verts = [vertex for ring in rings for vertex in ring]
    faces = [tuple(range(n - 1, -1, -1)),
             tuple(range((len(rings) - 1) * n, len(rings) * n))]
    for segment in range(len(rings) - 1):
        base_a, base_b = segment * n, (segment + 1) * n
        for k in range(n):
            m = (k + 1) % n
            faces.append((base_a + k, base_a + m, base_b + m, base_b + k))
    bucket.push(verts, faces)


def _keyhole(boundary, holes):
    polygon = [(p['x'], p['y']) for p in boundary]
    for hole in holes:
        reversed_hole = [(p['x'], p['y']) for p in reversed(hole)]
        best = None
        for i, outer in enumerate(polygon):
            for j, inner in enumerate(reversed_hole):
                distance = (outer[0] - inner[0]) ** 2 + (outer[1] - inner[1]) ** 2
                if best is None or distance < best[0]:
                    best = (distance, i, j)
        _, i, j = best
        polygon = (polygon[:i + 1] + reversed_hole[j:] + reversed_hole[:j + 1]
                   + polygon[i:])
    return polygon


def add_extrusion(bucket: MeshBucket, geometry) -> None:
    polygon = _keyhole(geometry['boundary'], geometry.get('holes') or [])
    z0, z1 = geometry['z_base'], geometry['z_top']
    n = len(polygon)
    verts = [(x, y, z0) for x, y in polygon] + [(x, y, z1) for x, y in polygon]
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    for k in range(n):
        m = (k + 1) % n
        faces.append((k, m, n + m, n + k))
    bucket.push(verts, faces)


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
        layers[layer].objects.link(obj)
        stats[name] = {'elements': bucket.count, 'faces': len(bucket.faces),
                       'layer': layer, 'subsystem': subsystem, 'category': category}
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


def render_views(camera, out_dir: Path) -> list[str]:
    scene = bpy.context.scene
    written = []
    for name, location, target, lens, (rx, ry) in VIEWS:
        camera.location = location
        camera.data.lens = lens
        point_at(camera, target)
        scene.render.resolution_x, scene.render.resolution_y = rx, ry
        scene.render.filepath = str(out_dir / f'{name}.png')
        bpy.ops.render.render(write_still=True)
        written.append(f'{name}.png')
    return written


def _set_semantic_visibility(visible_layers, *, program_zones_only=False) -> None:
    root = bpy.data.collections.get('MTA_v3')
    if root is None:
        raise RuntimeError('MTA_v3 semantic collection is missing')
    visible = set(visible_layers)
    available = {collection.name for collection in root.children}
    missing = visible - available
    if missing:
        raise RuntimeError(f'missing semantic layers: {sorted(missing)}')
    for collection in root.children:
        collection.hide_render = collection.name not in visible
        for obj in collection.objects:
            obj.hide_render = False
    if program_zones_only:
        program = bpy.data.collections.get('program')
        if program is None:
            raise RuntimeError('program semantic collection is missing')
        for obj in program.objects:
            obj.hide_render = obj.get('mta:subsystem') != 'zones'


def render_semantic_layers(camera, out_dir: Path) -> tuple[list[str], dict[str, list[str]]]:
    scene = bpy.context.scene
    written = []
    visibility = {}
    for name, layers, location, target, lens, (rx, ry) in SEMANTIC_LAYER_VIEWS:
        _set_semantic_visibility(layers, program_zones_only=name == '01_program')
        camera.location = location
        camera.data.lens = lens
        point_at(camera, target)
        scene.render.resolution_x, scene.render.resolution_y = rx, ry
        scene.render.filepath = str(out_dir / f'{name}.png')
        bpy.ops.render.render(write_still=True)
        written.append(f'{name}.png')
        visibility[f'{name}.png'] = list(layers)
    _set_semantic_visibility(
        collection.name for collection in bpy.data.collections['MTA_v3'].children)
    return written, visibility


def export_glb(path: Path) -> None:
    for obj in bpy.data.objects:
        obj.select_set(obj.type == 'MESH')
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

    clear_scene()
    materials = make_materials(model)
    stats = build(model, materials)
    camera = setup_scene()
    if render_mode == 'study':
        renders = render_views(camera, render_dir)
        render_visibility = {
            render: sorted({group['semantic_layer'] for group in model['element_groups']})
            for render in renders
        }
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
            'authority': 'presentation_only',
            'model_id': model['model_id'],
            'score_id': model['score_id'],
            'element_count': sum(len(g['instances']) for g in model['element_groups']),
            'element_groups': len(model['element_groups']),
            'merged_objects': len(stats),
            'total_faces': sum(s['faces'] for s in stats.values()),
            'objects': stats,
            'renders': renders,
            'render_mode': render_mode,
            'render_visibility': render_visibility,
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
