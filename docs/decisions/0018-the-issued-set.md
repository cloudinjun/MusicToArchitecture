# Decision 0018 — The issued set

- Status: accepted; the drawing set is issued as numbered sheets on one paper size
- Date: 2026-09-04
- Decision owner: user ("把这个项目的出图纸功能迭代到M Arch毕设的精细程度和美观度")
- Career-value tags: V3, V4

## The claim being tested

Plans and sections cut from the model already closed the loop on the model: every
mark named its element and every element landed in one of three buckets. What they
did not do was read as a set. Each drawing was its own oddly sized sheet with a
title line; sections put a grey column through the building where the lift shaft
was cut as a solid; the ground was a grey block; guard posts beyond the cut smeared
into cages; no elevation existed, so a third of the envelope was on no sheet at all.
The claim this decision tests is that the same reading of the model can be issued
at the level a thesis set is judged at, **without a single authored line** — every
improvement is a rule applied to the model, not a retouch of a sheet.

## What the set now is

**One paper, numbered sheets, a cover.** `drawing_sheet.paper_for` picks the smallest
ISO A-series landscape sheet whose drawing area holds every drawing in the set, and
every sheet takes it. Drawings of one kind are composed onto sheets by a shelf packer
that preserves issue order (`drawings._pack`): two sections stack, three small plans
sit in a row, each under its own caption with its own scale bar and its own audit.
Sheets are numbered A-1nn plans, A-2nn elevations, A-3nn sections; A-000 is the
cover, which lists the set, states the building's facts, and shows every drawing
again at 1:400 with that scale's own detail level applied.

**The title block is read, never written.** Typology, massing family, structural
system, facade grammar, envelope tectonic, model id, score id and compiler version
come off the model. There is no date and no author: the sheet is a pure function of
the model, and two issues of one model must be byte-identical. The key plan in the
strip is drawn from the lattice — a stack with the sheet's level filled, or the
footprint with the cut's trace and direction of view.

**Four elevations.** An elevation is `compile_drawing` with the plane set down
outside the nearest face; nothing is cut, everything is beyond, the painter's order
resolves the face. A cutaway run authors the envelope on two faces; the open faces
are drawn as what they are and the caption says so. With elevations the
`on_no_cut` bucket empties on the fixture.

## Rules the cut now applies, each of which a person applied by eye before

- **A figure is never cut.** `entourage` is a role: skipped in plan, drawn beyond the
  cut in section and elevation as a glyph sized from the figure's own boxes.
- **A lift shaft is cut hollow.** `_shaft_geometry` gives the solid prism a hole one
  wall in from its boundary. This is a drawing fact, so it lives in the drawing and
  not in the compiler, whose load path does not care where the car goes.
- **Thinner than a line is a line.** An uncut element whose silhouette is narrower
  than `THIN_LINE_PAPER_MM` on paper is drawn as its axis (`_principal_extent`).
- **The earth is hatched.** `DrawingStandard.hatch` names a fill pattern per role;
  the sheet defines the pattern once. Weights are unchanged: the hairline is the
  hairline.
- **The sheet edge is not a line.** A polygon clipped by the sheet keeps its fill and
  loses the edge the clip made (`_edges_off_boundary`).
- **A section is placed where it reads.** `resolve_section_offset` steps the plane off
  any wall it would lie inside, in half-metre steps, and the caption records the move.
- **Overhead railings are not dashed.** `NEVER_OVERHEAD_KINDS` keeps the one thing
  dashing carries — "this is above you" — from drowning in guard posts.
- **1:100 carries the loose furniture** at the lightest weight; 1:200 drops it. A plan
  without its tables is a diagram of walls.

## What is deliberately not done

No line is drawn that the model does not carry: no trees, no context, no sky, no
rendered texture. The cover's miniatures are the same marks at another scale. A
render is presentation and stays in Blender; a sheet is evidence and stays a reading.

## Verification

`backend/tests/test_drawings.py`: one paper per set; every drawing placed exactly
once on a sheet of its kind, inside the drawing area with room for its caption; the
title block names the model and carries no date; the cover lists every sheet; the
manifest carries each sheet's drawings and its aggregates; four elevations with
nothing cut and no poché, and a smaller `on_no_cut` than plans and sections alone;
the shaft hollow in plan and in section; figures never in plan, always beyond;
posts collapse to lines while columns keep their outline; earth hatched in section
and absent in elevation; clip edges never stroked; furniture present at 1:100;
railings never dashed overhead; sections name their rooms; the offset resolver
leaves no wall cut lengthwise and says so when it moved. The promoted demo at
`web/public/drawings/latest/A-*.svg` is the visual evidence; its immutable source version
is named by `artifacts/model_versions/latest.json`.
