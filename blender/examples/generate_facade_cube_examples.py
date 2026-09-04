"""Generate editable cube-facade study models and rendered screenshots in Blender.

This is a bounded visual/modeling fixture. Rhino/Grasshopper remains the authority for
accepted project geometry; the scene records that it is a Blender-authored example.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "docs" / "style_guides" / "facade" / "examples" / "models"
BLEND_PATH = OUTPUT_DIR / "cube_facade_model_examples.blend"

SCORES = {
    "international_style_informed": {
        "hierarchy": 0.80,
        "repetition": 0.72,
        "variation": 0.20,
        "density": 0.50,
        "continuity": 0.90,
        "interruption": 0.30,
        "polyphony": 0.45,
        "tension_release": 0.55,
        "tempo_of_change": 0.25,
    },
    "brutalism_informed": {
        "hierarchy": 0.90,
        "repetition": 0.55,
        "variation": 0.30,
        "density": 0.70,
        "continuity": 0.45,
        "interruption": 0.82,
        "polyphony": 0.55,
        "tension_release": 0.92,
        "tempo_of_change": 0.35,
    },
}


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def new_collection(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    return collection


def make_material(
    name: str,
    color: tuple[float, float, float, float],
    roughness: float,
    metallic: float = 0.0,
    transmission: float = 0.0,
    concrete_noise: bool = False,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    transmission_input = bsdf.inputs.get("Transmission Weight") or bsdf.inputs.get("Transmission")
    if transmission_input is not None:
        transmission_input.default_value = transmission

    if concrete_noise:
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 5.0
        noise.inputs["Detail"].default_value = 2.0
        noise.inputs["Roughness"].default_value = 0.65
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.13
        bump.inputs["Distance"].default_value = 0.08
        links.new(noise.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return material


def add_box(
    name: str,
    location: tuple[float, float, float],
    dimensions: tuple[float, float, float],
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    *,
    kind: str,
    grammar_id: str,
    rule_id: str,
    bevel: float = 0.025,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    for parent in list(obj.users_collection):
        parent.objects.unlink(obj)
    collection.objects.link(obj)
    obj.data.materials.append(material)

    if bevel > 0:
        modifier = obj.modifiers.new(name="Edge radius", type="BEVEL")
        modifier.width = min(bevel, min(dimensions) * 0.16)
        modifier.segments = 2

    obj["mta_element_kind"] = kind
    obj["mta_grammar_id"] = grammar_id
    obj["mta_rule_id"] = rule_id
    obj["mta_score_profile"] = json.dumps(SCORES.get(grammar_id, {}), sort_keys=True)
    obj["mta_geometry_status"] = "blender_authored_example_not_accepted_geometry"
    return obj


def add_cylinder(
    name: str,
    location: tuple[float, float, float],
    radius: float,
    depth: float,
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    *,
    grammar_id: str,
    rule_id: str,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    for parent in list(obj.users_collection):
        parent.objects.unlink(obj)
    collection.objects.link(obj)
    obj.data.materials.append(material)
    obj["mta_element_kind"] = "structure"
    obj["mta_grammar_id"] = grammar_id
    obj["mta_rule_id"] = rule_id
    obj["mta_geometry_status"] = "blender_authored_example_not_accepted_geometry"
    return obj


def build_international(
    center_x: float,
    collection: bpy.types.Collection,
    materials: dict[str, bpy.types.Material],
) -> None:
    grammar = "international_style_informed"
    shell = materials["warm_white"]
    glass = materials["blue_glass"]
    metal = materials["dark_metal"]
    interior = materials["interior_dark"]

    # The opaque cube edges keep the shared 12 m envelope legible.
    add_box("INT_BaseSlab", (center_x, 0, 0.18), (12, 12, 0.36), shell, collection,
            kind="slab", grammar_id=grammar, rule_id="INT_FREE_FACADE_SHELL_V1", bevel=0.04)
    add_box("INT_Roof", (center_x, 0, 11.80), (12, 12, 0.40), shell, collection,
            kind="roof", grammar_id=grammar, rule_id="INT_FREE_FACADE_SHELL_V1", bevel=0.04)
    add_box("INT_BackWall", (center_x, 5.80, 6), (12, 0.40, 12), shell, collection,
            kind="wall", grammar_id=grammar, rule_id="INT_FREE_FACADE_SHELL_V1", bevel=0.04)
    for side, x in (("West", center_x - 5.80), ("East", center_x + 5.80)):
        add_box(f"INT_{side}Wall", (x, 0, 6), (0.40, 12, 12), shell, collection,
                kind="wall", grammar_id=grammar, rule_id="INT_FREE_FACADE_SHELL_V1", bevel=0.04)

    # Floor plates and a dark interior make the transparent facade spatially legible.
    for level in (3.0, 6.0, 9.0):
        add_box(f"INT_Floor_{int(level)}", (center_x, 0.1, level), (11.45, 11.0, 0.18), shell, collection,
                kind="slab", grammar_id=grammar, rule_id="INT_HORIZONTAL_DATUM_V1", bevel=0.02)
    add_box("INT_InteriorShadow", (center_x, -5.35, 5.9), (10.9, 0.18, 11.2), interior, collection,
            kind="interior_backing", grammar_id=grammar, rule_id="INT_TRANSPARENT_ENVELOPE_V1", bevel=0.0)

    bay_width = 2.0
    level_height = 3.0
    for bay in range(6):
        x = center_x - 5.0 + bay * bay_width
        for level_index in range(4):
            z = 1.5 + level_index * level_height
            is_entry = bay in (2, 3) and level_index == 0
            if is_entry:
                continue
            add_box(
                f"INT_Glass_B{bay + 1}_L{level_index + 1}",
                (x, -5.94, z),
                (1.82, 0.12, 2.78),
                glass,
                collection,
                kind="glazing_panel",
                grammar_id=grammar,
                rule_id="INT_REGULAR_CURTAINWALL_GRID_V1",
                bevel=0.018,
            )

    for grid_index in range(7):
        x = center_x - 6.0 + grid_index * bay_width
        add_box(f"INT_Mullion_V{grid_index}", (x, -6.08, 6), (0.10, 0.24, 11.72), metal, collection,
                kind="mullion", grammar_id=grammar, rule_id="INT_REGULAR_CURTAINWALL_GRID_V1", bevel=0.012)
    for grid_index in range(5):
        z = 0.22 + grid_index * level_height
        add_box(f"INT_Mullion_H{grid_index}", (center_x, -6.08, z), (11.9, 0.24, 0.10), metal, collection,
                kind="mullion", grammar_id=grammar, rule_id="INT_HORIZONTAL_DATUM_V1", bevel=0.012)

    # Double-width recessed entry bay driven by hierarchy=0.80 and interruption=0.30.
    portal_width = 2.4 + 2.4 * SCORES[grammar]["hierarchy"]
    portal_height = 3.0 + 3.0 * SCORES[grammar]["tension_release"]
    recess_depth = 0.25 + 1.75 * SCORES[grammar]["interruption"]
    door_y = -6.0 + recess_depth
    add_box("INT_EntryDoor_Left", (center_x - portal_width / 4, door_y, 1.7),
            (portal_width / 2 - 0.08, 0.12, 3.4), glass, collection,
            kind="entry_glazing", grammar_id=grammar, rule_id="INT_DOUBLE_BAY_ENTRY_V1", bevel=0.015)
    add_box("INT_EntryDoor_Right", (center_x + portal_width / 4, door_y, 1.7),
            (portal_width / 2 - 0.08, 0.12, 3.4), glass, collection,
            kind="entry_glazing", grammar_id=grammar, rule_id="INT_DOUBLE_BAY_ENTRY_V1", bevel=0.015)
    add_box("INT_EntryCenterMullion", (center_x, door_y - 0.05, 1.7), (0.09, 0.20, 3.4), metal, collection,
            kind="entry_frame", grammar_id=grammar, rule_id="INT_DOUBLE_BAY_ENTRY_V1", bevel=0.01)
    add_box("INT_EntryHeader", (center_x, -6.08, portal_height), (portal_width + 0.20, 0.28, 0.14), metal, collection,
            kind="entry_frame", grammar_id=grammar, rule_id="INT_DOUBLE_BAY_ENTRY_V1", bevel=0.015)
    add_box("INT_EntryCanopy", (center_x, -6.72, portal_height - 0.10),
            (portal_width + 0.45, 1.55, 0.16), shell, collection,
            kind="canopy", grammar_id=grammar, rule_id="INT_RECESSED_ENTRY_PLANE_V1", bevel=0.03)

    # Slender frame visible behind the independent curtain wall.
    for x_offset in (-4.0, 0.0, 4.0):
        add_cylinder(f"INT_Column_{x_offset:+.0f}", (center_x + x_offset, -4.95, 6), 0.12, 11.6,
                     metal, collection, grammar_id=grammar, rule_id="INT_INDEPENDENT_FRAME_V1")


def build_brutalism(
    center_x: float,
    collection: bpy.types.Collection,
    materials: dict[str, bpy.types.Material],
) -> None:
    grammar = "brutalism_informed"
    concrete = materials["concrete"]
    concrete_dark = materials["concrete_dark"]
    glass = materials["smoked_glass"]
    joints = materials["joint_dark"]

    add_box("BRU_BaseSlab", (center_x, 0, 0.28), (12, 12, 0.56), concrete, collection,
            kind="slab", grammar_id=grammar, rule_id="BR_MONOLITHIC_ENVELOPE_V1", bevel=0.06)
    add_box("BRU_Roof", (center_x, 0, 11.72), (12, 12, 0.56), concrete, collection,
            kind="roof", grammar_id=grammar, rule_id="BR_MONOLITHIC_ENVELOPE_V1", bevel=0.06)
    add_box("BRU_BackWall", (center_x, 5.55, 6), (12, 0.90, 12), concrete, collection,
            kind="wall", grammar_id=grammar, rule_id="BR_MONOLITHIC_ENVELOPE_V1", bevel=0.05)
    for side, x in (("West", center_x - 5.55), ("East", center_x + 5.55)):
        add_box(f"BRU_{side}Wall", (x, 0, 6), (0.90, 12, 12), concrete, collection,
                kind="wall", grammar_id=grammar, rule_id="BR_MONOLITHIC_ENVELOPE_V1", bevel=0.05)

    portal_width = 2.4 + 2.4 * SCORES[grammar]["hierarchy"]
    portal_height = 3.0 + 3.0 * SCORES[grammar]["tension_release"]
    recess_depth = 0.25 + 1.75 * SCORES[grammar]["interruption"]
    side_width = (12.0 - portal_width) / 2.0
    side_offset = portal_width / 2.0 + side_width / 2.0
    wall_y = -5.60

    for side, sign in (("Left", -1), ("Right", 1)):
        add_box(f"BRU_LowerWall_{side}", (center_x + sign * side_offset, wall_y, portal_height / 2),
                (side_width, 0.80, portal_height), concrete, collection,
                kind="facade_mass", grammar_id=grammar, rule_id="BR_DEEP_ENTRY_CUT_V1", bevel=0.045)

    lower_band_bottom = portal_height
    window_band_bottom = 7.35
    window_band_top = 10.25
    add_box("BRU_MidBand", (center_x, wall_y, (lower_band_bottom + window_band_bottom) / 2),
            (12, 0.80, window_band_bottom - lower_band_bottom), concrete, collection,
            kind="facade_mass", grammar_id=grammar, rule_id="BR_PROGRAM_LEGIBLE_MASS_V1", bevel=0.045)
    add_box("BRU_TopBand", (center_x, wall_y, (window_band_top + 12.0) / 2),
            (12, 0.80, 12.0 - window_band_top), concrete, collection,
            kind="facade_mass", grammar_id=grammar, rule_id="BR_PROGRAM_LEGIBLE_MASS_V1", bevel=0.045)

    slot_centers = [-4.0, -2.0, 0.0, 2.0, 4.0]
    slot_width = 1.30
    cursor = -6.0
    segments: list[tuple[float, float]] = []
    for slot_center in slot_centers:
        slot_left = slot_center - slot_width / 2
        if slot_left > cursor:
            segments.append((cursor, slot_left))
        cursor = slot_center + slot_width / 2
    if cursor < 6.0:
        segments.append((cursor, 6.0))

    window_height = window_band_top - window_band_bottom
    for index, (left, right) in enumerate(segments):
        add_box(f"BRU_WindowPier_{index + 1}",
                (center_x + (left + right) / 2, wall_y, (window_band_bottom + window_band_top) / 2),
                (right - left, 0.80, window_height), concrete, collection,
                kind="facade_mass", grammar_id=grammar, rule_id="BR_REPEATED_DEEP_OPENINGS_V1", bevel=0.04)
    for index, slot_center in enumerate(slot_centers):
        add_box(f"BRU_Window_{index + 1}",
                (center_x + slot_center, -5.22, (window_band_bottom + window_band_top) / 2),
                (slot_width, 0.10, window_height - 0.30), glass, collection,
                kind="deep_window", grammar_id=grammar, rule_id="BR_REPEATED_DEEP_OPENINGS_V1", bevel=0.02)

    # The reveal extends from the exterior plane to the recessed weather enclosure.
    door_y = -6.0 + recess_depth
    reveal_y = (-6.0 + door_y) / 2
    for side, sign in (("Left", -1), ("Right", 1)):
        add_box(f"BRU_EntryReveal_{side}",
                (center_x + sign * (portal_width / 2 - 0.13), reveal_y, portal_height / 2),
                (0.26, recess_depth, portal_height), concrete_dark, collection,
                kind="entry_reveal", grammar_id=grammar, rule_id="BR_DEEP_ENTRY_CUT_V1", bevel=0.025)
    add_box("BRU_EntryReveal_Top", (center_x, reveal_y, portal_height - 0.13),
            (portal_width, recess_depth, 0.26), concrete_dark, collection,
            kind="entry_reveal", grammar_id=grammar, rule_id="BR_DEEP_ENTRY_CUT_V1", bevel=0.025)
    add_box("BRU_RecessedDoor", (center_x, door_y, 2.05), (portal_width - 0.70, 0.14, 4.10), glass, collection,
            kind="entry_glazing", grammar_id=grammar, rule_id="BR_RECESSED_WEATHER_ENCLOSURE_V1", bevel=0.018)
    add_box("BRU_EntryCompressionSlab", (center_x, -6.25, 3.75),
            (portal_width - 0.55, 2.15, 0.34), concrete, collection,
            kind="canopy", grammar_id=grammar, rule_id="BR_COMPRESSION_RELEASE_V1", bevel=0.035)

    # Thin physical strips represent board-form construction joints in the study model.
    joint_y = -6.015
    for z in (1.85, 3.70):
        for side, sign in (("L", -1), ("R", 1)):
            add_box(f"BRU_Joint_H_{side}_{z:.2f}",
                    (center_x + sign * side_offset, joint_y, z),
                    (side_width - 0.10, 0.025, 0.035), joints, collection,
                    kind="construction_joint", grammar_id=grammar, rule_id="BR_BOARD_FORM_JOINTS_V1", bevel=0.0)
    for x_offset in (-5.0, -3.8, 3.8, 5.0):
        add_box(f"BRU_Joint_V_{x_offset:+.1f}", (center_x + x_offset, joint_y, portal_height / 2),
                (0.035, 0.025, portal_height - 0.10), joints, collection,
                kind="construction_joint", grammar_id=grammar, rule_id="BR_BOARD_FORM_JOINTS_V1", bevel=0.0)


def add_ground_and_lighting(
    collection: bpy.types.Collection,
    materials: dict[str, bpy.types.Material],
) -> None:
    add_box("StudioGround", (0, 1.0, -0.18), (40, 32, 0.30), materials["ground"], collection,
            kind="presentation_ground", grammar_id="presentation_only", rule_id="PRESENTATION_GROUND", bevel=0.10)

    light_specs = [
        ("Key", (-11, -18, 22), 1900, 11.0, (1.0, 0.88, 0.72)),
        ("Fill", (15, -10, 15), 1450, 10.0, (0.72, 0.84, 1.0)),
        ("Top", (0, 6, 27), 1800, 9.0, (1.0, 0.97, 0.92)),
    ]
    for name, location, energy, size, color in light_specs:
        data = bpy.data.lights.new(name=f"{name}Light", type="AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        data.color = color
        obj = bpy.data.objects.new(name=f"{name}Light", object_data=data)
        obj.location = location
        collection.objects.link(obj)
        point_at(obj, (0, 0, 5.5))

    sun_data = bpy.data.lights.new(name="SunLight", type="SUN")
    sun_data.energy = 1.2
    sun_data.angle = math.radians(14)
    sun = bpy.data.objects.new(name="SunLight", object_data=sun_data)
    sun.rotation_euler = (math.radians(35), math.radians(-20), math.radians(-25))
    collection.objects.link(sun)


def point_at(obj: bpy.types.Object, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_camera(
    name: str,
    location: tuple[float, float, float],
    target: tuple[float, float, float],
    lens: float,
    collection: bpy.types.Collection,
) -> bpy.types.Object:
    camera_data = bpy.data.cameras.new(name=name)
    camera_data.lens = lens
    camera_data.sensor_width = 36
    camera = bpy.data.objects.new(name=name, object_data=camera_data)
    camera.location = location
    collection.objects.link(camera)
    point_at(camera, target)
    return camera


def configure_scene() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1050
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.render.image_settings.color_depth = "8"
    scene.render.resolution_percentage = 100
    scene.render.fps = 24
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass

    world = bpy.data.worlds.new("Facade Study World")
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.055, 0.07, 0.095, 1.0)
    background.inputs["Strength"].default_value = 0.32
    scene.world = world

    scene["mta_artifact_role"] = "facade_model_screenshot_example"
    scene["mta_authority"] = "Blender-authored visual fixture; Rhino/Grasshopper acceptance pending"
    scene["mta_cube_dimensions_m"] = "12 x 12 x 12"
    scene["mta_source_score_fixture"] = "docs/style_guides/facade/examples/cube_entry_score_examples.yaml"


def render(scene: bpy.types.Scene, camera: bpy.types.Object, filename: str) -> None:
    scene.camera = camera
    scene.render.filepath = str(OUTPUT_DIR / filename)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    clear_scene()
    configure_scene()

    international_collection = new_collection("MODEL_InternationalStyle")
    brutalism_collection = new_collection("MODEL_Brutalism")
    presentation_collection = new_collection("PRESENTATION")

    materials = {
        "warm_white": make_material("Warm White Mineral", (0.77, 0.79, 0.76, 1), 0.34),
        "blue_glass": make_material("Cool Blue Glass", (0.075, 0.20, 0.28, 1), 0.16, metallic=0.12, transmission=0.28),
        "dark_metal": make_material("Charcoal Aluminum", (0.035, 0.045, 0.052, 1), 0.20, metallic=0.82),
        "interior_dark": make_material("Interior Shadow", (0.018, 0.023, 0.030, 1), 0.55),
        "concrete": make_material("Board Form Concrete", (0.47, 0.43, 0.37, 1), 0.72, concrete_noise=True),
        "concrete_dark": make_material("Concrete Reveal", (0.19, 0.18, 0.17, 1), 0.80, concrete_noise=True),
        "smoked_glass": make_material("Smoked Entry Glass", (0.032, 0.055, 0.060, 1), 0.20, metallic=0.08, transmission=0.18),
        "joint_dark": make_material("Formwork Joint", (0.07, 0.065, 0.060, 1), 0.88),
        "ground": make_material("Studio Ground", (0.12, 0.135, 0.155, 1), 0.68),
    }

    build_international(-8.0, international_collection, materials)
    build_brutalism(8.0, brutalism_collection, materials)
    add_ground_and_lighting(presentation_collection, materials)

    comparison_camera = add_camera("CAM_Comparison", (0, -43, 13.0), (0, 0, 5.7), 52, presentation_collection)
    international_camera = add_camera("CAM_International", (-14.5, -32.5, 10.2), (-8.0, 0, 5.25), 54, presentation_collection)
    brutalism_camera = add_camera("CAM_Brutalism", (14.8, -32.5, 10.4), (8.0, 0, 5.25), 54, presentation_collection)

    scene = bpy.context.scene
    international_collection.hide_render = False
    brutalism_collection.hide_render = False
    render(scene, comparison_camera, "cube_facade_model_comparison.png")

    brutalism_collection.hide_render = True
    render(scene, international_camera, "cube_facade_model_international.png")
    brutalism_collection.hide_render = False
    international_collection.hide_render = True
    render(scene, brutalism_camera, "cube_facade_model_brutalism.png")

    international_collection.hide_render = False
    brutalism_collection.hide_render = False
    scene.camera = comparison_camera
    scene.render.filepath = str(OUTPUT_DIR / "cube_facade_model_comparison.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))

    print(json.dumps({
        "blend": str(BLEND_PATH),
        "renders": [
            str(OUTPUT_DIR / "cube_facade_model_comparison.png"),
            str(OUTPUT_DIR / "cube_facade_model_international.png"),
            str(OUTPUT_DIR / "cube_facade_model_brutalism.png"),
        ],
        "objects": len(bpy.data.objects),
        "collections": [collection.name for collection in bpy.data.collections],
    }, indent=2))


if __name__ == "__main__":
    main()
