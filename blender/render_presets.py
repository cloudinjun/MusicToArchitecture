"""Reusable five-style architectural rendering system for Blender 5.x.

The script treats every mesh already in the input .blend as accepted source geometry.
It only changes presentation state in memory, renders the requested views, and saves a
new render-ready copy.  The input .blend is never overwritten.

Run through ``python -m backend.scripts.render_archviz`` from the repository root.
All looks are built from Blender-native shader, world, light, Freestyle, and compositor
nodes; no external textures or generated assets are required.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector


SYSTEM_ID = "mta-render-presets-1.0"
SYSTEM_PREFIX = "MTA_RS__"
HELPER_COLLECTION = "MTA_RENDER_SYSTEM"

STYLE_ORDER = (
    "photoreal",
    "post_digital",
    "cinematic",
    "minimalist",
    "watercolor",
)

STYLE_LABELS = {
    "photoreal": "Photorealism",
    "post_digital": "Post-Digital Collage",
    "cinematic": "Cinematic / Atmospheric",
    "minimalist": "Conceptual / Minimalist",
    "watercolor": "Hand-drawn / Watercolor",
}

VIEW_SPECS = {
    "hero": {
        "label": "Hero three-quarter",
        "offset": (1.20, -1.62, 0.24),
        "target_z": 0.38,
        "lens": 36.0,
        "photoreal_scale": 0.80,
    },
    "reverse": {
        "label": "Opposite front three-quarter",
        "offset": (-1.34, -1.28, 0.27),
        "target_z": 0.39,
        "lens": 36.0,
        "photoreal_scale": 0.82,
    },
    "low": {
        "label": "Low architectural view",
        "offset": (0.72, -1.68, 0.10),
        "target_z": 0.38,
        "lens": 32.0,
        "photoreal_scale": 0.82,
    },
}

ROLE_TOKENS = {
    "glass": ("glass", "glaz", "window", "curtain"),
    "ground": ("ground", "site", "terrain", "paving", "landscape"),
    "timber": ("timber", "wood", "glulam", "clt", "furn", "desk", "seat", "shelv"),
    "metal": (
        "steel", "metal", "frame", "beam", "column", "structure", "truss",
        "brace", "mullion",
    ),
    "accent": ("accent", "red"),
    "vegetation": ("tree", "plant", "vegetation", "foliage"),
}


MATERIAL_SPECS = {
    "photoreal": {
        "concrete": dict(color=(0.46, 0.43, 0.38, 1), roughness=0.58,
                         noise=3.4, detail=5.0, bump=0.10, bevel=0.025),
        "metal": dict(color=(0.30, 0.36, 0.43, 1), roughness=0.24,
                      metallic=0.86, noise=24.0, detail=2.0, bump=0.018,
                      bevel=0.012),
        "glass": dict(color=(0.15, 0.42, 0.56, 1), roughness=0.075,
                      transmission=0.70, ior=1.45, alpha=1.0, coat=0.22,
                      transparent_mix=0.08, normal_noise=52.0, detail=2.0,
                      bump=0.012, bump_distance=0.012),
        "timber": dict(color=(0.38, 0.17, 0.055, 1), roughness=0.40,
                       noise=4.2, detail=4.0, bump=0.09, bevel=0.018),
        "ground": dict(color=(0.075, 0.10, 0.055, 1), roughness=0.86,
                       noise=7.0, detail=6.0, bump=0.24),
        "accent": dict(color=(0.22, 0.055, 0.025, 1), roughness=0.42,
                       coat=0.12, bevel=0.01),
        "vegetation": dict(color=(0.035, 0.18, 0.028, 1), roughness=0.68,
                           noise=2.8, detail=5.0, bump=0.15,
                           subsurface=0.06,
                           object_variation=((0.018, 0.075, 0.012, 1),
                                             (0.12, 0.34, 0.055, 1))),
    },
    "post_digital": {
        "concrete": dict(color=(0.86, 0.72, 0.58, 1), roughness=0.93,
                         noise=4.0, detail=2.0, bump=0.04),
        "metal": dict(color=(0.20, 0.30, 0.43, 1), roughness=0.88,
                      noise=7.0, detail=2.0, bump=0.03),
        "glass": dict(color=(0.56, 0.77, 0.79, 1), roughness=0.72,
                      alpha=0.78),
        "timber": dict(color=(0.78, 0.45, 0.24, 1), roughness=0.94,
                       noise=3.0, detail=2.0, bump=0.04),
        "ground": dict(color=(0.77, 0.74, 0.66, 1), roughness=0.98,
                       noise=3.4, detail=2.0, bump=0.05),
        "accent": dict(color=(0.83, 0.16, 0.13, 1), roughness=0.88),
        "vegetation": dict(color=(0.35, 0.51, 0.31, 1), roughness=0.96,
                           noise=2.0, detail=2.0, bump=0.05),
    },
    "cinematic": {
        "concrete": dict(color=(0.13, 0.16, 0.20, 1), roughness=0.52,
                         noise=2.0, detail=4.0, bump=0.14),
        "metal": dict(color=(0.075, 0.095, 0.13, 1), roughness=0.24,
                      metallic=0.82, noise=16.0, detail=2.0, bump=0.025),
        "glass": dict(color=(0.16, 0.24, 0.30, 1), roughness=0.12,
                      transmission=0.46, ior=1.45, alpha=0.68,
                      emission=(0.90, 0.27, 0.07, 1), emission_strength=0.22),
        "timber": dict(color=(0.31, 0.14, 0.06, 1), roughness=0.42,
                       noise=3.0, detail=3.0, bump=0.09),
        "ground": dict(color=(0.055, 0.070, 0.095, 1), roughness=0.62,
                       noise=5.0, detail=5.0, bump=0.17),
        "accent": dict(color=(0.52, 0.025, 0.012, 1), roughness=0.28,
                       emission=(1.0, 0.05, 0.01, 1), emission_strength=0.16),
        "vegetation": dict(color=(0.025, 0.075, 0.055, 1), roughness=0.74,
                           noise=2.0, detail=3.0, bump=0.12),
    },
    "minimalist": {
        "concrete": dict(color=(0.82, 0.81, 0.77, 1), roughness=0.82),
        "metal": dict(color=(0.16, 0.17, 0.18, 1), roughness=0.55),
        "glass": dict(color=(0.67, 0.72, 0.72, 1), roughness=0.36, alpha=0.72),
        "timber": dict(color=(0.67, 0.57, 0.43, 1), roughness=0.76),
        "ground": dict(color=(0.69, 0.68, 0.64, 1), roughness=0.94),
        "accent": dict(color=(0.64, 0.12, 0.09, 1), roughness=0.72),
        "vegetation": dict(color=(0.39, 0.46, 0.35, 1), roughness=0.90),
    },
    "watercolor": {
        "concrete": dict(color=(0.82, 0.77, 0.68, 1), roughness=0.98,
                         noise=1.3, detail=2.0, bump=0.035),
        "metal": dict(color=(0.25, 0.36, 0.45, 1), roughness=0.90,
                      noise=2.8, detail=2.0, bump=0.025),
        "glass": dict(color=(0.56, 0.73, 0.76, 1), roughness=0.82, alpha=0.72,
                      noise=1.8, detail=2.0),
        "timber": dict(color=(0.68, 0.46, 0.29, 1), roughness=0.96,
                       noise=1.4, detail=2.0, bump=0.03),
        "ground": dict(color=(0.75, 0.71, 0.62, 1), roughness=1.0,
                       noise=1.1, detail=2.0, bump=0.04),
        "accent": dict(color=(0.67, 0.18, 0.16, 1), roughness=0.92,
                       noise=1.6, detail=2.0),
        "vegetation": dict(color=(0.36, 0.50, 0.33, 1), roughness=0.98,
                           noise=1.2, detail=2.0, bump=0.03),
    },
}


WORLD_SPECS = {
    "photoreal": dict(color=(0.12, 0.20, 0.34, 1), strength=0.72,
                      gradient=True),
    "post_digital": dict(color=(0.93, 0.88, 0.78, 1), strength=0.78),
    "cinematic": dict(color=(0.018, 0.040, 0.085, 1), strength=0.28,
                      volume_density=0.00055),
    "minimalist": dict(color=(0.92, 0.91, 0.87, 1), strength=0.88),
    "watercolor": dict(color=(0.94, 0.91, 0.83, 1), strength=0.82),
}


LIGHT_SPECS = {
    "photoreal": (
        dict(kind="SUN", energy=1.70, color=(1.0, 0.88, 0.76), rotation=(52, 4, -42), angle=1.5),
        dict(kind="AREA", energy=2800, color=(0.68, 0.82, 1.0), offset=(-0.72, -0.82, 0.72), size=0.72),
        dict(kind="AREA", energy=1300, color=(1.0, 0.78, 0.58), offset=(0.86, 0.38, 0.38), size=0.42),
    ),
    "post_digital": (
        dict(kind="SUN", energy=2.4, color=(1.0, 0.86, 0.70), rotation=(48, 6, -42), angle=1.0),
        dict(kind="AREA", energy=11000, color=(0.72, 0.84, 1.0), offset=(-0.7, -0.8, 0.8), size=0.70),
    ),
    "cinematic": (
        dict(kind="SUN", energy=3.6, color=(1.0, 0.34, 0.13), rotation=(72, 4, -58), angle=3.0),
        dict(kind="AREA", energy=42000, color=(1.0, 0.24, 0.075), offset=(-0.8, -0.75, 0.32), size=0.42),
        dict(kind="AREA", energy=32000, color=(0.08, 0.46, 1.0), offset=(0.72, 0.48, 0.62), size=0.52),
    ),
    "minimalist": (
        dict(kind="SUN", energy=1.25, color=(1.0, 0.92, 0.78), rotation=(42, 0, -34), angle=5.0),
        dict(kind="AREA", energy=17000, color=(1.0, 0.96, 0.90), offset=(-0.65, -0.72, 0.88), size=0.92),
    ),
    "watercolor": (
        dict(kind="SUN", energy=1.6, color=(1.0, 0.83, 0.65), rotation=(50, 7, -38), angle=5.0),
        dict(kind="AREA", energy=13000, color=(0.70, 0.84, 1.0), offset=(-0.8, -0.72, 0.82), size=0.82),
    ),
}

STYLE_EXPOSURE = {
    "photoreal": 0.20,
    "post_digital": 0.15,
    "cinematic": 1.1,
    "minimalist": 0.25,
    "watercolor": 0.28,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def set_socket(node, names, value) -> bool:
    if isinstance(names, str):
        names = (names,)
    for name in names:
        socket = node.inputs.get(name)
        if socket is not None:
            try:
                socket.default_value = value
                return True
            except (AttributeError, TypeError, ValueError):
                continue
    return False


def toned(color, factor):
    return tuple(min(1.0, max(0.0, c * factor)) for c in color[:3]) + (color[3],)


def role_from_fields(fields):
    text = " ".join(str(field) for field in fields if field).lower()
    for role, tokens in ROLE_TOKENS.items():
        if any(token in text for token in tokens):
            return role
    return None


def material_uses_glass_shader(material) -> bool:
    """Recognize glazing even when an imported material has an opaque name."""
    if not material or not material.use_nodes or not material.node_tree:
        return False
    for node in material.node_tree.nodes:
        if node.bl_idname == "ShaderNodeBsdfGlass":
            return True
        if node.bl_idname != "ShaderNodeBsdfPrincipled":
            continue
        for socket_name in ("Transmission Weight", "Transmission"):
            socket = node.inputs.get(socket_name)
            if socket is not None and float(socket.default_value) >= 0.15:
                return True
    return False


def object_role(obj) -> str:
    fields = [obj.name]
    fields.extend(collection.name for collection in obj.users_collection)
    for key in ("mta:layer", "mta:subsystem", "mta:category", "mta:kinds", "mta:role"):
        value = obj.get(key)
        if value:
            fields.append(value)
    return role_from_fields(fields) or "concrete"


def role_for_material_slot(obj, material) -> str:
    """Classify one slot so mixed wall/window meshes retain face assignments."""
    if material:
        fields = [material.name]
        for key in ("mta:layer", "mta:category", "mta:role"):
            value = material.get(key)
            if value:
                fields.append(value)
        role = role_from_fields(fields)
        if role:
            return role
        if material_uses_glass_shader(material):
            return "glass"
    return object_role(obj)


def role_for(obj, original_materials) -> str:
    """Return a dominant role for callers that do not operate per material slot."""
    roles = [role_for_material_slot(obj, material) for material in original_materials]
    return roles[0] if roles and len(set(roles)) == 1 else object_role(obj)


def is_site_context(obj) -> bool:
    """Use ownership metadata for framing; a material name cannot demote a roof."""
    fields = [obj.name]
    fields.extend(collection.name for collection in obj.users_collection)
    fields.append(str(obj.get("mta:layer", "")))
    text = " ".join(fields).lower()
    return any(token in text for token in ("site", "ground", "terrain", "landscape"))


def target_meshes(scene):
    return [
        obj for obj in scene.objects
        if obj.type == "MESH" and not obj.hide_render
        and not obj.get("mta:render_system")
        and not obj.name.startswith(SYSTEM_PREFIX)
    ]


def world_bounds(objects):
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    if not points:
        raise RuntimeError("No visible mesh objects were found in the input scene")
    low = Vector(tuple(min(point[i] for point in points) for i in range(3)))
    high = Vector(tuple(max(point[i] for point in points) for i in range(3)))
    return low, high


def point_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def remove_datablock(collection, item):
    try:
        collection.remove(item, do_unlink=True)
    except TypeError:
        collection.remove(item)


def prepare_helper_collection(scene):
    previous = bpy.data.collections.get(HELPER_COLLECTION)
    if previous:
        for obj in list(previous.all_objects):
            if obj.get("mta:render_system"):
                remove_datablock(bpy.data.objects, obj)
        remove_datablock(bpy.data.collections, previous)
    helper = bpy.data.collections.new(HELPER_COLLECTION)
    helper["mta:render_system"] = SYSTEM_ID
    scene.collection.children.link(helper)
    return helper


def make_ground(helper, low, high):
    center = (low + high) * 0.5
    span = max(high.x - low.x, high.y - low.y, 10.0)
    z = low.z - max(0.04, span * 0.002)
    radius = span * 2.8
    mesh = bpy.data.meshes.new(f"{SYSTEM_PREFIX}GROUND_MESH")
    mesh.from_pydata(
        [
            (center.x - radius, center.y - radius, z),
            (center.x + radius, center.y - radius, z),
            (center.x + radius, center.y + radius, z),
            (center.x - radius, center.y + radius, z),
        ],
        [], [(0, 1, 2, 3)],
    )
    obj = bpy.data.objects.new(f"{SYSTEM_PREFIX}GROUND", mesh)
    obj["mta:render_system"] = SYSTEM_ID
    obj["mta:authority"] = "presentation_only"
    helper.objects.link(obj)
    return obj


def make_unit_mesh(name, build):
    previous = bpy.data.meshes.get(name)
    if previous and previous.users == 0:
        remove_datablock(bpy.data.meshes, previous)
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    build(bm)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return mesh


def make_landscape(helper, low, high):
    """Add deterministic presentation-only trees outside the building envelope."""
    center = (low + high) * 0.5
    span = max(high.x - low.x, high.y - low.y, 20.0)
    ground_z = low.z + span * 0.002

    def build_trunk(bm):
        bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False, segments=10,
            radius1=1.0, radius2=0.68, depth=1.0)

    def build_canopy(bm):
        blobs = (
            ((-0.62, 0.02, -0.12), (0.68, 0.62, 0.78)),
            ((0.58, 0.10, -0.08), (0.66, 0.58, 0.72)),
            ((0.02, -0.58, 0.00), (0.72, 0.62, 0.76)),
            ((0.02, 0.58, 0.04), (0.68, 0.64, 0.72)),
            ((-0.42, -0.38, 0.50), (0.64, 0.58, 0.72)),
            ((0.42, -0.32, 0.54), (0.62, 0.56, 0.70)),
            ((-0.32, 0.38, 0.62), (0.60, 0.54, 0.68)),
            ((0.34, 0.34, 0.68), (0.58, 0.52, 0.66)),
            ((0.00, 0.00, 1.08), (0.72, 0.66, 0.82)),
        )
        for location, scale in blobs:
            result = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
            transform = Matrix.Translation(Vector(location)) @ Matrix.Diagonal((*scale, 1.0))
            bmesh.ops.transform(bm, matrix=transform, verts=result["verts"])

    trunk_mesh = make_unit_mesh(f"{SYSTEM_PREFIX}TREE_TRUNK_MESH", build_trunk)
    canopy_mesh = make_unit_mesh(f"{SYSTEM_PREFIX}TREE_CANOPY_MESH", build_canopy)
    for polygon in trunk_mesh.polygons:
        polygon.use_smooth = True
    for polygon in canopy_mesh.polygons:
        polygon.use_smooth = True
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))
    for index in range(96):
        variation = 0.5 + 0.5 * math.sin(index * 12.9898 + 4.1414)
        angle = index * golden_angle
        radius = span * (1.46 + 0.50 * variation)
        height = span * (0.15 + 0.07 * (0.5 + 0.5 * math.sin(index * 3.71)))
        crown_scale = height * 0.22
        x = center.x + math.cos(angle) * radius
        y = center.y + math.sin(angle) * radius

        trunk = bpy.data.objects.new(f"{SYSTEM_PREFIX}TREE__{index:02d}__TRUNK", trunk_mesh)
        trunk.location = (x, y, ground_z + height * 0.36)
        trunk.scale = (height * 0.028, height * 0.028, height * 0.72)
        trunk.rotation_euler[2] = angle * 0.37
        trunk["mta:render_system"] = SYSTEM_ID
        trunk["mta:authority"] = "presentation_only"
        trunk["mta:role"] = "timber"
        helper.objects.link(trunk)

        canopy = bpy.data.objects.new(f"{SYSTEM_PREFIX}TREE__{index:02d}__CANOPY", canopy_mesh)
        canopy.location = (x, y, ground_z + height * 0.72)
        canopy.scale = (crown_scale, crown_scale, crown_scale * 1.10)
        canopy.rotation_euler[2] = angle * 0.61
        canopy["mta:render_system"] = SYSTEM_ID
        canopy["mta:authority"] = "presentation_only"
        canopy["mta:role"] = "vegetation"
        helper.objects.link(canopy)
    return {"timber": trunk_mesh, "vegetation": canopy_mesh}


def assign_landscape_materials(landscape_meshes, style_materials):
    for role, mesh in landscape_meshes.items():
        mesh.materials.clear()
        mesh.materials.append(style_materials[role])


def configure_landscape_visibility(helper, style_id):
    hidden = style_id == "minimalist"
    for obj in helper.objects:
        if obj.name.startswith(f"{SYSTEM_PREFIX}TREE__"):
            obj.hide_render = hidden


def make_cameras(helper):
    cameras = {}
    for view_id in VIEW_SPECS:
        data = bpy.data.cameras.new(f"{SYSTEM_PREFIX}CAM__{view_id}")
        data.sensor_width = 36.0
        data.clip_start = 0.05
        obj = bpy.data.objects.new(f"{SYSTEM_PREFIX}CAM__{view_id}", data)
        obj["mta:render_system"] = SYSTEM_ID
        obj["mta:view_id"] = view_id
        obj["mta:authority"] = "presentation_only"
        helper.objects.link(obj)
        cameras[view_id] = obj
    return cameras


def camera_basis(offset):
    from_target = Vector(offset).normalized()
    forward = -from_target
    world_up = Vector((0.0, 0.0, 1.0))
    right = forward.cross(world_up).normalized()
    up = right.cross(forward).normalized()
    return forward, right, up


def frame_camera(camera, view_spec, corners, low, high, aspect, orthographic=False,
                 framing_scale=1.0):
    size = high - low
    target = Vector(((low.x + high.x) * 0.5, (low.y + high.y) * 0.5,
                     low.z + size.z * view_spec["target_z"]))
    forward, right, up = camera_basis(view_spec["offset"])
    projected = []
    for point in corners:
        relative = point - target
        projected.append((relative.dot(right), relative.dot(up), relative.dot(forward)))

    margin = 1.30 if orthographic else 1.13
    camera.data.lens = view_spec["lens"]
    if orthographic:
        camera.data.type = "ORTHO"
        half_width = max(abs(value[0]) for value in projected)
        half_height = max(abs(value[1]) for value in projected)
        camera.data.ortho_scale = margin * max(2.0 * half_height, 2.0 * half_width / aspect)
        distance = max((high - low).length * 1.8, 20.0)
    else:
        camera.data.type = "PERSP"
        half_horizontal = math.atan(36.0 / (2.0 * camera.data.lens))
        tan_h = math.tan(half_horizontal)
        tan_v = tan_h / aspect
        distance = max(
            max(margin * abs(x) / tan_h - depth for x, _, depth in projected),
            max(margin * abs(y) / tan_v - depth for _, y, depth in projected),
            (high - low).length * 0.65,
        )
    distance *= framing_scale
    camera.location = target - forward * distance
    camera.data.clip_end = max(1000.0, distance + (high - low).length * 4.0)
    point_at(camera, target)
    return target, distance


def make_material(style_id, role, spec):
    name = f"{SYSTEM_PREFIX}MAT__{style_id}__{role}"
    previous = bpy.data.materials.get(name)
    if previous:
        remove_datablock(bpy.data.materials, previous)
    material = bpy.data.materials.new(name)
    material.use_fake_user = True
    material["mta:render_system"] = SYSTEM_ID
    material["mta:style"] = style_id
    material["mta:role"] = role
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (520, 0)
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.location = (180, 0)
    shader.label = f"{STYLE_LABELS[style_id]} / {role}"
    set_socket(shader, "Base Color", spec["color"])
    set_socket(shader, "Weight", 1.0)
    set_socket(shader, "Roughness", spec.get("roughness", 0.6))
    set_socket(shader, "Metallic", spec.get("metallic", 0.0))
    set_socket(shader, ("Transmission Weight", "Transmission"), spec.get("transmission", 0.0))
    set_socket(shader, "IOR", spec.get("ior", 1.45))
    set_socket(shader, "Alpha", spec.get("alpha", 1.0))
    set_socket(shader, ("Coat Weight", "Coat"), spec.get("coat", 0.0))
    set_socket(shader, ("Subsurface Weight", "Subsurface"), spec.get("subsurface", 0.0))
    if spec.get("emission"):
        set_socket(shader, ("Emission Color", "Emission"), spec["emission"])
        set_socket(shader, "Emission Strength", spec.get("emission_strength", 0.0))
    surface = shader.outputs["BSDF"]
    if spec.get("transparent_mix"):
        transparent = nodes.new("ShaderNodeBsdfTransparent")
        transparent.location = (160, -210)
        set_socket(transparent, "Weight", 1.0)
        mix = nodes.new("ShaderNodeMixShader")
        mix.location = (360, 0)
        set_socket(mix, "Fac", 1.0 - spec["transparent_mix"])
        links.new(transparent.outputs["BSDF"], mix.inputs[1])
        links.new(shader.outputs["BSDF"], mix.inputs[2])
        surface = mix.outputs["Shader"]
    links.new(surface, output.inputs["Surface"])

    bevel = None
    if spec.get("bevel"):
        bevel = nodes.new("ShaderNodeBevel")
        bevel.location = (-80, -300)
        set_socket(bevel, "Radius", spec["bevel"])
        set_socket(bevel, "Samples", 4)

    texture_scale = spec.get("noise") or spec.get("normal_noise")
    if texture_scale:
        texcoord = nodes.new("ShaderNodeTexCoord")
        texcoord.location = (-760, 0)
        noise = nodes.new("ShaderNodeTexNoise")
        noise.location = (-540, 0)
        noise.noise_dimensions = "3D"
        set_socket(noise, "Scale", texture_scale)
        set_socket(noise, "Detail", spec.get("detail", 3.0))
        set_socket(noise, "Roughness", 0.62)
        links.new(texcoord.outputs["Generated"], noise.inputs["Vector"])
        if spec.get("noise"):
            ramp = nodes.new("ShaderNodeValToRGB")
            ramp.location = (-250, 80)
            ramp.color_ramp.elements[0].position = 0.20
            ramp.color_ramp.elements[0].color = toned(spec["color"], 0.72)
            ramp.color_ramp.elements[1].position = 0.82
            ramp.color_ramp.elements[1].color = toned(spec["color"], 1.22)
            links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
            links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
        if spec.get("bump"):
            bump = nodes.new("ShaderNodeBump")
            bump.location = (-40, -150)
            set_socket(bump, "Strength", spec["bump"])
            set_socket(bump, "Distance", spec.get("bump_distance", 0.08))
            links.new(noise.outputs["Fac"], bump.inputs["Height"])
            if bevel:
                links.new(bevel.outputs["Normal"], bump.inputs["Normal"])
            links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    elif bevel:
        links.new(bevel.outputs["Normal"], shader.inputs["Normal"])

    if spec.get("object_variation"):
        object_info = nodes.new("ShaderNodeObjectInfo")
        object_info.location = (-500, 260)
        variation = nodes.new("ShaderNodeValToRGB")
        variation.location = (-250, 260)
        variation.color_ramp.elements[0].color = spec["object_variation"][0]
        variation.color_ramp.elements[1].color = spec["object_variation"][1]
        links.new(object_info.outputs["Random"], variation.inputs["Fac"])
        links.new(variation.outputs["Color"], shader.inputs["Base Color"])

    if spec.get("alpha", 1.0) < 1.0 or spec.get("transparent_mix"):
        for attribute, value in (("surface_render_method", "DITHERED"),
                                 ("blend_method", "BLEND")):
            try:
                setattr(material, attribute, value)
            except (AttributeError, TypeError, ValueError):
                pass
    return material


def make_material_library():
    return {
        style_id: {
            role: make_material(style_id, role, spec)
            for role, spec in roles.items()
        }
        for style_id, roles in MATERIAL_SPECS.items()
    }


def assign_style_materials(objects, originals, style_materials):
    assignments = {}
    assigned_meshes = {}
    for obj in objects:
        mesh = obj.data
        if mesh in assigned_meshes:
            assignments[obj.name] = list(assigned_meshes[mesh])
            continue
        source_slots = originals[mesh]
        roles = [role_for_material_slot(obj, material) for material in source_slots]
        if source_slots:
            # Replace slots in place. Polygon material_index values remain untouched,
            # so a mesh containing both wall and window faces stays mixed-material.
            for index, role in enumerate(roles):
                mesh.materials[index] = style_materials[role]
        else:
            roles = [object_role(obj)]
            mesh.materials.append(style_materials[roles[0]])
        assigned_meshes[mesh] = list(roles)
        assignments[obj.name] = list(roles)
    return assignments


def make_world(style_id, spec):
    name = f"{SYSTEM_PREFIX}WORLD__{style_id}"
    world = bpy.data.worlds.get(name) or bpy.data.worlds.new(name)
    world.use_fake_user = True
    world["mta:render_system"] = SYSTEM_ID
    world["mta:style"] = style_id
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputWorld")
    output.location = (420, 0)
    background = nodes.new("ShaderNodeBackground")
    background.location = (100, 80)
    set_socket(background, "Color", spec["color"])
    set_socket(background, "Strength", spec["strength"])
    set_socket(background, "Weight", 1.0)
    links.new(background.outputs["Background"], output.inputs["Surface"])
    if spec.get("gradient"):
        texcoord = nodes.new("ShaderNodeTexCoord")
        texcoord.location = (-620, 80)
        separate = nodes.new("ShaderNodeSeparateXYZ")
        separate.location = (-440, 80)
        mapping = nodes.new("ShaderNodeMapRange")
        mapping.location = (-260, 80)
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.location = (-60, 80)
        set_socket(mapping, "From Min", -1.0)
        set_socket(mapping, "From Max", 1.0)
        set_socket(mapping, "To Min", 0.0)
        set_socket(mapping, "To Max", 1.0)
        ramp.color_ramp.elements.remove(ramp.color_ramp.elements[1])
        low = ramp.color_ramp.elements[0]
        low.position = 0.0
        low.color = (0.08, 0.18, 0.34, 1)
        horizon = ramp.color_ramp.elements.new(0.47)
        horizon.color = (0.24, 0.50, 0.82, 1)
        zenith = ramp.color_ramp.elements.new(1.0)
        zenith.color = (0.025, 0.12, 0.42, 1)
        clouds = nodes.new("ShaderNodeTexNoise")
        clouds.location = (-440, -180)
        clouds.noise_dimensions = "3D"
        set_socket(clouds, "Scale", 1.8)
        set_socket(clouds, "Detail", 5.0)
        set_socket(clouds, "Roughness", 0.72)
        set_socket(clouds, "Distortion", 0.18)
        cloud_ramp = nodes.new("ShaderNodeValToRGB")
        cloud_ramp.location = (-230, -150)
        cloud_ramp.color_ramp.elements[0].position = 0.48
        cloud_ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1)
        cloud_ramp.color_ramp.elements[1].position = 0.66
        cloud_ramp.color_ramp.elements[1].color = (0.30, 0.30, 0.30, 1)
        cloud_mix = nodes.new("ShaderNodeMixRGB")
        cloud_mix.location = (-10, 20)
        cloud_mix.blend_type = "MIX"
        cloud_mix.inputs[2].default_value = (0.68, 0.72, 0.73, 1)
        links.new(texcoord.outputs["Normal"], separate.inputs["Vector"])
        links.new(texcoord.outputs["Normal"], clouds.inputs["Vector"])
        links.new(separate.outputs["Z"], mapping.inputs["Value"])
        links.new(mapping.outputs["Result"], ramp.inputs["Fac"])
        links.new(clouds.outputs["Fac"], cloud_ramp.inputs["Fac"])
        links.new(cloud_ramp.outputs["Color"], cloud_mix.inputs[0])
        links.new(ramp.outputs["Color"], cloud_mix.inputs[1])
        links.new(cloud_mix.outputs["Color"], background.inputs["Color"])
    elif spec.get("sky"):
        sky = nodes.new("ShaderNodeTexSky")
        sky.location = (-220, 80)
        # Blender 5 replaces the former Nishita enum with its explicit scattering mode.
        sky.sky_type = "MULTIPLE_SCATTERING"
        sky.sun_elevation = math.radians(24.0)
        sky.sun_rotation = math.radians(128.0)
        sky.altitude = 0.4
        sky.air_density = 1.15
        links.new(sky.outputs["Color"], background.inputs["Color"])
    if spec.get("volume_density"):
        volume = nodes.new("ShaderNodeVolumePrincipled")
        volume.location = (100, -150)
        set_socket(volume, "Color", (0.055, 0.12, 0.20, 1))
        set_socket(volume, "Density", spec["volume_density"])
        set_socket(volume, "Anisotropy", 0.18)
        set_socket(volume, "Weight", 1.0)
        links.new(volume.outputs["Volume"], output.inputs["Volume"])
    return world


def make_world_library():
    return {style_id: make_world(style_id, spec)
            for style_id, spec in WORLD_SPECS.items()}


def clear_style_lights(helper):
    for obj in list(helper.objects):
        if obj.type == "LIGHT":
            data = obj.data
            remove_datablock(bpy.data.objects, obj)
            if data.users == 0:
                remove_datablock(bpy.data.lights, data)


def make_lights(style_id, helper, low, high):
    clear_style_lights(helper)
    center = (low + high) * 0.5
    center.z = low.z + (high.z - low.z) * 0.45
    span = max(high.x - low.x, high.y - low.y, 20.0)
    names = []
    for index, spec in enumerate(LIGHT_SPECS[style_id], start=1):
        data = bpy.data.lights.new(f"{SYSTEM_PREFIX}LIGHT__{style_id}__{index:02d}", spec["kind"])
        data.energy = spec["energy"] * max(0.65, min(2.2, (span / 100.0) ** 1.1))
        data.color = spec["color"]
        obj = bpy.data.objects.new(data.name, data)
        obj["mta:render_system"] = SYSTEM_ID
        obj["mta:style"] = style_id
        obj["mta:authority"] = "presentation_only"
        helper.objects.link(obj)
        if spec["kind"] == "SUN":
            data.angle = math.radians(spec.get("angle", 2.0))
            obj.rotation_euler = tuple(math.radians(value) for value in spec["rotation"])
        else:
            data.shape = "DISK"
            data.size = span * spec.get("size", 0.5)
            obj.location = center + Vector(spec["offset"]) * span
            point_at(obj, center)
        names.append(obj.name)

    if style_id in {"photoreal", "cinematic"}:
        height = high.z - low.z
        levels = max(2, min(6, int(round(height / 4.2))))
        for level in range(levels):
            for side in (-1, 1):
                index = len(names) + 1
                data = bpy.data.lights.new(
                    f"{SYSTEM_PREFIX}LIGHT__{style_id}__interior__{index:02d}", "AREA")
                data.energy = 160.0 if style_id == "photoreal" else 900.0
                data.color = (1.0, 0.58, 0.32)
                data.shape = "RECTANGLE"
                data.size = span * 0.20
                data.size_y = span * 0.08
                obj = bpy.data.objects.new(data.name, data)
                obj.location = (
                    center.x + side * (high.x - low.x) * 0.18,
                    center.y,
                    low.z + height * ((level + 0.72) / levels),
                )
                point_at(obj, obj.location - Vector((0.0, 0.0, 1.0)))
                obj["mta:render_system"] = SYSTEM_ID
                obj["mta:style"] = style_id
                obj["mta:authority"] = "presentation_only"
                helper.objects.link(obj)
                names.append(obj.name)
    return names


def compositor_group(style_id):
    name = f"{SYSTEM_PREFIX}COMP__{style_id}"
    previous = bpy.data.node_groups.get(name)
    if previous:
        remove_datablock(bpy.data.node_groups, previous)
    group = bpy.data.node_groups.new(name, "CompositorNodeTree")
    group.use_fake_user = True
    group["mta:render_system"] = SYSTEM_ID
    group["mta:style"] = style_id
    group.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    nodes = group.nodes
    links = group.links
    render_layers = nodes.new("CompositorNodeRLayers")
    render_layers.location = (-520, 0)
    current = render_layers.outputs["Image"]

    if style_id == "photoreal":
        glare = nodes.new("CompositorNodeGlare")
        glare.location = (-340, 0)
        set_socket(glare, "Threshold", 1.05)
        set_socket(glare, "Strength", 0.08)
        set_socket(glare, "Saturation", 1.02)
        set_socket(glare, "Size", 0.45)
        hue = nodes.new("CompositorNodeHueSat")
        hue.location = (-80, 0)
        set_socket(hue, "Saturation", 1.04)
        set_socket(hue, "Value", 1.01)
        links.new(current, glare.inputs["Image"])
        links.new(glare.outputs["Image"], hue.inputs["Image"])
        current = hue.outputs["Image"]
    elif style_id == "post_digital":
        posterize = nodes.new("CompositorNodePosterize")
        posterize.location = (-240, 0)
        set_socket(posterize, "Steps", 7.0)
        links.new(current, posterize.inputs["Image"])
        current = posterize.outputs["Image"]
    elif style_id == "cinematic":
        glare = nodes.new("CompositorNodeGlare")
        glare.location = (-240, 0)
        set_socket(glare, "Threshold", 0.72)
        set_socket(glare, "Strength", 0.22)
        set_socket(glare, "Saturation", 0.88)
        set_socket(glare, "Size", 0.62)
        links.new(current, glare.inputs["Image"])
        current = glare.outputs["Image"]
    elif style_id == "minimalist":
        hue = nodes.new("CompositorNodeHueSat")
        hue.location = (-240, 0)
        set_socket(hue, "Saturation", 0.24)
        set_socket(hue, "Value", 1.03)
        set_socket(hue, "Factor", 1.0)
        links.new(current, hue.inputs["Image"])
        current = hue.outputs["Image"]
    elif style_id == "watercolor":
        kuwahara = nodes.new("CompositorNodeKuwahara")
        kuwahara.location = (-320, 0)
        set_socket(kuwahara, "Size", 1.8)
        set_socket(kuwahara, "Uniformity", 0.34)
        set_socket(kuwahara, "Sharpness", 0.46)
        set_socket(kuwahara, "High Precision", True)
        hue = nodes.new("CompositorNodeHueSat")
        hue.location = (-60, 0)
        set_socket(hue, "Saturation", 0.84)
        set_socket(hue, "Value", 1.06)
        set_socket(hue, "Factor", 1.0)
        links.new(current, kuwahara.inputs["Image"])
        links.new(kuwahara.outputs["Image"], hue.inputs["Image"])
        current = hue.outputs["Image"]

    output = nodes.new("NodeGroupOutput")
    output.location = (260, 0)
    links.new(current, output.inputs["Image"])
    return group


def make_compositor_library():
    return {style_id: compositor_group(style_id) for style_id in STYLE_ORDER}


def configure_freestyle(scene, style_id):
    enabled = style_id in {"post_digital", "watercolor"}
    scene.render.use_freestyle = enabled
    scene.render.line_thickness = 0.78 if style_id == "post_digital" else 0.98
    if not enabled:
        return
    try:
        settings = scene.view_layers[0].freestyle_settings
        lineset = settings.linesets[0]
        line = lineset.linestyle
        line.color = (0.055, 0.065, 0.075) if style_id == "post_digital" else (0.16, 0.13, 0.10)
        line.alpha = 0.72 if style_id == "post_digital" else 0.90
        line.thickness = 0.82 if style_id == "post_digital" else 1.02
    except (AttributeError, IndexError):
        pass


def configure_scene(scene, resolution, samples):
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.render.image_settings.color_management = "FOLLOW_SCENE"
    scene.use_nodes = True
    for attribute, value in (("taa_render_samples", samples), ("taa_samples", samples),
                             ("use_raytracing", True), ("use_shadows", True)):
        try:
            setattr(scene.eevee, attribute, value)
        except (AttributeError, TypeError):
            pass
    for look in ("AgX - Medium High Contrast", "AgX - Base Contrast", "None"):
        try:
            scene.view_settings.look = look
            break
        except TypeError:
            continue


def configure_style_engine(scene, style_id, samples):
    if style_id == "photoreal":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
        scene.cycles.use_preview_denoising = True
        scene.cycles.max_bounces = 8
        scene.cycles.transmission_bounces = 8
        scene.cycles.transparent_max_bounces = 8
    else:
        scene.render.engine = "BLENDER_EEVEE"


def configure_style_visibility(objects, original_visibility, style_id):
    hidden = []
    photo_cleanup = style_id in {"photoreal", "cinematic"}
    for obj in objects:
        subsystem = str(obj.get("mta:subsystem", "")).lower()
        should_hide = photo_cleanup and subsystem in {"scale_reference", "zones"}
        obj.hide_render = original_visibility[obj] or should_hide
        if should_hide and not original_visibility[obj]:
            hidden.append(obj.name)
    return hidden


def configure_camera_style(camera, style_id, distance):
    dof = camera.data.dof
    dof.use_dof = style_id == "cinematic"
    if dof.use_dof:
        dof.focus_distance = distance
        dof.aperture_fstop = 4.0
        dof.aperture_blades = 7


def parse_selection(value, valid, kind):
    if value == "all":
        return list(valid)
    selected = [item.strip() for item in value.split(",") if item.strip()]
    unknown = set(selected) - set(valid)
    if unknown:
        raise ValueError(f"Unknown {kind}: {sorted(unknown)}; choose from {list(valid)}")
    return selected


def render_all(args):
    scene = bpy.context.scene
    source_path = Path(bpy.data.filepath).resolve() if bpy.data.filepath else None
    if not source_path or not source_path.is_file():
        raise RuntimeError("Save the input .blend before running the render system")
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    template_path = Path(args.template).resolve() if args.template else output_dir / "MTA_Render_Ready.blend"
    manifest_path = Path(args.manifest).resolve() if args.manifest else output_dir / "render_manifest.json"

    styles = parse_selection(args.styles, STYLE_ORDER, "style")
    views = parse_selection(args.views, VIEW_SPECS, "view")
    resolution = tuple(int(value) for value in args.resolution.lower().split("x"))
    if len(resolution) != 2 or min(resolution) < 64:
        raise ValueError("--resolution must look like 1400x900")
    configure_scene(scene, resolution, args.samples)

    meshes = target_meshes(scene)
    originals = {obj.data: list(obj.data.materials) for obj in meshes}
    scene_low, scene_high = world_bounds(meshes)
    focus_meshes = [obj for obj in meshes if not is_site_context(obj)] or meshes
    low, high = world_bounds(focus_meshes)
    corners = [
        obj.matrix_world @ Vector(corner)
        for obj in focus_meshes for corner in obj.bound_box
    ]
    existing_lights = {obj: obj.hide_render for obj in scene.objects if obj.type == "LIGHT"}
    original_visibility = {obj: obj.hide_render for obj in meshes}
    for light in existing_lights:
        light.hide_render = True

    helper = prepare_helper_collection(scene)
    ground = make_ground(helper, low, high)
    landscape_meshes = make_landscape(helper, low, high)
    cameras = make_cameras(helper)
    materials = make_material_library()
    worlds = make_world_library()
    compositors = make_compositor_library()
    aspect = resolution[0] / resolution[1]

    manifest = {
        "schema_version": "mta.render-manifest/1.0",
        "system_id": SYSTEM_ID,
        "authority": "presentation_only",
        "source_blend": str(source_path),
        "source_sha256": sha256(source_path),
        "template_blend": str(template_path),
        "blender_version": bpy.app.version_string,
        "engine": scene.render.engine,
        "resolution": list(resolution),
        "samples": args.samples,
        "bounds": {
            "min": [round(value, 5) for value in low],
            "max": [round(value, 5) for value in high],
            "size": [round(value, 5) for value in high - low],
        },
        "scene_bounds": {
            "min": [round(value, 5) for value in scene_low],
            "max": [round(value, 5) for value in scene_high],
            "size": [round(value, 5) for value in scene_high - scene_low],
        },
        "mesh_object_count": len(meshes),
        "framing_object_count": len(focus_meshes),
        "styles": {},
        "views": {},
        "renders": [],
        "assumptions": [
            "Unknown materials default to warm concrete.",
            "Material roles are inferred per material slot from object, collection, metadata, material names, and transmissive shader nodes.",
            "Mixed-material meshes preserve polygon material indices when style materials are assigned.",
            "Presentation lights, ground, cameras, and materials do not alter source geometry.",
            "All textures and post-processing are procedural Blender-native nodes.",
        ],
    }

    for view_id in views:
        spec = VIEW_SPECS[view_id]
        manifest["views"][view_id] = {"label": spec["label"], "offset": list(spec["offset"])}

    assignment_summary = {}
    for style_id in styles:
        style_dir = output_dir / style_id
        style_dir.mkdir(parents=True, exist_ok=True)
        configure_style_engine(scene, style_id, args.samples)
        hidden_source_objects = configure_style_visibility(
            meshes, original_visibility, style_id)
        assignments = assign_style_materials(meshes, originals, materials[style_id])
        assignment_summary[style_id] = {
            role: sum(1 for values in assignments.values() for value in values if value == role)
            for role in MATERIAL_SPECS[style_id]
        }
        ground.data.materials.clear()
        ground.data.materials.append(materials[style_id]["ground"])
        assign_landscape_materials(landscape_meshes, materials[style_id])
        configure_landscape_visibility(helper, style_id)
        scene.world = worlds[style_id]
        scene.compositing_node_group = compositors[style_id]
        scene.view_settings.exposure = STYLE_EXPOSURE[style_id]
        light_names = make_lights(style_id, helper, low, high)
        configure_freestyle(scene, style_id)
        style_start = time.perf_counter()
        style_record = {
            "label": STYLE_LABELS[style_id],
            "engine": scene.render.engine,
            "world": worlds[style_id].name,
            "materials": [material.name for material in materials[style_id].values()],
            "material_role_counts": assignment_summary[style_id],
            "lights": light_names,
            "compositor": compositors[style_id].name,
            "hidden_source_objects": hidden_source_objects,
            "shader_node_types": sorted({
                node.bl_idname
                for material in materials[style_id].values()
                for node in material.node_tree.nodes
            }),
            "compositor_node_types": sorted(node.bl_idname for node in compositors[style_id].nodes),
            "render_seconds": 0.0,
        }
        manifest["styles"][style_id] = style_record

        if not args.no_render:
            for view_id in views:
                camera = cameras[view_id]
                _, distance = frame_camera(
                    camera, VIEW_SPECS[view_id], corners, low, high, aspect,
                    orthographic=style_id == "minimalist",
                    framing_scale=(VIEW_SPECS[view_id].get("photoreal_scale", 1.0)
                                   if style_id == "photoreal" else 1.0),
                )
                configure_camera_style(camera, style_id, distance)
                scene.camera = camera
                destination = style_dir / f"{view_id}.png"
                scene.render.filepath = str(destination)
                started = time.perf_counter()
                bpy.ops.render.render(write_still=True)
                elapsed = time.perf_counter() - started
                manifest["renders"].append({
                    "style": style_id,
                    "view": view_id,
                    "path": str(destination.relative_to(output_dir)).replace("\\", "/"),
                    "sha256": sha256(destination),
                    "seconds": round(elapsed, 3),
                    "camera_type": camera.data.type,
                    "camera_location": [round(value, 4) for value in camera.location],
                    "lens_mm": round(camera.data.lens, 3),
                    "ortho_scale": round(camera.data.ortho_scale, 3) if camera.data.type == "ORTHO" else None,
                })
        style_record["render_seconds"] = round(time.perf_counter() - style_start, 3)

    # Save a presentation-only copy ready to render in the most generally useful look.
    ready_style = styles[0] if "photoreal" not in styles else "photoreal"
    configure_style_engine(scene, ready_style, args.samples)
    configure_style_visibility(meshes, original_visibility, ready_style)
    assign_style_materials(meshes, originals, materials[ready_style])
    ground.data.materials.clear()
    ground.data.materials.append(materials[ready_style]["ground"])
    assign_landscape_materials(landscape_meshes, materials[ready_style])
    configure_landscape_visibility(helper, ready_style)
    scene.world = worlds[ready_style]
    scene.compositing_node_group = compositors[ready_style]
    scene.view_settings.exposure = STYLE_EXPOSURE[ready_style]
    make_lights(ready_style, helper, low, high)
    configure_freestyle(scene, ready_style)
    ready_view = views[0]
    _, distance = frame_camera(
        cameras[ready_view], VIEW_SPECS[ready_view], corners, low, high, aspect,
        orthographic=ready_style == "minimalist",
        framing_scale=(VIEW_SPECS[ready_view].get("photoreal_scale", 1.0)
                       if ready_style == "photoreal" else 1.0),
    )
    configure_camera_style(cameras[ready_view], ready_style, distance)
    scene.camera = cameras[ready_view]
    scene["mta:render_system"] = SYSTEM_ID
    scene["mta:render_styles"] = ",".join(STYLE_ORDER)
    scene["mta:render_views"] = ",".join(VIEW_SPECS)
    scene["mta:source_blend"] = str(source_path)
    scene["mta:authority"] = "presentation_only"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(template_path))

    manifest["template_sha256"] = sha256(template_path)
    manifest["render_count"] = len(manifest["renders"])
    manifest["expected_render_count"] = 0 if args.no_render else len(styles) * len(views)
    manifest["complete"] = manifest["render_count"] == manifest["expected_render_count"]
    manifest["input_overwritten"] = source_path == template_path
    manifest["geometry_mutated"] = False
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "template": str(template_path),
        "manifest": str(manifest_path),
        "renders": manifest["render_count"],
        "complete": manifest["complete"],
    }))


def main():
    argv = __import__("sys").argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--template")
    parser.add_argument("--manifest")
    parser.add_argument("--styles", default="all")
    parser.add_argument("--views", default="all")
    parser.add_argument("--resolution", default="1400x900")
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--no-render", action="store_true")
    render_all(parser.parse_args(argv))


if __name__ == "__main__":
    main()
