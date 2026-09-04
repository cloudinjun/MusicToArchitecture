# Five-style Blender rendering

Run all five styles and three self-framing views:

```powershell
python -m backend.scripts.render_archviz --input-blend path\to\model.blend
```

`render_all_styles.cmd` runs the same command and automatically chooses the latest
file in `blender/generated/` when no input is supplied. Double-click it for the project
default, or pass a `.blend` path from a terminal.

## Outputs

Each run writes a presentation-only copy and fifteen PNGs:

```text
artifacts/render_presets/<model>/
├── MTA_Render_Ready.blend
├── render_manifest.json
├── photoreal/{hero,reverse,low}.png
├── post_digital/{hero,reverse,low}.png
├── cinematic/{hero,reverse,low}.png
├── minimalist/{hero,reverse,low}.png
└── watercolor/{hero,reverse,low}.png
```

The source `.blend` is never overwritten. Cameras fit all visible mesh objects from
their world-space bounds. Render-system objects are isolated in `MTA_RENDER_SYSTEM` and
tagged `mta:authority = presentation_only`.

## Native Blender stack

- Photoreal renders use Cycles with denoising; the four graphic looks use Eevee.
- Procedural Principled materials use Noise, Color Ramp, Bump, Object Info variation,
  transmission, metal, and emission nodes.
- Each style has its own World node tree and data-driven light rig.
- The photoreal look adds a procedural sky, cloud variation, warm interior lights,
  softened material edges, and a deterministic distant tree belt built from shared
  native meshes. These helpers remain presentation-only.
- Diagram-only program zones and scale-reference figures are hidden in photoreal and
  cinematic output; accepted source geometry is untouched.
- Post-digital and watercolor use Freestyle linework.
- Post-digital uses the native Posterize compositor node.
- Cinematic uses native volume shading and Glare.
- Watercolor uses native Kuwahara and Hue/Saturation compositor nodes.
- Minimalist switches the same three views to orthographic projection.

## Material assumptions

Each material slot is classified as glass, metal, timber, ground, accent, vegetation,
or concrete. Recognition uses object, collection, material, and `mta:*` names, plus
Glass BSDF or Principled transmission nodes. Mixed wall/window meshes keep their face
material indices, so only glazing slots receive the glass preset. Unknown content
receives warm concrete. Add clear semantic names to improve automatic assignment; no
external textures are needed.

The photoreal cameras use closer 32–36 mm architectural framing. Full-quality Cycles
renders take longer than previews; use `--preview` for look development and the default
command for the final 1400×900 evidence set.

For quick iteration use `--preview`. To render selected looks or views:

```powershell
python -m backend.scripts.render_archviz --styles photoreal,watercolor --views hero
```
