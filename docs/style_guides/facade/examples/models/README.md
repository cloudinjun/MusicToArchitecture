# Cube facade model examples

These files are editable Blender model studies generated from the manual entry-score
fixtures in `../cube_entry_score_examples.yaml`.

## Included comparison

- `international_style_informed`: regular curtain-wall bays, continuous floor datum,
  independent frame, and a double-width recessed glazed entry.
- `brutalism_informed`: heavy facade mass, repeated deep openings, board-form joints,
  and a deep compressed entry threshold.

Both studies use a 12 m × 12 m × 12 m cube envelope. Object custom properties record
the grammar ID, rule ID, score profile, element kind, and geometry status.

## Authority status

This is a Blender-authored visual/modeling fixture. It demonstrates how the facade
guidelines can become editable geometry, but it is not accepted project geometry. The
accepted route remains compiler → Grasshopper validation → Rhino bake/export → Blender
presentation.

## Regeneration

Run Blender in background mode with:

```powershell
$env:BLENDER_EXE = (Get-Command blender).Source
& $env:BLENDER_EXE `
  --background --factory-startup `
  --python blender\examples\generate_facade_cube_examples.py
```
