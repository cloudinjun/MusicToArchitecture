"""Render one saved v3 building with cameras that actually frame it.

The generation pipeline writes its review views from fixed camera literals, which is
right for comparing two runs of the same building and wrong for a portfolio: a plate
that grows past 90 m walks straight out of the frame. This script reads the .blend the
pipeline already saved, measures the building's own bounds -- envelope, structure,
program and circulation, never the site plane or its context masses -- and solves for
the distance at which every corner lands inside the frame. Same direction, same lens,
same light for every recording, so a contact sheet of twenty compares buildings rather
than camera luck.

Run (Blender 4.x/5.x, background):

    blender --background model.blend --python tools/portfolio/render_portfolio_views.py \
        -- --out artifacts/portfolio_plates/<id> --label "Track name"
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

# The building, not the ground it stands on. `site` carries a 150 x 130 m plane and the
# context masses; including it would frame the neighbourhood and shrink the subject.
BUILDING_LAYERS = ('envelope', 'structure', 'program', 'circulation')
SENSOR_MM = 36.0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--label', default='')
    parser.add_argument('--views', default='hero,aerial,elevation,plan')
    parser.add_argument('--width', type=int, default=1800)
    parser.add_argument('--height', type=int, default=1200)
    parser.add_argument('--samples', type=int, default=96)
    parser.add_argument('--margin', type=float, default=1.06)
    parser.add_argument('--hide-site', action='store_true')
    parser.add_argument('--layer-views', default='',
                        help='Comma-separated semantic layers to isolate from the hero '
                             'camera, e.g. site,structure,envelope,program,circulation')
    parser.add_argument('--layer-camera', default='hero',
                        help='Which view specification the layer isolations reuse')
    return parser.parse_args(argv)


def gather(collection) -> list:
    """Every mesh under a collection.

    ``Collection.all_objects`` yields a stray ``None`` on some builds when the tree is
    nested several levels deep, which is exactly the shape ``Program_Volumes`` has.
    Walking ``objects`` and ``children`` gives the same set without that hazard.
    """
    found = [obj for obj in collection.objects if obj is not None]
    for child in collection.children:
        found.extend(gather(child))
    return found


def building_corners() -> list[Vector]:
    root = bpy.data.collections.get('MTA_v3')
    if root is None:
        raise SystemExit('MTA_v3 collection is missing; this is not a v3 model file')
    corners: list[Vector] = []
    for name in BUILDING_LAYERS:
        layer = bpy.data.collections.get(name)
        if layer is None:
            continue
        for obj in gather(layer):
            if obj.type != 'MESH':
                continue
            corners.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    if not corners:
        raise SystemExit('No building geometry found in the semantic layers')
    return corners


def bounds(corners: list[Vector]) -> tuple[Vector, Vector]:
    low = Vector((min(p[i] for p in corners) for i in range(3)))
    high = Vector((max(p[i] for p in corners) for i in range(3)))
    return low, high


def camera_basis(direction: Vector) -> tuple[Vector, Vector, Vector]:
    """Right/up/forward for a camera looking back down `direction` at the target."""
    forward = -direction.normalized()
    world_up = Vector((0.0, 0.0, 1.0))
    if abs(forward.dot(world_up)) > 0.999:
        world_up = Vector((0.0, 1.0, 0.0))
    right = forward.cross(world_up).normalized()
    up = right.cross(forward).normalized()
    return right, up, forward


def fits(distance: float, corners, target, direction, lens, aspect, margin) -> bool:
    right, up, forward = camera_basis(direction)
    location = target + direction.normalized() * distance
    half_h = math.atan((SENSOR_MM / 2.0) / lens)
    half_v = math.atan((SENSOR_MM / (2.0 * aspect)) / lens) if aspect >= 1.0 else half_h
    if aspect < 1.0:                                    # portrait: sensor fits height
        half_h = math.atan((SENSOR_MM * aspect / 2.0) / lens)
        half_v = math.atan((SENSOR_MM / 2.0) / lens)
    tan_h, tan_v = math.tan(half_h) / margin, math.tan(half_v) / margin
    for corner in corners:
        offset = corner - location
        depth = offset.dot(forward)
        if depth <= 0.1:
            return False
        if abs(offset.dot(right)) > depth * tan_h:
            return False
        if abs(offset.dot(up)) > depth * tan_v:
            return False
    return True


def solve_distance(corners, target, direction, lens, aspect, margin) -> float:
    """Smallest distance along `direction` that keeps every corner inside the frame."""
    span = max((max(p[i] for p in corners) - min(p[i] for p in corners)) for i in range(3))
    low, high = span * 0.2, span * 40.0
    if not fits(high, corners, target, direction, lens, aspect, margin):
        return high
    for _ in range(60):
        middle = (low + high) / 2.0
        if fits(middle, corners, target, direction, lens, aspect, margin):
            high = middle
        else:
            low = middle
    return high


def ortho_scale(corners, target, direction, aspect, margin) -> float:
    right, up, _ = camera_basis(direction)
    width = max(abs((corner - target).dot(right)) for corner in corners) * 2.0
    height = max(abs((corner - target).dot(up)) for corner in corners) * 2.0
    # Blender's ortho_scale is the extent along the sensor's longer axis.
    return max(width, height * aspect if aspect >= 1.0 else height) * margin


def point_at(obj, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat('-Z', 'Y').to_euler()


def prepare_scene(args) -> None:
    scene = bpy.context.scene
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False
    for attribute, value in (('taa_render_samples', args.samples),
                             ('use_raytracing', True), ('use_shadows', True)):
        try:
            setattr(scene.eevee, attribute, value)
        except (AttributeError, TypeError):
            pass
    if args.hide_site:
        site = bpy.data.collections.get('site')
        if site is not None:
            for obj in gather(site):
                obj.hide_render = True
    volumes = bpy.data.collections.get('Program_Volumes')
    if volumes is not None:                 # diagram overlay, never in a portfolio view
        for obj in gather(volumes):
            obj.hide_render = True


def set_layer_visibility(visible: set[str], keep_site: bool) -> None:
    """Show only the named semantic layers; the site plane is a separate decision.

    Every isolation reuses one camera, so a layer cannot be made to look better by
    being photographed from somewhere kinder than the layer beside it.
    """
    root = bpy.data.collections.get('MTA_v3')
    if root is None:
        raise SystemExit('MTA_v3 collection is missing')
    for layer in root.children:
        shown = layer.name in visible or (layer.name == 'site' and keep_site)
        for obj in gather(layer):
            obj.hide_render = not shown


def camera_object():
    camera = bpy.context.scene.camera
    if camera is None:
        data = bpy.data.cameras.new('PortfolioCamera')
        camera = bpy.data.objects.new('PortfolioCamera', data)
        bpy.context.scene.collection.objects.link(camera)
        bpy.context.scene.camera = camera
    return camera


def render(camera, name: str, out: Path) -> str:
    bpy.context.scene.render.filepath = str(out / f'{name}.png')
    bpy.ops.render.render(write_still=True)
    return f'{name}.png'


def main() -> None:
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    args = parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    prepare_scene(args)

    corners = building_corners()
    low, high = bounds(corners)
    target = (low + high) / 2.0
    aspect = args.width / args.height
    camera = camera_object()

    # One direction set for every recording. The hero looks from the south-west so the
    # entrance face and the long face are both foreshortened rather than flat-on.
    view_specs = {
        'hero':      dict(direction=Vector((-0.92, -1.0, 0.40)), lens=50.0, kind='PERSP'),
        'aerial':    dict(direction=Vector((0.80, -0.86, 0.95)), lens=45.0, kind='PERSP'),
        'elevation': dict(direction=Vector((0.0, -1.0, 0.0)),    lens=0.0,  kind='ORTHO'),
        'plan':      dict(direction=Vector((0.0, 0.0, 1.0)),     lens=0.0,  kind='ORTHO'),
    }
    written, records = [], {}
    for name in [v.strip() for v in args.views.split(',') if v.strip()]:
        spec = view_specs[name]
        direction = spec['direction'].normalized()
        if spec['kind'] == 'ORTHO':
            camera.data.type = 'ORTHO'
            # An elevation of a long low building letterboxes badly inside a fixed
            # 3:2 frame, so the orthographic frame takes the subject's own proportion
            # (clamped, so a tower does not become a ribbon).
            right, up, _ = camera_basis(direction)
            extent_x = max(abs((c - target).dot(right)) for c in corners) * 2.0
            extent_y = max(abs((c - target).dot(up)) for c in corners) * 2.0
            view_aspect = min(3.2, max(0.62, extent_x / max(extent_y, 1e-6)))
            height_px = int(round(args.width / view_aspect))
            bpy.context.scene.render.resolution_x = args.width
            bpy.context.scene.render.resolution_y = height_px
            scale = ortho_scale(corners, target, direction, view_aspect, args.margin)
            camera.data.ortho_scale = scale
            distance = max(high - low) * 4.0 + scale
            camera.data.clip_end = max(camera.data.clip_end, distance * 3.0)
            camera.location = target + direction * distance
            records[name] = {'type': 'ORTHO', 'ortho_scale': round(scale, 3),
                             'resolution': [args.width, height_px]}
        else:
            bpy.context.scene.render.resolution_x = args.width
            bpy.context.scene.render.resolution_y = args.height
            camera.data.type = 'PERSP'
            camera.data.lens = spec['lens']
            camera.data.sensor_width = SENSOR_MM
            distance = solve_distance(corners, target, direction, spec['lens'],
                                      aspect, args.margin)
            camera.data.clip_end = max(camera.data.clip_end, distance * 3.0)
            camera.location = target + direction * distance
            records[name] = {'type': 'PERSP', 'lens': spec['lens'],
                             'distance': round(distance, 3)}
        point_at(camera, target)
        records[name].update(location=[round(v, 3) for v in camera.location],
                             target=[round(v, 3) for v in target])
        written.append(render(camera, name, args.out))

    layers = [name.strip() for name in args.layer_views.split(',') if name.strip()]
    if layers:
        spec = view_specs[args.layer_camera]
        direction = spec['direction'].normalized()
        bpy.context.scene.render.resolution_x = args.width
        bpy.context.scene.render.resolution_y = args.height
        camera.data.type = 'PERSP'
        camera.data.lens = spec['lens']
        camera.data.sensor_width = SENSOR_MM
        distance = solve_distance(corners, target, direction, spec['lens'],
                                  aspect, args.margin)
        camera.data.clip_end = max(camera.data.clip_end, distance * 3.0)
        camera.location = target + direction * distance
        point_at(camera, target)
        isolated = {}
        for name in layers:
            keep_site = name == 'site'
            set_layer_visibility({name}, keep_site)
            written.append(render(camera, f'layer_{name}', args.out))
            isolated[name] = {'render': f'layer_{name}.png', 'site_shown': keep_site}
        root = bpy.data.collections.get('MTA_v3')
        set_layer_visibility({layer.name for layer in root.children}, True)
        manifest_layers = {'camera': args.layer_camera, 'isolated': isolated}
    else:
        manifest_layers = None

    manifest = {
        'label': args.label,
        'blend': bpy.data.filepath,
        'resolution': [args.width, args.height],
        'margin': args.margin,
        'building_bounds': {'min': [round(v, 3) for v in low],
                            'max': [round(v, 3) for v in high],
                            'span': [round(high[i] - low[i], 3) for i in range(3)]},
        'views': records,
        'layer_views': manifest_layers,
        'renders': written,
    }
    (args.out / 'views_manifest.json').write_text(
        json.dumps(manifest, indent=1), encoding='utf-8')
    print('PORTFOLIO_VIEWS_OK ' + json.dumps({'out': str(args.out), 'renders': written}))


main()
