"""Plans and sections drawn by Blender, not by arithmetic written here.

The first version of this pipeline cut the model with a plane in Python: it solidified
members from their profiles, sliced convex hulls, ordered crossings by angle, hulled the
silhouettes and sorted back-to-front for a painter's occlusion. All of that works, and
all of it is a reimplementation of machinery Blender already ships and does better --
Solidify, Boolean, and Line Art, the last of which resolves silhouette, crease,
intersection and occlusion as separate edge types rather than as one flat outline.

So the division here is: the model states dimensions, Blender makes geometry from them.

* a quad panel carries `thickness_m`; **Solidify** gives it a body
* a section is a half-space; **Boolean** removes what is in front of the plane, and the
  cut faces it leaves are real geometry, not an inferred polygon
* the linework comes from **Line Art**, which knows the difference between a silhouette
  and a crease -- a distinction the hand-rolled slicer had no way to make
* **Grease Pencil SVG export** gets vectors off the end, so the sheet stays a drawing

`drawing_standard.py` still governs. It writes a profile of weights, greys and dash
patterns, and this script applies it; nothing about the drawing's appearance is decided
here. That keeps one template behind both paths rather than two that drift.

Run:
  blender -b --python blender/draw_building.py -- \
      --model building_model_v3.json --out artifacts/drawings/native \
      --view plan --z 6.709
  blender -b --python blender/draw_building.py -- ... --view section --bearing 37
"""

import argparse
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from import_building_model_v3 import (  # noqa: E402
    MeshBucket, add_box, add_extrusion, add_member, add_quad, clear_scene,
)


# How far the cutting solid reaches past the model. Any number larger than the building
# does, but it is named so the half-space reads as deliberate rather than as a magic box.
CUT_REACH_M = 400.0

# A plan is cut here above the floor: above a sill, below a door head.
PLAN_CUT_HEIGHT_M = 1.2


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--profile', default='')
    parser.add_argument('--out', required=True)
    parser.add_argument('--view', choices=('plan', 'section'), required=True)
    parser.add_argument('--z', type=float, default=0.0)
    parser.add_argument('--bearing', type=float, default=90.0)
    parser.add_argument('--offset', type=float, default=0.0)
    parser.add_argument('--name', default='DWG')
    parser.add_argument('--scale', type=int, default=100)
    parser.add_argument('--dpi', type=float, default=300.0)
    return parser.parse_args(argv)


# --- geometry ---------------------------------------------------------------------

def build_by_role(model: dict, roles: dict) -> dict:
    """One mesh object per drawing role, so Line Art can weight them apart.

    The GLB exporter buckets by material because that is what a viewport needs. A
    drawing needs the opposite grouping: a steel column and a steel handrail share a
    material and must not share a line weight.
    """
    profiles = model['profiles']
    buckets: dict[str, MeshBucket] = {}
    sheets: dict[str, list] = {}

    for group in model['element_groups']:
        role = roles.get(group['kind'], 'furniture')
        thickness = group.get('thickness_m')
        for instance in group['instances']:
            geometry = instance['geometry']
            primitive = geometry['type']
            if primitive == 'quad' and thickness:
                # Held back and solidified as its own object: Solidify works on a whole
                # mesh, so panels of different depths cannot share one.
                sheets.setdefault((role, round(thickness, 4)), MeshBucket())
                add_quad(sheets[(role, round(thickness, 4))], geometry)
                continue
            bucket = buckets.setdefault(role, MeshBucket())
            if primitive == 'box':
                add_box(bucket, geometry)
            elif primitive == 'member':
                add_member(bucket, geometry, profiles)
            elif primitive == 'extrusion':
                add_extrusion(bucket, geometry)
            elif primitive == 'quad':
                add_quad(bucket, geometry)

    root = bpy.data.collections.new('MTA_DRAW')
    bpy.context.scene.collection.children.link(root)
    collections: dict[str, object] = {}

    def collection_for(role: str):
        if role not in collections:
            collection = bpy.data.collections.new(role)
            root.children.link(collection)
            collections[role] = collection
        return collections[role]

    made = []
    for role, bucket in sorted(buckets.items()):
        if not bucket.verts:
            continue
        made.append(_object_from(f'{role}__solid', bucket, collection_for(role)))
    for (role, thickness), bucket in sorted(sheets.items()):
        if not bucket.verts:
            continue
        obj = _object_from(f'{role}__sheet_{thickness * 1000:.0f}', bucket,
                           collection_for(role))
        # The panel's declared construction depth, given a body by Blender rather than
        # by extrusion arithmetic written here.
        modifier = obj.modifiers.new('assembly_depth', 'SOLIDIFY')
        modifier.thickness = thickness
        modifier.offset = 0.0
        modifier.use_even_offset = True
        made.append(obj)
    return {'objects': made, 'collections': collections}


def _object_from(name: str, bucket: MeshBucket, collection):
    mesh = bpy.data.meshes.new(f'{name}_mesh')
    mesh.from_pydata(bucket.verts, [], bucket.faces)
    mesh.validate(verbose=False)
    # Outward, consistently. `from_pydata` takes the winding it is given, and the
    # emitters were never asked to agree on one -- which does not matter for a shaded
    # render and matters completely here, because the poche is the back face. With
    # normals as they came, half the slabs faced down, and looking at a plan from above
    # filled the floor solid black.
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update(calc_edges=True)
    mesh.shade_flat()
    obj = bpy.data.objects.new(name, mesh)
    obj['mta:elements'] = bucket.count
    collection.objects.link(obj)
    return obj


# --- the cut ----------------------------------------------------------------------

def _paper_material():
    """White, unlit, and single-sided.

    Poche was tried two ways here and both failed for the same underlying reason. A
    Boolean left its cut faces exactly on the camera's near plane, which then clipped
    them away. Shading back-faces instead depends on every normal pointing outward,
    and they do not: each role is one merged mesh of interpenetrating columns, beams
    and slabs, so "outward" is not defined for it and `recalc_face_normals` cannot
    recover it -- half the slabs faced down and filled the plan solid black.

    So the base drawing does not fill the cut. Backface culling makes a clipped-open
    solid simply transparent rather than black, which leaves clean white masses,
    correct occlusion, and the linework on top -- which is what a base drawing is for.
    The poche belongs with the annotation that goes on afterwards, and putting it there
    is honest about which of the two this pipeline actually produces.
    """
    material = bpy.data.materials.new('paper_face')
    material.use_nodes = True
    material.use_backface_culling = True
    tree = material.node_tree
    tree.nodes.clear()
    emission = tree.nodes.new('ShaderNodeEmission')
    emission.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
    output = tree.nodes.new('ShaderNodeOutputMaterial')
    tree.links.new(emission.outputs['Emission'], output.inputs['Surface'])
    return material


def prepare_faces(objects, poche: dict) -> None:
    """Give every object a flat paper face and a poche slot.

    There was a Boolean here, subtracting the half-space in front of the plane. It had
    to go: the camera's near clip is that same plane, so the faces the Boolean left on
    it were immediately clipped away, and every slab the section passed through
    vanished -- the floors came back as a single line with figures standing on nothing.
    Two mechanisms cutting at one plane cancel.

    The camera does the cutting now. What is left here is the tone: flat, unlit, and
    exactly the value the standard asked for, because a diffuse surface would be shaded
    by the world and come back a different grey on every face.
    """
    paper = _paper_material()
    for obj in objects:
        obj.data.materials.append(paper)


# --- the view ---------------------------------------------------------------------

def frame_camera(view: str, z: float, bearing_deg: float, offset_m: float,
                 bounds: tuple, centre: tuple[float, float]):
    """An orthographic camera on the plane's normal. Nothing is foreshortened, so a
    dimension can be taken off the drawing."""
    (min_x, min_y, min_z), (max_x, max_y, max_z) = bounds
    camera_data = bpy.data.cameras.new('drawing_camera')
    camera_data.type = 'ORTHO'
    camera = bpy.data.objects.new('drawing_camera', camera_data)
    bpy.context.scene.collection.objects.link(camera)

    if view == 'plan':
        span = max(max_x - min_x, max_y - min_y)
        camera.location = ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0,
                           z + CUT_REACH_M / 4.0)
        camera.rotation_euler = (0.0, 0.0, 0.0)   # looking down -Z
    else:
        angle = math.radians(bearing_deg)
        view_dir = (math.sin(angle), math.cos(angle))
        origin = (centre[0] - view_dir[0] * offset_m,
                  centre[1] - view_dir[1] * offset_m)
        span = max(max_x - min_x, max_y - min_y, max_z - min_z)
        back = CUT_REACH_M / 4.0
        camera.location = (origin[0] - view_dir[0] * back,
                           origin[1] - view_dir[1] * back,
                           (min_z + max_z) / 2.0)
        camera.rotation_euler = (math.pi / 2.0, 0.0, -angle)
    camera_data.ortho_scale = span * 1.12
    # The near plane *is* the section. Everything in front of it is not drawn, which
    # is what a section means, and Line Art marks the boundary where solids meet it.
    camera_data.clip_start = CUT_REACH_M / 4.0
    camera_data.clip_end = CUT_REACH_M * 2.0
    bpy.context.scene.camera = camera
    return camera, span * 1.12


def add_line_art(collections: dict, strokes: dict, scale_denominator: int,
                 drawn_roles: set):
    """One Grease Pencil per role, each reading only its own collection.

    Line Art separates silhouette, crease, contour and intersection, and resolves
    occlusion itself. That is the part worth having: a hand-rolled slicer can produce
    an outline, but it cannot tell a fold in a surface from the edge of one, and
    without that difference a section reads as a flat cartoon.
    """
    made = []
    for role, collection in sorted(collections.items()):
        stroke = strokes.get(role)
        # The standard decides what a scale carries. At 1:100 furniture is dropped --
        # a plan at that scale showing every desk is a grey field, not a more
        # informative drawing -- and honouring `drawn_roles` here is what makes that
        # decision apply to both renderers instead of only to the Python one.
        if stroke is None or role not in drawn_roles:
            continue
        bpy.ops.object.grease_pencil_add(type='LINEART_COLLECTION')
        gp = bpy.context.active_object
        gp.name = f'lineart__{role}'
        modifier = next((m for m in gp.modifiers if m.type == 'LINEART'), None)
        if modifier is None:
            continue
        modifier.source_type = 'COLLECTION'
        modifier.source_collection = collection
        # Grease Pencil states stroke width as a radius in *world* units, and the
        # standard states weights in millimetres of paper. One millimetre of paper is
        # `scale_denominator` millimetres of building, so the conversion runs through
        # the scale -- and then halves, because it is a radius. Handing the paper
        # figure over directly, as the first version did, is out by the scale: every
        # line on the sheet came back the same weight, because they had all collapsed
        # below the renderer's minimum and were being drawn at it.
        modifier.radius = (stroke['weight_mm'] * scale_denominator) / 1000.0 / 2.0
        modifier.use_contour = True
        modifier.use_crease = True
        modifier.use_intersection = True
        modifier.use_material = False
        modifier.use_edge_mark = False
        # The cut itself. Line Art draws a boundary wherever geometry meets the
        # camera's near plane, so putting that plane where the section is gives the
        # cut line from the renderer rather than from a Boolean. The Boolean stays for
        # the poche fill, but the *lines* no longer depend on it -- and they were the
        # part it was least reliable at, because every column, beam and slab in a role
        # is one merged mesh and they interpenetrate, which is exactly the input an
        # exact solver is entitled to refuse.
        modifier.use_clip_plane_boundaries = True
        material = bpy.data.materials.new(f'ink__{role}')
        bpy.data.materials.create_gpencil_data(material)
        grey = stroke['grey']
        material.grease_pencil.color = (grey, grey, grey, 1.0)
        material.grease_pencil.show_stroke = True
        material.grease_pencil.show_fill = False
        gp.data.materials.append(material)
        modifier.target_material = material
        made.append(gp)
    return made


def main() -> None:
    args = parse_args()
    model = json.loads(Path(args.model).read_text(encoding='utf-8'))
    profile = (json.loads(Path(args.profile).read_text(encoding='utf-8'))
               if args.profile else {'roles': {}, 'strokes': {}})

    clear_scene()
    built = build_by_role(model, profile.get('roles', {}))

    # The sheet is sized on the building, not on the site. A hundred-and-fifty metre
    # ground slab sets the orthographic span to 168 m if it is included, which at 1:100
    # is a metre and a half of paper with a building somewhere along it.
    xs, ys, zs = [], [], []
    for group in model['element_groups']:
        if group['semantic_layer'] == 'site' or group['kind'].startswith('site_'):
            continue
        for instance in group['instances']:
            position, size = instance['position'], instance['dimensions']
            xs += [position['x'] - size['x'] / 2, position['x'] + size['x'] / 2]
            ys += [position['y'] - size['y'] / 2, position['y'] + size['y'] / 2]
            zs += [position['z'] - size['z'] / 2, position['z'] + size['z'] / 2]
    bounds = ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))
    centre = ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)

    poche = {role: stroke.get('poche_grey')
             for role, stroke in profile.get('strokes', {}).items()}
    prepare_faces(built['objects'], poche)
    camera, ortho_span = frame_camera(args.view, args.z, args.bearing, args.offset,
                                      bounds, centre)

    # Resolution follows the sheet: the drawing is `ortho_span` metres wide, which is
    # `ortho_span * 1000 / scale` millimetres on paper. Fixing the pixel count from
    # that is what lets a line weight be specified in millimetres and stay true.
    sheet_mm = ortho_span * 1000.0 / args.scale
    px_per_mm = args.dpi / 25.4
    scene = bpy.context.scene
    scene.render.resolution_x = max(64, int(sheet_mm * px_per_mm))
    scene.render.resolution_y = max(64, int(sheet_mm * px_per_mm))
    # Paper, not alpha. A transparent sheet renders dark-on-nothing and has to be
    # composited before anyone can look at it.
    scene.render.film_transparent = False
    # Standard, not AgX: a drawing is not a photograph, and a view transform that
    # rolls off the highlights turns white paper into light grey and every tone in
    # the standard into a different one than was specified.
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'
    world = bpy.data.worlds.new('paper')
    world.use_nodes = True
    background = world.node_tree.nodes.get('Background')
    if background is not None:
        background.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
        background.inputs['Strength'].default_value = 1.0
    scene.world = world

    drawn = set(profile.get('drawn_roles', profile.get('strokes', {}).keys()))
    if args.view == 'plan' and args.z > 2.0:
        # A floor plan three storeys up is not a site plan. Left in, the ground
        # slab is clipped by the camera frustum and lands on the sheet as a
        # skewed quadrilateral lying across the building.
        drawn.discard('site')
    add_line_art(built['collections'], profile.get('strokes', {}), args.scale,
                 drawn)

    # Resolved: Blender writes a relative render path against its own notion of the
    # working directory, which on Windows dropped the drive and quietly saved the
    # sheet to C:\artifacts while reporting success.
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    # A raster of the same sheet, capped so it stays openable. The vector export is the
    # deliverable; this is how the drawing gets looked at, and it is a usable base to
    # annotate over on its own.
    preview_px = min(scene.render.resolution_x, 2400)
    aspect = 1.0
    scene.render.resolution_x = preview_px
    scene.render.resolution_y = int(preview_px * aspect)
    scene.render.filepath = str((out / f'{args.name}.png').resolve())
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    bpy.ops.object.select_all(action='DESELECT')
    gp_objects = [obj for obj in bpy.data.objects if obj.type == 'GREASEPENCIL']
    for obj in gp_objects:
        obj.select_set(True)
    if gp_objects:
        bpy.context.view_layer.objects.active = gp_objects[0]
        svg = out / f'{args.name}.svg'
        bpy.ops.wm.grease_pencil_export_svg(
            filepath=str(svg), selected_object_type='SELECTED',
            use_fill=False, use_clip_camera=True)
        # What the camera framed, so the sheet can be restated in millimetres at the
        # intended scale afterwards. The exporter writes scene units and cannot know
        # the drawing is meant for A1 at 1:100; this is the one number that recovers it.
        (out / f'{args.name}.json').write_text(json.dumps({
            'name': args.name, 'view': args.view, 'bearing': args.bearing,
            'offset_m': args.offset, 'z': args.z,
            'metres_across': ortho_span, 'scale_denominator': args.scale,
            'objects': len(built['objects']), 'grease_pencil': len(gp_objects),
        }, indent=2), encoding='utf-8')
        print(f'[draw] wrote {svg}')
    bpy.ops.render.render(write_still=True)
    print(f'[draw] rendered {out / (args.name + ".png")}')
    print(f'[draw] view={args.view} objects={len(built["objects"])} '
          f'gp={len(gp_objects)} sheet={sheet_mm:.0f}mm '
          f'res={scene.render.resolution_x}px')


if __name__ == '__main__':
    main()
