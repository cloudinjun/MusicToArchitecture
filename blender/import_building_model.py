"""Author a semantic Blender building scene from ``building_model_v2.json``.

Run with Blender in background mode. Arguments after ``--`` are:

SOURCE_JSON OUTPUT_BLEND OUTPUT_RENDER OUTPUT_SCENE_STATE [OUTPUT_GLB OUTPUT_MANIFEST]

Use ``-`` for an optional output that should be skipped. The shared JSON remains the
authority. Blender materializes its explicit semantic elements without inventing a
second facade or structural system.
"""

from __future__ import annotations

import json
import math
import sys
import traceback
from collections import Counter
from pathlib import Path

import bpy
from mathutils import Vector


MAX_SOURCE_OBJECTS = 500
FACADE_THICKNESS = 0.18
ROOF_THICKNESS = 0.22
SLAB_THICKNESS = 0.22
BEAM_WIDTH = 0.24
BEAM_DEPTH = 0.36
FOUNDATION_SIZE = 0.9
FOUNDATION_DEPTH = 0.35
TREE_SPECS = (
    ("tree-01", (-16.0, -5.0), 5.8),
    ("tree-02", (-16.0, 6.5), 6.6),
    ("tree-03", (-8.0, 9.5), 5.4),
    ("tree-04", (0.5, 9.7), 6.2),
    ("tree-05", (14.8, 7.0), 7.0),
    ("tree-06", (15.5, -4.8), 5.7),
)
VEHICLE_SPECS = (
    ("vehicle-01", (-5.0, -9.7), (0.12, 0.28, 0.44, 1.0)),
    ("vehicle-02", (7.0, -9.7), (0.76, 0.79, 0.78, 1.0)),
)
PERSON_SPECS = (
    ("person-01", (-11.4, -3.5)),
    ("person-02", (-10.1, -4.3)),
    ("person-03", (-0.8, -5.8)),
    ("person-04", (7.8, -5.9)),
)


def output_path(value: str) -> Path | None:
    return None if value == "-" else Path(value).resolve()


def script_arguments():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) not in (4, 6):
        raise ValueError(
            "Expected SOURCE_JSON OUTPUT_BLEND OUTPUT_RENDER OUTPUT_SCENE_STATE "
            "[OUTPUT_GLB OUTPUT_MANIFEST] after --"
        )
    if len(args) == 4:
        args.extend(["-", "-"])
    source = Path(args[0]).resolve()
    return source, *(output_path(value) for value in args[1:])


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for value in list(bpy.data.collections):
        bpy.data.collections.remove(value)
    for value in list(bpy.data.meshes):
        if value.users == 0:
            bpy.data.meshes.remove(value)
    for value in list(bpy.data.materials):
        if value.users == 0:
            bpy.data.materials.remove(value)


def make_collection(name: str, *, hidden: bool = False):
    value = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(value)
    value.hide_render = hidden
    value.hide_viewport = hidden
    return value


def make_material(name: str, rgba: tuple[float, float, float, float], roughness: float):
    value = bpy.data.materials.new(name)
    value.diffuse_color = rgba
    value.use_nodes = True
    bsdf = value.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = 0.0
    value["mta:material_role"] = name.removeprefix("MTA_").lower()
    return value


def make_materials():
    return {
        "program_public": make_material("MTA_Program_Public", (0.0, 0.24, 0.95, 1.0), 0.62),
        "program_private": make_material("MTA_Program_Private", (0.82, 0.16, 0.18, 1.0), 0.68),
        "program_circulation": make_material("MTA_Program_Circulation", (0.05, 0.62, 0.32, 1.0), 0.64),
        "program_service": make_material("MTA_Program_Service", (0.92, 0.54, 0.08, 1.0), 0.72),
        "gallery_facade": make_material("MTA_Gallery_Plaster", (0.86, 0.87, 0.85, 1.0), 0.76),
        "entry_facade": make_material("MTA_Entry_Cobalt", (0.0, 0.20, 0.82, 1.0), 0.58),
        "service_facade": make_material("MTA_Service_Concrete", (0.50, 0.52, 0.52, 1.0), 0.82),
        "column": make_material("MTA_Columns", (0.23, 0.29, 0.34, 1.0), 0.46),
        "beam": make_material("MTA_Beams", (0.10, 0.14, 0.18, 1.0), 0.42),
        "slab": make_material("MTA_Slabs", (0.67, 0.69, 0.69, 1.0), 0.88),
        "foundation": make_material("MTA_Foundations", (0.37, 0.38, 0.37, 1.0), 0.95),
        "brace": make_material("MTA_Bracing", (0.88, 0.18, 0.08, 1.0), 0.40),
        "core": make_material("MTA_Cores", (0.44, 0.46, 0.48, 1.0), 0.86),
        "facade_panel": make_material("MTA_Facade_Aluminum_Panel", (0.78, 0.80, 0.82, 1.0), 0.48),
        "facade_glazing": make_material("MTA_Facade_Vision_Glass", (0.18, 0.48, 0.68, 0.78), 0.20),
        "facade_mullion": make_material("MTA_Facade_Mullion", (0.07, 0.09, 0.11, 1.0), 0.34),
        "facade_support": make_material("MTA_Facade_Support", (0.24, 0.28, 0.31, 1.0), 0.42),
        "facade_canopy": make_material("MTA_Facade_Canopy", (0.94, 0.94, 0.92, 1.0), 0.38),
        "interior_floor": make_material("MTA_Interior_Path", (0.70, 0.45, 0.20, 1.0), 0.72),
        "threshold_frame": make_material("MTA_Interior_Threshold", (0.08, 0.09, 0.10, 1.0), 0.40),
        "source": make_material("MTA_Source_Volume", (0.70, 0.72, 0.76, 0.28), 0.82),
        "site": make_material("MTA_Site", (0.82, 0.81, 0.78, 1.0), 0.96),
        "road": make_material("MTA_Context_Road", (0.17, 0.18, 0.18, 1.0), 0.94),
        "paving": make_material("MTA_Context_Paving", (0.68, 0.67, 0.63, 1.0), 0.92),
        "tree_trunk": make_material("MTA_Context_Tree_Trunk", (0.25, 0.16, 0.09, 1.0), 0.92),
        "tree_canopy": make_material("MTA_Context_Tree_Canopy", (0.16, 0.32, 0.19, 1.0), 0.88),
        "vehicle_glass": make_material("MTA_Context_Vehicle_Glass", (0.10, 0.14, 0.17, 1.0), 0.38),
        "vehicle_tire": make_material("MTA_Context_Vehicle_Tire", (0.035, 0.038, 0.04, 1.0), 0.86),
        "person": make_material("MTA_Context_Person", (0.12, 0.13, 0.14, 1.0), 0.78),
    }


def box_mesh(name: str, dimensions):
    x, y, z = (float(value) for value in dimensions)
    if min(x, y, z) < 0.01:
        raise ValueError(f"Degenerate element {name}: {(x, y, z)}")
    hx, hy, hz = x / 2.0, y / 2.0, z / 2.0
    vertices = [
        (-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
        (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz),
    ]
    faces = [
        (0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
        (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
    ]
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.validate(verbose=False)
    mesh.update(calc_edges=True)
    return mesh


def frustum_mesh(name: str, bottom_radius: float, top_radius: float, depth: float, vertices: int = 10):
    half_depth = depth / 2.0
    points = []
    for z, radius in ((-half_depth, bottom_radius), (half_depth, top_radius)):
        points.extend(
            (radius * math.cos(2 * math.pi * index / vertices),
             radius * math.sin(2 * math.pi * index / vertices), z)
            for index in range(vertices)
        )
    faces = [tuple(range(vertices - 1, -1, -1)), tuple(range(vertices, 2 * vertices))]
    for index in range(vertices):
        next_index = (index + 1) % vertices
        faces.append((index, next_index, vertices + next_index, vertices + index))
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(points, [], faces)
    mesh.validate(verbose=False)
    mesh.update(calc_edges=True)
    return mesh


def add_mesh(
    name, mesh, position, target_collection, target_material, model, *,
    layer, subsystem, program="", category=None, element_id=None, derived_from=None,
    score_bindings=None, exportable=True, rotation=None, context_type=None,
    context_id=None, context_role=None, element_metadata=None,
):
    obj = bpy.data.objects.new(name, mesh)
    obj.location = tuple(float(value) for value in position)
    if rotation:
        obj.rotation_euler = tuple(float(value) for value in rotation)
    obj.data.materials.append(target_material)
    metadata = {
        "mta:model_id": model["model_id"],
        "mta:score_id": model["score_id"],
        "mta:layer": layer,
        "mta:subsystem": subsystem,
        "mta:program": program,
        "mta:exportable": exportable,
    }
    optional_metadata = {
        "mta:category": category,
        "mta:element_id": element_id,
        "mta:derived_from": derived_from,
        "mta:context_type": context_type,
        "mta:context_id": context_id,
        "mta:context_role": context_role,
    }
    metadata.update({key: value for key, value in optional_metadata.items() if value})
    if element_id:
        metadata["mta:source_element"] = True
    if score_bindings:
        metadata["mta:score_bindings"] = json.dumps(score_bindings, separators=(",", ":"))
    if element_metadata:
        for key, value in element_metadata.items():
            if value not in (None, "", [], {}):
                metadata[f"mta:{key}"] = (
                    json.dumps(value, separators=(",", ":"))
                    if isinstance(value, (list, dict)) else value
                )
    for key, value in metadata.items():
        obj[key] = value
    target_collection.objects.link(obj)
    return obj


def add_box(
    name, position, dimensions, target_collection, target_material, model, *,
    layer, subsystem, program="", category=None, element_id=None, derived_from=None,
    score_bindings=None, exportable=True, rotation=None, context_type=None,
    context_id=None, context_role=None, element_metadata=None,
):
    return add_mesh(
        name, box_mesh(name, dimensions), position, target_collection, target_material,
        model, layer=layer, subsystem=subsystem, program=program, category=category,
        element_id=element_id, derived_from=derived_from, score_bindings=score_bindings,
        exportable=exportable, rotation=rotation, context_type=context_type,
        context_id=context_id, context_role=context_role,
        element_metadata=element_metadata,
    )


def element_values(element):
    position = element["position"]
    dimensions = element["dimensions"]
    return (
        (position["x"], position["y"], position["z"]),
        (dimensions["x"], dimensions["y"], dimensions["z"]),
    )


ELEMENT_MATERIAL = {
    "column": "column",
    "beam": "beam",
    "slab": "slab",
    "foundation": "foundation",
    "brace": "brace",
    "core": "core",
    "facade_panel": "facade_panel",
    "glazing": "facade_glazing",
    "mullion": "facade_mullion",
    "facade_support": "facade_support",
    "canopy": "facade_canopy",
    "interior_floor": "interior_floor",
    "threshold_frame": "threshold_frame",
}


def element_rotation(element):
    value = element.get("rotation")
    if not value:
        return None
    return value["x"], value["y"], value["z"]


def element_metadata(element):
    return {
        "space_type": element.get("space_type"),
        "access_class": element.get("access_class"),
        "level_id": element.get("level_id"),
        "material_profile": element.get("material_profile"),
        "host_surface_id": element.get("host_surface_id"),
        "supports": element.get("supports"),
        "supports_elements": element.get("supports_elements"),
        "program_constraints": element.get("program_constraints"),
        "rule_refs": element.get("rule_refs"),
        "reason": element.get("reason"),
        "authority": element.get("authority"),
        "validation_status": element.get("validation_status"),
    }


def add_semantic_elements(model, collections, materials):
    """Materialize each explicit contract element exactly once.

    Program massing keeps a hidden authority/source copy and a colored review copy.
    Every other element is exported from its declared semantic layer/subsystem.
    """
    source_objects = []
    for element in model["elements"]:
        position, dimensions = element_values(element)
        kind = element["kind"]
        subsystem = element["subsystem"]
        if kind == "massing":
            source = add_box(
                element["id"], position, dimensions, collections["source"],
                materials["source"], model, layer="source", subsystem="source",
                program=element.get("program", ""), category=element.get("category"),
                element_id=element["id"], score_bindings=element.get("score_bindings", []),
                exportable=False, rotation=element_rotation(element),
                element_metadata=element_metadata(element),
            )
            source["mta:kind"] = kind
            source_objects.append(source)
            review = add_program_massing(element, model, collections["program"], materials)
            review["mta:element_id"] = element["id"]
            review["mta:kind"] = kind
            for key, value in element_metadata(element).items():
                if value not in (None, "", [], {}):
                    review[f"mta:{key}"] = json.dumps(value) if isinstance(value, (list, dict)) else value
            continue

        target_collection = collections[subsystem]
        target_material = materials[ELEMENT_MATERIAL[kind]]
        obj = add_box(
            element["id"], position, dimensions, target_collection, target_material, model,
            layer=element["semantic_layer"], subsystem=subsystem,
            program=element.get("program", ""), category=element.get("category"),
            element_id=element["id"], score_bindings=element.get("score_bindings", []),
            exportable=True, rotation=element_rotation(element),
            element_metadata=element_metadata(element),
        )
        obj["mta:kind"] = kind
        source_objects.append(obj)
    return source_objects


def add_program_massing(massing, model, target_collection, materials):
    position, dimensions = element_values(massing)
    category = massing["category"]
    return add_box(
        f"program-{massing['id']}", position, dimensions, target_collection,
        materials[f"program_{category}"], model, layer="program",
        subsystem="program_massing", program=massing.get("program", ""),
        category=category, derived_from=massing["id"],
        score_bindings=massing.get("score_bindings", []),
    )


def facade_material(program, materials):
    return materials.get(f"{program}_facade", materials["gallery_facade"])


def add_facade(massing, model, target_collection, materials):
    position, dimensions = element_values(massing)
    x, y, z = (float(value) for value in position)
    dx, dy, dz = (float(value) for value in dimensions)
    wall = min(FACADE_THICKNESS, dx / 4, dy / 4)
    material_value = facade_material(massing.get("program", "gallery"), materials)
    parts = [
        ("south", (x, y - dy / 2 + wall / 2, z), (dx, wall, dz)),
        ("north", (x, y + dy / 2 - wall / 2, z), (dx, wall, dz)),
        ("west", (x - dx / 2 + wall / 2, y, z), (wall, max(0.02, dy - 2 * wall), dz)),
        ("east", (x + dx / 2 - wall / 2, y, z), (wall, max(0.02, dy - 2 * wall), dz)),
        ("roof", (x, y, z + dz / 2 - ROOF_THICKNESS / 2), (dx, dy, ROOF_THICKNESS)),
    ]
    for face, face_position, face_dimensions in parts:
        add_box(
            f"facade-{massing['id']}-{face}", face_position, face_dimensions,
            target_collection, material_value, model, layer="facade", subsystem="facade",
            program=massing.get("program", ""), derived_from=massing["id"],
            category=massing.get("category"),
            score_bindings=massing.get("score_bindings", []),
        )


def add_perimeter_frame(massing, model, collections, materials, existing_columns):
    position, dimensions = element_values(massing)
    x, y, z = (float(value) for value in position)
    dx, dy, dz = (float(value) for value in dimensions)
    top = z + dz / 2 - ROOF_THICKNESS - BEAM_DEPTH / 2
    bindings = massing.get("score_bindings", [])
    beam_specs = [
        ("south", (x, y - dy / 2 + FACADE_THICKNESS, top), (dx, BEAM_WIDTH, BEAM_DEPTH)),
        ("north", (x, y + dy / 2 - FACADE_THICKNESS, top), (dx, BEAM_WIDTH, BEAM_DEPTH)),
        ("west", (x - dx / 2 + FACADE_THICKNESS, y, top), (BEAM_WIDTH, dy, BEAM_DEPTH)),
        ("east", (x + dx / 2 - FACADE_THICKNESS, y, top), (BEAM_WIDTH, dy, BEAM_DEPTH)),
    ]
    for side, beam_position, beam_dimensions in beam_specs:
        add_box(
            f"beam-{massing['id']}-{side}", beam_position, beam_dimensions,
            collections["beams"], materials["beam"], model, layer="structure",
            subsystem="beams", program="structure", derived_from=massing["id"],
            category=massing.get("category"),
            score_bindings=bindings,
        )
    base = z - dz / 2
    add_box(
        f"slab-{massing['id']}", (x, y, base + SLAB_THICKNESS / 2),
        (dx, dy, SLAB_THICKNESS), collections["slabs"], materials["slab"], model,
        layer="structure", subsystem="slabs", program="structure",
        category=massing.get("category"),
        derived_from=massing["id"], score_bindings=bindings,
    )
    has_source_columns = any(massing["id"] in obj.name for obj in existing_columns)
    if has_source_columns:
        return []
    column_size = float(model.get("grid", {}).get("column_size", 0.24))
    derived_columns = []
    for xi, x_offset in enumerate((-dx / 2 + FACADE_THICKNESS, dx / 2 - FACADE_THICKNESS)):
        for yi, y_offset in enumerate((-dy / 2 + FACADE_THICKNESS, dy / 2 - FACADE_THICKNESS)):
            derived_columns.append(add_box(
                f"column-{massing['id']}-derived-{xi}-{yi}",
                (x + x_offset, y + y_offset, base + dz / 2),
                (column_size, column_size, dz), collections["columns"], materials["column"],
                model, layer="structure", subsystem="columns", program="structure",
                category=massing.get("category"),
                derived_from=massing["id"], score_bindings=bindings,
            ))
    return derived_columns


def add_foundations(columns, model, target_collection, target_material):
    for column in columns:
        add_box(
            f"foundation-{column.name}",
            (column.location.x, column.location.y, -FOUNDATION_DEPTH / 2),
            (FOUNDATION_SIZE, FOUNDATION_SIZE, FOUNDATION_DEPTH),
            target_collection, target_material, model, layer="structure",
            subsystem="foundations", program="structure",
            category=column.get("mta:category"),
            derived_from=column.get("mta:element_id") or column.get("mta:derived_from") or column.name,
        )


def add_site(model, target_collection, target_material):
    site = model["site"]
    return add_box(
        "site-envelope", (0.0, 0.0, -0.09),
        (float(site["width"]), float(site["length"]), 0.18),
        target_collection, target_material, model, layer="site", subsystem="site",
        program="site",
    )


def add_site_surface(name, position, dimensions, collection, material, model, role):
    return add_box(
        name, position, dimensions, collection, material, model,
        layer="context", subsystem="site_context", program="site",
        context_type="site_feature", context_id=name, context_role=role,
    )


def add_tree(tree_id, xy, height, collection, materials, model):
    x, y = xy
    trunk_height = height * 0.43
    canopy_height = height - trunk_height * 0.72
    add_mesh(
        f"{tree_id}-trunk",
        frustum_mesh(f"{tree_id}-trunk", 0.20, 0.16, trunk_height, vertices=8),
        (x, y, trunk_height / 2), collection, materials["tree_trunk"], model,
        layer="context", subsystem="context_tree", program="site",
        context_type="tree", context_id=tree_id, context_role="trunk",
    )
    add_mesh(
        f"{tree_id}-canopy",
        frustum_mesh(
            f"{tree_id}-canopy", height * 0.25, height * 0.055,
            canopy_height, vertices=10,
        ),
        (x, y, trunk_height * 0.72 + canopy_height / 2),
        collection, materials["tree_canopy"], model,
        layer="context", subsystem="context_tree", program="site",
        context_type="tree", context_id=tree_id, context_role="canopy",
    )


def add_vehicle(vehicle_id, xy, body_color, collection, materials, model):
    body_material = make_material(
        f"MTA_Context_{vehicle_id.title().replace('-', '_')}", body_color, 0.58
    )
    x, y = xy
    specs = (
        ("body", (x, y, 0.58), (4.4, 1.82, 0.62), body_material, None),
        ("cabin", (x - 0.12, y, 1.07), (2.15, 1.54, 0.52), materials["vehicle_glass"], None),
    )
    for role, position, dimensions, material, rotation in specs:
        add_box(
            f"{vehicle_id}-{role}", position, dimensions, collection, material, model,
            layer="context", subsystem="context_vehicle", program="site",
            context_type="vehicle", context_id=vehicle_id, context_role=role,
            rotation=rotation,
        )
    wheel_mesh = frustum_mesh(f"{vehicle_id}-wheel", 0.31, 0.31, 0.18, vertices=12)
    for index, (x_offset, y_offset) in enumerate(
        ((-1.45, -0.86), (-1.45, 0.86), (1.45, -0.86), (1.45, 0.86)), start=1
    ):
        add_mesh(
            f"{vehicle_id}-wheel-{index:02d}", wheel_mesh.copy(),
            (x + x_offset, y + y_offset, 0.34), collection,
            materials["vehicle_tire"], model, layer="context",
            subsystem="context_vehicle", program="site",
            context_type="vehicle", context_id=vehicle_id, context_role="wheel",
            rotation=(math.radians(90), 0.0, 0.0),
        )
    bpy.data.meshes.remove(wheel_mesh)


def add_person(person_id, xy, collection, material, model):
    x, y = xy
    parts = (
        ("head", (x, y, 1.62), (0.24, 0.24, 0.24)),
        ("torso", (x, y, 1.12), (0.42, 0.28, 0.76)),
        ("leg-left", (x - 0.10, y, 0.42), (0.15, 0.22, 0.84)),
        ("leg-right", (x + 0.10, y, 0.42), (0.15, 0.22, 0.84)),
    )
    for role, position, dimensions in parts:
        add_box(
            f"{person_id}-{role}", position, dimensions, collection, material, model,
            layer="context", subsystem="context_person", program="site",
            context_type="person", context_id=person_id, context_role=role,
        )


def add_site_context(model, collections, materials):
    site = model["site"]
    site_width = float(site["width"])
    site_length = float(site["length"])
    add_site_surface(
        "site-road-south", (0.0, -site_length / 2 + 2.15, 0.04),
        (site_width, 4.3, 0.08), collections["site_context"], materials["road"],
        model, "access_road",
    )
    add_site_surface(
        "site-entry-walk", (-11.8, -5.5, 0.085),
        (2.6, 4.0, 0.10), collections["site_context"], materials["paving"],
        model, "entry_walk",
    )
    add_site_surface(
        "site-entry-plaza", (-11.8, -2.75, 0.085),
        (4.6, 1.8, 0.10), collections["site_context"], materials["paving"],
        model, "entry_plaza",
    )
    for tree_id, xy, height in TREE_SPECS:
        add_tree(tree_id, xy, height, collections["trees"], materials, model)
    for vehicle_id, xy, body_color in VEHICLE_SPECS:
        add_vehicle(vehicle_id, xy, body_color, collections["vehicles"], materials, model)
    for person_id, xy in PERSON_SPECS:
        add_person(person_id, xy, collections["people"], materials["person"], model)


def point_camera(camera, target):
    camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()


def add_camera_and_lights():
    camera_data = bpy.data.cameras.new("Camera")
    camera = bpy.data.objects.new("Camera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = (29.0, -34.0, 25.0)
    camera.data.lens = 52
    point_camera(camera, (0.0, 0.0, 2.2))
    bpy.context.scene.camera = camera
    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 2.2
    sun_data.angle = math.radians(3.0)
    sun = bpy.data.objects.new("Sun", sun_data)
    sun.rotation_euler = (math.radians(28), math.radians(-18), math.radians(-35))
    bpy.context.scene.collection.objects.link(sun)
    area_data = bpy.data.lights.new("Softbox", "AREA")
    area_data.energy = 650.0
    area_data.shape = "DISK"
    area_data.size = 12.0
    area = bpy.data.objects.new("Softbox", area_data)
    area.location = (-14.0, -10.0, 22.0)
    point_camera(area, (0.0, 0.0, 2.0))
    bpy.context.scene.collection.objects.link(area)


def configure_render(output_render):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 960
    scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output_render)
    scene.render.film_transparent = False
    scene.world.color = (0.92, 0.92, 0.92)
    scene.view_settings.look = "AgX - Medium High Contrast"


def object_record(obj):
    return {
        "name": obj.name,
        "location": [round(value, 4) for value in obj.location],
        "dimensions": [round(value, 4) for value in obj.dimensions],
        "collection": obj.users_collection[0].name,
        "layer": obj.get("mta:layer"),
        "subsystem": obj.get("mta:subsystem"),
        "category": obj.get("mta:category"),
        "kind": obj.get("mta:kind"),
        "element_id": obj.get("mta:element_id"),
        "derived_from": obj.get("mta:derived_from"),
        "context_type": obj.get("mta:context_type"),
        "context_id": obj.get("mta:context_id"),
        "context_role": obj.get("mta:context_role"),
        "space_type": obj.get("mta:space_type"),
        "access_class": obj.get("mta:access_class"),
        "level_id": obj.get("mta:level_id"),
        "material_profile": obj.get("mta:material_profile"),
        "host_surface_id": obj.get("mta:host_surface_id"),
        "supports": obj.get("mta:supports"),
        "rule_refs": obj.get("mta:rule_refs"),
        "reason": obj.get("mta:reason"),
        "authority": obj.get("mta:authority"),
        "validation_status": obj.get("mta:validation_status"),
        "source_element": bool(obj.get("mta:source_element", False)),
        "exportable": bool(obj.get("mta:exportable", False)),
        "material": obj.data.materials[0].name if obj.data.materials else None,
    }


def export_scene_state(path, model):
    objects = sorted(
        (object_record(obj) for obj in bpy.data.objects if obj.type == "MESH"),
        key=lambda value: value["name"],
    )
    subsystem_counts = Counter(obj["subsystem"] for obj in objects if obj["subsystem"])
    payload = {
        "schema_version": model["schema_version"],
        "adapter_schema_version": "1.0",
        "model_id": model["model_id"],
        "source_coordinate_system": model["coordinate_system"],
        "object_count": len(objects),
        "source_object_count": sum(obj["source_element"] for obj in objects),
        "exportable_object_count": sum(obj["exportable"] for obj in objects),
        "subsystem_counts": dict(sorted(subsystem_counts.items())),
        "objects": objects,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def export_manifest(path, model, glb_path):
    exportable = [
        obj for obj in bpy.data.objects
        if obj.type == "MESH" and bool(obj.get("mta:exportable", False))
    ]
    subsystem_counts = Counter(obj.get("mta:subsystem") for obj in exportable)
    category_counts = Counter(
        obj.get("mta:category")
        for obj in exportable
        if obj.get("mta:subsystem") == "program_massing"
    )
    context_counts = Counter()
    for context_type in ("site_feature", "tree", "vehicle", "person"):
        context_counts[context_type] = len({
            obj.get("mta:context_id") for obj in exportable
            if obj.get("mta:context_type") == context_type
        })
    materials = sorted({obj.data.materials[0].name for obj in exportable if obj.data.materials})
    payload = {
        "schema_version": "1.0",
        "model_id": model["model_id"],
        "producer": "Blender 5.0 semantic adapter",
        "asset": glb_path.name if glb_path else None,
        "coordinate_conversion": "Blender right-handed Z-up to glTF right-handed Y-up",
        "layers": {
            "overall": ["facade", "columns", "beams", "slabs", "foundations", "bracing", "cores", "interior_sequence", "site", "site_context", "context_tree", "context_vehicle", "context_person"],
            "program": ["program_massing", "site", "site_context", "context_tree", "context_vehicle", "context_person"],
            "facade": ["facade", "site", "site_context", "context_tree", "context_vehicle", "context_person"],
            "structure": ["columns", "beams", "slabs", "foundations", "bracing", "cores"],
            "interior": ["interior_sequence", "facade", "structure"],
        },
        "subsystem_counts": dict(sorted(subsystem_counts.items())),
        "program_category_counts": dict(sorted(category_counts.items())),
        "context_counts": dict(sorted(context_counts.items())),
        "materials": materials,
        "object_count": len(exportable),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def export_glb(path):
    bpy.ops.object.select_all(action="DESELECT")
    selected = []
    for obj in bpy.data.objects:
        if obj.type == "MESH" and bool(obj.get("mta:exportable", False)):
            obj.hide_set(False)
            obj.select_set(True)
            selected.append(obj)
    if not selected:
        raise ValueError("No exportable Blender objects were authored")
    bpy.context.view_layer.objects.active = selected[0]
    properties = set(bpy.ops.export_scene.gltf.get_rna_type().properties.keys())
    kwargs = {
        "filepath": str(path),
        "export_format": "GLB",
        "export_extras": True,
        "export_yup": True,
    }
    if "use_selection" in properties:
        kwargs["use_selection"] = True
    elif "export_selected" in properties:
        kwargs["export_selected"] = True
    if "export_cameras" in properties:
        kwargs["export_cameras"] = False
    if "export_lights" in properties:
        kwargs["export_lights"] = False
    bpy.ops.export_scene.gltf(**kwargs)


def main():
    source, output_blend, output_render, output_state, output_glb, output_manifest = script_arguments()
    model = json.loads(source.read_text(encoding="utf-8-sig"))
    if model.get("schema_version") != "2.0":
        raise ValueError(f"Unsupported schema_version: {model.get('schema_version')}")
    elements = model.get("elements", [])
    if len(elements) > MAX_SOURCE_OBJECTS:
        raise ValueError(f"Source object budget exceeded: {len(elements)} > {MAX_SOURCE_OBJECTS}")
    for path in (output_blend, output_render, output_state, output_glb, output_manifest):
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)

    clear_scene()
    collections = {
        "source": make_collection("MTA_Source", hidden=True),
        "program": make_collection("MTA_Program_Massing"),
        "facade": make_collection("MTA_Facade"),
        "columns": make_collection("MTA_Structure_Columns"),
        "beams": make_collection("MTA_Structure_Beams"),
        "slabs": make_collection("MTA_Structure_Slabs"),
        "foundations": make_collection("MTA_Structure_Foundations"),
        "bracing": make_collection("MTA_Structure_Bracing"),
        "cores": make_collection("MTA_Structure_Cores"),
        "interior_sequence": make_collection("MTA_Interior_Sequence"),
        "site": make_collection("MTA_Site"),
        "site_context": make_collection("MTA_Site_Context"),
        "trees": make_collection("MTA_Context_Trees"),
        "vehicles": make_collection("MTA_Context_Vehicles"),
        "people": make_collection("MTA_Context_People"),
    }
    materials = make_materials()
    source_objects = add_semantic_elements(model, collections, materials)
    add_site(model, collections["site"], materials["site"])
    add_site_context(model, collections, materials)
    add_camera_and_lights()
    bpy.context.view_layer.update()
    if output_state:
        export_scene_state(output_state, model)
    if output_blend:
        bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    if output_glb:
        export_glb(output_glb)
    if output_manifest:
        export_manifest(output_manifest, model, output_glb)
    if output_render:
        configure_render(output_render)
        bpy.ops.render.render(write_still=True)

    exportable_count = sum(
        obj.type == "MESH" and bool(obj.get("mta:exportable", False))
        for obj in bpy.data.objects
    )
    print(
        f"BLENDER_IMPORT_OK source={len(source_objects)} exportable={exportable_count} "
        f"blend={output_blend} glb={output_glb}"
    )


try:
    main()
except Exception:
    traceback.print_exc()
    raise
